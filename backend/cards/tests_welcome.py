"""Welcome-email feature tests. Email delivery uses Django's in-memory backend
during tests (django.core.mail.outbox) — no real mail is sent."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import Profile, WelcomeLetter
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
    """Give the user the one welcome setting they own: a sender email."""
    defaults = {'sender_email': 'sender@example.com'}
    defaults.update(overrides)
    Profile.objects.update_or_create(user=user, defaults=defaults)


def set_letter(user, **fields):
    """Give this user their own letter. Any field left out stays blank, i.e.
    falls back to the reviewed default for that language."""
    letter = WelcomeLetter.load(user)
    letter.user = user
    for name, value in fields.items():
        setattr(letter, name, value)
    letter.save()
    return letter


def make_admin(username):
    return User.objects.create_user(
        username=username, password='StrongPass!234', email=f'{username}@x.com', is_staff=True,
    )


class ProfileConfigApiTests(TestCase):
    """A regular user owns exactly one welcome setting: the sender email."""

    def test_saves_sender_email(self):
        user = make_user('alice')
        resp = auth_client(user).patch(
            '/api/auth/profile', {'sender_email': 'alice@example.com'}, format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        cfg = resp.data['welcome_email']
        self.assertEqual(cfg['sender_email'], 'alice@example.com')
        self.assertTrue(cfg['configured'])
        self.assertEqual(Profile.objects.get(user=user).sender_email, 'alice@example.com')

    def test_not_configured_until_sender_email_set(self):
        user = make_user('bob')
        resp = auth_client(user).patch('/api/auth/profile', {'phone': '0900'}, format='json')
        self.assertFalse(resp.data['welcome_email']['configured'])

    def test_profile_endpoint_refuses_letter_fields(self):
        # The letter has its own endpoint. Rejected outright rather than ignored,
        # so a stale client never believes this call saved its wording.
        user = make_user('carla')
        resp = auth_client(user).patch(
            '/api/auth/profile', {'welcome_message': 'نصّي أنا'}, format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('welcome_message', resp.data)
        self.assertFalse(WelcomeLetter.load(user).is_customized)


@override_settings(WELCOME_FROM_EMAIL='platform@site.com')
class SendWelcomeApiTests(TestCase):
    def setUp(self):
        self.user = make_user('carol')
        configure_profile(self.user)
        set_letter(self.user, subject_ar='أهلاً', body_ar='مرحبًا بك')
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
        # Arabic-only card → one Arabic block, sent exactly as the admin wrote it.
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
        admin = make_admin('admin_send')
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
        configure_profile(self.user)
        # Custom Arabic letter, secondary language left on the reviewed default.
        set_letter(self.user, subject_ar='أهلاً', body_ar='مرحبًا بك')
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
        # Platform letter left untouched → the default letter, which carries the
        # salutation token.
        configure_profile(self.user)
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

    def test_letter_without_the_token_is_sent_verbatim(self):
        set_letter(self.user, subject_ar='خاص', body_ar='نصّي أنا فقط.')
        card = make_card(self.user, ['verbatim@corp.com'], printed_languages=['ar'],
                         salutation_ar='حضرة السيد المحترم،')
        msg = self.send(card)
        self.assertEqual(msg.body, 'نصّي أنا فقط.')
        self.assertNotIn('حضرة السيد المحترم،', msg.body)


@override_settings(WELCOME_FROM_EMAIL='platform@site.com')
class SalutationPlaceholderGuardTests(TestCase):
    """No email may ever go out carrying the raw placeholder."""

    def test_placeholder_is_replaced_even_when_composing_the_blocks_fails(self):
        user = make_user('guarded')
        configure_profile(user)
        card = make_card(user, ['guard@corp.com'], printed_languages=['ar'])
        with patch(
            'cards.views.build_welcome_sections', side_effect=RuntimeError('boom'),
        ):
            resp = auth_client(user).post(
                f'/api/cards/{card.id}/send-welcome', {}, format='json',
            )
        # The send still succeeds, on the default letter…
        self.assertEqual(resp.status_code, 200, resp.data)
        body = mail.outbox[-1].body
        # …and the placeholder is gone, replaced by the generic wording.
        self.assertNotIn('{{salutation}}', body)
        self.assertIn('السادة الضيوف الكرام،', body)

    def test_admin_test_send_contains_no_placeholder(self):
        admin = make_admin('tester')
        configure_profile(admin)
        resp = auth_client(admin).post('/api/auth/welcome-test', {'to': 'me@test.com'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertNotIn('{{salutation}}', mail.outbox[-1].body)
        self.assertIn('السادة الضيوف الكرام،', mail.outbox[-1].body)


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

    def test_every_user_starts_on_the_default_and_may_edit(self):
        resp = auth_client(make_user('viewer')).get('/api/auth/welcome-letter')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertTrue(resp.data['can_edit_letter'])
        self.assertFalse(resp.data['is_customized'])
        self.assertIn('نائب وزير الاقتصاد والصناعة', resp.data['welcome_message'])

    def test_test_send_stays_admin_only(self):
        # Sending to an arbitrary address is a mail-config diagnostic, not part
        # of owning your letter.
        self.assertFalse(auth_client(make_user('plain')).get(
            '/api/auth/welcome-letter').data['can_test_send'])
        self.assertTrue(auth_client(make_admin('boss')).get(
            '/api/auth/welcome-letter').data['can_test_send'])


@override_settings(WELCOME_FROM_EMAIL='platform@site.com')
class PersonalLetterTests(TestCase):
    """Every account owns its letter: anyone may rewrite theirs, and one
    account's wording never reaches another's recipients."""

    def test_any_user_can_edit_their_own_letter(self):
        user = make_user('grunt')
        resp = auth_client(user).patch(
            '/api/auth/welcome-letter',
            {'welcome_subject': 'تحياتي', 'welcome_message': 'نصّي أنا'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertTrue(resp.data['is_customized'])
        self.assertEqual(WelcomeLetter.load(user).body_ar, 'نصّي أنا')

    def test_the_edited_letter_is_what_that_user_sends(self):
        user = make_user('writer')
        configure_profile(user)
        auth_client(user).patch(
            '/api/auth/welcome-letter',
            {'welcome_subject': 'تحياتي', 'welcome_message': 'نصّي أنا'},
            format='json',
        )
        card = make_card(user, ['mine@corp.com'], printed_languages=['ar'])
        send = auth_client(user).post(f'/api/cards/{card.id}/send-welcome', {}, format='json')
        self.assertEqual(send.status_code, 200, send.data)
        self.assertEqual(mail.outbox[-1].subject, 'تحياتي')
        self.assertEqual(mail.outbox[-1].body, 'نصّي أنا')

    def test_one_users_letter_does_not_leak_into_anothers(self):
        author = make_user('author')
        auth_client(author).patch(
            '/api/auth/welcome-letter',
            {'welcome_subject': 'خاص بي', 'welcome_message': 'نصّ خاص جدًا.'},
            format='json',
        )

        other = make_user('bystander')
        configure_profile(other)
        seen = auth_client(other).get('/api/auth/welcome-letter').data
        self.assertFalse(seen['is_customized'])
        self.assertEqual(seen['welcome_subject'], 'رسالة شكر وتقدير')

        card = make_card(other, ['other@corp.com'], printed_languages=['ar'])
        auth_client(other).post(f'/api/cards/{card.id}/send-welcome', {}, format='json')
        self.assertEqual(mail.outbox[-1].subject, 'رسالة شكر وتقدير')
        self.assertNotIn('نصّ خاص جدًا.', mail.outbox[-1].body)

    def test_blanking_every_field_is_the_same_as_a_reset(self):
        user = make_user('blanker')
        set_letter(user, subject_ar='شيء', body_ar='نصّ')
        resp = auth_client(user).patch(
            '/api/auth/welcome-letter',
            {'welcome_subject': '', 'welcome_message': '', 'welcome_subject_en': '', 'welcome_message_en': ''},
            format='json',
        )
        self.assertFalse(resp.data['is_customized'])
        # No row of empty strings left pinned behind.
        self.assertFalse(WelcomeLetter.objects.filter(user=user).exists())
        self.assertEqual(resp.data['welcome_subject'], 'رسالة شكر وتقدير')

    def test_letter_is_removed_with_its_owner(self):
        user = make_user('departing')
        set_letter(user, body_ar='نصّ')
        user.delete()
        self.assertFalse(WelcomeLetter.objects.exists())


@override_settings(WELCOME_FROM_EMAIL='platform@site.com')
class ResetWelcomeLetterTests(TestCase):
    """The reset button puts this account's letter back to the ministry default."""

    def setUp(self):
        self.admin = make_user('resetter')
        set_letter(
            self.admin,
            subject_ar='نصّ مؤقت', body_ar='نصّ مؤقت للعرض.',
            subject_en='Temporary', body_en='Temporary body.',
        )

    def test_reset_restores_the_default_letter(self):
        resp = auth_client(self.admin).post('/api/auth/welcome-letter/reset', {}, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertFalse(resp.data['is_customized'])
        self.assertEqual(resp.data['welcome_subject'], 'رسالة شكر وتقدير')
        self.assertIn('نائب وزير الاقتصاد والصناعة', resp.data['welcome_message'])
        self.assertEqual(resp.data['welcome_subject_en'], 'Message of Appreciation')

    def test_reset_drops_the_row_rather_than_copying_the_template(self):
        # Dropping it keeps the letter tracking the shipped default, so a future
        # correction to the template reaches everyone without another reset.
        auth_client(self.admin).post('/api/auth/welcome-letter/reset', {}, format='json')
        self.assertFalse(WelcomeLetter.objects.filter(user=self.admin).exists())
        self.assertEqual(WelcomeLetter.load(self.admin).body_ar, '')

    def test_reset_then_send_uses_the_official_letter(self):
        configure_profile(self.admin)
        auth_client(self.admin).post('/api/auth/welcome-letter/reset', {}, format='json')
        card = make_card(self.admin, ['after@corp.com'], printed_languages=['ar'])
        auth_client(self.admin).post(f'/api/cards/{card.id}/send-welcome', {}, format='json')
        self.assertEqual(mail.outbox[-1].subject, 'رسالة شكر وتقدير')
        self.assertNotIn('نصّ مؤقت', mail.outbox[-1].body)

    def test_reset_is_idempotent(self):
        client = auth_client(self.admin)
        client.post('/api/auth/welcome-letter/reset', {}, format='json')
        resp = client.post('/api/auth/welcome-letter/reset', {}, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertFalse(resp.data['is_customized'])

    def test_reset_only_touches_the_callers_own_letter(self):
        other = make_user('untouched')
        set_letter(other, subject_ar='نصّ الآخر', body_ar='يبقى كما هو.')
        auth_client(self.admin).post('/api/auth/welcome-letter/reset', {}, format='json')
        self.assertEqual(WelcomeLetter.load(other).body_ar, 'يبقى كما هو.')
