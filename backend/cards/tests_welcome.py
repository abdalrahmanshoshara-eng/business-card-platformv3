"""Welcome-email feature tests. Email delivery uses Django's in-memory backend
during tests (django.core.mail.outbox) — no real mail is sent."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import Profile
from .models import BusinessCard
from .services.card_data import prepare_card_data

User = get_user_model()


def make_user(username):
    return User.objects.create_user(username=username, password='StrongPass!234', email=f'{username}@x.com')


def auth_client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def make_card(owner, emails):
    data = prepare_card_data({'person_name': 'P', 'company_name': 'C', 'emails': emails}, infer_missing_investment=False)
    return BusinessCard.objects.create(owner=owner, **data)


def configure_profile(user, **overrides):
    defaults = {
        'sender_email': 'sender@example.com',
        'welcome_subject': 'أهلاً',
        'welcome_message': 'مرحبًا بك',
    }
    defaults.update(overrides)
    Profile.objects.update_or_create(user=user, defaults=defaults)


class ProfileConfigApiTests(TestCase):
    def test_saves_three_fields(self):
        user = make_user('alice')
        client = auth_client(user)
        resp = client.patch('/api/auth/profile', {
            'sender_email': 'alice@example.com',
            'welcome_subject': 'ترحيب',
            'welcome_message': 'أهلاً وسهلاً',
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        cfg = resp.data['welcome_email']
        self.assertEqual(cfg['sender_email'], 'alice@example.com')
        self.assertEqual(cfg['welcome_subject'], 'ترحيب')
        self.assertEqual(cfg['welcome_message'], 'أهلاً وسهلاً')
        self.assertTrue(cfg['configured'])
        profile = Profile.objects.get(user=user)
        self.assertEqual(profile.sender_email, 'alice@example.com')

    def test_not_configured_until_email_and_message_set(self):
        user = make_user('bob')
        client = auth_client(user)
        resp = client.patch('/api/auth/profile', {'welcome_subject': 'x'}, format='json')
        self.assertFalse(resp.data['welcome_email']['configured'])


@override_settings(WELCOME_FROM_EMAIL='platform@site.com')
class SendWelcomeApiTests(TestCase):
    def setUp(self):
        self.user = make_user('carol')
        configure_profile(self.user)
        self.client = auth_client(self.user)
        self.card = make_card(self.user, ['recipient@corp.com'])

    def test_send_success_sets_status_and_sends_once(self):
        resp = self.client.post(f'/api/cards/{self.card.id}/send-welcome', {}, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data['welcome_status'], 'sent')
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, ['recipient@corp.com'])
        # Always sent FROM the single platform address, with the user's email as
        # display name + Reply-To.
        self.assertIn('platform@site.com', msg.from_email)
        self.assertIn('sender@example.com', msg.from_email)
        self.assertEqual(msg.reply_to, ['sender@example.com'])
        self.assertEqual(msg.subject, 'أهلاً')
        self.assertEqual(msg.body, 'مرحبًا بك')
        self.card.refresh_from_db()
        self.assertEqual(self.card.welcome_status, 'sent')
        self.assertEqual(self.card.welcome_sent_to, 'recipient@corp.com')

    def test_one_time_guard_then_resend(self):
        self.client.post(f'/api/cards/{self.card.id}/send-welcome', {}, format='json')
        again = self.client.post(f'/api/cards/{self.card.id}/send-welcome', {}, format='json')
        self.assertTrue(again.data.get('already_sent'))
        self.assertEqual(len(mail.outbox), 1)
        resent = self.client.post(f'/api/cards/{self.card.id}/send-welcome', {'resend': True}, format='json')
        self.assertEqual(resent.data['welcome_status'], 'sent')
        self.assertEqual(len(mail.outbox), 2)

    def test_requires_configuration(self):
        user = make_user('dave')  # no profile config
        client = auth_client(user)
        card = make_card(user, ['x@y.com'])
        resp = client.post(f'/api/cards/{card.id}/send-welcome', {}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['error_type'], 'welcome_not_configured')

    def test_no_recipient_email(self):
        card = make_card(self.user, [])
        resp = self.client.post(f'/api/cards/{card.id}/send-welcome', {}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['error_type'], 'no_recipient')

    def test_invalid_recipient_rejected(self):
        resp = self.client.post(f'/api/cards/{self.card.id}/send-welcome', {'to': 'attacker@evil.com'}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['error_type'], 'invalid_recipient')

    def test_cannot_send_for_another_users_card(self):
        other = make_user('eve')
        other_card = make_card(other, ['z@z.com'])
        resp = self.client.post(f'/api/cards/{other_card.id}/send-welcome', {}, format='json')
        self.assertEqual(resp.status_code, 404)

    def test_welcome_test_endpoint_sends_to_arbitrary_email(self):
        resp = self.client.post('/api/auth/welcome-test', {'to': 'me@test.com'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertTrue(resp.data['sent'])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['me@test.com'])
        self.assertIn('platform@site.com', mail.outbox[0].from_email)

    def test_welcome_test_endpoint_rejects_invalid_email(self):
        resp = self.client.post('/api/auth/welcome-test', {'to': 'not-an-email'}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['error_type'], 'invalid_email')
        self.assertEqual(len(mail.outbox), 0)

    def test_send_failure_marks_failed_without_leaking_error(self):
        with patch('accounts.services_email.get_connection', side_effect=Exception('SMTP auth failed')):
            resp = self.client.post(f'/api/cards/{self.card.id}/send-welcome', {}, format='json')
        self.assertEqual(resp.status_code, 502)
        self.assertEqual(resp.data['error_type'], 'welcome_send_failed')
        self.card.refresh_from_db()
        self.assertEqual(self.card.welcome_status, 'failed')
        self.assertNotIn('SMTP auth failed', str(resp.data))
