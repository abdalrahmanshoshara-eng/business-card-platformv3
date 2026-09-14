"""Tests for concurrent card numbering and idempotency-key reuse.

These cover the two failure modes that only appear when more than one upload is
in flight at once: two savers claiming the same sequence_number, and one
idempotency key being answered from a different upload's stored result.
"""

from __future__ import annotations

import threading

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TestCase, TransactionTestCase, override_settings

from .models import BusinessCard, CardNumberCounter, allocate_sequence_number
from .services.card_data import prepare_card_data
from .tests_pipeline import (
    TEST_SETTINGS,
    PipelineTestCase,
    auth_client,
    card_response,
    jpeg_bytes,
    mock_gemini,
    upload,
)

User = get_user_model()


def make_card(owner, **overrides):
    data = {'person_name': 'P', 'company_name': 'C', 'emails': [], 'mobile_numbers': []}
    data.update(overrides)
    prepared = prepare_card_data(data, infer_missing_investment=False)
    return BusinessCard.objects.create(owner=owner, **prepared)


class SequenceNumberAllocationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='u1', password='x', email='u1@mei.com')

    def test_numbers_increment_without_gaps_in_the_simple_case(self):
        first = make_card(self.user, company_name='A')
        second = make_card(self.user, company_name='B')
        self.assertEqual(second.sequence_number, first.sequence_number + 1)

    def test_counter_is_created_on_demand_when_missing(self):
        CardNumberCounter.objects.all().delete()
        card = make_card(self.user, company_name='C')
        self.assertEqual(card.sequence_number, 1)
        self.assertEqual(CardNumberCounter.objects.get(pk=1).last_value, 1)

    def test_allocation_skips_past_explicitly_imported_numbers(self):
        """The Excel importers assign numbers directly, bypassing the counter."""
        BusinessCard.objects.create(
            owner=self.user, sequence_number=5000,
            **prepare_card_data({'person_name': 'Legacy', 'company_name': 'L'}, infer_missing_investment=False),
        )
        card = make_card(self.user, company_name='After')
        self.assertEqual(card.sequence_number, 5001)

    def test_explicit_sequence_number_is_preserved(self):
        card = BusinessCard.objects.create(
            owner=self.user, sequence_number=77,
            **prepare_card_data({'person_name': 'Fixed', 'company_name': 'F'}, infer_missing_investment=False),
        )
        self.assertEqual(card.sequence_number, 77)


class ConcurrentCardNumberingTests(TransactionTestCase):
    """Threads need real committed transactions, hence TransactionTestCase."""

    # Mirrors production capacity: 3 gunicorn workers x 4 threads.
    WRITERS = 12

    def setUp(self):
        self.user = User.objects.create_user(username='u2', password='x', email='u2@mei.com')

    def test_concurrent_saves_all_get_distinct_numbers(self):
        numbers: list[int] = []
        errors: list[BaseException] = []
        lock = threading.Lock()
        start = threading.Barrier(self.WRITERS)

        def worker(index: int):
            try:
                start.wait(timeout=30)  # maximise real contention
                card = make_card(self.user, company_name=f'Co{index}', person_name=f'P{index}')
                with lock:
                    numbers.append(card.sequence_number)
            except BaseException as exc:  # noqa: BLE001 - surfaced via assertion below
                with lock:
                    errors.append(exc)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(self.WRITERS)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        self.assertEqual(errors, [], f'concurrent saves raised: {errors}')
        self.assertEqual(len(numbers), self.WRITERS)
        self.assertEqual(len(set(numbers)), self.WRITERS, f'duplicate numbers issued: {sorted(numbers)}')
        self.assertEqual(sorted(numbers), list(range(min(numbers), min(numbers) + self.WRITERS)))

    def test_concurrent_allocation_never_repeats_a_number(self):
        """The allocator alone, without the surrounding card INSERT."""
        issued: list[int] = []
        lock = threading.Lock()
        start = threading.Barrier(self.WRITERS)

        def worker():
            try:
                start.wait(timeout=30)
                value = allocate_sequence_number()
                with lock:
                    issued.append(value)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker) for _ in range(self.WRITERS)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        self.assertEqual(len(set(issued)), self.WRITERS, f'allocator repeated a number: {sorted(issued)}')


@override_settings(**TEST_SETTINGS)
class IdempotencyKeyReuseTests(PipelineTestCase):
    """A key identifies one upload. Reusing it for different images must not
    hand back the first upload's card."""

    def test_completed_key_with_different_images_is_rejected(self):
        client, _ = auth_client()
        first = jpeg_bytes(color=(10, 20, 30))
        second = jpeg_bytes(color=(200, 100, 50))
        script = [card_response(person_name='Ada', company_name='Acme', mobile_numbers=['+963 944 111 222'])]
        with mock_gemini(script) as models:
            created = client.post(
                '/api/cards/extract', {'front': upload('a.jpg', first)},
                format='multipart', HTTP_X_IDEMPOTENCY_KEY='reused-key',
            )
            reused = client.post(
                '/api/cards/extract', {'front': upload('b.jpg', second)},
                format='multipart', HTTP_X_IDEMPOTENCY_KEY='reused-key',
            )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(reused.status_code, 409)
        self.assertEqual(reused.data['error_type'], 'idempotency_key_reused')
        # The second upload must not be answered with the first card, and must
        # not have spent a Gemini call either.
        self.assertNotIn('card', reused.data)
        self.assertEqual(models.calls, 1)
        self.assertEqual(BusinessCard.objects.count(), 1)

    def test_same_key_with_same_images_still_replays(self):
        """The guard must not break an ordinary retry."""
        client, _ = auth_client()
        same = jpeg_bytes(color=(77, 77, 77))
        script = [card_response(person_name='Bo', company_name='Initech', mobile_numbers=['+963 944 333 444'])]
        with mock_gemini(script) as models:
            first = client.post(
                '/api/cards/extract', {'front': upload('same.jpg', same)},
                format='multipart', HTTP_X_IDEMPOTENCY_KEY='retry-key',
            )
            retry = client.post(
                '/api/cards/extract', {'front': upload('same.jpg', same)},
                format='multipart', HTTP_X_IDEMPOTENCY_KEY='retry-key',
            )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(retry.status_code, 200)
        self.assertTrue(retry.data.get('idempotent_replay'))
        self.assertEqual(models.calls, 1)

    def test_rejection_does_not_consume_the_key_for_its_own_images(self):
        """After a 409 the client retires the key; the images themselves are
        still extractable under a fresh one."""
        client, _ = auth_client()
        first = jpeg_bytes(color=(1, 2, 3))
        second = jpeg_bytes(color=(250, 250, 250))
        script = [
            card_response(person_name='Cy', company_name='Umbrella', mobile_numbers=['+963 944 555 666']),
            card_response(person_name='Di', company_name='Tyrell', mobile_numbers=['+963 944 777 888']),
        ]
        with mock_gemini(script):
            client.post('/api/cards/extract', {'front': upload('1.jpg', first)},
                        format='multipart', HTTP_X_IDEMPOTENCY_KEY='k1')
            rejected = client.post('/api/cards/extract', {'front': upload('2.jpg', second)},
                                   format='multipart', HTTP_X_IDEMPOTENCY_KEY='k1')
            accepted = client.post('/api/cards/extract', {'front': upload('2.jpg', second)},
                                   format='multipart', HTTP_X_IDEMPOTENCY_KEY='k2')
        self.assertEqual(rejected.status_code, 409)
        self.assertEqual(accepted.status_code, 201)
        self.assertEqual(BusinessCard.objects.count(), 2)
