"""Duplicate detection: every field is compared and combined into a similarity %.

>= 95% → duplicate, 75–95% → possible duplicate, below → a distinct card.
"""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import BusinessCard
from .services.card_data import prepare_card_data
from .services.duplicates import (
    find_duplicate_candidates,
    find_existing_duplicate,
    find_possible_duplicate,
    score_duplicate,
)
from .tests import make_card, make_user
from .tests_pipeline import TEST_SETTINGS, PipelineTestCase, card_response, mock_gemini, upload

CARD = {
    'person_name': 'Ali Hassan',
    'job_title': 'General Manager',
    'company_name': 'Hassan Trading',
    'emails': ['ali@hassan.com', 'info@hassan.com'],
    'mobile_numbers': ['+963944123456'],
    'website': 'hassan.com',
    'address': 'Damascus - Mazzeh',
}


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def prepared(**changes):
    return prepare_card_data({**CARD, **changes}, infer_missing_investment=False)


class SimilarityScoreTests(TestCase):
    def setUp(self):
        self.owner = make_user('dup_owner')
        self.existing = make_card(owner=self.owner, **CARD)
        self.scoped = BusinessCard.objects.filter(owner=self.owner)

    def test_identical_card_scores_100(self):
        match = score_duplicate(prepared(), self.existing)
        self.assertEqual(match.score, 100)
        self.assertEqual(match.differing, [])
        self.assertEqual(match.reason, 'تطابق كامل لجميع بيانات الكرت')
        self.assertEqual(find_existing_duplicate(prepared(), self.scoped).card, self.existing)

    def test_formatting_and_order_differences_still_score_100(self):
        data = prepared(
            person_name='ali  hassan', website='https://www.hassan.com/',
            emails=['INFO@hassan.com', 'ali@hassan.com'], mobile_numbers=['+963 944 123 456'],
        )
        self.assertEqual(score_duplicate(data, self.existing).score, 100)

    def test_one_ocr_slip_is_still_a_duplicate(self):
        for changes in ({'person_name': 'Ali Hasan'}, {'address': 'Damascus - Mazze'}, {'address': ''}):
            with self.subTest(changes=changes):
                match = find_existing_duplicate(prepared(**changes), self.scoped)
                self.assertIsNotNone(match)
                self.assertGreaterEqual(match.score, 95)
                self.assertLess(match.score, 100)
                self.assertTrue(match.differing)

    def test_missing_emails_is_a_possible_duplicate(self):
        data = prepared(emails=[])
        self.assertIsNone(find_existing_duplicate(data, self.scoped))
        match = find_possible_duplicate(data, self.scoped)
        self.assertEqual(match.score, 80)
        self.assertEqual(match.differing, ['الإيميل'])
        self.assertIn('80%', match.reason)

    def test_a_different_person_is_never_a_duplicate(self):
        # Same company email, phone and everything else — but another person.
        data = prepared(person_name='Khaled Nour')
        self.assertEqual(score_duplicate(data, self.existing).score, 0)
        self.assertEqual(find_duplicate_candidates(data, self.scoped), [])

    def test_only_the_company_in_common_is_not_a_match(self):
        data = prepare_card_data({
            'person_name': 'Ali Hassan', 'company_name': 'Hassan Trading',
            'emails': ['someone@else.com'], 'mobile_numbers': ['+963955000111'],
            'job_title': 'Accountant', 'website': 'else.com', 'address': 'Aleppo',
        }, infer_missing_investment=False)
        self.assertEqual(find_duplicate_candidates(data, self.scoped), [])

    def test_card_with_a_stale_stored_hash_is_still_found(self):
        BusinessCard.objects.filter(pk=self.existing.pk).update(duplicate_hash='legacy-hash')
        self.assertEqual(find_existing_duplicate(prepared(), self.scoped).card, self.existing)

    def test_empty_card_is_never_a_duplicate(self):
        empty = {'person_name': '', 'company_name': '', 'emails': [], 'mobile_numbers': []}
        make_card(owner=self.owner, **empty)
        data = prepare_card_data(empty, infer_missing_investment=False)
        self.assertEqual(find_duplicate_candidates(data, self.scoped), [])


class ManualCreateDuplicateApiTests(TestCase):
    def setUp(self):
        self.owner = make_user('api_owner')
        self.client = client_for(self.owner)
        make_card(owner=self.owner, **CARD)

    def test_identical_card_is_rejected_until_confirmed(self):
        resp = self.client.post('/api/cards/', CARD, format='json')
        self.assertEqual(resp.status_code, 409, resp.data)
        candidate = resp.data['duplicate_candidates'][0]
        self.assertTrue(candidate['is_duplicate'])
        self.assertEqual(candidate['score'], 100)

        resp = self.client.post('/api/cards/', {**CARD, 'confirm_duplicate': True}, format='json')
        self.assertEqual(resp.status_code, 201, resp.data)

        # The confirmed copy (salted hash) is still recognised next time.
        resp = self.client.post('/api/cards/', CARD, format='json')
        self.assertEqual(resp.status_code, 409, resp.data)
        self.assertEqual(len(resp.data['duplicate_candidates']), 2)

    def test_possible_duplicate_is_returned_with_its_score(self):
        resp = self.client.post('/api/cards/', {**CARD, 'emails': []}, format='json')
        self.assertEqual(resp.status_code, 409, resp.data)
        candidate = resp.data['duplicate_candidates'][0]
        self.assertFalse(candidate['is_duplicate'])
        self.assertEqual(candidate['score'], 80)
        self.assertEqual(candidate['differing_fields'], ['الإيميل'])

    def test_a_different_person_is_saved(self):
        resp = self.client.post('/api/cards/', {**CARD, 'person_name': 'Khaled Nour'}, format='json')
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(BusinessCard.objects.filter(owner=self.owner).count(), 2)

    def test_identical_card_of_another_user_is_not_a_duplicate(self):
        resp = client_for(make_user('other_owner')).post('/api/cards/', CARD, format='json')
        self.assertEqual(resp.status_code, 201, resp.data)


@override_settings(**TEST_SETTINGS)
class UploadDuplicateTests(PipelineTestCase):
    def setUp(self):
        super().setUp()
        self.owner = make_user('upload_owner')
        self.client = client_for(self.owner)
        self.existing = make_card(owner=self.owner, company_activity='تجارة', **CARD)

    def _extract(self, **fields):
        fields = {**CARD, 'company_activity': 'تجارة', **fields}
        with mock_gemini([card_response(**fields)]):
            return self.client.post('/api/cards/extract', {'front': upload()}, format='multipart')

    def test_near_identical_upload_reuses_the_existing_card(self):
        resp = self._extract(person_name='Ali Hasan')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertTrue(resp.data['duplicate'])
        self.assertGreaterEqual(resp.data['score'], 95)
        self.assertEqual(BusinessCard.objects.filter(owner=self.owner).count(), 1)

    def test_possible_duplicate_upload_is_saved_and_flagged_for_review(self):
        resp = self._extract(emails=[])
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data['possible_duplicate']['id'], self.existing.id)
        card = BusinessCard.objects.get(pk=resp.data['card']['id'])
        self.assertTrue(card.needs_review)
        self.assertIn(f'مشابه لكرت #{self.existing.sequence_number}', card.review_notes)
        self.assertEqual(BusinessCard.objects.filter(owner=self.owner).count(), 2)
