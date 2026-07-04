from __future__ import annotations

import re

_AR = re.compile(r'[؀-ۿ]')


def _is_arabic(text: str) -> bool:
    return bool(_AR.search(text or ''))


def _translate(text: str, source: str, target: str) -> str:
    if not text or not text.strip():
        return ''
    try:
        from deep_translator import GoogleTranslator
        result = GoogleTranslator(source=source, target=target).translate(text.strip())
        return (result or '').strip()
    except Exception:
        return ''


def fill_bilingual_fields(data: dict) -> dict:
    """
    For each bilingual field pair (_ar/_en), if one side is missing,
    translate from the other side using Google Translate (free, no Gemini quota used).
    """
    pairs = [
        ('job_title_ar', 'job_title_en'),
        ('person_name_ar', 'person_name_en'),
        ('company_name_ar', 'company_name_en'),
    ]
    for ar_field, en_field in pairs:
        ar_val = (data.get(ar_field) or '').strip()
        en_val = (data.get(en_field) or '').strip()

        if ar_val and not en_val:
            data[en_field] = _translate(ar_val, source='ar', target='en')
        elif en_val and not ar_val:
            data[ar_field] = _translate(en_val, source='en', target='ar')

    return data
