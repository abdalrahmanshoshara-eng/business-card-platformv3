"""Duplicate detection by weighted similarity across ALL of a card's information.

Each field is compared on its own (0..1), then combined into a percentage:

- text fields (name, company, job title, website, address) — fuzzy ratio after
  normalisation, so one OCR slip lowers the score a little instead of to zero;
- emails / phone numbers — share of entries the two cards have in common
  (phones compared on their last 9 digits, ignoring the country prefix);
- a field empty on BOTH cards is skipped; empty on one side only counts as 0.

Outcome by score:
- >= DUPLICATE_THRESHOLD  → duplicate (manual: 409; upload: reuse the existing card),
- >= POSSIBLE_THRESHOLD   → possible duplicate (manual: 409 for the user to decide;
                            upload: saved but flagged for review),
- below                   → a distinct card.

Guard: when both cards name a person and those names are less than
NAME_GUARD similar, the cards are never duplicates — colleagues often share a
company email (info@) or a switchboard number.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from django.db.models import Q

from ..models import BusinessCard
from .normalization import build_duplicate_hash, has_card_identity, normalize_text

DUPLICATE_THRESHOLD = 95
POSSIBLE_THRESHOLD = 75
NAME_GUARD = 0.70

# (key, Arabic label, weight)
FIELDS = (
    ('person', 'الاسم', 25),
    ('emails', 'الإيميل', 20),
    ('phones', 'الرقم', 20),
    ('company', 'الشركة', 15),
    ('job_title', 'المسمى', 8),
    ('website', 'الموقع', 7),
    ('address', 'العنوان', 5),
)
_MULTILINGUAL = {'person': 'person_name', 'company': 'company_name', 'job_title': 'job_title'}

# Upper bound of cards scored in Python per lookup (after the DB pre-filter).
_CANDIDATE_LIMIT = 300


@dataclass
class DuplicateMatch:
    card: BusinessCard
    score: int
    differing: list[str] = field(default_factory=list)

    @property
    def is_duplicate(self) -> bool:
        return self.score >= DUPLICATE_THRESHOLD

    @property
    def reason(self) -> str:
        if not self.differing:
            return 'تطابق كامل لجميع بيانات الكرت'
        return f'تشابه بنسبة {self.score}% — اختلاف: {"، ".join(self.differing)}'


def _value(data, name: str):
    if isinstance(data, dict):
        return data.get(name)
    return getattr(data, name, None)


def _texts(data, key: str) -> list[str]:
    """Normalised, non-empty variants of a field (all languages for names)."""
    if key in _MULTILINGUAL:
        base = _MULTILINGUAL[key]
        names = (base, f'{base}_ar', f'{base}_en')
    else:
        names = (key,)
    seen = []
    for name in names:
        text = normalize_text(_value(data, name))
        if text and text not in seen:
            seen.append(text)
    return seen


def _text_similarity(a: list[str], b: list[str]) -> float:
    # Best pairing across language variants (an Arabic-only card vs a bilingual one).
    return max(SequenceMatcher(None, x, y).ratio() for x in a for y in b)


def _emails(data) -> set[str]:
    return {normalize_text(str(x)) for x in _value(data, 'emails') or [] if x} - {''}


def _phones(data) -> set[str]:
    return {re.sub(r'\D+', '', str(x))[-9:] for x in _value(data, 'mobile_numbers') or [] if x} - {''}


def _set_similarity(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b)


def _field_values(data, key: str):
    if key == 'emails':
        return _emails(data)
    if key == 'phones':
        return _phones(data)
    return _texts(data, key)


def score_duplicate(data, existing: BusinessCard) -> DuplicateMatch:
    total_weight = 0
    earned = 0.0
    differing: list[str] = []
    for key, label, weight in FIELDS:
        new, old = _field_values(data, key), _field_values(existing, key)
        if not new and not old:
            continue
        total_weight += weight
        if not new or not old:
            similarity = 0.0
        elif key in ('emails', 'phones'):
            similarity = _set_similarity(new, old)
        else:
            similarity = _text_similarity(new, old)
        if key == 'person' and new and old and similarity < NAME_GUARD:
            return DuplicateMatch(existing, 0, [label])
        earned += weight * similarity
        if similarity < 1:
            differing.append(label)
    if not total_weight:
        return DuplicateMatch(existing, 0)
    score = round(earned / total_weight * 100)
    # Rounding must never report 100% for cards that differ somewhere.
    if differing and score == 100:
        score = 99
    return DuplicateMatch(existing, score, differing)


def _hash_lookup(duplicate_hash: str) -> Q:
    # A confirmed duplicate kept as its own row carries "<hash>:<salt>".
    return Q(duplicate_hash=duplicate_hash) | Q(duplicate_hash__startswith=f'{duplicate_hash}:')


def _tokens(value: str | None) -> list[str]:
    return [t for t in re.split(r'[\s,،\-/|]+', (value or '').strip()) if len(t) >= 3]


def _candidate_lookup(data: dict) -> Q:
    """Broad DB pre-filter: any card sharing a word of the name/company, an
    email, the website domain or the exact hash. Scoring decides the rest."""
    duplicate_hash = data.get('duplicate_hash') or build_duplicate_hash(data)
    query = _hash_lookup(duplicate_hash.split(':', 1)[0])
    for email in data.get('emails') or []:
        if email:
            query |= Q(emails__icontains=str(email).strip().lower())
    domain = re.sub(r'^https?://', '', str(data.get('website') or ''), flags=re.I)
    domain = re.sub(r'^www\.', '', domain).split('/')[0].strip().lower()
    if domain:
        query |= Q(website__icontains=domain)
    for prefix in ('person_name', 'company_name'):
        for name in (prefix, f'{prefix}_ar', f'{prefix}_en'):
            for token in _tokens(data.get(name)):
                query |= (Q(**{f'{prefix}__icontains': token}) | Q(**{f'{prefix}_ar__icontains': token})
                          | Q(**{f'{prefix}_en__icontains': token}))
    return query


def find_matches(data: dict, queryset, *, min_score: int = POSSIBLE_THRESHOLD) -> list[DuplicateMatch]:
    """Cards in ``queryset`` scoring at least ``min_score``, best first.

    ``queryset`` is the ownership-scoped base queryset, so a regular user only
    ever matches against their own cards and never learns about a duplicate
    owned by someone else.
    """
    if not has_card_identity(data):
        return []
    cards = queryset.filter(_candidate_lookup(data)).distinct().order_by('-sequence_number')[:_CANDIDATE_LIMIT]
    matches = [m for m in (score_duplicate(data, card) for card in cards) if m.score >= min_score]
    # Highest score first; among equals, the oldest card is the original.
    matches.sort(key=lambda m: (-m.score, m.card.sequence_number))
    return matches


def candidate_payload(match: DuplicateMatch) -> dict:
    card = match.card
    return {
        'id': card.id,
        'sequence_number': card.sequence_number,
        'person_name': card.person_name,
        'company_name': card.company_name,
        'mobile_numbers': card.mobile_numbers or [],
        'emails': card.emails or [],
        'website': card.website,
        'reason': match.reason,
        'score': match.score,
        'differing_fields': match.differing,
        'is_duplicate': match.is_duplicate,
    }


def find_duplicate_candidates(data: dict, queryset, *, limit: int = 5) -> list[dict]:
    """Duplicates and possible duplicates (score >= POSSIBLE_THRESHOLD)."""
    return [candidate_payload(m) for m in find_matches(data, queryset)[:limit]]


def find_existing_duplicate(data: dict, queryset) -> DuplicateMatch | None:
    """The best match scoring >= DUPLICATE_THRESHOLD, if any."""
    matches = find_matches(data, queryset, min_score=DUPLICATE_THRESHOLD)
    return matches[0] if matches else None


def find_possible_duplicate(data: dict, queryset) -> DuplicateMatch | None:
    """The best match between POSSIBLE_THRESHOLD and DUPLICATE_THRESHOLD."""
    matches = [m for m in find_matches(data, queryset) if not m.is_duplicate]
    return matches[0] if matches else None


def salt_duplicate_hash(data: dict) -> dict:
    copy = dict(data)
    base = copy.get('duplicate_hash') or uuid.uuid4().hex
    copy['duplicate_hash'] = f'{base[:64]}:{uuid.uuid4().hex}'[:128]
    return copy
