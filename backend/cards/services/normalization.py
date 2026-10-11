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


# Every piece of information printed on a card. The stored ``duplicate_hash`` is
# the exact fingerprint of all of them; near-duplicates (OCR slips, a missing
# field) are scored field by field in ``duplicates.py``.
DUPLICATE_TEXT_FIELDS = (
    'person_name', 'person_name_ar', 'person_name_en',
    'job_title', 'job_title_ar', 'job_title_en',
    'company_name', 'company_name_ar', 'company_name_en',
    'website', 'address',
)


def _card_value(data, name: str):
    """Read a field from a prepared-data dict or a BusinessCard instance."""
    if isinstance(data, dict):
        return data.get(name)
    return getattr(data, name, None)


def duplicate_key(data) -> str:
    """Normalised fingerprint of ALL the card's information.

    Equal keys mean identical cards. Emails and phone numbers are compared as
    sets, so their order on the card is ignored.
    """
    parts = [f'{name}={normalize_text(_card_value(data, name))}' for name in DUPLICATE_TEXT_FIELDS]
    emails = sorted({normalize_text(str(x)) for x in _card_value(data, 'emails') or [] if x} - {''})
    phones = sorted({re.sub(r'\D+', '', str(x)) for x in _card_value(data, 'mobile_numbers') or [] if x} - {''})
    parts.append('emails=' + '|'.join(emails))
    parts.append('phones=' + '|'.join(phones))
    return 'full:' + ';'.join(parts)


def has_card_identity(data) -> bool:
    """False for a card carrying no information at all — never a duplicate."""
    if any(normalize_text(_card_value(data, name)) for name in DUPLICATE_TEXT_FIELDS):
        return True
    return bool(_card_value(data, 'emails') or _card_value(data, 'mobile_numbers'))


def build_duplicate_hash(data) -> str:
    return hashlib.sha256(duplicate_key(data).encode('utf-8')).hexdigest()


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
