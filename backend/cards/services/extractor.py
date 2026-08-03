from __future__ import annotations

import json
import logging
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image
from django.conf import settings
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from .gemini_keys import manager as gemini_key_manager
from .normalization import clean_list, normalize_phones, normalize_website
from .translation import fill_bilingual_fields

logger = logging.getLogger(__name__)

# Bump when the prompt/schema/pipeline changes in a way that should invalidate
# cached extraction fingerprints. Part of the image fingerprint (see views).
EXTRACTION_SCHEMA_VERSION = '2'


class ExtractionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        category: str = 'gemini_external_error',
        status_code: int = 502,
        recoverable: bool = True,
        original: Exception | None = None,
    ):
        super().__init__(message)
        self.category = category
        self.status_code = status_code
        self.recoverable = recoverable
        self.original = original


class BusinessCardData(BaseModel):
    person_name: str = ''
    person_name_ar: str = ''
    person_name_en: str = ''
    job_title: str = ''
    job_title_ar: str = ''
    job_title_en: str = ''
    company_name: str = ''
    company_name_ar: str = ''
    company_name_en: str = ''
    mobile_numbers: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    website: str = ''
    address: str = ''
    company_activity: str = ''
    investment_type: str = ''
    investment_type_other: str = ''
    raw_text: str = ''
    confidence: float = 0.0
    needs_review: bool = True
    review_notes: str = ''
    review_fields: list[str] = Field(default_factory=list)
    website_visit_note: str = ''


@dataclass
class GeminiUsage:
    """Real usage metadata returned by Gemini for a single call."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    thoughts_tokens: int | None = None
    cached_tokens: int | None = None
    available: bool = False


@dataclass
class ExtractionMeta:
    """Everything the caller needs to write a GeminiUsageLog row."""

    model_name: str = ''
    usage: GeminiUsage = field(default_factory=GeminiUsage)
    request_count: int = 0
    retry_number: int = 0
    latency_ms: int = 0
    status: str = 'completed'


@dataclass
class ExtractionResult:
    data: BusinessCardData
    meta: ExtractionMeta


# The schema is enforced via response_schema (real structured output); the prompt
# only describes intent and the disambiguation rules — it is NOT the sole thing
# keeping the output valid.
SYSTEM_PROMPT = """
You extract structured contact data from business-card images. A card may be
Arabic, English, or mixed, and may be supplied as a single image (front only) or
as two images that are the FRONT and BACK of the SAME physical card.

Treat the two images as one card. Merge complementary information into a single
result. Do NOT duplicate a person or emit two records.

Rules:
- Extract identity and contact data only. Never invent contact values
  (phones, emails, website, address); leave unknown fields empty ("" or []).
- Prefer printed data over handwritten notes.
- ALWAYS provide BOTH Arabic and English for these three fields, even when the
  card shows only one language:
  person_name_ar & person_name_en, job_title_ar & job_title_en,
  company_name_ar & company_name_en.
    • Keep the printed-language version exactly as printed.
    • Fill the MISSING language yourself:
        - person_name: transliterate faithfully to the other script — do NOT
          translate the meaning. e.g. "عبد الرحمن" ⇄ "Abdalrahman", "Sara" ⇄ "سارة".
        - job_title and company_name: translate accurately to the other language
          (e.g. "مدير التسويق" ⇄ "Marketing Manager").
    • Also set the combined base fields (person_name, job_title, company_name).
- company_activity must be Arabic when clearly printed or strongly implied.
- investment_type must be one of the official Arabic values when clear; otherwise
  use "غير ذلك" and put the free value in investment_type_other.
- raw_text: only important identity/contact text, under 1200 characters. Be concise.
- When the two sides conflict, do NOT invent a value: keep the clearest one and
  add that field name to review_fields.
- Set needs_review=true and populate review_fields when a field is uncertain,
  conflicting, or likely incomplete.
"""

STRING_FIELDS = {
    'person_name', 'person_name_ar', 'person_name_en',
    'job_title', 'job_title_ar', 'job_title_en',
    'company_name', 'company_name_ar', 'company_name_en',
    'website', 'address', 'company_activity', 'investment_type',
    'investment_type_other', 'raw_text', 'review_notes', 'website_visit_note',
}
LIST_FIELDS = {'mobile_numbers', 'emails', 'review_fields'}
ALLOWED_REVIEW_FIELDS = STRING_FIELDS | {'mobile_numbers', 'emails'}
EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+', re.I)
URL_RE = re.compile(r'(?<!@)\b(?:https?://)?(?:www\.)?[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)+(?:/[^\s]*)?', re.I)
PHONE_RE = re.compile(r'(?:\+?\d[\d\s().-]{6,}\d)')

# Transient categories are retried with backoff on the SAME operation; the key
# manager separately rotates keys for rate-limit / invalid-key cases.
RETRYABLE_CATEGORIES = {
    'gemini_timeout',
    'gemini_transient',
    'extraction_parse_error',
    'gemini_external_error',
    'gemini_output_truncated',
    'gemini_empty_response',
}
# Finish reasons that mean the model refused/blocked (not worth retrying).
_BLOCKED_FINISH_REASONS = {'SAFETY', 'RECITATION', 'BLOCKLIST', 'PROHIBITED_CONTENT', 'SPII'}


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


def _open_image(path: str | Path) -> Image.Image:
    return Image.open(path).convert('RGB')


def _sanitize_extracted_payload(payload: dict) -> dict:
    sanitized = dict(payload or {})
    for field_name in STRING_FIELDS:
        value = sanitized.get(field_name)
        sanitized[field_name] = '' if value is None else str(value).strip()
    for field_name in LIST_FIELDS:
        value = sanitized.get(field_name)
        if not isinstance(value, list):
            sanitized[field_name] = []
        else:
            sanitized[field_name] = [str(item).strip() for item in value if item not in {None, ''}]

    # Only keep review_fields that name real fields (never let the model inject
    # arbitrary keys through this list).
    sanitized['review_fields'] = [f for f in sanitized['review_fields'] if f in ALLOWED_REVIEW_FIELDS]

    try:
        sanitized['confidence'] = float(sanitized.get('confidence') or 0.0)
    except (TypeError, ValueError):
        sanitized['confidence'] = 0.0

    sanitized['confidence'] = max(0.0, min(1.0, sanitized['confidence']))
    sanitized['needs_review'] = bool(sanitized.get('needs_review', True))
    sanitized['raw_text'] = sanitized['raw_text'][:2000]
    # Drop any unexpected keys so a hallucinated field never reaches the model.
    return {k: v for k, v in sanitized.items() if k in BusinessCardData.model_fields}


def _combine_bilingual(arabic: str, english: str, fallback: str = '') -> str:
    parts = [part.strip() for part in [arabic, english] if part and part.strip()]
    if parts:
        return '\n'.join(dict.fromkeys(parts))
    return (fallback or '').strip()


def _error_text(exc: Exception) -> str:
    return str(exc) or exc.__class__.__name__


def _safe_error_summary(exc: Exception) -> str:
    text = _error_text(exc)
    text = re.sub(r'AIza[0-9A-Za-z_\-]{20,}', '[REDACTED_GEMINI_KEY]', text)
    text = re.sub(r'(x-goog-api-key\s*[:=]\s*)\S+', r'\1[REDACTED]', text, flags=re.I)
    return text[:240]


def _status_code_of(exc: Exception):
    """Best-effort HTTP status code from a google-genai / requests-style error,
    so classification doesn't rely on the message text alone."""
    for attr in ('code', 'status_code', 'http_status'):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, 'response', None)
    value = getattr(response, 'status_code', None)
    return value if isinstance(value, int) else None


def _classify_exception(exc: Exception) -> tuple[str, int, str, bool]:
    if isinstance(exc, ExtractionError):
        return exc.category, exc.status_code, str(exc), exc.recoverable

    text = _error_text(exc).lower()
    status_code = _status_code_of(exc)
    status_name = str(getattr(exc, 'status', '') or '').lower()

    if 'did not return json' in text or ('json' in text and isinstance(exc, (ValueError, json.JSONDecodeError))):
        return 'extraction_parse_error', 502, 'تعذر قراءة استجابة Gemini بصيغة JSON صحيحة.', True
    if 'timeout' in text or 'deadline' in text or 'timed out' in text:
        return 'gemini_timeout', 504, 'انتهت مهلة الاتصال مع Gemini. يرجى المحاولة بصورة أصغر أو لاحقاً.', True
    # Detect a 429 by HTTP status / RESOURCE_EXHAUSTED too — not just text — so a
    # key that hit its limit reliably triggers a switch to the next key.
    _is_429 = status_code == 429 or status_name == 'resource_exhausted' or any(
        token in text for token in ('resource_exhausted', '429', 'rate limit', 'too many requests')
    )
    # Only a DAILY limit deserves the long cooldown. Google's per-minute (RPM)
    # 429s also say "quota", so require an explicit daily marker — otherwise a
    # momentary burst would wrongly lock every key for the long cooldown.
    _is_daily = any(token in text for token in (
        'per day', 'perday', 'requests per day', 'per-day', 'daily limit', 'quota per day',
    ))
    if _is_429:
        if _is_daily:
            return 'gemini_quota_exceeded', 429, 'انتهت حصة Gemini اليومية على كل المفاتيح. يرجى المحاولة لاحقاً أو إضافة مفاتيح من حسابات أخرى.', False
        return 'gemini_rate_limit', 429, 'تم الوصول إلى حد الطلبات اللحظي في Gemini. تتم إعادة المحاولة تلقائياً بعد قليل.', False
    if _is_daily:
        return 'gemini_quota_exceeded', 429, 'انتهت حصة Gemini اليومية. يرجى المحاولة لاحقاً أو إضافة مفاتيح من حسابات أخرى.', False
    if 'api_key_invalid' in text or 'api key not valid' in text or 'invalid api key' in text or 'api key is invalid' in text:
        return 'gemini_invalid_api_key', 502, 'مفتاح Gemini API غير صالح. يرجى التحقق من إعدادات الخادم.', False
    if 'unauthenticated' in text or 'permission denied' in text or 'forbidden' in text:
        return 'gemini_invalid_api_key', 502, 'مفتاح Gemini API غير مسموح له بتنفيذ الطلب.', False
    if 'user location is not supported' in text or 'location is not supported' in text or 'failed_precondition' in text:
        return 'gemini_location_not_supported', 502, 'موقع استخدام Gemini API غير مدعوم حالياً من هذه الشبكة.', False
    if any(token in text for token in ('connection reset', 'econnreset', 'socket hang up', 'broken pipe', '503', '504', '502', '500')):
        return 'gemini_transient', 502, 'تعذر الاتصال بخدمة Gemini مؤقتاً. يرجى المحاولة لاحقاً.', True
    return 'gemini_external_error', 502, 'تعذر استخراج بيانات الكرت من Gemini.', True


def _raise_key_exhausted(reason: str) -> None:
    if reason == 'missing_gemini_api_key':
        raise ExtractionError('لم يتم إعداد مفتاح Gemini API على الخادم.', category='missing_gemini_api_key', status_code=502, recoverable=False)
    if reason == 'all_gemini_keys_invalid':
        raise ExtractionError('كل مفاتيح Gemini API المتاحة غير صالحة حالياً.', category='all_gemini_keys_invalid', status_code=502, recoverable=False)
    if reason == 'all_gemini_keys_rate_limited':
        raise ExtractionError('تم الوصول إلى حد استخدام كل مفاتيح Gemini المتاحة حالياً.', category='all_gemini_keys_rate_limited', status_code=429, recoverable=False)
    raise ExtractionError('لا يوجد مفتاح Gemini متاح حالياً.', category='all_gemini_keys_exhausted', status_code=502, recoverable=True)


def _read_usage(response) -> GeminiUsage:
    """Pull real usage metadata off a Gemini response. Never raises."""
    meta = getattr(response, 'usage_metadata', None)
    if meta is None:
        return GeminiUsage()

    def _int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    input_tokens = _int(getattr(meta, 'prompt_token_count', None)) or 0
    output_tokens = _int(getattr(meta, 'candidates_token_count', None)) or 0
    total_tokens = _int(getattr(meta, 'total_token_count', None)) or (input_tokens + output_tokens)
    thoughts = _int(getattr(meta, 'thoughts_token_count', None))
    cached = _int(getattr(meta, 'cached_content_token_count', None))
    return GeminiUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        thoughts_tokens=thoughts,
        cached_tokens=cached,
        available=True,
    )


def _generation_config(max_output_tokens: int | None = None) -> types.GenerateContentConfig:
    kwargs = dict(
        system_instruction=SYSTEM_PROMPT,
        temperature=float(getattr(settings, 'GEMINI_CARD_TEMPERATURE', 0)),
        max_output_tokens=int(max_output_tokens or getattr(settings, 'GEMINI_CARD_MAX_OUTPUT_TOKENS', 2048)),
        response_mime_type='application/json',
        response_schema=BusinessCardData,
    )
    budget = int(getattr(settings, 'GEMINI_CARD_THINKING_BUDGET', 0))
    # Minimise "thinking" for this extraction task. -1 lets the model decide.
    kwargs['thinking_config'] = types.ThinkingConfig(thinking_budget=budget)
    return types.GenerateContentConfig(**kwargs)


def _finish_reason(response) -> str:
    """Best-effort finish reason name of the first candidate ('' if unknown)."""
    try:
        candidates = getattr(response, 'candidates', None) or []
        if not candidates:
            return ''
        reason = getattr(candidates[0], 'finish_reason', None)
        if reason is None:
            return ''
        return getattr(reason, 'name', str(reason)).upper()
    except Exception:
        return ''


def _parse_response(response) -> BusinessCardData:
    """Prefer the structured-output parse; fall back to text JSON only if needed.

    Distinguishes *why* a response has no usable JSON (truncated vs blocked vs
    empty) so the user gets an accurate message instead of a generic failure.
    Always re-validates through the pydantic schema so an off-schema payload is
    rejected instead of producing a corrupt card.
    """
    parsed = getattr(response, 'parsed', None)
    if isinstance(parsed, BusinessCardData):
        return BusinessCardData.model_validate(_sanitize_extracted_payload(parsed.model_dump()))
    if isinstance(parsed, dict):
        return BusinessCardData.model_validate(_sanitize_extracted_payload(parsed))

    text = getattr(response, 'text', '') or ''
    if not text.strip():
        reason = _finish_reason(response)
        if reason == 'MAX_TOKENS':
            raise ExtractionError(
                'اقتُطعت استجابة Gemini قبل اكتمالها بسبب حد المخرجات. تتم إعادة المحاولة تلقائياً.',
                category='gemini_output_truncated', status_code=502, recoverable=True)
        if reason in _BLOCKED_FINISH_REASONS:
            raise ExtractionError(
                'تعذّر استخراج الكرت لأن الصورة حُجبت من Gemini. جرّب صورة أوضح للبطاقة.',
                category='gemini_content_blocked', status_code=422, recoverable=False)
        raise ExtractionError(
            'لم تُعِد Gemini أي بيانات قابلة للقراءة لهذه الصورة.',
            category='gemini_empty_response', status_code=502, recoverable=True)

    return BusinessCardData.model_validate(_sanitize_extracted_payload(_extract_json(text)))


def _call_gemini_once(image_paths: list[str | Path], user_instruction: str, context: dict, max_output_tokens: int | None = None) -> tuple[BusinessCardData, GeminiUsage, str]:
    """Perform a single Gemini generate_content call, rotating keys on
    rate-limit / invalid-key errors. Returns (data, usage, model_name).
    """
    contents: list[object] = [user_instruction]
    contents.extend(_open_image(path) for path in image_paths)
    model_name = settings.GEMINI_CARD_MODEL
    config = _generation_config(max_output_tokens)

    last_error: ExtractionError | None = None
    while True:
        tried_indexes: set[int] = context['tried_key_indexes']
        candidate = gemini_key_manager.get_candidate(tried_indexes)
        if candidate is None:
            reason = gemini_key_manager.exhaustion_reason(tried_indexes)
            logger.warning('gemini_all_keys_exhausted reason=%s key_attempt_count=%s', reason, len(tried_indexes))
            if reason in {'missing_gemini_api_key', 'all_gemini_keys_invalid', 'all_gemini_keys_rate_limited'}:
                _raise_key_exhausted(reason)
            if last_error:
                raise last_error
            _raise_key_exhausted(reason)

        key_index, key = candidate
        tried_indexes.add(key_index)
        client = genai.Client(api_key=key)
        started = time.perf_counter()
        try:
            response = client.models.generate_content(model=model_name, contents=contents, config=config)
            context['requests_made'] = int(context.get('requests_made', 0)) + 1
            usage = _read_usage(response)
            data = _parse_response(response)
            logger.info(
                'gemini_request_success images=%d elapsed_ms=%d selected_key_index=%s requests_made=%s in_tok=%s out_tok=%s',
                len(image_paths), int((time.perf_counter() - started) * 1000), key_index,
                context['requests_made'], usage.input_tokens, usage.output_tokens,
            )
            return data, usage, model_name
        except Exception as exc:
            context['requests_made'] = int(context.get('requests_made', 0)) + 1
            category, code, message, recoverable = _classify_exception(exc)
            logger.warning(
                'gemini_request_failed selected_key_index=%s category=%s error_class=%s error=%s requests_made=%s',
                key_index, category, exc.__class__.__name__, _safe_error_summary(exc), context['requests_made'],
            )
            if category == 'gemini_invalid_api_key':
                gemini_key_manager.mark_invalid(key_index, category)
                last_error = ExtractionError(message, category=category, status_code=code, recoverable=recoverable, original=exc)
                continue
            if category in {'gemini_rate_limit', 'gemini_quota_exceeded'}:
                # Daily-quota exhaustion lasts far longer than a burst rate limit,
                # so cool that key down for much longer to stop wasting calls on
                # it and let other keys take over.
                cooldown = (
                    int(getattr(settings, 'GEMINI_KEY_QUOTA_COOLDOWN_SECONDS', 900))
                    if category == 'gemini_quota_exceeded' else None
                )
                gemini_key_manager.mark_cooldown(key_index, category, seconds=cooldown)
                last_error = ExtractionError(message, category=category, status_code=code, recoverable=recoverable, original=exc)
                continue
            raise ExtractionError(message, category=category, status_code=code, recoverable=recoverable, original=exc) from exc


def _extract_single_call(front_image, back_image, context: dict) -> ExtractionResult:
    """The ONLY Gemini path: front (and optional back) in a single request,
    with bounded exponential-backoff+jitter retry for transient failures.
    """
    images = [front_image, *([back_image] if back_image else [])]
    instruction = (
        'Extract contact information from the front and back of this ONE business card '
        'and return a single merged JSON object.'
        if back_image else
        'Extract contact information from this business card and return a single JSON object.'
    )

    max_retries = int(getattr(settings, 'GEMINI_CARD_MAX_RETRIES', 2))
    base_delay = float(getattr(settings, 'GEMINI_CARD_RETRY_BASE_DELAY', 0.75))
    token_budget = int(getattr(settings, 'GEMINI_CARD_MAX_OUTPUT_TOKENS', 2048))
    total_started = time.perf_counter()
    attempt = 0
    last_error: ExtractionError | None = None

    while attempt <= max_retries:
        # Each backoff retry starts with a fresh key-attempt set (the within-call
        # set only exists to avoid re-hitting a rate-limited key in one attempt).
        context['tried_key_indexes'] = set()
        try:
            data, usage, model_name = _call_gemini_once(images, instruction, context, max_output_tokens=token_budget)
            return ExtractionResult(
                data=data,
                meta=ExtractionMeta(
                    model_name=model_name,
                    usage=usage,
                    request_count=int(context.get('requests_made', 0)),
                    retry_number=attempt,
                    latency_ms=int((time.perf_counter() - total_started) * 1000),
                    status='completed',
                ),
            )
        except ExtractionError as exc:
            last_error = exc
            waitable = exc.category in {'all_gemini_keys_rate_limited', 'all_gemini_keys_exhausted'}
            if (exc.category not in RETRYABLE_CATEGORIES and not waitable) or attempt >= max_retries:
                raise
            if waitable:
                # Every key is momentarily rate-limited (per-minute limit). Wait
                # for the earliest key's cooldown to lapse, then retry — so a
                # transient burst self-heals instead of erroring to the user.
                remaining = gemini_key_manager.seconds_until_available()
                cap = float(getattr(settings, 'GEMINI_ALL_KEYS_WAIT_SECONDS', 30))
                delay = min(max(remaining or base_delay, 1.0), cap)
                logger.warning('gemini_all_keys_cooldown_wait attempt=%s sleep=%.1fs', attempt + 1, delay)
            else:
                # A truncated JSON won't fix itself on retry — give the next
                # attempt a bigger output budget instead of just waiting.
                if exc.category == 'gemini_output_truncated':
                    token_budget = min(token_budget * 2, 8192)
                    logger.warning('gemini_output_truncated bumping max_output_tokens=%s', token_budget)
                delay = base_delay * (2 ** attempt) + random.uniform(0, base_delay)
                logger.warning('gemini_retry attempt=%s category=%s sleep=%.2fs', attempt + 1, exc.category, delay)
            time.sleep(delay)
            attempt += 1

    raise last_error or ExtractionError('تعذر استخراج بيانات الكرت من Gemini.')


# ── QR local decoding (no Gemini call) ────────────────────────────────────
def _decode_qr_images(image_paths: list[str | Path]) -> list[str]:
    try:
        import cv2
    except Exception:
        return []

    decoded: list[str] = []
    detector = cv2.QRCodeDetector()
    for path in image_paths:
        image = cv2.imread(str(path))
        if image is None:
            continue
        try:
            ok, values, _, _ = detector.detectAndDecodeMulti(image)
            if ok:
                decoded.extend(value.strip() for value in values if value and value.strip())
                continue
            value, _, _ = detector.detectAndDecode(image)
            if value and value.strip():
                decoded.append(value.strip())
        except Exception:
            logger.info('qr_decode_failed path=%s', path)
            continue
    return clean_list(decoded)


def _parse_vcard(text: str) -> dict:
    data: dict[str, object] = {'mobile_numbers': [], 'emails': []}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        upper = line.upper()
        value = line.split(':', 1)[1].strip() if ':' in line else ''
        if upper.startswith('FN:') or upper.startswith('N:'):
            data.setdefault('person_name', value.replace(';', ' ').strip())
        elif upper.startswith('ORG:'):
            data.setdefault('company_name', value)
        elif upper.startswith('TITLE:'):
            data.setdefault('job_title', value)
        elif upper.startswith('TEL'):
            data['mobile_numbers'].append(value)
        elif upper.startswith('EMAIL'):
            data['emails'].append(value)
        elif upper.startswith('URL:'):
            data.setdefault('website', value)
        elif upper.startswith('ADR:'):
            data.setdefault('address', value.replace(';', ' ').strip())
    return data


def _qr_payloads_to_data(payloads: list[str]) -> BusinessCardData:
    collected: dict[str, object] = {'mobile_numbers': [], 'emails': [], 'raw_text': ''}
    raw_text_parts = []
    for payload in payloads:
        raw_text_parts.append(f'QR: {payload}')
        if 'BEGIN:VCARD' in payload.upper():
            parsed = _parse_vcard(payload)
        else:
            parsed = {
                'emails': EMAIL_RE.findall(payload),
                'mobile_numbers': PHONE_RE.findall(payload),
            }
            urls = [url for url in URL_RE.findall(payload) if '@' not in url]
            if urls:
                parsed['website'] = urls[0]
        for field_name in ('person_name', 'job_title', 'company_name', 'website', 'address'):
            if parsed.get(field_name) and not collected.get(field_name):
                collected[field_name] = parsed[field_name]
        collected['emails'].extend(parsed.get('emails', []))
        collected['mobile_numbers'].extend(parsed.get('mobile_numbers', []))

    collected['emails'] = clean_list(collected['emails'])
    collected['mobile_numbers'] = normalize_phones(collected['mobile_numbers'])
    collected['raw_text'] = '\n'.join(raw_text_parts)[:2000]
    return BusinessCardData.model_validate(_sanitize_extracted_payload(collected))


def _merge_qr(parsed: BusinessCardData, qr_data: BusinessCardData) -> BusinessCardData:
    if not qr_data.raw_text:
        return parsed
    for field_name in ('person_name', 'job_title', 'company_name', 'website', 'address'):
        if not getattr(parsed, field_name) and getattr(qr_data, field_name):
            setattr(parsed, field_name, getattr(qr_data, field_name))
    parsed.mobile_numbers = clean_list([*parsed.mobile_numbers, *qr_data.mobile_numbers])
    parsed.emails = clean_list([*parsed.emails, *qr_data.emails])
    parsed.raw_text = '\n'.join(part for part in [parsed.raw_text, qr_data.raw_text] if part)[:2000]
    parsed.review_notes = ' | '.join(part for part in [parsed.review_notes, 'تمت قراءة QR محلياً'] if part)
    return parsed


def _postprocess(parsed: BusinessCardData) -> BusinessCardData:
    parsed.mobile_numbers = normalize_phones([*parsed.mobile_numbers, *PHONE_RE.findall(parsed.raw_text or '')])
    parsed.emails = clean_list([*parsed.emails, *EMAIL_RE.findall(parsed.raw_text or '')])
    if not parsed.website:
        urls = [url for url in URL_RE.findall(parsed.raw_text or '') if '@' not in url]
        if urls:
            parsed.website = urls[0]
    parsed.website = normalize_website(parsed.website)
    parsed.raw_text = re.sub(r'\n{3,}', '\n\n', parsed.raw_text or '').strip()[:2000]
    return parsed


def _finalize(parsed: BusinessCardData) -> BusinessCardData:
    """Deterministic, local finalisation only.

    Website enrichment is now a separate, opt-in step (see services/enrichment.py
    and the /cards/{id}/enrich endpoints) and never runs during extraction.
    """
    bilingual = fill_bilingual_fields({
        'person_name_ar': parsed.person_name_ar,
        'person_name_en': parsed.person_name_en,
        'job_title_ar': parsed.job_title_ar,
        'job_title_en': parsed.job_title_en,
        'company_name_ar': parsed.company_name_ar,
        'company_name_en': parsed.company_name_en,
    })
    for field_name, value in bilingual.items():
        setattr(parsed, field_name, value)

    parsed.person_name = _combine_bilingual(parsed.person_name_ar, parsed.person_name_en, parsed.person_name)
    parsed.job_title = _combine_bilingual(parsed.job_title_ar, parsed.job_title_en, parsed.job_title)
    parsed.company_name = _combine_bilingual(parsed.company_name_ar, parsed.company_name_en, parsed.company_name)

    if not parsed.person_name or not parsed.company_name or not parsed.mobile_numbers:
        parsed.needs_review = True
    elif parsed.confidence >= 0.75 and not parsed.review_notes and not parsed.review_fields:
        parsed.needs_review = False

    return parsed


def extract_business_card(front_image: str | Path, back_image: str | Path | None = None) -> ExtractionResult:
    """Extract a business card in a SINGLE Gemini request.

    Front is sufficient; back is optional and, when present, is sent together
    with the front in the same request (never a separate call, never a third
    merge call). Returns the parsed data plus usage/cost metadata.
    """
    if not gemini_key_manager.has_keys():
        raise ExtractionError('لم يتم إعداد مفتاح Gemini API على الخادم.', category='missing_gemini_api_key', status_code=502, recoverable=False)

    started = time.perf_counter()
    context = {'requests_made': 0, 'tried_key_indexes': set()}
    result = _extract_single_call(front_image, back_image, context)

    qr_payloads = _decode_qr_images([front_image, *([back_image] if back_image else [])])
    parsed = result.data
    if qr_payloads:
        parsed = _merge_qr(parsed, _qr_payloads_to_data(qr_payloads))
    parsed = _finalize(_postprocess(parsed))
    result.data = parsed

    logger.info(
        'business_card_extracted elapsed_ms=%d qr_count=%d gemini_requests=%d retries=%d needs_review=%s confidence=%.2f',
        int((time.perf_counter() - started) * 1000), len(qr_payloads),
        result.meta.request_count, result.meta.retry_number, parsed.needs_review, parsed.confidence,
    )
    return result
