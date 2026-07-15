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


# ── Country derivation ───────────────────────────────────────
# Cards have no dedicated country column in source data; the country lives in
# the free-text address (usually as the leading "الدولة - المدينة" segment) and,
# as a fallback, can be inferred from the phone country code. Values are folded
# to a canonical Arabic country name so the dashboard filter stays consistent.
_COUNTRY_TOKENS = [
    ('سوريا', ['سوريا', 'سورية', 'سوري', 'الجمهورية العربية السورية', 'syria', 'suriye',
               'damascus', 'دمشق', 'حلب', 'حمص', 'حماة', 'اللاذقية', 'طرطوس', 'mazzeh']),
    ('تركيا', ['تركيا', 'تركية', 'تركي', 'türkiye', 'turkiye', 'turkey', 'turkish',
               'türk', 'istanbul', 'اسطنبول', 'اسطنبۇل', 'ankara', 'انقرة']),
    ('السعودية', ['المملكة العربية السعودية', 'السعودية', 'سعودية', 'saudi', 'k.s.a', 'ksa',
                  'riyadh', 'الرياض', 'jeddah', 'جدة', 'الدمام', 'dammam']),
    ('الأردن', ['الأردن', 'الاردن', 'اردن', 'jordan', 'amman']),
    ('الإمارات', ['الإمارات', 'الامارات', 'uae', 'u.a.e', 'emirates', 'dubai', 'دبي',
                  'abu dhabi', 'أبوظبي', 'ابوظبي', 'الشارقة', 'sharjah']),
    ('لبنان', ['لبنان', 'lebanon', 'beirut', 'بيروت']),
    ('مصر', ['مصر', 'egypt', 'cairo', 'القاهرة']),
    ('قطر', ['قطر', 'qatar', 'doha', 'الدوحة']),
    ('الكويت', ['الكويت', 'kuwait']),
    ('العراق', ['العراق', 'iraq', 'baghdad', 'بغداد', 'erbil', 'اربيل']),
    ('الصين', ['الصين', 'china', 'shanghai', 'beijing']),
    ('إيطاليا', ['إيطاليا', 'ايطاليا', 'italy', 'italia']),
    ('ألمانيا', ['ألمانيا', 'المانيا', 'germany', 'deutschland']),
    ('فرنسا', ['فرنسا', 'france', 'paris']),
    ('بريطانيا', ['بريطانيا', 'المملكة المتحدة', 'united kingdom', 'england', 'london', 'لندن']),
    ('الولايات المتحدة', ['الولايات المتحدة', 'أمريكا', 'امريكا', 'أميركا', 'اميركا',
                          'united states', 'u.s.a', 'usa', 'america']),
    ('تونس', ['تونس', 'tunisia', 'tunis']),
    ('كمبوديا', ['كمبوديا', 'cambodia', 'phnom penh', 'بنوم بنه']),
    ('المجر', ['المجر', 'hungary', 'budapest']),
]

_PHONE_COUNTRY = [
    ('963', 'سوريا'), ('966', 'السعودية'), ('971', 'الإمارات'), ('974', 'قطر'),
    ('965', 'الكويت'), ('964', 'العراق'), ('962', 'الأردن'), ('961', 'لبنان'),
    ('216', 'تونس'), ('855', 'كمبوديا'),
    ('90', 'تركيا'), ('20', 'مصر'), ('86', 'الصين'), ('39', 'إيطاليا'),
    ('49', 'ألمانيا'), ('33', 'فرنسا'), ('44', 'بريطانيا'), ('36', 'المجر'),
    ('1', 'الولايات المتحدة'),
]

_UNKNOWN_MARKERS = {'', 'غير محدد', 'غير معروف', 'na', 'n/a', '-', '—'}


def _match_country(text: str) -> str:
    low = (text or '').strip().lower()
    if not low:
        return ''
    for canonical, tokens in _COUNTRY_TOKENS:
        for token in tokens:
            if token.lower() in low:
                return canonical
    return ''


def derive_country(data) -> str:
    """Best-effort canonical Arabic country name for a card.

    Order: leading "الدولة - المدينة" address segment (accepted even if not in
    the token map, so new countries appear automatically) → token scan of the
    whole address → phone country code. Returns '' when nothing is found.
    """
    if hasattr(data, 'get'):
        address = str(data.get('address') or '')
        phones = data.get('mobile_numbers') or []
    else:  # model instance
        address = str(getattr(data, 'address', '') or '')
        phones = getattr(data, 'mobile_numbers', None) or []

    # 1) Leading segment of a spaced "country - city" address.
    if re.search(r'\s[-–—]\s', address):
        lead = re.split(r'\s[-–—]\s', address.strip(), 1)[0].strip()
        if lead.lower() not in _UNKNOWN_MARKERS:
            match = _match_country(lead)
            if match:
                return match
            # Accept a short, name-like leading segment as a country as-is.
            if (len(lead) <= 25 and not any(ch.isdigit() for ch in lead)
                    and len(lead.split()) <= 3 and ',' not in lead and '،' not in lead):
                return lead

    # 2) Token scan of the whole address.
    match = _match_country(address)
    if match:
        return match

    # 3) Phone country code.
    for phone in phones:
        raw = str(phone).strip()
        digits = re.sub(r'\D+', '', raw)
        if not digits:
            continue
        if raw.startswith('00'):
            digits = digits[2:]
        for code, country in _PHONE_COUNTRY:
            if digits.startswith(code):
                return country
    return ''
