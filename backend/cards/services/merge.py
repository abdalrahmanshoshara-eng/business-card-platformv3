"""Merge duplicate business cards without losing any data.

Duplicates are cards that share the same *base* duplicate_hash (the part before
the ':' salt that was appended when a genuine duplicate contact was kept as a
separate row). Cards are grouped per owner by that base hash.

Merging keeps the lowest-sequence card as primary and folds the others in:
- list fields (emails, mobile_numbers) are unioned (no loss),
- blank scalar/text fields are filled from the duplicate,
- conflicting non-empty values are appended to review_notes (never dropped),
- images are kept: the primary takes a duplicate's image only if it has none,
  and the underlying files are never deleted (only the duplicate row is).
"""
from __future__ import annotations

from collections import defaultdict

LIST_FIELDS = ['emails', 'mobile_numbers']
TEXT_FIELDS = [
    'person_name', 'person_name_ar', 'person_name_en',
    'job_title', 'job_title_ar', 'job_title_en',
    'company_name', 'company_name_ar', 'company_name_en',
    'website', 'address', 'country', 'company_activity',
    'investment_type', 'investment_type_other', 'website_visit_note', 'raw_text',
]


def _base_hash(card) -> str:
    return (card.duplicate_hash or '').split(':', 1)[0]


def _live_base_hash(card) -> str:
    """Recompute the base hash from the card's *current* data (ignores the
    stored hash). Cards with no identifying data stay ungrouped (return '')."""
    from .normalization import build_duplicate_hash

    emails = list(getattr(card, 'emails', None) or [])
    phones = list(getattr(card, 'mobile_numbers', None) or [])
    website = (getattr(card, 'website', '') or '').strip()
    person = (getattr(card, 'person_name', '') or getattr(card, 'person_name_ar', '')
              or getattr(card, 'person_name_en', '') or '').strip()
    company = (getattr(card, 'company_name', '') or getattr(card, 'company_name_ar', '')
               or getattr(card, 'company_name_en', '') or '').strip()
    if not (emails or phones or website or person or company):
        return ''
    return build_duplicate_hash({
        'emails': emails,
        'mobile_numbers': phones,
        'website': website,
        'person_name': getattr(card, 'person_name', '') or '',
        'person_name_ar': getattr(card, 'person_name_ar', '') or '',
        'person_name_en': getattr(card, 'person_name_en', '') or '',
        'company_name': getattr(card, 'company_name', '') or '',
        'company_name_ar': getattr(card, 'company_name_ar', '') or '',
        'company_name_en': getattr(card, 'company_name_en', '') or '',
    })


def merge_two(primary, dup) -> None:
    """Fold ``dup`` into ``primary`` (data-preserving), then delete ``dup``'s row."""
    for field in LIST_FIELDS:
        pv = list(getattr(primary, field) or [])
        dv = list(getattr(dup, field) or [])
        setattr(primary, field, list(dict.fromkeys([*pv, *dv])))

    conflicts = []
    for field in TEXT_FIELDS:
        pv = (getattr(primary, field, '') or '').strip()
        dv = (getattr(dup, field, '') or '').strip()
        if not pv and dv:
            setattr(primary, field, dv)
        elif pv and dv and pv != dv:
            conflicts.append(f'{field}={dv}')

    try:
        primary.confidence = max(primary.confidence or 0, dup.confidence or 0)
    except Exception:
        pass

    # Keep images: only borrow the duplicate's image if the primary lacks one.
    if not primary.front_image and dup.front_image:
        primary.front_image = dup.front_image.name
    if not primary.back_image and dup.back_image:
        primary.back_image = dup.back_image.name

    if conflicts:
        note = (primary.review_notes or '').strip()
        addition = f'[دمج من كرت #{dup.sequence_number}] ' + ' | '.join(conflicts)
        primary.review_notes = (note + ('\n' if note else '') + addition)[:5000]

    primary.save()
    dup.delete()  # deletes the row only; image files on disk are preserved


def merge_duplicate_cards(queryset, *, apply: bool = True, rehash: bool = False) -> dict:
    """Group ``queryset`` by (owner, base hash) and merge each duplicate group.

    Returns counts. With apply=False nothing is written (dry-run preview).
    """
    groups: dict[tuple, list] = defaultdict(list)
    for card in queryset.order_by('sequence_number', 'id'):
        base = _live_base_hash(card) if rehash else _base_hash(card)
        key = (card.owner_id, base) if base else (card.owner_id, f'__id{card.id}')
        groups[key].append(card)

    duplicate_groups = 0
    removed = 0
    for cards in groups.values():
        if len(cards) < 2:
            continue
        duplicate_groups += 1
        primary = cards[0]
        for dup in cards[1:]:
            removed += 1
            if apply:
                merge_two(primary, dup)

    return {'duplicate_groups': duplicate_groups, 'cards_removed': removed}


def resequence_cards(queryset) -> int:
    """Renumber sequence_number to a gap-free 1..N (oldest → 1), preserving order.

    Two passes with a temporary offset avoid unique-constraint collisions during
    the update.
    """
    cards = list(queryset.order_by('created_at', 'id'))
    if not cards:
        return 0
    model = type(cards[0])
    offset = 100_000_000
    for i, card in enumerate(cards):
        card.sequence_number = offset + i
    model.objects.bulk_update(cards, ['sequence_number'], batch_size=200)
    for i, card in enumerate(cards, start=1):
        card.sequence_number = i
    model.objects.bulk_update(cards, ['sequence_number'], batch_size=200)
    return len(cards)
