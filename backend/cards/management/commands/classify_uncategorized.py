"""Classify cards currently under 'غير ذلك' into a concrete investment type.

Conservative by design: a card is reclassified only when its text matches
EXACTLY ONE category by distinctive keywords. Ambiguous cards (matching more
than one category) or unmatched cards are left as 'غير ذلك' and flagged
needs_review so a human confirms them.

    python manage.py classify_uncategorized --dry-run   # preview + breakdown
    python manage.py classify_uncategorized             # apply
"""
from __future__ import annotations

import contextlib
import re
from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from cards.models import BusinessCard

OTHER = 'غير ذلك'

# Distinctive keywords per category (Arabic + English). Overlaps are intentional
# so a genuinely ambiguous card matches >1 category and is left for review.
CATEGORY_KEYWORDS = {
    'مؤسسة الحلج و الاقطان': ['حلج', 'اقطان', 'قطن', 'cotton', 'ginning'],
    'المؤسسة العامة للصناعات الهندسية': [
        'هندس', 'ميكانيك', 'الات', 'معدات', 'مسبك', 'خراطة', 'صناعات معدنية',
        'قطع غيار', 'حدادة', 'قوالب معدنية',
        'engineering', 'mechanical', 'machinery',
    ],
    'المؤسسة العامة للصناعات النسيجية': [
        'نسيج', 'منسوجات', 'البسة', 'اقمشة', 'قماش', 'خياطة', 'غزل',
        'textile', 'garment', 'fabric',
    ],
    'المؤسسة العامة للصناعات الكيميائية': [
        'كيميا', 'كيماوي', 'دهان', 'بلاستيك', 'منظفات', 'اسمدة', 'دوائية', 'ادوية',
        'chemical', 'plastic', 'paint', 'detergent', 'pharma',
    ],
    'مؤسسة الصناعات الغذائية': [
        'غذائية', 'اغذية', 'مشروبات', 'البان', 'مخبوزات', 'حلويات', 'معلبات',
        'food', 'beverage', 'dairy',
    ],
    'المؤسسة العامة للتبغ': ['تبغ', 'دخان', 'سجائر', 'tobacco', 'cigarette'],
    'هيئة ادارة المعادن النبيلة وهيئة المواصفات و المقاييس': [
        'ذهب', 'فضة', 'معادن نبيلة', 'مجوهرات', 'مصاغ', 'مواصفات', 'مقاييس',
        'gold', 'silver', 'jewelry', 'hallmark', 'metrology',
    ],
    'مديرية المدن و المناطق الصناعية': [
        'مدينة صناعية', 'مدن صناعية', 'منطقة صناعية', 'مناطق صناعية',
        'industrial city', 'industrial zone',
    ],
    'مديرية الاشراف على التاهيل الفني': [
        'تاهيل فني', 'تدريب مهني', 'تدريب فني', 'vocational', 'technical training',
    ],
    'مركز الاختبارات و الابحاث': [
        'اختبارات', 'مختبر', 'مخبر', 'ابحاث', 'بحوث', 'laboratory', 'research',
    ],
    # Non-industrial categories (added to reduce 'غير ذلك' accurately).
    'بنوك ومصارف': ['بنك', 'مصرف', 'مصارف', 'bank'],
    'جهات حكومية': ['وزارة', 'مديرية', 'هيئة', 'حكوم', 'ministry', 'government', 'authority'],
    'بعثات دبلوماسية': ['سفارة', 'قنصلية', 'دبلوماسي', 'embassy', 'consulate'],
    'غرف تجارة': ['غرفة تجارة', 'غرف تجارة', 'chamber'],
    'منظمات وجمعيات': ['منظمة', 'جمعية', 'اتحاد', 'organization', 'nations'],
    'شركات قابضة واستثمار': ['قابضة', 'holding', 'ventures'],
    'استشارات': ['استشار', 'consult'],
}


def _norm(text: str) -> str:
    text = (text or '').lower()
    text = text.replace('ـ', '')                 # tatweel
    text = re.sub('[إأآا]', 'ا', text)           # unify alef forms
    text = text.replace('ى', 'ي').replace('ؤ', 'و').replace('ئ', 'ي').replace('ة', 'ه')
    text = re.sub('[ً-ْ]', '', text)   # strip tashkeel
    return text


_NORM_KEYWORDS = {cat: [_norm(k) for k in kws] for cat, kws in CATEGORY_KEYWORDS.items()}


def classify(text: str):
    """Return the single matching category, or None if 0 or >1 categories match."""
    norm = _norm(text)
    matched = [cat for cat, kws in _NORM_KEYWORDS.items() if any(k in norm for k in kws)]
    return matched[0] if len(matched) == 1 else None


class Command(BaseCommand):
    help = "Classify 'غير ذلك' cards into a concrete investment type (conservative)."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Preview only; write nothing.')

    def handle(self, *args, **opts):
        dry = opts.get('dry_run')
        qs = BusinessCard.objects.filter(investment_type=OTHER)
        total = qs.count()
        classified = Counter()
        unmatched = 0

        ctx = contextlib.nullcontext() if dry else transaction.atomic()
        with ctx:
            for card in qs:
                text = ' '.join(filter(None, [
                    card.company_activity, card.investment_type_other, card.company_name,
                ]))
                category = classify(text)
                if category:
                    classified[category] += 1
                    if not dry:
                        # Preserve the custom text if the activity field is empty.
                        if not (card.company_activity or '').strip() and (card.investment_type_other or '').strip():
                            card.company_activity = card.investment_type_other
                        card.investment_type = category
                        card.investment_type_other = ''
                        card.save(update_fields=[
                            'investment_type', 'investment_type_other', 'company_activity', 'updated_at',
                        ])
                else:
                    # Non-industrial / unspecified: leave as 'غير ذلك' untouched.
                    unmatched += 1

        prefix = '[dry-run] ' if dry else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}كروت «غير ذلك»: {total} — صُنِّف بثقة: {sum(classified.values())} — '
            f'بقيت «غير ذلك» (غير صناعية غالبًا): {unmatched}'
        ))
        for cat, n in classified.most_common():
            self.stdout.write(f'   {n:>4}  ->  {cat}')
