from __future__ import annotations

from .normalization import build_duplicate_hash, clean_list, normalize_phones, normalize_website
from .website_enrichment import infer_investment_type

INVESTMENT_TYPE_CHOICES = [
    'مؤسسة الحلج و الاقطان',
    'المؤسسة العامة للصناعات الهندسية',
    'المؤسسة العامة للصناعات النسيجية',
    'المؤسسة العامة للصناعات الكيميائية',
    'مؤسسة الصناعات الغذائية',
    'المؤسسة العامة للتبغ',
    'هيئة ادارة المعادن النبيلة وهيئة المواصفات و المقاييس',
    'مديرية المدن و المناطق الصناعية',
    'مديرية الاشراف على التاهيل الفني',
    'مركز الاختبارات و الابحاث',
    'غير ذلك',
]


def split_bilingual_lines(value: str) -> tuple[str, str]:
    parts = [part.strip() for part in (value or '').splitlines() if part.strip()]
    if not parts:
        return '', ''
    if len(parts) == 1:
        return parts[0], ''
    return parts[0], parts[1]


def combine_bilingual(arabic: str, english: str, fallback: str = '') -> str:
    parts = [part.strip() for part in [arabic, english] if part and part.strip()]
    if parts:
        return '\n'.join(dict.fromkeys(parts))
    return (fallback or '').strip()


def prepare_card_data(
    data: dict,
    *,
    infer_missing_investment: bool = True,
    touched_fields: set[str] | None = None,
) -> dict:
    """Normalize incoming card payloads before saving them in BusinessCard.

    This function is intentionally shared by the API and Excel import command so
    manual imports and AI-extracted cards follow the same rules.
    """
    prepared = dict(data)
    touched_fields = touched_fields or set()
    prepared['mobile_numbers'] = normalize_phones(prepared.get('mobile_numbers', []))
    prepared['emails'] = clean_list(prepared.get('emails', []))
    prepared['website'] = normalize_website(prepared.get('website', ''))

    for base_name in ('person_name', 'job_title', 'company_name'):
        value = prepared.get(base_name, '') or ''
        arabic_field = f'{base_name}_ar'
        english_field = f'{base_name}_en'
        base_was_touched = base_name in touched_fields
        split_from_base = (
            base_was_touched
            and arabic_field not in touched_fields
            and english_field not in touched_fields
        )
        if split_from_base:
            arabic_value, english_value = split_bilingual_lines(value)
            prepared[arabic_field] = arabic_value
            prepared[english_field] = english_value
        elif value and not prepared.get(arabic_field) and not prepared.get(english_field):
            arabic_value, english_value = split_bilingual_lines(value)
            prepared[arabic_field] = arabic_value
            prepared[english_field] = english_value
        prepared[base_name] = combine_bilingual(
            prepared.get(arabic_field, ''),
            prepared.get(english_field, ''),
            value,
        )

    if prepared.get('investment_type') not in INVESTMENT_TYPE_CHOICES:
        if prepared.get('investment_type'):
            prepared['investment_type_other'] = prepared.get('investment_type_other') or prepared['investment_type']
        prepared['investment_type'] = 'غير ذلك' if prepared.get('investment_type_other') else ''
    elif prepared.get('investment_type') != 'غير ذلك':
        prepared['investment_type_other'] = ''

    if infer_missing_investment and not prepared.get('investment_type'):
        inferred_type, inferred_other = infer_investment_type(
            prepared.get('company_name', ''),
            prepared.get('company_activity', ''),
            '',
            prepared.get('raw_text', ''),
        )
        prepared['investment_type'] = inferred_type
        prepared['investment_type_other'] = inferred_other

    prepared['duplicate_hash'] = build_duplicate_hash(prepared)
    return prepared
