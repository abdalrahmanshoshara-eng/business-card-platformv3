"""Opt-in company website enrichment, cached by canonical domain.

This is intentionally decoupled from card extraction:
- Extraction never triggers it (no automatic Gemini/website calls).
- Results are cached per registered domain (see services/domains.py) and reused
  across cards/owners, so one company site is analysed once.
- A DB-level lock (status=processing + locked_at) prevents two concurrent
  enrichments of the same domain.
- Website fetching reuses the SSRF-safe fetcher in website_enrichment.py.
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from ..models import CompanyDomainEnrichment, GeminiUsageLog
from .domains import canonical_domain
from .extractor import GeminiUsage, _read_usage, _safe_error_summary
from .gemini_keys import manager as gemini_key_manager
from .usage import log_gemini_usage
from .website_enrichment import fetch_website_text

logger = logging.getLogger(__name__)

ENRICHMENT_SCHEMA_VERSION = '1'
# A lock older than this is considered stale (a crashed worker) and reclaimable.
LOCK_STALE_SECONDS = 180


class CompanyEnrichmentData(BaseModel):
    company_name: str = ''
    company_description: str = ''
    industry: str = ''
    services: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    language: str = ''


ENRICH_PROMPT = """
You summarise a company from the text of its own website. Use ONLY the provided
text. Never invent facts. Leave a field empty when the text does not support it.
- company_description: 1–3 concise sentences (Arabic if the site is Arabic).
- industry: short label.
- services / products: short items actually mentioned.
- countries: countries/locations the company operates in, if stated.
- language: primary language of the site ("ar", "en", ...).
"""


def _refresh_deadline() -> timezone.datetime:
    days = int(getattr(settings, 'WEBSITE_ENRICHMENT_TTL_DAYS', 90))
    return timezone.now() + timedelta(days=days)


def _enrichment_config() -> types.GenerateContentConfig:
    budget = int(getattr(settings, 'GEMINI_CARD_THINKING_BUDGET', 0))
    return types.GenerateContentConfig(
        system_instruction=ENRICH_PROMPT,
        temperature=float(getattr(settings, 'GEMINI_CARD_TEMPERATURE', 0)),
        max_output_tokens=int(getattr(settings, 'GEMINI_CARD_MAX_OUTPUT_TOKENS', 1024)),
        response_mime_type='application/json',
        response_schema=CompanyEnrichmentData,
        thinking_config=types.ThinkingConfig(thinking_budget=budget),
    )


def _call_gemini_enrichment(page_text: str) -> tuple[CompanyEnrichmentData, GeminiUsage, str]:
    model_name = settings.GEMINI_CARD_MODEL
    client = genai.Client(api_key=gemini_key_manager.get_candidate(set())[1])
    response = client.models.generate_content(
        model=model_name,
        contents=[f'Company website text:\n{page_text[:18000]}'],
        config=_enrichment_config(),
    )
    usage = _read_usage(response)
    parsed = getattr(response, 'parsed', None)
    if isinstance(parsed, CompanyEnrichmentData):
        data = parsed
    elif isinstance(parsed, dict):
        data = CompanyEnrichmentData.model_validate(parsed)
    else:
        import json
        data = CompanyEnrichmentData.model_validate(json.loads(getattr(response, 'text', '') or '{}'))
    return data, usage, model_name


def _acquire_lock(domain: str) -> tuple[CompanyDomainEnrichment, bool]:
    """Return (row, acquired). ``acquired`` is False when another worker holds a
    fresh lock (caller should return the current status without calling Gemini).
    """
    now = timezone.now()
    with transaction.atomic():
        row, _ = CompanyDomainEnrichment.objects.select_for_update().get_or_create(
            canonical_domain=domain,
            defaults={'status': CompanyDomainEnrichment.STATUS_PENDING},
        )
        if row.status == CompanyDomainEnrichment.STATUS_PROCESSING and row.locked_at:
            if (now - row.locked_at).total_seconds() < LOCK_STALE_SECONDS:
                return row, False  # someone else is actively enriching
        row.status = CompanyDomainEnrichment.STATUS_PROCESSING
        row.locked_at = now
        row.save(update_fields=['status', 'locked_at', 'updated_at'])
    return row, True


def get_cached_enrichment(url: str) -> CompanyDomainEnrichment | None:
    domain = canonical_domain(url)
    if not domain:
        return None
    return CompanyDomainEnrichment.objects.filter(canonical_domain=domain).first()


def run_enrichment(url: str, *, owner=None, card=None, force_refresh: bool = False) -> tuple[CompanyDomainEnrichment | None, bool]:
    """Enrich a company from its website. Returns (row, reused).

    ``reused=True`` means a fresh cached result was returned WITHOUT a new Gemini
    call. Never raises for expected failures — status/last_error carry the outcome.
    """
    if not getattr(settings, 'ENABLE_WEBSITE_ENRICHMENT', True):
        return None, False
    domain = canonical_domain(url)
    if not domain:
        return None, False

    existing = CompanyDomainEnrichment.objects.filter(canonical_domain=domain).first()
    if existing and existing.is_fresh() and not force_refresh:
        return existing, True

    row, acquired = _acquire_lock(domain)
    if not acquired:
        return row, True  # concurrent enrichment in flight; reuse its in-progress row

    started = time.perf_counter()
    if not gemini_key_manager.has_keys():
        row.status = CompanyDomainEnrichment.STATUS_UNAVAILABLE
        row.last_error = 'no_gemini_key'
        row.locked_at = None
        row.save()
        return row, False

    page_text, note = fetch_website_text(url)
    if not page_text:
        row.status = CompanyDomainEnrichment.STATUS_UNAVAILABLE
        row.last_error = (note or 'no_website_text')[:2000]
        row.locked_at = None
        row.source_url = url[:500]
        row.save()
        return row, False

    content_hash = hashlib.sha256(page_text.encode('utf-8')).hexdigest()
    if existing and existing.content_hash == content_hash and existing.status == CompanyDomainEnrichment.STATUS_COMPLETED and not force_refresh:
        # Content unchanged since last successful enrichment: refresh TTL, skip Gemini.
        row.status = CompanyDomainEnrichment.STATUS_COMPLETED
        row.refresh_after = _refresh_deadline()
        row.locked_at = None
        row.save()
        return row, True

    try:
        data, usage, model_name = _call_gemini_enrichment(page_text)
    except Exception as exc:
        logger.warning('enrichment_gemini_failed domain=%s error=%s', domain, _safe_error_summary(exc))
        row.status = CompanyDomainEnrichment.STATUS_FAILED
        row.last_error = _safe_error_summary(exc)
        row.locked_at = None
        row.save()
        log_gemini_usage(
            operation_type=GeminiUsageLog.OP_WEBSITE_ENRICHMENT,
            model_name=settings.GEMINI_CARD_MODEL,
            usage=None,
            owner=owner,
            card=card,
            request_status='failed',
            latency_ms=int((time.perf_counter() - started) * 1000),
            error_type=exc.__class__.__name__,
        )
        return row, False

    row.source_url = url[:500]
    row.company_name = data.company_name[:255]
    row.company_description = data.company_description
    row.industry = data.industry[:255]
    row.services = data.services
    row.products = data.products
    row.countries = data.countries
    row.language = data.language[:16]
    row.raw_extracted_data = data.model_dump()
    row.model_name = model_name
    row.schema_version = ENRICHMENT_SCHEMA_VERSION
    row.content_hash = content_hash
    row.status = CompanyDomainEnrichment.STATUS_COMPLETED
    row.last_error = ''
    row.enriched_at = timezone.now()
    row.refresh_after = _refresh_deadline()
    row.locked_at = None
    row.save()

    log_gemini_usage(
        operation_type=GeminiUsageLog.OP_WEBSITE_ENRICHMENT,
        model_name=model_name,
        usage=usage,
        owner=owner,
        card=card,
        request_status='completed',
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    return row, False
