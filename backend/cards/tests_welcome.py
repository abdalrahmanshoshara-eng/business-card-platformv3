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


def make_card(owner, emails, **overrides):
    fields = {'person_name': 'P', 'company_name': 'C', 'emails': emails}
    fields.update(overrides)
    data = prepare_card_data(fields, infer_missing_investment=False)
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
        self.card = make_card(self.user, ['recipient@corp.com'], printed_languages=['ar'])

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
        # Arabic-only card → one Arabic block, sent exactly as the owner wrote it.
        self.assertEqual(msg.subject, 'أهلاً')
        self.assertEqual(msg.body, 'مرحبًا بك')
        # A styled HTML alternative is attached and frames the user's email as sender.
        self.assertTrue(msg.alternatives)
        html, mime = msg.alternatives[0]
        self.assertEqual(mime, 'text/html')
        self.assertIn('sender@example.com', html)
        self.assertIn('مرحبًا بك', html)
        # Ministry identity: header references the inline logo (CID) and the
        # logo image is embedded so external recipients can see it.
        self.assertIn('cid:welcomelogo', html)
        self.assertTrue(msg.attachments)
        self.assertEqual(msg.mixed_subtype, 'related')
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
        # The test-send endpoint is admin-only.
        admin = User.objects.create_user(username='admin_send', password='x', is_staff=True)
        configure_profile(admin)
        resp = auth_client(admin).post('/api/auth/welcome-test', {'to': 'me@test.com'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertTrue(resp.data['sent'])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['me@test.com'])
        self.assertIn('platform@site.com', mail.outbox[0].from_email)

    def test_welcome_test_endpoint_forbidden_for_regular_user(self):
        resp = self.client.post('/api/auth/welcome-test', {'to': 'me@test.com'}, format='json')
        self.assertIn(resp.status_code, (403, 401))
        self.assertEqual(len(mail.outbox), 0)

    def test_welcome_test_endpoint_rejects_invalid_email(self):
        admin = User.objects.create_user(username='admin_bad', password='x', is_staff=True)
        resp = auth_client(admin).post('/api/auth/welcome-test', {'to': 'not-an-email'}, format='json')
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


@override_settings(WELCOME_FROM_EMAIL='platform@site.com')
class WelcomeLanguageTests(TestCase):
    """The email is written in the card's language(s): Arabic always, plus the
    card's own language beside it when the card is not Arabic — one email."""

    def setUp(self):
        self.user = make_user('lang')
        configure_profile(self.user)  # custom Arabic letter, default secondary
        self.client = auth_client(self.user)

    def send(self, card):
        resp = self.client.post(f'/api/cards/{card.id}/send-welcome', {}, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        return mail.outbox[-1]

    def test_arabic_card_gets_arabic_only(self):
        card = make_card(self.user, ['ar@corp.com'], printed_languages=['ar'])
        msg = self.send(card)
        self.assertEqual(msg.subject, 'أهلاً')
        self.assertNotIn('Message of Appreciation', msg.body)

    def test_english_card_gets_arabic_and_english_in_one_email(self):
        card = make_card(self.user, ['en@corp.com'], printed_languages=['en'])
        msg = self.send(card)
        self.assertEqual(len(mail.outbox), 1)  # ONE email, not two
        self.assertEqual(msg.subject, 'أهلاً | Message of Appreciation')
        self.assertIn('مرحبًا بك', msg.body)
        self.assertIn('Ministry of Economy and Industry', msg.body)
        # Arabic first, then the card's language.
        self.assertLess(msg.body.index('مرحبًا بك'), msg.body.index('Ministry of Economy'))

    def test_bilingual_card_gets_both(self):
        card = make_card(self.user, ['both@corp.com'], printed_languages=['ar', 'en'])
        msg = self.send(card)
        self.assertIn('مرحبًا بك', msg.body)
        self.assertIn('Message of Appreciation', msg.subject)

    def test_german_card_uses_reviewed_template_without_translating(self):
        card = make_card(self.user, ['de@corp.com'], printed_languages=['de'])
        with patch('cards.services.welcome_translate.translate_letter') as translate:
            msg = self.send(card)
        translate.assert_not_called()  # a reviewed German letter needs no API call
        self.assertIn('Dankschreiben', msg.subject)
        self.assertIn('Ministerium für Wirtschaft und Industrie', msg.body)
        html = msg.alternatives[0][0]
        self.assertIn('dir="ltr" lang="de"', html)   # German block reads LTR…
        self.assertIn('dir="rtl" lang="ar"', html)   # …beside the Arabic one

    def test_language_without_template_is_translated_once(self):
        card = make_card(self.user, ['ja@corp.com'], printed_languages=['ja'])
        with patch(
            'cards.services.welcome_translate.translate_letter',
            return_value=('感謝状', '{{salutation}}\n\n拝啓'),
        ) as translate:
            msg = self.send(card)
        translate.assert_called_once()
        self.assertIn('感謝状', msg.subject)
        self.assertIn('拝啓', msg.body)

    def test_failed_translation_falls_back_to_english_never_empty(self):
        card = make_card(self.user, ['ja2@corp.com'], printed_languages=['ja'])
        with patch('cards.services.welcome_translate.translate_letter', return_value=None):
            msg = self.send(card)
        self.assertIn('Message of Appreciation', msg.subject)
        self.assertIn('Ministry of Economy and Industry', msg.body)

    def test_legacy_card_without_languages_is_detected_from_its_text(self):
        arabic = make_card(self.user, ['legacy-ar@corp.com'], person_name='أحمد', company_name='شركة النور')
        self.assertNotIn('Message of Appreciation', self.send(arabic).subject)

        latin = make_card(self.user, ['legacy-en@corp.com'], person_name='John Smith', company_name='Acme')
        self.assertIn('Message of Appreciation', self.send(latin).subject)


@override_settings(WELCOME_FROM_EMAIL='platform@site.com')
class WelcomeSalutationTests(TestCase):
    """The letter opens with a salutation that fits the specific card."""

    def setUp(self):
        self.user = make_user('salut')
        # Default letter (blank profile message) so the salutation token applies.
        configure_profile(self.user, welcome_subject='', welcome_message='')
        self.client = auth_client(self.user)

    def send(self, card):
        resp = self.client.post(f'/api/cards/{card.id}/send-welcome', {}, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        return mail.outbox[-1]

    def test_uses_the_generated_salutation_and_leaves_no_placeholder(self):
        card = make_card(
            self.user, ['min@gov.sy'], printed_languages=['ar'],
            salutation_ar='معالي وزير الصناعة المحترم،',
        )
        msg = self.send(card)
        self.assertIn('معالي وزير الصناعة المحترم،', msg.body)
        self.assertNotIn('{{salutation}}', msg.body)
        self.assertNotIn('السادة الضيوف الكرام', msg.body)

    def test_each_language_block_uses_its_own_salutation(self):
        card = make_card(
            self.user, ['dual@corp.com'], printed_languages=['ar', 'en'],
            salutation_ar='حضرة السيد أحمد المحترم،', salutation_en='Dear Mr. Ahmad,',
        )
        msg = self.send(card)
        self.assertIn('حضرة السيد أحمد المحترم،', msg.body)
        self.assertIn('Dear Mr. Ahmad,', msg.body)

    def test_native_salutation_used_for_the_cards_own_language(self):
        card = make_card(
            self.user, ['de2@corp.com'], printed_languages=['de'],
            salutation_en='Dear Dr. Weber,', salutation_native='Sehr geehrter Herr Dr. Weber,',
        )
        msg = self.send(card)
        self.assertIn('Sehr geehrter Herr Dr. Weber,', msg.body)
        self.assertNotIn('Dear Dr. Weber,', msg.body)

    def test_legacy_card_falls_back_to_a_rule_based_salutation(self):
        card = make_card(
            self.user, ['legacy@corp.com'], printed_languages=['ar'],
            company_name_ar='شركة النور للتجارة',
        )
        msg = self.send(card)
        self.assertIn('السادة في شركة النور للتجارة الكرام،', msg.body)

    def test_card_with_nothing_to_address_keeps_the_generic_wording(self):
        card = make_card(
            self.user, ['blank@corp.com'], printed_languages=['ar'],
            person_name='', company_name='',
        )
        self.assertIn('السادة الضيوف الكرام،', self.send(card).body)

    def test_owner_text_without_the_token_is_sent_verbatim(self):
        configure_profile(self.user, welcome_subject='خاص', welcome_message='نصّي أنا فقط.')
        # Re-fetch so the request user does not carry the profile cached in setUp.
        self.user = User.objects.get(pk=self.user.pk)
        self.client = auth_client(self.user)
        card = make_card(self.user, ['verbatim@corp.com'], printed_languages=['ar'],
                         salutation_ar='حضرة السيد المحترم،')
        msg = self.send(card)
        self.assertEqual(msg.body, 'نصّي أنا فقط.')
        self.assertNotIn('حضرة السيد المحترم،', msg.body)


class DefaultWelcomeLetterTests(TestCase):
    """The ministry's letter of appreciation is the default for every account."""

    def test_profile_api_returns_the_default_letter_in_both_languages(self):
        user = make_user('defaults')
        resp = auth_client(user).get('/api/auth/me')
        cfg = resp.data['welcome_email']
        self.assertEqual(cfg['welcome_subject'], 'رسالة شكر وتقدير')
        self.assertEqual(cfg['welcome_subject_en'], 'Message of Appreciation')
        self.assertIn('نائب وزير الاقتصاد والصناعة', cfg['welcome_message'])
        self.assertIn('Deputy Minister of Economy and Industry', cfg['welcome_message_en'])
        # The salutation placeholder is exposed so the owner can keep or drop it.
        self.assertIn('{{salutation}}', cfg['welcome_message'])
        self.assertIn('{{salutation}}', cfg['welcome_message_en'])

    def test_secondary_language_letter_is_editable(self):
        user = make_user('editor')
        resp = auth_client(user).patch('/api/auth/profile', {
            'welcome_subject_en': 'Thank you',
            'welcome_message_en': 'Dear guest,',
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data['welcome_email']['welcome_subject_en'], 'Thank you')
        self.assertEqual(Profile.objects.get(user=user).welcome_message_en, 'Dear guest,')
