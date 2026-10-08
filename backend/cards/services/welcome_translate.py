"""Fallback translation of a welcome letter into a language we have no reviewed
template for.

This is deliberately the LAST resort. Reviewed letters for the common languages
live in ``accounts/welcome_templates.py`` and never reach this module; a card in
one of those languages costs nothing to send. This path only runs when:
  * the card's language has no reviewed template (e.g. Japanese), or
  * the account owner rewrote the letter themselves, so no template applies.

Every result is cached in ``WelcomeTranslation`` keyed by (language,
source_hash), so a given letter is translated at most once per language — ever.
Any failure returns ``None`` and the caller falls back to the letter it already
has (never an empty message).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re

from django.conf import settings
from django.db import DatabaseError

from accounts.welcome_templates import SALUTATION_TOKEN
from ..models import WelcomeTranslation
from .gemini_keys import manager as gemini_key_manager

logger = logging.getLogger(__name__)

# Language names for the prompt, so the model is never guessing from a code.
LANGUAGE_NAMES = {
    'ar': 'Arabic', 'en': 'English', 'fr': 'French', 'de': 'German',
    'tr': 'Turkish', 'ru': 'Russian', 'es': 'Spanish', 'zh': 'Chinese',
    'it': 'Italian', 'pt': 'Portuguese', 'nl': 'Dutch', 'ja': 'Japanese',
    'ko': 'Korean', 'hi': 'Hindi', 'ur': 'Urdu', 'fa': 'Persian',
    'he': 'Hebrew', 'el': 'Greek', 'pl': 'Polish', 'sv': 'Swedish',
    'uk': 'Ukrainian', 'ro': 'Romanian', 'hu': 'Hungarian', 'cs': 'Czech',
    'id': 'Indonesian', 'ms': 'Malay', 'th': 'Thai', 'vi': 'Vietnamese',
    'az': 'Azerbaijani', 'hy': 'Armenian', 'ka': 'Georgian', 'ku': 'Kurdish',
}

PROMPT = """You are a translator for a government ministry's official
correspondence. Translate the following formal letter of appreciation into
{language}.

Requirements:
- Preserve the formal, diplomatic register of official state correspondence.
  This letter is signed by the Ministry; it must not read casually.
- Preserve the paragraph structure and the closing signature block exactly.
- Translate the subject line too.
- Do NOT add, remove, or explain anything. Output the translation only.

Return JSON with exactly two string keys: "subject" and "body".

SUBJECT:
{subject}

BODY:
{body}
"""


def source_hash(subject: str, body: str) -> str:
    """Stable fingerprint of the source letter, so editing the source produces a
    new cache row instead of serving a stale translation."""
    payload = f'{(subject or "").strip()}\x00{(body or "").strip()}'
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def language_name(code: str) -> str:
    code = (code or '').lower()
    return LANGUAGE_NAMES.get(code, code.upper())


def _cached(language: str, digest: str) -> tuple[str, str] | None:
    try:
        row = WelcomeTranslation.objects.filter(language=language, source_hash=digest).first()
    except DatabaseError:
        logger.warning('welcome_translation_cache_read_failed language=%s', language)
        return None
    if row and row.body.strip():
        return row.subject, row.body
    return None


def _store(language: str, digest: str, subject: str, body: str) -> None:
    try:
        WelcomeTranslation.objects.update_or_create(
            language=language, source_hash=digest,
            defaults={'subject': subject[:255], 'body': body},
        )
    except DatabaseError:
        # A cache write failure must never break sending; we just pay for the
        # translation again next time.
        logger.warning('welcome_translation_cache_write_failed language=%s', language)


def _extract_json(text: str) -> dict:
    cleaned = (text or '').strip()
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.I)
    cleaned = re.sub(r'\s*```$', '', cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', cleaned, flags=re.S)
        if not match:
            raise ValueError('Gemini did not return JSON')
        return json.loads(match.group(0))


def call_gemini_json(prompt: str) -> dict:
    """One text-only Gemini call with the platform's key rotation. Raises on
    failure after every usable key has been tried."""
    from google import genai
    from google.genai import types

    model_name = getattr(settings, 'GEMINI_MODEL', '') or 'gemini-2.5-flash'
    config = types.GenerateContentConfig(
        temperature=0,
        response_mime_type='application/json',
        max_output_tokens=int(getattr(settings, 'GEMINI_WELCOME_MAX_OUTPUT_TOKENS', 4096)),
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    tried: set[int] = set()
    last_error: Exception | None = None
    while True:
        candidate = gemini_key_manager.get_candidate(tried)
        if candidate is None:
            raise last_error or RuntimeError(gemini_key_manager.exhaustion_reason(tried))
        key_index, key = candidate
        tried.add(key_index)
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(model=model_name, contents=[prompt], config=config)
            return _extract_json(getattr(response, 'text', '') or '')
        except Exception as exc:  # noqa: BLE001 — classified below, then rotated
            last_error = exc
            text = str(exc).lower()
            if 'api key' in text or 'unauthenticated' in text or 'permission denied' in text:
                gemini_key_manager.mark_invalid(key_index)
            elif '429' in text or 'resource_exhausted' in text or 'rate limit' in text:
                gemini_key_manager.mark_cooldown(key_index)
            else:
                # Not a key problem — retrying other keys would not help.
                raise


def translate_letter(subject: str, body: str, language: str) -> tuple[str, str] | None:
    """Return ``(subject, body)`` translated into ``language``, or None if the
    translation is unavailable. Cached permanently on success.

    The salutation token is stripped before translating and restored afterwards,
    so the per-card salutation placeholder always survives intact.
    """
    language = (language or '').lower()
    if not language or not (body or '').strip():
        return None

    digest = source_hash(subject, body)
    cached = _cached(language, digest)
    if cached:
        logger.info('welcome_translation_cache_hit language=%s', language)
        return cached

    if not gemini_key_manager.has_keys():
        logger.info('welcome_translation_skipped reason=no_gemini_keys language=%s', language)
        return None

    # Keep the placeholder out of the model's reach entirely.
    source_body = body
    has_token = SALUTATION_TOKEN in source_body
    if has_token:
        source_body = source_body.replace(SALUTATION_TOKEN, '').lstrip('\n')

    prompt = PROMPT.format(
        language=language_name(language),
        subject=(subject or '').strip(),
        body=source_body.strip(),
    )
    try:
        payload = call_gemini_json(prompt)
    except Exception as exc:  # noqa: BLE001 — a failed translation is not fatal
        logger.warning(
            'welcome_translation_failed language=%s error=%s',
            language, re.sub(r'\s+', ' ', str(exc))[:200],
        )
        return None

    translated_subject = str(payload.get('subject') or '').strip()[:255]
    translated_body = str(payload.get('body') or '').strip()
    if not translated_body:
        logger.warning('welcome_translation_empty language=%s', language)
        return None

    if has_token:
        translated_body = f'{SALUTATION_TOKEN}\n\n{translated_body}'

    _store(language, digest, translated_subject, translated_body)
    logger.info('welcome_translation_created language=%s', language)
    return translated_subject, translated_body
