"""Tests for the improved Gemini card-extraction pipeline.

Gemini is always mocked — no test consumes paid quota. The mock lets each test
script a sequence of responses / exceptions and asserts exactly how many Gemini
calls happened, which is how we prove the cost-reduction guarantees.
"""

from __future__ import annotations

import tempfile
from contextlib import contextmanager
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from PIL import Image

from .models import BusinessCard, CompanyDomainEnrichment, ExtractionRequest, GeminiUsageLog
from .services.extractor import BusinessCardData
from .services import domains, pricing, security
from .services.gemini_keys import manager as gemini_key_manager


class PipelineTestCase(TestCase):
    """Reset the process-wide Gemini key manager so a disabled/cooled-down key in
    one test never leaks into the next."""

    def setUp(self):
        super().setUp()
        gemini_key_manager.reset()

User = get_user_model()
_MEDIA = tempfile.mkdtemp(prefix='card-tests-media-')

TEST_SETTINGS = dict(
    GEMINI_API_KEYS=['test-key-1'],
    GEMINI_CARD_MODEL='gemini-2.5-flash',
    GEMINI_CARD_MAX_RETRIES=2,
    GEMINI_CARD_RETRY_BASE_DELAY=0,  # no real sleeping in tests
    MEDIA_ROOT=_MEDIA,
    ENABLE_WEBSITE_ENRICHMENT=True,
    GEMINI_PRICING={'gemini-2.5-flash': {'input': '0.30', 'output': '2.50'}},
)


# ── Gemini mock plumbing ───────────────────────────────────────────────────
class FakeUsage:
    def __init__(self, pin=1000, pout=200, total=None, thoughts=None, cached=None):
        self.prompt_token_count = pin
        self.candidates_token_count = pout
        self.total_token_count = total if total is not None else (pin or 0) + (pout or 0)
        self.thoughts_token_count = thoughts
        self.cached_content_token_count = cached


class FakeCandidate:
    def __init__(self, finish_reason):
        self.finish_reason = type('FinishReason', (), {'name': finish_reason})()


class FakeResponse:
    def __init__(self, parsed=None, text='', usage=None, finish_reason=None):
        self.parsed = parsed
        self.text = text
        self.usage_metadata = usage
        self.candidates = [FakeCandidate(finish_reason)] if finish_reason else []


class FakeModels:
    def __init__(self, script):
        self.script = script
        self.calls = 0
        self.last_config = None

    def generate_content(self, **kwargs):
        self.last_config = kwargs.get('config')
        item = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return item


@contextmanager
def mock_gemini(script, target='cards.services.extractor.genai.Client'):
    models = FakeModels(script)
    client = type('FakeClient', (), {'models': models})()
    with patch(target, return_value=client):
        yield models


@contextmanager
def mock_extract_and_enrich(extract_response, industry='صناعة', description=''):
    """Extraction now always visits the website, so extraction AND the inline
    enrichment share the same google.genai.Client. Route by response_schema:
    BusinessCardData → the extraction response; CompanyEnrichmentData → an
    enrichment response. Also stubs the website fetch. Yields call counters."""
    from .services.enrichment import CompanyEnrichmentData
    counters = {'extract': 0, 'enrich': 0}
    enrich_resp = FakeResponse(
        parsed=CompanyEnrichmentData(company_name='Co', industry=industry, company_description=description),
        text='{}', usage=FakeUsage(),
    )

    class Router:
        def generate_content(self, **kwargs):
            if getattr(kwargs.get('config'), 'response_schema', None) is CompanyEnrichmentData:
                counters['enrich'] += 1
                return enrich_resp
            counters['extract'] += 1
            return extract_response

    fake = type('FakeClient', (), {'models': Router()})()
    with patch('cards.services.extractor.genai.Client', return_value=fake), \
         patch('cards.services.enrichment.fetch_website_text', return_value=('company website text', 'ok')):
        yield counters


def card_response(usage=None, **fields):
    fields.setdefault('confidence', 0.9)
    fields.setdefault('needs_review', False)
    data = BusinessCardData(**fields)
    return FakeResponse(parsed=data, text=data.model_dump_json(), usage=usage or FakeUsage())


def jpeg_bytes(color=(210, 210, 210), size=(640, 400)):
    buf = BytesIO()
    Image.new('RGB', size, color).save(buf, 'JPEG')
    return buf.getvalue()


def upload(name='front.jpg', data=None):
    return SimpleUploadedFile(name, data or jpeg_bytes(), content_type='image/jpeg')


def auth_client():
    user = User.objects.create_user(username=f'u{User.objects.count()}', password='StrongPass!234')
    client = APIClient()
    client.force_authenticate(user)
    return client, user


@override_settings(**TEST_SETTINGS)
class ExtractionSingleCallTests(PipelineTestCase):
    def test_front_only_extracts_in_one_call(self):
        client, _ = auth_client()
        script = [card_response(person_name='Alice', company_name='Acme', mobile_numbers=['+963 944 111 222'])]
        with mock_gemini(script) as models:
            res = client.post('/api/cards/extract', {'front': upload()}, format='multipart')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(models.calls, 1)
        self.assertTrue(res.data['saved'])
        self.assertEqual(BusinessCard.objects.count(), 1)

    def test_two_faces_use_single_gemini_call(self):
        client, _ = auth_client()
        script = [card_response(person_name='Bob', company_name='Globex', mobile_numbers=['+963 944 333 444'])]
        with mock_gemini(script) as models:
            res = client.post(
                '/api/cards/extract',
                {'front': upload('front.jpg'), 'back': upload('back.jpg', jpeg_bytes(color=(90, 90, 90)))},
                format='multipart',
            )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(models.calls, 1)  # NOT one-per-face, NOT a third merge call
        self.assertEqual(BusinessCard.objects.count(), 1)

    def test_structured_output_config_is_applied(self):
        client, _ = auth_client()
        with mock_gemini([card_response(person_name='Cara', company_name='Initech', mobile_numbers=['+963 944 555 666'])]) as models:
            client.post('/api/cards/extract', {'front': upload()}, format='multipart')
        config = models.last_config
        self.assertEqual(config.response_mime_type, 'application/json')
        self.assertIsNotNone(config.response_schema)
        self.assertEqual(config.temperature, 0)
        self.assertEqual(config.thinking_config.thinking_budget, 0)

    def test_non_json_response_is_rejected_without_saving(self):
        client, _ = auth_client()
        bad = FakeResponse(parsed=None, text='totally not json', usage=FakeUsage())
        with mock_gemini([bad, bad, bad]):
            res = client.post('/api/cards/extract', {'front': upload()}, format='multipart')
        self.assertGreaterEqual(res.status_code, 400)
        self.assertEqual(BusinessCard.objects.count(), 0)

    def test_review_fields_persisted(self):
        client, _ = auth_client()
        script = [card_response(person_name='Dan', company_name='Umbrella', mobile_numbers=['+963 944 777 888'],
                                needs_review=True, review_fields=['company_name', 'website'], confidence=0.4)]
        with mock_gemini(script):
            res = client.post('/api/cards/extract', {'front': upload()}, format='multipart')
        card = BusinessCard.objects.get()
        self.assertIn('company_name', card.review_fields)
        self.assertTrue(res.data['card']['needs_review'])


@override_settings(**TEST_SETTINGS)
class ResponseFailureModeTests(PipelineTestCase):
    """Covers the causes behind the generic 'cannot extract from Gemini' error."""

    def test_truncated_output_retries_with_bigger_budget_then_succeeds(self):
        client, _ = auth_client()
        truncated = FakeResponse(parsed=None, text='', usage=FakeUsage(), finish_reason='MAX_TOKENS')
        good = card_response(person_name='Ana', company_name='Big Co', mobile_numbers=['+963 944 010 010'])
        with mock_gemini([truncated, good]) as models:
            res = client.post('/api/cards/extract', {'front': upload()}, format='multipart')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(models.calls, 2)
        # Second attempt used a larger max_output_tokens than the configured floor.
        self.assertGreater(models.last_config.max_output_tokens, 2048)

    def test_blocked_content_gives_clear_error_no_retry(self):
        client, _ = auth_client()
        blocked = FakeResponse(parsed=None, text='', usage=FakeUsage(), finish_reason='SAFETY')
        with mock_gemini([blocked, blocked]) as models:
            res = client.post('/api/cards/extract', {'front': upload()}, format='multipart')
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.data['error_type'], 'gemini_content_blocked')
        self.assertEqual(models.calls, 1)  # not retried
        self.assertEqual(BusinessCard.objects.count(), 0)

    def test_empty_response_is_retried_then_reported(self):
        client, _ = auth_client()
        empty = FakeResponse(parsed=None, text='', usage=FakeUsage())  # no finish reason
        with mock_gemini([empty, empty, empty]) as models:
            res = client.post('/api/cards/extract', {'front': upload()}, format='multipart')
        self.assertGreaterEqual(res.status_code, 500)
        self.assertEqual(res.data['error_type'], 'gemini_empty_response')
        self.assertEqual(models.calls, 3)  # 1 + GEMINI_CARD_MAX_RETRIES(2)
        self.assertEqual(BusinessCard.objects.count(), 0)


@override_settings(**TEST_SETTINGS)
class IdempotencyTests(PipelineTestCase):
    def test_same_idempotency_key_does_not_call_gemini_twice(self):
        client, _ = auth_client()
        script = [card_response(person_name='Eve', company_name='Hooli', mobile_numbers=['+963 944 999 000'])]
        with mock_gemini(script) as models:
            headers = {'HTTP_X_IDEMPOTENCY_KEY': 'fixed-key-1'}
            r1 = client.post('/api/cards/extract', {'front': upload()}, format='multipart', **headers)
            r2 = client.post('/api/cards/extract', {'front': upload()}, format='multipart', **headers)
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 200)
        self.assertTrue(r2.data.get('idempotent_replay'))
        self.assertEqual(models.calls, 1)
        self.assertEqual(BusinessCard.objects.count(), 1)

    def test_identical_images_reuse_result_without_new_call(self):
        client, _ = auth_client()
        same = jpeg_bytes(color=(123, 123, 123))
        script = [card_response(person_name='Finn', company_name='Stark', mobile_numbers=['+963 944 121 212'])]
        with mock_gemini(script) as models:
            # Different idempotency keys, byte-identical front image.
            client.post('/api/cards/extract', {'front': upload('a.jpg', same)}, format='multipart', HTTP_X_IDEMPOTENCY_KEY='k-a')
            r2 = client.post('/api/cards/extract', {'front': upload('b.jpg', same)}, format='multipart', HTTP_X_IDEMPOTENCY_KEY='k-b')
        self.assertEqual(models.calls, 1)
        self.assertTrue(r2.data.get('idempotent_replay'))

    def test_completed_request_returns_previous_result(self):
        client, _ = auth_client()
        script = [card_response(person_name='Gia', company_name='Wayne', mobile_numbers=['+963 944 343 434'])]
        with mock_gemini(script):
            r1 = client.post('/api/cards/extract', {'front': upload()}, format='multipart', HTTP_X_IDEMPOTENCY_KEY='done-1')
        seq = r1.data['card']['sequence_number']
        # No mock needed: a completed replay must not touch Gemini at all.
        r2 = client.post('/api/cards/extract', {'front': upload()}, format='multipart', HTTP_X_IDEMPOTENCY_KEY='done-1')
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.data['card']['sequence_number'], seq)


@override_settings(**TEST_SETTINGS)
class UsageAndCostTests(PipelineTestCase):
    def test_usage_logged_with_decimal_cost(self):
        client, _ = auth_client()
        usage = FakeUsage(pin=1000, pout=200, thoughts=15)
        with mock_gemini([card_response(person_name='Hank', company_name='Cyberdyne', mobile_numbers=['+963 944 565 656'], usage=usage)]):
            client.post('/api/cards/extract', {'front': upload()}, format='multipart')
        log = GeminiUsageLog.objects.get(operation_type=GeminiUsageLog.OP_CARD_EXTRACTION)
        self.assertEqual(log.input_token_count, 1000)
        self.assertEqual(log.output_token_count, 200)
        self.assertEqual(log.thoughts_token_count, 15)
        self.assertIsInstance(log.estimated_total_cost_usd, Decimal)
        # 1000/1e6*0.30 + 200/1e6*2.50 = 0.0003 + 0.0005 = 0.0008
        self.assertEqual(log.estimated_total_cost_usd, Decimal('0.000800'))

    def test_card_saved_even_when_usage_metadata_missing(self):
        client, _ = auth_client()
        no_meta = card_response(person_name='Iris', company_name='Soylent', mobile_numbers=['+963 944 787 878'])
        no_meta.usage_metadata = None
        with mock_gemini([no_meta]):
            res = client.post('/api/cards/extract', {'front': upload()}, format='multipart')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(BusinessCard.objects.count(), 1)
        log = GeminiUsageLog.objects.get()
        self.assertIsNone(log.estimated_total_cost_usd)
        self.assertEqual(log.cost_note, 'no_usage_metadata')

    def test_estimate_cost_uses_decimal(self):
        result = pricing.estimate_cost('gemini-2.5-flash', 1_000_000, 1_000_000)
        self.assertEqual(result['input'], Decimal('0.300000'))
        self.assertEqual(result['output'], Decimal('2.500000'))
        self.assertEqual(result['total'], Decimal('2.800000'))

    def test_estimate_cost_unknown_model_returns_none(self):
        result = pricing.estimate_cost('no-such-model', 100, 100)
        self.assertIsNone(result['total'])
        self.assertIn('no_pricing_for_model', result['reason'])


@override_settings(**TEST_SETTINGS)
class RetryPolicyTests(PipelineTestCase):
    def test_transient_error_is_retried_then_succeeds(self):
        client, _ = auth_client()
        script = [RuntimeError('503 Service Unavailable'),
                  card_response(person_name='Jax', company_name='Tyrell', mobile_numbers=['+963 944 909 090'])]
        with mock_gemini(script) as models:
            res = client.post('/api/cards/extract', {'front': upload()}, format='multipart')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(models.calls, 2)

    def test_invalid_api_key_is_not_retried(self):
        client, _ = auth_client()
        script = [RuntimeError('API key not valid. Please pass a valid API key.')]
        with mock_gemini(script) as models:
            res = client.post('/api/cards/extract', {'front': upload()}, format='multipart')
        self.assertGreaterEqual(res.status_code, 400)
        self.assertEqual(models.calls, 1)  # permanent error → no retry
        self.assertEqual(BusinessCard.objects.count(), 0)


@override_settings(**{**TEST_SETTINGS, 'GEMINI_API_KEYS': ['k1', 'k2']})
class QuotaFailoverTests(PipelineTestCase):
    def test_429_detected_by_status_code_switches_to_next_key(self):
        client, _ = auth_client()

        class Quota429(RuntimeError):
            code = 429  # google-genai style; message intentionally lacks '429'/'quota'

        err = Quota429('You have exceeded the allowed limit for this model.')
        good = card_response(person_name='Q', company_name='C', mobile_numbers=['+963 944 000 111'])
        with mock_gemini([err, good]) as models:
            res = client.post('/api/cards/extract', {'front': upload()}, format='multipart')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(models.calls, 2)  # first key hit the limit → switched to the second key
        self.assertEqual(BusinessCard.objects.count(), 1)


@override_settings(GEMINI_API_KEYS=['KEY1', 'KEY2', 'KEY3'])
class GeminiKeySelectionTests(PipelineTestCase):
    def test_strict_priority_prefers_first_key(self):
        # Two independent selections both pick key #0 (no round-robin).
        i1, _ = gemini_key_manager.get_candidate(set())
        i2, _ = gemini_key_manager.get_candidate(set())
        self.assertEqual((i1, i2), (0, 0))

    def test_failover_to_next_key_on_cooldown(self):
        gemini_key_manager.get_candidate(set())  # prime key state (as the real flow does)
        gemini_key_manager.mark_cooldown(0, 'gemini_rate_limit')
        index, key = gemini_key_manager.get_candidate(set())
        self.assertEqual((index, key), (1, 'KEY2'))

    def test_failover_to_next_key_on_invalid(self):
        gemini_key_manager.get_candidate(set())
        gemini_key_manager.mark_invalid(0, 'gemini_invalid_api_key')
        index, key = gemini_key_manager.get_candidate(set())
        self.assertEqual((index, key), (1, 'KEY2'))

    def test_within_call_skips_already_tried_keys(self):
        first, _ = gemini_key_manager.get_candidate(set())
        second, _ = gemini_key_manager.get_candidate({first})
        self.assertEqual((first, second), (0, 1))

    def test_all_keys_unavailable_returns_none(self):
        gemini_key_manager.get_candidate(set())
        for i in range(3):
            gemini_key_manager.mark_cooldown(i, 'gemini_rate_limit')
        self.assertIsNone(gemini_key_manager.get_candidate(set()))
        self.assertEqual(gemini_key_manager.exhaustion_reason(set()), 'all_gemini_keys_rate_limited')


@override_settings(**TEST_SETTINGS)
class DomainNormalizationTests(PipelineTestCase):
    def test_canonical_domain_variants(self):
        self.assertEqual(domains.canonical_domain('https://www.Example.com/about?x=1'), 'example.com')
        self.assertEqual(domains.canonical_domain('http://example.com'), 'example.com')
        self.assertEqual(domains.canonical_domain('https://EXAMPLE.com/'), 'example.com')
        self.assertEqual(domains.canonical_domain('https://careers.example.com/jobs'), 'example.com')
        self.assertEqual(domains.canonical_domain('https://shop.example.co.uk:8443/x'), 'example.co.uk')
        self.assertEqual(domains.canonical_domain(''), '')

    def test_ssrf_blocks_internal_hosts(self):
        self.assertFalse(security.is_public_http_url('http://localhost:8000'))
        self.assertFalse(security.is_public_http_url('http://127.0.0.1/'))
        self.assertFalse(security.is_public_http_url('http://169.254.169.254/latest/meta-data'))
        self.assertFalse(security.is_public_http_url('ftp://example.com'))


@override_settings(**TEST_SETTINGS)
class EnrichmentTests(PipelineTestCase):
    """Extraction ALWAYS visits the company website to determine the activity."""

    def test_extraction_visits_site_fills_activity_and_caches(self):
        client, _ = auth_client()
        extract_resp = card_response(person_name='Ned', company_name='Visit Co', website='https://visit-co.com/',
                                     mobile_numbers=['+963 944 222 444'], company_activity='', confidence=0.9)
        with mock_extract_and_enrich(extract_resp, industry='الطاقة المتجددة') as counters:
            res = client.post('/api/cards/extract', {'front': upload()}, format='multipart')
        self.assertEqual(res.status_code, 201, res.data)
        card = BusinessCard.objects.get()
        self.assertEqual(card.company_activity, 'الطاقة المتجددة')      # filled from the site
        self.assertNotIn('company_activity', card.review_fields)
        self.assertEqual(counters['enrich'], 1)                         # visited once
        self.assertTrue(CompanyDomainEnrichment.objects.filter(canonical_domain='visit-co.com').exists())
        self.assertTrue(GeminiUsageLog.objects.filter(operation_type=GeminiUsageLog.OP_WEBSITE_ENRICHMENT).exists())

    def test_no_website_and_unknown_activity_flags_review(self):
        client, _ = auth_client()
        # No website → nothing to visit → activity stays unknown → needs review.
        script = [card_response(person_name='Lee', company_name='NoSite Co',
                                mobile_numbers=['+963 944 222 111'], company_activity='')]
        with mock_gemini(script):
            res = client.post('/api/cards/extract', {'front': upload()}, format='multipart')
        self.assertEqual(res.status_code, 201, res.data)
        card = BusinessCard.objects.get()
        self.assertTrue(card.needs_review)
        self.assertIn('company_activity', card.review_fields)
        self.assertEqual(CompanyDomainEnrichment.objects.count(), 0)

    def test_known_activity_not_flagged(self):
        client, _ = auth_client()
        script = [card_response(person_name='Mia', company_name='HasActivity Co',
                                mobile_numbers=['+963 944 222 333'], company_activity='مقاولات وإنشاءات', confidence=0.9)]
        with mock_gemini(script):
            res = client.post('/api/cards/extract', {'front': upload()}, format='multipart')
        card = BusinessCard.objects.get()
        self.assertNotIn('company_activity', card.review_fields)
        self.assertFalse(card.needs_review)

    def test_same_registered_domain_reuses_cache(self):
        from .services.enrichment import CompanyEnrichmentData, run_enrichment
        _, user = auth_client()
        calls = {'n': 0}

        class Models:
            def generate_content(self, **kwargs):
                calls['n'] += 1
                return FakeResponse(parsed=CompanyEnrichmentData(company_name='Acme', industry='صناعة'),
                                    text='{}', usage=FakeUsage())

        fake = type('FakeClient', (), {'models': Models()})()
        with patch('cards.services.enrichment.genai.Client', return_value=fake), \
             patch('cards.services.enrichment.fetch_website_text', return_value=('t', 'ok')):
            row1, reused1 = run_enrichment('https://acme.com/', owner=user)
            # Different subdomain/path but same registered domain → cache hit, no new call.
            row2, reused2 = run_enrichment('https://careers.acme.com/jobs', owner=user)
        self.assertEqual(calls['n'], 1)
        self.assertFalse(reused1)
        self.assertTrue(reused2)
        self.assertEqual(row2.canonical_domain, 'acme.com')

    def test_processing_lock_prevents_parallel_enrichment(self):
        from django.utils import timezone
        from .services.enrichment import run_enrichment
        _, user = auth_client()
        CompanyDomainEnrichment.objects.create(
            canonical_domain='locked-co.com',
            status=CompanyDomainEnrichment.STATUS_PROCESSING,
            locked_at=timezone.now(),
        )
        calls = {'n': 0}

        class Models:
            def generate_content(self, **kwargs):
                calls['n'] += 1
                raise AssertionError('Gemini must not be called while another enrichment holds the lock')

        fake = type('FakeClient', (), {'models': Models()})()
        with patch('cards.services.enrichment.genai.Client', return_value=fake), \
             patch('cards.services.enrichment.fetch_website_text', return_value=('t', 'ok')):
            row, reused = run_enrichment('https://locked-co.com/', owner=user)
        self.assertEqual(calls['n'], 0)   # locked → no Gemini call
        self.assertTrue(reused)
