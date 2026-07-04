"""Very small rule/keyword based natural-language search parser.

No external AI or paid API is used here. The goal is to turn short
Arabic/English sentences like "عرضلي شركات المياه" or "companies in Damascus"
into a dict of structured filters, then apply those filters to the
BusinessCard queryset while tolerating the messy reality of the imported
data: mixed Arabic spelling of hamza/alef/ta-marbuta, free-text activity
fields, and multi-word phrases that never appear verbatim in any single
field.
"""
from __future__ import annotations

import re

from django.db.models import Q

# Trigger phrases that only signal *intent* and carry no search value.
COMMAND_WORDS = [
    'عرضلي', 'اعرض', 'أعرض', 'بدي', 'بدّي', 'ابغى', 'أبغى', 'اريد', 'أريد',
    'عرض', 'اظهر', 'أظهر', 'ورجيني', 'وريني',
    'show', 'display', 'list', 'give', 'find', 'get', 'me',
]

# Generic nouns/stopwords that carry no search value on their own - always
# stripped, regardless of whether a specific filter was also detected.
GENERIC_NOUNS = [
    'شركات', 'شركة', 'كروت', 'كرت', 'الموجودة', 'الموجودين', 'الذين',
    'التي', 'الذي', 'في', 'من', 'على', 'مع',
    'companies', 'company', 'cards', 'card', 'in', 'the', 'of', 'with', 'at',
]

REVIEW_TRIGGERS = [
    'تحتاج مراجعة', 'يحتاج مراجعة', 'تحتاج للمراجعة', 'بحاجة لمراجعة',
    'needs review', 'need review', 'need to review',
]

MISSING_EMAIL_TRIGGERS = [
    'بدون ايميل', 'بدون إيميل', 'بدون بريد', 'بلا بريد', 'بلا ايميل',
    'ليس لديها بريد الكتروني', 'ليس لديها بريد إلكتروني', 'بدون بريد الكتروني',
    'no email', 'without email', "doesn't have email", 'missing email',
]

MISSING_PHONE_TRIGGERS = [
    'بدون هاتف', 'بلا هاتف', 'بدون رقم', 'بدون موبايل', 'بلا موبايل',
    'no phone', 'without phone', 'missing phone', "doesn't have phone",
]

# key -> canonical value searched against the free-text address field.
COUNTRY_MAP = {
    'تركيا': 'تركيا', 'تركية': 'تركيا', 'turkey': 'Turkey', 'turkish': 'Turkey',
    'سوريا': 'سوريا', 'سورية': 'سوريا', 'syria': 'Syria',
    'لبنان': 'لبنان', 'lebanon': 'Lebanon',
    'الأردن': 'الأردن', 'اردن': 'الأردن', 'jordan': 'Jordan',
    'مصر': 'مصر', 'egypt': 'Egypt',
    'السعودية': 'السعودية', 'سعودية': 'السعودية', 'saudi': 'Saudi Arabia',
    'الإمارات': 'الإمارات', 'امارات': 'الإمارات', 'uae': 'UAE', 'emirates': 'UAE',
    'قطر': 'قطر', 'qatar': 'Qatar',
    'الكويت': 'الكويت', 'kuwait': 'Kuwait',
    'العراق': 'العراق', 'iraq': 'Iraq',
}

CITY_MAP = {
    'دمشق': 'دمشق', 'damascus': 'Damascus',
    'حلب': 'حلب', 'aleppo': 'Aleppo',
    'حمص': 'حمص', 'homs': 'Homs',
    'حماة': 'حماة', 'hama': 'Hama',
    'اللاذقية': 'اللاذقية', 'latakia': 'Latakia',
    'طرطوس': 'طرطوس', 'tartus': 'Tartus',
    'اسطنبول': 'اسطنبول', 'istanbul': 'Istanbul',
    'انقرة': 'انقرة', 'ankara': 'Ankara',
    'الرياض': 'الرياض', 'riyadh': 'Riyadh',
    'جدة': 'جدة', 'jeddah': 'Jeddah',
}

# key -> canonical Arabic keyword to search for in activity/investment fields.
# Mainly useful for English -> Arabic translation; Arabic free text typed by
# the user is matched directly through the generic tokenized search below,
# so this map does not need to be exhaustive.
ACTIVITY_MAP = {
    'مياه': 'مياه', 'water': 'مياه',
    'كهرباء': 'كهرباء', 'كهربائية': 'كهرباء', 'electricity': 'كهرباء', 'power': 'كهرباء',
    'مقاولات': 'مقاولات', 'contracting': 'مقاولات', 'construction': 'مقاولات',
    'نسيج': 'نسيج', 'نسيجية': 'نسيج', 'textile': 'نسيج', 'textiles': 'نسيج',
    'غذائية': 'غذائية', 'غذاء': 'غذائية', 'food': 'غذائية',
    'كيميائية': 'كيميائية', 'chemical': 'كيميائية', 'chemicals': 'كيميائية',
    'هندسية': 'هندسية', 'هندسة': 'هندسية', 'engineering': 'هندسية',
    'تبغ': 'تبغ', 'tobacco': 'تبغ',
    'تعدين': 'تعدين', 'mining': 'تعدين',
    'معادن': 'معادن', 'metals': 'معادن',
    'سيبراني': 'سيبراني', 'cyber': 'سيبراني', 'cybersecurity': 'سيبراني',
    'اتصالات': 'اتصالات', 'telecom': 'اتصالات',
    'سياحة': 'سياحة', 'tourism': 'سياحة',
    'تعليم': 'تعليم', 'education': 'تعليم',
    'قانونية': 'قانونية', 'legal': 'قانونية',
    'طاقة': 'طاقة', 'energy': 'طاقة',
}

# Fields searched for each kind of term. JSON list fields (emails,
# mobile_numbers) are flattened to a string before matching.
ADDRESS_FIELDS = ['address']
ACTIVITY_FIELDS = ['company_activity', 'investment_type', 'investment_type_other', 'company_name']
SEARCHALL_FIELDS = [
    'person_name', 'person_name_ar', 'person_name_en',
    'company_name', 'company_name_ar', 'company_name_en',
    'job_title', 'job_title_ar', 'job_title_en',
    'company_activity', 'investment_type', 'investment_type_other',
    'website', 'address', 'raw_text', 'review_notes',
    'emails', 'mobile_numbers',
]

# Arabic combining diacritics (U+064B-U+0652), superscript alef (U+0670)
# and tatweel (U+0640).
_DIACRITICS_RE = re.compile('[ً-ْٰـ]')
# Alef/hamza variants: alef with madda (U+0622), hamza above/below alef
# (U+0623, U+0625), plain alef (U+0627).
_ALEF_RE = re.compile('[آأإا]')


def normalize_arabic(text: str) -> str:
    """Fold common Arabic spelling variants so search is spelling-tolerant.

    Handles hamza/alef variants (أ/إ/آ -> ا), alef maksura (ى -> ي),
    ta marbuta (ة -> ه), diacritics, and tatweel. Also lowercases Latin
    text so Arabic and English terms can share the same comparison path.
    """
    if not text:
        return ''
    text = _DIACRITICS_RE.sub('', text)
    text = _ALEF_RE.sub('ا', text)
    text = text.replace('ى', 'ي')  # alef maksura (ى) -> ya (ي)
    text = text.replace('ة', 'ه')  # ta marbuta (ة) -> ha (ه)
    text = text.replace('ؤ', 'و')  # waw with hamza (ؤ) -> waw (و)
    text = text.replace('ئ', 'ي')  # ya with hamza (ئ) -> ya (ي)
    return text.strip().lower()


def _flatten_field(value) -> str:
    if isinstance(value, (list, tuple)):
        return ' '.join(str(item) for item in value)
    return str(value or '')


def _token_matches_key(token_norm: str, key_norm: str) -> bool:
    """True if a token equals a keyword, optionally with the Arabic "ال" prefix."""
    if not token_norm or not key_norm:
        return False
    return token_norm == key_norm or token_norm == 'ال' + key_norm


def parse_natural_query(query: str) -> dict:
    """Parse a short Arabic/English sentence into structured search filters.

    Returns a dict with keys: text, city, country, status, missing_email,
    missing_phone, activity_keyword. ``text`` is whatever free text is left
    after stripping recognized trigger phrases/keywords - it should be
    tokenized and matched as a "must contain all these words somewhere"
    search rather than as one exact phrase.
    """
    raw = (query or '').strip()

    result = {
        'text': raw,
        'city': None,
        'country': None,
        'status': None,
        'missing_email': False,
        'missing_phone': False,
        'activity_keyword': None,
    }

    if not raw:
        return result

    normalized_full = normalize_arabic(raw)

    for trig in REVIEW_TRIGGERS:
        if normalize_arabic(trig) in normalized_full:
            result['status'] = 'needs_review'
            break

    for trig in MISSING_EMAIL_TRIGGERS:
        if normalize_arabic(trig) in normalized_full:
            result['missing_email'] = True
            break

    for trig in MISSING_PHONE_TRIGGERS:
        if normalize_arabic(trig) in normalized_full:
            result['missing_phone'] = True
            break

    # Tokenize once and consume words as they get matched, so leftover text
    # never contains dangling fragments (e.g. a stray "ال").
    trigger_words = set()
    for trig in REVIEW_TRIGGERS + MISSING_EMAIL_TRIGGERS + MISSING_PHONE_TRIGGERS:
        for word in normalize_arabic(trig).split():
            trigger_words.add(word)

    tokens = raw.split()
    remaining = []
    for token in tokens:
        token_norm = normalize_arabic(token)
        if not token_norm:
            continue

        if token_norm in trigger_words:
            continue

        if any(_token_matches_key(token_norm, normalize_arabic(w)) for w in COMMAND_WORDS):
            continue

        if any(_token_matches_key(token_norm, normalize_arabic(w)) for w in GENERIC_NOUNS):
            continue

        if result['country'] is None:
            for key, canonical in COUNTRY_MAP.items():
                if _token_matches_key(token_norm, normalize_arabic(key)):
                    result['country'] = canonical
                    token_norm = None
                    break
            if token_norm is None:
                continue

        if result['city'] is None:
            for key, canonical in CITY_MAP.items():
                if _token_matches_key(token_norm, normalize_arabic(key)):
                    result['city'] = canonical
                    token_norm = None
                    break
            if token_norm is None:
                continue

        if result['activity_keyword'] is None:
            for key, canonical in ACTIVITY_MAP.items():
                if _token_matches_key(token_norm, normalize_arabic(key)):
                    result['activity_keyword'] = canonical
                    token_norm = None
                    break
            if token_norm is None:
                continue

        remaining.append(token)

    result['text'] = ' '.join(remaining).strip()
    return result


def _row_matches(row: dict, terms: list[tuple[str, list[str]]]) -> bool:
    cache: dict[str, str] = {}

    def normalized_field(field: str) -> str:
        if field not in cache:
            cache[field] = normalize_arabic(_flatten_field(row.get(field)))
        return cache[field]

    for term, fields in terms:
        term_norm = normalize_arabic(term)
        if not term_norm:
            continue
        if not any(term_norm in normalized_field(field) for field in fields):
            return False
    return True


def apply_natural_search(qs, parsed: dict):
    """Apply a parsed natural query to a BusinessCard queryset.

    Structural conditions (status/missing email/missing phone) are applied
    as plain SQL filters. Free-text conditions (city/country/activity/
    leftover words) are evaluated in Python with Arabic-spelling-tolerant
    normalization, since SQL ``icontains`` cannot reliably match hamza/
    ta-marbuta variants or multi-word phrases split across fields. The
    dataset size here (business card imports) makes this comfortably fast.
    """
    structural = Q()
    has_structural = False

    if parsed.get('status'):
        structural &= Q(status=parsed['status'])
        has_structural = True

    if parsed.get('missing_email'):
        structural &= (Q(emails=[]) | Q(emails__isnull=True))
        has_structural = True

    if parsed.get('missing_phone'):
        structural &= (Q(mobile_numbers=[]) | Q(mobile_numbers__isnull=True))
        has_structural = True

    if has_structural:
        qs = qs.filter(structural)

    terms: list[tuple[str, list[str]]] = []
    if parsed.get('city'):
        terms.append((parsed['city'], ADDRESS_FIELDS))
    if parsed.get('country'):
        terms.append((parsed['country'], ADDRESS_FIELDS))
    if parsed.get('activity_keyword'):
        terms.append((parsed['activity_keyword'], ACTIVITY_FIELDS))
    for token in (parsed.get('text') or '').split():
        if len(token) >= 2:
            terms.append((token, SEARCHALL_FIELDS))

    if not terms:
        return qs

    needed_fields = {'id'}
    for _, fields in terms:
        needed_fields.update(fields)

    rows = qs.values(*needed_fields)
    matched_ids = [row['id'] for row in rows if _row_matches(row, terms)]
    return qs.filter(id__in=matched_ids)


def derive_category(activity: str) -> str:
    """Bucket a free-text company_activity value into a compact category.

    The imported data mixes a placeholder ("نشاط غير محدد"), short single
    words ("هندسية", "مقاولات"), and long "category - details" or
    "category/details" descriptions (e.g. "هندسية - شركة الإنشاءات..."،
    "تكنو فيست تركيا/استشارات تجارية"). Taking the segment before the first
    separator keeps the specialty stats compact instead of showing one row
    per company.
    """
    text = (activity or '').strip()
    if not text or text == 'نشاط غير محدد':
        return 'غير محدد'
    for separator in (' - ', '/'):
        if separator in text:
            head = text.split(separator, 1)[0].strip()
            if head:
                return head
    return text
