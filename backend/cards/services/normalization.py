from __future__ import annotations
import hashlib
import re
from typing import Iterable
import phonenumbers


def clean_list(values: Iterable[str] | None) -> list[str]:
    seen = set()
    result = []
    for value in values or []:
        item = str(value).strip()
        if item and item.lower() not in seen:
            seen.add(item.lower())
            result.append(item)
    return result


def normalize_text(value: str | None) -> str:
    value = (value or '').lower().strip()
    value = re.sub(r'https?://', '', value)
    value = re.sub(r'www\.', '', value)
    value = re.sub(r'[^\w\u0600-\u06FF]+', '', value)
    return value


def normalize_website(value: str | None) -> str:
    value = (value or '').strip().replace(' ', '')
    if not value:
        return ''
    if not value.startswith(('http://', 'https://')):
        value = 'https://' + value
    return value


def normalize_phones(values: Iterable[str] | None, default_region: str = 'SA') -> list[str]:
    normalized = []
    for value in values or []:
        raw = re.sub(r'[^0-9+]+', '', str(value))
        if len(raw) < 7:
            continue
        try:
            parsed = phonenumbers.parse(raw, default_region)
            if phonenumbers.is_possible_number(parsed):
                normalized.append(phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL))
                continue
        except Exception:
            pass
        normalized.append(raw)
    return clean_list(normalized)


def build_duplicate_hash(data: dict) -> str:
    emails = [normalize_text(x) for x in data.get('emails', []) if x]
    phones = [re.sub(r'\D+', '', x) for x in data.get('mobile_numbers', []) if x]
    website = normalize_text(data.get('website'))
    person = normalize_text(data.get('person_name') or data.get('person_name_ar') or data.get('person_name_en'))
    company = normalize_text(data.get('company_name') or data.get('company_name_ar') or data.get('company_name_en'))

    # Prefer stable contact identifiers over name-only matching.
    if emails:
        key = 'email:' + '|'.join(sorted(emails))
    elif phones:
        key = 'phone:' + '|'.join(sorted(phones))
    elif website and person:
        key = f'person_site:{person}:{website}'
    else:
        key = f'name_company:{person}:{company}:{website}'
    return hashlib.sha256(key.encode('utf-8')).hexdigest()


def duplicate_reason(new_data: dict, existing) -> str:
    new_emails = {normalize_text(x) for x in new_data.get('emails', [])}
    old_emails = {normalize_text(x) for x in existing.emails or []}
    if new_emails & old_emails:
        return 'نفس البريد الإلكتروني'
    new_phones = {re.sub(r'\D+', '', x) for x in new_data.get('mobile_numbers', [])}
    old_phones = {re.sub(r'\D+', '', x) for x in existing.mobile_numbers or []}
    if new_phones & old_phones:
        return 'نفس رقم الموبايل'
    return 'نفس بصمة الاسم/الشركة/الموقع'
