from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

from PIL import Image
from django.conf import settings
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from .gemini_keys import manager as gemini_key_manager
from .normalization import clean_list, normalize_phones, normalize_website
from .translation import fill_bilingual_fields
from .website_enrichment import fetch_website_text, infer_company_activity, infer_investment_type

logger = logging.getLogger(__name__)


class ExtractionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        category: str = 'gemini_external_error',
        status_code: int = 502,
        recoverable: bool = True,
        original: Exception | None = None,
    ):
        super().__init__(message)
        self.category = category
        self.status_code = status_code
        self.recoverable = recoverable
        self.original = original


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
You extract structured contact data from business-card images. The card can be Arabic, English, or mixed.
Return ONLY valid JSON with this exact shape:
{"person_name":"","person_name_ar":"","person_name_en":"","job_title":"","job_title_ar":"","job_title_en":"","company_name":"","company_name_ar":"","company_name_en":"","mobile_numbers":[],"emails":[],"website":"","address":"","company_activity":"","investment_type":"","investment_type_other":"","raw_text":"","confidence":0.0,"needs_review":true,"review_notes":""}

Rules:
- Extract business-card identity and contact data only.
- Do not invent missing values. Leave unknown fields empty.
- Prefer printed business-card data over handwritten notes.
- If clear handwritten contact data is visible, include it in raw_text or review_notes. Add it to phone/email only when very clear and not duplicated.
- Support Arabic and English. For _ar and _en fields, copy the printed language version exactly. Do not translate names.
- company_activity must be Arabic when activity is clearly printed or strongly implied by the card.
- investment_type must be one of the official Arabic values when clear; otherwise use "غير ذلك" and put the free value in investment_type_other.
- If a QR code is visible, do not rely on it as the only source; local QR decoding may be merged separately.
- raw_text must contain only important identity/contact text and must be under 2000 characters.
- Set needs_review=true when fields conflict, OCR is uncertain, important data may be missing, or confidence is low.
"""

STRING_FIELDS = {
    'person_name', 'person_name_ar', 'person_name_en',
    'job_title', 'job_title_ar', 'job_title_en',
    'company_name', 'company_name_ar', 'company_name_en',
    'website', 'address', 'company_activity', 'investment_type',
    'investment_type_other', 'raw_text', 'review_notes', 'website_visit_note',
}
LIST_FIELDS = {'mobile_numbers', 'emails'}
EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+', re.I)
URL_RE = re.compile(r'(?<!@)\b(?:https?://)?(?:www\.)?[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)+(?:/[^\s]*)?', re.I)
PHONE_RE = re.compile(r'(?:\+?\d[\d\s().-]{6,}\d)')

NON_FALLBACK_CATEGORIES = {
    'gemini_rate_limit',
    'gemini_quota_exceeded',
    'all_gemini_keys_rate_limited',
    'all_gemini_keys_invalid',
    'gemini_location_not_supported',
    'gemini_invalid_api_key',
    'missing_gemini_api_key',
}
FALLBACK_CATEGORIES = {
    'gemini_timeout',
    'gemini_transient',
    'extraction_parse_error',
    'gemini_external_error',
}


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
        sanitized[field] = '' if value is None else str(value).strip()
    for field in LIST_FIELDS:
        value = sanitized.get(field)
        if not isinstance(value, list):
            sanitized[field] = []
        else:
            sanitized[field] = [str(item).strip() for item in value if item not in {None, ''}]

    try:
        sanitized['confidence'] = float(sanitized.get('confidence') or 0.0)
    except (TypeError, ValueError):
        sanitized['confidence'] = 0.0

    sanitized['confidence'] = max(0.0, min(1.0, sanitized['confidence']))
    sanitized['needs_review'] = bool(sanitized.get('needs_review', True))
    sanitized['raw_text'] = sanitized['raw_text'][:2000]
    return sanitized


def _is_weak_activity(value: str | None) -> bool:
    text = re.sub(r'\s+', ' ', value or '').strip()
    return not text or len(text) < 25 or text in {'شركة متخصصة', 'خدمات متنوعة', 'غير معروف', 'غير محدد'}


def _combine_bilingual(arabic: str, english: str, fallback: str = '') -> str:
    parts = [part.strip() for part in [arabic, english] if part and part.strip()]
    if parts:
        return '\n'.join(dict.fromkeys(parts))
    return (fallback or '').strip()


def _error_text(exc: Exception) -> str:
    return str(exc) or exc.__class__.__name__


def _safe_error_summary(exc: Exception) -> str:
    text = _error_text(exc)
    text = re.sub(r'AIza[0-9A-Za-z_\-]{20,}', '[REDACTED_GEMINI_KEY]', text)
    text = re.sub(r'(x-goog-api-key\s*[:=]\s*)\S+', r'\1[REDACTED]', text, flags=re.I)
    return text[:240]


def _classify_exception(exc: Exception) -> tuple[str, int, str, bool]:
    if isinstance(exc, ExtractionError):
        return exc.category, exc.status_code, str(exc), exc.recoverable

    text = _error_text(exc).lower()

    if 'did not return json' in text or ('json' in text and isinstance(exc, (ValueError, json.JSONDecodeError))):
        return 'extraction_parse_error', 502, 'تعذر قراءة استجابة Gemini بصيغة JSON صحيحة.', True
    if 'timeout' in text or 'deadline' in text or 'timed out' in text:
        return 'gemini_timeout', 504, 'انتهت مهلة الاتصال مع Gemini. يرجى المحاولة بصورة أصغر أو لاحقاً.', True
    if any(token in text for token in ('resource_exhausted', '429', 'rate limit', 'too many requests')):
        return 'gemini_rate_limit', 429, 'تم الوصول إلى حد استخدام Gemini. يرجى المحاولة لاحقاً.', False
    if 'quota' in text or 'rpd' in text or 'requests per day' in text:
        return 'gemini_quota_exceeded', 429, 'انتهت حصة Gemini المتاحة حالياً. يرجى المحاولة لاحقاً أو استخدام مفتاح آخر.', False
    if 'api_key_invalid' in text or 'api key not valid' in text or 'invalid api key' in text or 'api key is invalid' in text:
        return 'gemini_invalid_api_key', 502, 'مفتاح Gemini API غير صالح. يرجى التحقق من إعدادات الخادم.', False
    if 'unauthenticated' in text or 'permission denied' in text or 'forbidden' in text:
        return 'gemini_invalid_api_key', 502, 'مفتاح Gemini API غير مسموح له بتنفيذ الطلب.', False
    if 'user location is not supported' in text or 'location is not supported' in text or 'failed_precondition' in text:
        return 'gemini_location_not_supported', 502, 'موقع استخدام Gemini API غير مدعوم حالياً من هذه الشبكة.', False
    if any(token in text for token in ('connection reset', 'econnreset', 'socket hang up', 'broken pipe', '503', '504', '502', '500')):
        return 'gemini_transient', 502, 'تعذر الاتصال بخدمة Gemini مؤقتاً. يرجى المحاولة لاحقاً.', True
    return 'gemini_external_error', 502, 'تعذر استخراج بيانات الكرت من Gemini.', True


def _raise_key_exhausted(reason: str) -> None:
    if reason == 'missing_gemini_api_key':
        raise ExtractionError('لم يتم إعداد مفتاح Gemini API على الخادم.', category='missing_gemini_api_key', status_code=502, recoverable=False)
    if reason == 'all_gemini_keys_invalid':
        raise ExtractionError('كل مفاتيح Gemini API المتاحة غير صالحة حالياً.', category='all_gemini_keys_invalid', status_code=502, recoverable=False)
    if reason == 'all_gemini_keys_rate_limited':
        raise ExtractionError('تم الوصول إلى حد استخدام كل مفاتيح Gemini المتاحة حالياً.', category='all_gemini_keys_rate_limited', status_code=429, recoverable=False)
    raise ExtractionError('لا يوجد مفتاح Gemini متاح حالياً.', category='all_gemini_keys_exhausted', status_code=502, recoverable=True)


def _increment_request_count(context: dict) -> None:
    context['requests_made'] = int(context.get('requests_made', 0)) + 1


def _ensure_request_budget(context: dict) -> None:
    if int(context.get('requests_made', 0)) >= int(context.get('max_requests', 3)):
        raise ExtractionError('تم إيقاف العملية لتجنب استهلاك طلبات Gemini إضافية لهذا الكرت.', category='gemini_request_budget_exceeded', status_code=429, recoverable=False)


def _call_gemini(image_paths: list[str | Path], user_instruction: str, context: dict | None = None) -> BusinessCardData:
    if context is None:
        context = {'requests_made': 0, 'max_requests': 3, 'tried_key_indexes': set()}
    context.setdefault('tried_key_indexes', set())

    contents: list[object] = [user_instruction]
    contents.extend(_open_image(path) for path in image_paths)

    last_error: ExtractionError | None = None
    while True:
        tried_indexes: set[int] = context['tried_key_indexes']
        candidate = gemini_key_manager.get_candidate(tried_indexes)
        if candidate is None:
            reason = gemini_key_manager.exhaustion_reason(tried_indexes)
            logger.warning('gemini_all_keys_exhausted reason=%s key_attempt_count=%s', reason, len(tried_indexes))
            if reason in {'missing_gemini_api_key', 'all_gemini_keys_invalid', 'all_gemini_keys_rate_limited'}:
                _raise_key_exhausted(reason)
            if last_error:
                raise last_error
            _raise_key_exhausted(reason)

        _ensure_request_budget(context)
        key_index, key = candidate
        tried_indexes.add(key_index)
        client = genai.Client(api_key=key)
        started = time.perf_counter()
        try:
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0,
                    response_mime_type='application/json',
                ),
            )
            _increment_request_count(context)
            logger.info(
                'gemini_request_success images=%d elapsed_ms=%d selected_key_index=%s key_attempt_count=%s requests_made=%s',
                len(image_paths),
                int((time.perf_counter() - started) * 1000),
                key_index,
                len(tried_indexes),
                context['requests_made'],
            )
            return BusinessCardData.model_validate(_sanitize_extracted_payload(_extract_json(getattr(response, 'text', '') or '')))
        except Exception as exc:
            _increment_request_count(context)
            category, code, message, recoverable = _classify_exception(exc)
            logger.warning(
                'gemini_request_failed selected_key_index=%s key_attempt_count=%s category=%s error_class=%s error=%s requests_made=%s',
                key_index,
                len(tried_indexes),
                category,
                exc.__class__.__name__,
                _safe_error_summary(exc),
                context['requests_made'],
            )

            if category == 'gemini_invalid_api_key':
                gemini_key_manager.mark_invalid(key_index, category)
                last_error = ExtractionError(message, category=category, status_code=code, recoverable=recoverable, original=exc)
                continue
            if category in {'gemini_rate_limit', 'gemini_quota_exceeded'}:
                gemini_key_manager.mark_cooldown(key_index, category)
                last_error = ExtractionError(message, category=category, status_code=code, recoverable=recoverable, original=exc)
                continue
            if category == 'gemini_location_not_supported':
                raise ExtractionError(message, category=category, status_code=code, recoverable=recoverable, original=exc) from exc

            raise ExtractionError(message, category=category, status_code=code, recoverable=recoverable, original=exc) from exc


def _extract_with_fallback(front_image: str | Path, back_image: str | Path | None, context: dict | None = None) -> tuple[BusinessCardData, str]:
    images = [front_image, *([back_image] if back_image else [])]
    if context is None:
        context = {'requests_made': 0, 'max_requests': 3, 'tried_key_indexes': set()}

    try:
        return _call_gemini(images, 'Extract contact information from the front and back business-card images together. Return JSON only.', context=context), 'single_shot'
    except ExtractionError as exc:
        logger.warning('gemini_single_shot_failed category=%s recoverable=%s requests_made=%s', exc.category, exc.recoverable, context.get('requests_made'))
        if exc.category in NON_FALLBACK_CATEGORIES or exc.category not in FALLBACK_CATEGORIES or not back_image:
            raise

    results: list[BusinessCardData] = []
    failures: list[ExtractionError] = []
    # Use a fresh per-fallback key-attempt set so the second/third Gemini requests
    # do not blindly exhaust every key because the unified request used one key.
    for label, path in (('front', front_image), ('back', back_image)):
        side_context = {
            'requests_made': context.get('requests_made', 0),
            'max_requests': context.get('max_requests', 3),
            'tried_key_indexes': set(),
        }
        try:
            item = _call_gemini([path], f'Extract contact information from the {label} side of this business card. Return JSON only.', context=side_context)
            context['requests_made'] = side_context['requests_made']
            results.append(item)
        except ExtractionError as exc:
            context['requests_made'] = side_context.get('requests_made', context.get('requests_made', 0))
            failures.append(exc)
            logger.warning('gemini_fallback_side_failed side=%s category=%s recoverable=%s', label, exc.category, exc.recoverable)
            if exc.category in NON_FALLBACK_CATEGORIES:
                break

    if not results:
        if failures:
            raise failures[-1]
        raise ExtractionError('تعذر استخراج بيانات الكرت من Gemini.', category='gemini_external_error', status_code=502, recoverable=True)
    return _merge_extractions(results), 'fallback_two_stage'


def _merge_text(primary: str, secondary: str) -> tuple[str, bool]:
    primary = (primary or '').strip()
    secondary = (secondary or '').strip()
    if primary and secondary and primary != secondary:
        return primary if len(primary) >= len(secondary) else secondary, True
    return primary or secondary, False


def _merge_extractions(items: list[BusinessCardData]) -> BusinessCardData:
    merged = BusinessCardData()
    conflict = False
    for item in items:
        for field in STRING_FIELDS - {'raw_text', 'review_notes', 'website_visit_note'}:
            value, field_conflict = _merge_text(getattr(merged, field), getattr(item, field))
            setattr(merged, field, value)
            conflict = conflict or field_conflict
        merged.mobile_numbers = clean_list([*merged.mobile_numbers, *item.mobile_numbers])
        merged.emails = clean_list([*merged.emails, *item.emails])
        merged.confidence = max(merged.confidence, item.confidence)
        merged.needs_review = merged.needs_review or item.needs_review

    raw_parts = [item.raw_text for item in items if item.raw_text]
    merged.raw_text = '\n\n--- front/back ---\n\n'.join(dict.fromkeys(raw_parts))[:2000]
    notes = [item.review_notes for item in items if item.review_notes]
    merged.review_notes = ' | '.join(dict.fromkeys(notes))
    merged.needs_review = merged.needs_review or conflict
    return merged


def _decode_qr_images(image_paths: list[str | Path]) -> list[str]:
    try:
        import cv2
    except Exception:
        return []

    decoded: list[str] = []
    detector = cv2.QRCodeDetector()
    for path in image_paths:
        image = cv2.imread(str(path))
        if image is None:
            continue
        try:
            ok, values, _, _ = detector.detectAndDecodeMulti(image)
            if ok:
                decoded.extend(value.strip() for value in values if value and value.strip())
                continue
            value, _, _ = detector.detectAndDecode(image)
            if value and value.strip():
                decoded.append(value.strip())
        except Exception:
            logger.info('qr_decode_failed path=%s', path)
            continue
    return clean_list(decoded)


def _parse_vcard(text: str) -> dict:
    data: dict[str, object] = {'mobile_numbers': [], 'emails': []}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        upper = line.upper()
        value = line.split(':', 1)[1].strip() if ':' in line else ''
        if upper.startswith('FN:') or upper.startswith('N:'):
            data.setdefault('person_name', value.replace(';', ' ').strip())
        elif upper.startswith('ORG:'):
            data.setdefault('company_name', value)
        elif upper.startswith('TITLE:'):
            data.setdefault('job_title', value)
        elif upper.startswith('TEL'):
            data['mobile_numbers'].append(value)
        elif upper.startswith('EMAIL'):
            data['emails'].append(value)
        elif upper.startswith('URL:'):
            data.setdefault('website', value)
        elif upper.startswith('ADR:'):
            data.setdefault('address', value.replace(';', ' ').strip())
    return data


def _qr_payloads_to_data(payloads: list[str]) -> BusinessCardData:
    collected: dict[str, object] = {'mobile_numbers': [], 'emails': [], 'raw_text': ''}
    raw_text_parts = []
    for payload in payloads:
        raw_text_parts.append(f'QR: {payload}')
        if 'BEGIN:VCARD' in payload.upper():
            parsed = _parse_vcard(payload)
        else:
            parsed = {
                'emails': EMAIL_RE.findall(payload),
                'mobile_numbers': PHONE_RE.findall(payload),
            }
            urls = [url for url in URL_RE.findall(payload) if '@' not in url]
            if urls:
                parsed['website'] = urls[0]
        for field in ('person_name', 'job_title', 'company_name', 'website', 'address'):
            if parsed.get(field) and not collected.get(field):
                collected[field] = parsed[field]
        collected['emails'].extend(parsed.get('emails', []))
        collected['mobile_numbers'].extend(parsed.get('mobile_numbers', []))

    collected['emails'] = clean_list(collected['emails'])
    collected['mobile_numbers'] = normalize_phones(collected['mobile_numbers'])
    collected['raw_text'] = '\n'.join(raw_text_parts)[:2000]
    return BusinessCardData.model_validate(_sanitize_extracted_payload(collected))


def _merge_qr(parsed: BusinessCardData, qr_data: BusinessCardData) -> BusinessCardData:
    if not qr_data.raw_text:
        return parsed
    for field in ('person_name', 'job_title', 'company_name', 'website', 'address'):
        if not getattr(parsed, field) and getattr(qr_data, field):
            setattr(parsed, field, getattr(qr_data, field))
    parsed.mobile_numbers = clean_list([*parsed.mobile_numbers, *qr_data.mobile_numbers])
    parsed.emails = clean_list([*parsed.emails, *qr_data.emails])
    parsed.raw_text = '\n'.join(part for part in [parsed.raw_text, qr_data.raw_text] if part)[:2000]
    parsed.review_notes = ' | '.join(part for part in [parsed.review_notes, 'تمت قراءة QR محلياً'] if part)
    return parsed


def _postprocess(parsed: BusinessCardData) -> BusinessCardData:
    parsed.mobile_numbers = normalize_phones([*parsed.mobile_numbers, *PHONE_RE.findall(parsed.raw_text or '')])
    parsed.emails = clean_list([*parsed.emails, *EMAIL_RE.findall(parsed.raw_text or '')])
    if not parsed.website:
        urls = [url for url in URL_RE.findall(parsed.raw_text or '') if '@' not in url]
        if urls:
            parsed.website = urls[0]
    parsed.website = normalize_website(parsed.website)
    parsed.raw_text = re.sub(r'\n{3,}', '\n\n', parsed.raw_text or '').strip()[:2000]
    return parsed


def _finalize(parsed: BusinessCardData) -> BusinessCardData:
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
    elif parsed.confidence >= 0.75 and not parsed.review_notes:
        parsed.needs_review = False

    return parsed


def extract_business_card(front_image: str | Path, back_image: str | Path | None = None) -> BusinessCardData:
    if not gemini_key_manager.has_keys():
        raise ExtractionError('لم يتم إعداد مفتاح Gemini API على الخادم.', category='missing_gemini_api_key', status_code=502, recoverable=False)

    started = time.perf_counter()
    context = {
        'requests_made': 0,
        'max_requests': int(getattr(settings, 'GEMINI_MAX_REQUESTS_PER_CARD', 3)),
        'tried_key_indexes': set(),
    }
    parsed, strategy = _extract_with_fallback(front_image, back_image, context=context)
    qr_payloads = _decode_qr_images([front_image, *([back_image] if back_image else [])])
    if qr_payloads:
        parsed = _merge_qr(parsed, _qr_payloads_to_data(qr_payloads))
    parsed = _finalize(_postprocess(parsed))
    logger.info(
        'business_card_extracted strategy=%s elapsed_ms=%d qr_count=%d gemini_requests=%d needs_review=%s confidence=%.2f',
        strategy,
        int((time.perf_counter() - started) * 1000),
        len(qr_payloads),
        context.get('requests_made', 0),
        parsed.needs_review,
        parsed.confidence,
    )
    return parsed
