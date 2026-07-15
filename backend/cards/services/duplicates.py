from __future__ import annotations

import re
import uuid

from django.db.models import Q

from ..models import BusinessCard
from .normalization import normalize_text


def _duplicate_candidate_payload(card: BusinessCard, reason: str, score: int) -> dict:
    return {
        'id': card.id,
        'sequence_number': card.sequence_number,
        'person_name': card.person_name,
        'company_name': card.company_name,
        'mobile_numbers': card.mobile_numbers or [],
        'emails': card.emails or [],
        'website': card.website,
        'reason': reason,
        'score': score,
    }


def score_duplicate(data: dict, existing: BusinessCard) -> tuple[int, str]:
    if data.get('duplicate_hash') and data.get('duplicate_hash') == existing.duplicate_hash:
        return 100, 'نفس بصمة التكرار'

    new_emails = {normalize_text(item) for item in data.get('emails', []) if item}
    old_emails = {normalize_text(item) for item in existing.emails or [] if item}
    if new_emails and old_emails and new_emails & old_emails:
        return 100, 'نفس البريد الإلكتروني'

    new_phones = {re.sub(r'\D+', '', item) for item in data.get('mobile_numbers', []) if item}
    old_phones = {re.sub(r'\D+', '', item) for item in existing.mobile_numbers or [] if item}
    for new_phone in new_phones:
        for old_phone in old_phones:
            if new_phone and old_phone and (new_phone == old_phone or new_phone[-8:] == old_phone[-8:]):
                return 95, 'نفس رقم الهاتف'

    new_website = normalize_text(data.get('website'))
    old_website = normalize_text(existing.website)
    new_person = normalize_text(data.get('person_name') or data.get('person_name_ar') or data.get('person_name_en'))
    old_person = normalize_text(existing.person_name or existing.person_name_ar or existing.person_name_en)
    new_company = normalize_text(data.get('company_name') or data.get('company_name_ar') or data.get('company_name_en'))
    old_company = normalize_text(existing.company_name or existing.company_name_ar or existing.company_name_en)

    if new_website and old_website and new_website == old_website and new_person and old_person and new_person == old_person:
        return 90, 'نفس الموقع واسم الشخص'
    if new_company and old_company and new_company == old_company and new_person and old_person and new_person == old_person:
        return 88, 'نفس الشركة واسم الشخص'
    if new_website and old_website and new_website == old_website and new_company and old_company and new_company == old_company:
        return 86, 'نفس الموقع والشركة'
    if new_company and old_company and new_company == old_company and (new_website or new_emails or new_phones):
        return 70, 'اسم الشركة مطابق مع بيانات اتصال مختلفة أو ناقصة'
    return 0, ''


def find_duplicate_candidates(data: dict, queryset, *, limit: int = 5) -> list[dict]:
    """Find likely duplicates of ``data`` within ``queryset``.

    ``queryset`` is the ownership-scoped base queryset, so a regular user only
    ever matches against their own cards and never learns about a duplicate
    owned by someone else.
    """
    query = Q()
    if data.get('duplicate_hash'):
        query |= Q(duplicate_hash=data['duplicate_hash'])
    for email in data.get('emails', []) or []:
        if email:
            query |= Q(emails__icontains=str(email).strip().lower())
    for phone in data.get('mobile_numbers', []) or []:
        digits = re.sub(r'\D+', '', str(phone))
        if len(digits) >= 8:
            query |= Q(mobile_numbers__icontains=digits[-8:])
    website_lookup = re.sub(r'^https?://', '', str(data.get('website') or ''), flags=re.I)
    website_lookup = re.sub(r'^www\.', '', website_lookup).split('/')[0].strip().lower()
    if website_lookup:
        query |= Q(website__icontains=website_lookup[:120])
    company = (data.get('company_name') or data.get('company_name_ar') or data.get('company_name_en') or '').strip()
    person = (data.get('person_name') or data.get('person_name_ar') or data.get('person_name_en') or '').strip()
    if company:
        query |= Q(company_name__icontains=company) | Q(company_name_ar__icontains=company) | Q(company_name_en__icontains=company)
    if person:
        query |= Q(person_name__icontains=person) | Q(person_name_ar__icontains=person) | Q(person_name_en__icontains=person)

    if not query:
        return []

    scored: list[dict] = []
    for card in queryset.filter(query).distinct().order_by('-sequence_number')[:50]:
        score, reason = score_duplicate(data, card)
        if score >= 60:
            scored.append(_duplicate_candidate_payload(card, reason, score))
    scored.sort(key=lambda item: item['score'], reverse=True)
    return scored[:limit]


def salt_duplicate_hash(data: dict) -> dict:
    copy = dict(data)
    base = copy.get('duplicate_hash') or uuid.uuid4().hex
    copy['duplicate_hash'] = f'{base[:64]}:{uuid.uuid4().hex}'[:128]
    return copy


def find_existing_duplicate(data: dict, queryset):
    """Locate the strongest matching card (score >= 80) within ``queryset``."""
    existing = None
    if data.get('duplicate_hash'):
        existing = queryset.filter(duplicate_hash=data['duplicate_hash']).first()
    if not existing:
        for email in data.get('emails', []) or []:
            existing = queryset.filter(emails__icontains=email).first()
            if existing:
                break
    if not existing:
        for phone in data.get('mobile_numbers', []) or []:
            digits = ''.join(char for char in str(phone) if char.isdigit())
            if digits:
                existing = queryset.filter(mobile_numbers__icontains=digits[-8:]).first()
                if existing:
                    break
    return existing
