"""Builds the welcome email for one card: which languages to write it in, how to
address the recipient, and which letter text to use for each language.

Language rule — Arabic is the ministry's primary language and always appears;
the card's own language appears beside it when the card is not Arabic:
    card printed in Arabic          → Arabic only
    card printed in English         → Arabic + English
    card printed in German          → Arabic + German
    card printed in Arabic + English → Arabic + English
Both blocks travel in a SINGLE email, Arabic first.

Letter text per language, in order of preference:
    1. the letter the account owner wrote in their profile (Arabic field for the
       Arabic block, secondary field for the other block),
    2. the reviewed template for that language (accounts/welcome_templates.py),
    3. a cached machine translation (services/welcome_translate.py),
    4. the English text as-is — never an empty message.
"""

from __future__ import annotations

import logging
import re

from accounts.services_email import WelcomeSection
from accounts.welcome_templates import (
    SALUTATION_TOKEN,
    default_letter,
    default_salutation,
    is_rtl,
)

logger = logging.getLogger(__name__)

PRIMARY_LANGUAGE = 'ar'
SECONDARY_FALLBACK_LANGUAGE = 'en'

_ARABIC_RE = re.compile(r'[؀-ۿݐ-ݿ]')
_LATIN_RE = re.compile(r'[A-Za-z]')


# ── Language detection ────────────────────────────────────────────────────────

def _detect_from_text(card) -> list[str]:
    """Fallback for cards extracted before ``printed_languages`` existed: judge
    by the scripts present in the card's own text."""
    sample = ' '.join(str(value or '') for value in (
        card.person_name, card.job_title, card.company_name, card.address, card.raw_text,
    ))
    languages = []
    if _ARABIC_RE.search(sample):
        languages.append('ar')
    if _LATIN_RE.search(sample):
        languages.append('en')
    return languages or ['ar']


def card_languages(card) -> list[str]:
    """The languages this card's welcome email should be written in: Arabic
    first, then the card's own language when it is not Arabic.

    At most two blocks — a card printed in three languages still gets Arabic
    plus its most prominent other language, because a three-block letter reads
    as a form, not as correspondence.
    """
    printed = [str(code).strip().lower() for code in (getattr(card, 'printed_languages', None) or [])]
    printed = [code for code in printed if code]
    if not printed:
        printed = _detect_from_text(card)

    secondary = next((code for code in printed if code != PRIMARY_LANGUAGE), '')
    if not secondary and PRIMARY_LANGUAGE not in printed:
        # Card language is unknown-but-not-Arabic; address it in English.
        secondary = SECONDARY_FALLBACK_LANGUAGE
    return [PRIMARY_LANGUAGE, secondary] if secondary else [PRIMARY_LANGUAGE]


# ── Salutation ────────────────────────────────────────────────────────────────

def _rule_based_salutation(card, language: str) -> str:
    """Salutation for cards extracted before the model generated one.

    Prefers addressing the organisation, which is both dignified and free of the
    gender guess a personal honorific would force on us. ``manage.py
    backfill_card_salutations`` upgrades legacy cards to model-written
    salutations.
    """
    arabic = language == PRIMARY_LANGUAGE

    def pick(per_language: str, combined: str) -> str:
        """The name in this language. The combined base field holds
        "عربي\nEnglish", so fall back to its first line for Arabic and its last
        line for anything else."""
        if (per_language or '').strip():
            return per_language.strip()
        lines = [line.strip() for line in (combined or '').splitlines() if line.strip()]
        if not lines:
            return ''
        return lines[0] if arabic else lines[-1]

    company = pick(card.company_name_ar if arabic else card.company_name_en, card.company_name)
    person = pick(card.person_name_ar if arabic else card.person_name_en, card.person_name)

    if arabic:
        if company:
            return f'السادة في {company} الكرام،'
        if person:
            return f'حضرة {person} المحترم،'
    else:
        if person:
            return f'Dear {person},'
        if company:
            return f'Dear {company},'
    return default_salutation(language)


def build_salutation(card, language: str) -> str:
    """The line that opens the letter for ``language``."""
    if language == PRIMARY_LANGUAGE:
        generated = (card.salutation_ar or '').strip()
    elif language == 'en':
        generated = (card.salutation_en or '').strip()
    else:
        generated = (card.salutation_native or '').strip() or (card.salutation_en or '').strip()
    return generated or _rule_based_salutation(card, language)


def apply_salutation(body: str, salutation: str) -> str:
    """Replace the salutation placeholder. A letter the account owner rewrote
    without the token is sent exactly as they wrote it."""
    if SALUTATION_TOKEN not in body:
        return body
    return body.replace(SALUTATION_TOKEN, salutation)


# ── Letter text ───────────────────────────────────────────────────────────────

def _profile_letter(profile, language: str) -> tuple[str, str]:
    """The account owner's own letter for this language, or ('', '') when they
    left it at the default."""
    if profile is None:
        return '', ''
    if language == PRIMARY_LANGUAGE:
        return (profile.welcome_subject or '').strip(), (profile.welcome_message or '').strip()
    return (
        (getattr(profile, 'welcome_subject_en', '') or '').strip(),
        (getattr(profile, 'welcome_message_en', '') or '').strip(),
    )


def resolve_letter(profile, language: str) -> tuple[str, str]:
    """(subject, body) for one language, before the salutation is filled in."""
    subject, body = _profile_letter(profile, language)
    if body:
        if language in {PRIMARY_LANGUAGE, 'en'}:
            return subject, body
        # Custom text for a card language we can't assume the owner wrote in:
        # translate once (cached), and keep their original if that fails.
        from .welcome_translate import translate_letter
        translated = translate_letter(subject, body, language)
        return translated if translated else (subject, body)

    template = default_letter(language)
    if template:
        return template

    # No reviewed template for this language — translate the English one once.
    english_subject, english_body = default_letter(SECONDARY_FALLBACK_LANGUAGE)
    from .welcome_translate import translate_letter
    translated = translate_letter(english_subject, english_body, language)
    if translated:
        return translated
    logger.info('welcome_letter_fallback_english language=%s', language)
    return english_subject, english_body


def build_welcome_sections(card, profile) -> list[WelcomeSection]:
    """The full message for ``card``: one block per language, Arabic first."""
    sections = []
    for language in card_languages(card):
        subject, body = resolve_letter(profile, language)
        body = apply_salutation(body, build_salutation(card, language))
        if not body.strip():
            continue
        sections.append(WelcomeSection(
            subject=subject,
            body=body,
            language=language,
            rtl=is_rtl(language),
        ))
    return sections
