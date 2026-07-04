from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image
from django.conf import settings
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from .normalization import clean_list, normalize_phones, normalize_website
from .translation import fill_bilingual_fields
from .website_enrichment import fetch_website_text, infer_company_activity, infer_investment_type


class BusinessCardData(BaseModel):
    person_name: str = ''
    person_name_ar: str = ''
    person_name_en: str = ''
    job_title: str = ''
    job_title_ar: str = ''
    job_title_en: str = ''
    company_name: str = ''
    company_name_ar: str = ''
    company_name_en: str = ''
    mobile_numbers: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    website: str = ''
    address: str = ''
    company_activity: str = ''
    investment_type: str = ''
    investment_type_other: str = ''
    raw_text: str = ''
    confidence: float = 0.0
    needs_review: bool = True
    review_notes: str = ''
    website_visit_note: str = ''


SYSTEM_PROMPT = """
You extract structured contact data from two sides of a business card.
The card may be Arabic, English, or mixed. Return ONLY valid JSON.
Shape: {"person_name":"","person_name_ar":"","person_name_en":"","job_title":"","job_title_ar":"","job_title_en":"","company_name":"","company_name_ar":"","company_name_en":"","mobile_numbers":[],"emails":[],"website":"","address":"","company_activity":"","investment_type":"","investment_type_other":"","raw_text":"","confidence":0.0,"needs_review":true,"review_notes":""}
Do not invent missing values. raw_text must include all readable text.
For bilingual fields: copy each language version exactly as printed on the card into the matching _ar or _en field. Do NOT translate — leave the other field empty if not on the card.
company_activity must be Arabic. If the card has only English activity text, translate only the clearly visible meaning into Arabic.
investment_type must be one of the official Arabic values when it is clear, otherwise use "غير ذلك" and put the free value in investment_type_other.
"""

STRING_FIELDS = {
    'person_name',
    'person_name_ar',
    'person_name_en',
    'job_title',
    'job_title_ar',
    'job_title_en',
    'company_name',
    'company_name_ar',
    'company_name_en',
    'website',
    'address',
    'company_activity',
    'investment_type',
    'investment_type_other',
    'raw_text',
    'review_notes',
    'website_visit_note',
}
LIST_FIELDS = {'mobile_numbers', 'emails'}


def _extract_json(text: str) -> dict:
    cleaned = (text or '').strip()
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.I)
    cleaned = re.sub(r'\s*```$', '', cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', cleaned, flags=re.S)
        if not match:
            raise ValueError('Gemini did not return JSON')
        return json.loads(match.group(0))


def _open_image(path: str | Path) -> Image.Image:
    return Image.open(path).convert('RGB')


def _sanitize_extracted_payload(payload: dict) -> dict:
    sanitized = dict(payload or {})
    for field in STRING_FIELDS:
        value = sanitized.get(field)
        sanitized[field] = '' if value is None else str(value)
    for field in LIST_FIELDS:
        value = sanitized.get(field)
        if not isinstance(value, list):
            sanitized[field] = []
        else:
            sanitized[field] = [str(item).strip() for item in value if item not in {None, ''}]

    confidence = sanitized.get('confidence')
    try:
        sanitized['confidence'] = float(confidence or 0.0)
    except (TypeError, ValueError):
        sanitized['confidence'] = 0.0

    sanitized['needs_review'] = bool(sanitized.get('needs_review', True))
    return sanitized


def _is_weak_activity(value: str | None) -> bool:
    text = re.sub(r'\s+', ' ', value or '').strip()
    return not text or len(text) < 25 or text in {'شركة متخصصة', 'خدمات متنوعة', 'غير معروف'}


def _combine_bilingual(arabic: str, english: str, fallback: str = '') -> str:
    parts = [part.strip() for part in [arabic, english] if part and part.strip()]
    if parts:
        return '\n'.join(dict.fromkeys(parts))
    return (fallback or '').strip()


def extract_business_card(front_image: str | Path, back_image: str | Path | None = None) -> BusinessCardData:
    if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY.startswith('your_'):
        raise RuntimeError('GEMINI_API_KEY غير موجود أو ما زال قيمة تجريبية داخل .env')

    contents: list[object] = ['Extract all contact information from these business card images. Return JSON only.']
    contents.append(_open_image(front_image))
    if back_image:
        contents.append(_open_image(back_image))

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0,
            response_mime_type='application/json',
        ),
    )

    parsed = BusinessCardData.model_validate(
        _sanitize_extracted_payload(_extract_json(getattr(response, 'text', '') or ''))
    )
    parsed.mobile_numbers = normalize_phones(parsed.mobile_numbers)
    parsed.emails = clean_list(parsed.emails)
    parsed.website = normalize_website(parsed.website)

    page_text = ''
    if settings.ENABLE_WEBSITE_ENRICHMENT and parsed.website:
        page_text, note = fetch_website_text(parsed.website)
        parsed.website_visit_note = note
        if _is_weak_activity(parsed.company_activity):
            activity = infer_company_activity(parsed.company_name, parsed.website, page_text, parsed.raw_text)
            if activity:
                parsed.company_activity = activity
        if note:
            parsed.review_notes = ((parsed.review_notes or '') + ' ' + note).strip()

    if not parsed.investment_type:
        investment_type, investment_type_other = infer_investment_type(
            parsed.company_name,
            parsed.company_activity,
            page_text,
            parsed.raw_text,
        )
        parsed.investment_type = investment_type
        parsed.investment_type_other = investment_type_other

    bilingual = fill_bilingual_fields({
        'person_name_ar': parsed.person_name_ar,
        'person_name_en': parsed.person_name_en,
        'job_title_ar': parsed.job_title_ar,
        'job_title_en': parsed.job_title_en,
        'company_name_ar': parsed.company_name_ar,
        'company_name_en': parsed.company_name_en,
    })
    for field, value in bilingual.items():
        setattr(parsed, field, value)

    parsed.person_name = _combine_bilingual(parsed.person_name_ar, parsed.person_name_en, parsed.person_name)
    parsed.job_title = _combine_bilingual(parsed.job_title_ar, parsed.job_title_en, parsed.job_title)
    parsed.company_name = _combine_bilingual(parsed.company_name_ar, parsed.company_name_en, parsed.company_name)

    if not parsed.person_name or not parsed.company_name or not parsed.mobile_numbers:
        parsed.needs_review = True
    elif parsed.confidence >= 0.75:
        parsed.needs_review = False

    return parsed
