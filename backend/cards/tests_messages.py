"""Custom message to selected cards (POST /api/cards/send-message). Email
delivery uses Django's in-memory backend during tests — no real mail is sent."""

from __future__ import annotations

from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings

from accounts.services_email import WelcomeEmailError
from .models import BusinessCard
from .services.card_messages import MAX_RECIPIENTS
from .tests_welcome import auth_client, configure_profile, make_admin, make_card, make_user

URL = '/api/cards/send-message'


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    WELCOME_FROM_EMAIL='platform@example.com',
)
class SendMessageTests(TestCase):
    def setUp(self):
        self.user = make_user('alice')
        configure_profile(self.user, sender_email='alice@example.com')
        self.client = auth_client(self.user)

    def post(self, card_ids, subject='اجتماع', body='نص الرسالة كما كُتب.', client=None):
        return (client or self.client).post(
            URL, {'card_ids': card_ids, 'subject': subject, 'body': body}, format='json',
        )

    def test_sends_one_separate_email_per_card(self):
        a = make_card(self.user, ['a@x.com'], person_name='Ahmad')
        b = make_card(self.user, ['b@x.com', 'b2@x.com'], person_name='Basel')

        resp = self.post([a.id, b.id])

        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data['sent'], 2)
        self.assertEqual(resp.data['total'], 2)
        self.assertEqual([r['status'] for r in resp.data['results']], ['sent', 'sent'])
        self.assertEqual(resp.data['results'][0]['name'], 'Ahmad')
        # One email each, to the card's first address only — recipients never see each other.
        self.assertEqual([m.to for m in mail.outbox], [['a@x.com'], ['b@x.com']])
        self.assertTrue(all(not m.cc and not m.bcc for m in mail.outbox))

    def test_text_is_sent_exactly_as_written_from_platform_address(self):
        card = make_card(self.user, ['a@x.com'], person_name='سعادة السفير')
        body = 'مرحباً،\nنود دعوتكم إلى الاجتماع.'

        self.post([card.id], subject='دعوة', body=body)

        message = mail.outbox[0]
        self.assertEqual(message.subject, 'دعوة')
        self.assertEqual(message.body, body)  # no salutation, no extra language block
        # The ministry address is the only sender: a leftover per-user sender
        # email is neither the display name nor the Reply-To.
        self.assertEqual(message.from_email, 'platform@example.com')
        self.assertEqual(message.reply_to, [])
        self.assertNotIn('alice@example.com', message.alternatives[0][0])
        html = message.alternatives[0][0]
        self.assertIn('dir="rtl"', html)

    def test_latin_text_renders_left_to_right(self):
        card = make_card(self.user, ['a@x.com'])
        self.post([card.id], subject='Invitation', body='Dear partner, see you soon.')
        self.assertIn('dir="ltr"', mail.outbox[0].alternatives[0][0])

    def test_does_not_touch_welcome_status(self):
        card = make_card(self.user, ['a@x.com'])
        self.post([card.id])
        card.refresh_from_db()
        self.assertEqual(card.welcome_status, BusinessCard.WELCOME_NOT_SENT)

    def test_card_without_email_is_skipped(self):
        with_email = make_card(self.user, ['a@x.com'])
        without = make_card(self.user, [], person_name='No Mail')

        resp = self.post([with_email.id, without.id])

        self.assertEqual(resp.data['sent'], 1)
        self.assertEqual(resp.data['results'][1]['status'], 'no_email')
        self.assertEqual(len(mail.outbox), 1)

    def test_shared_address_is_emailed_once(self):
        a = make_card(self.user, ['same@x.com'], person_name='A')
        b = make_card(self.user, ['SAME@x.com'], person_name='B')

        resp = self.post([a.id, b.id])

        self.assertEqual([r['status'] for r in resp.data['results']], ['sent', 'duplicate_email'])
        self.assertEqual(len(mail.outbox), 1)

    def test_repeated_ids_are_sent_once(self):
        card = make_card(self.user, ['a@x.com'])
        resp = self.post([card.id, card.id])
        self.assertEqual(resp.data['total'], 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_other_users_card_is_not_found_and_not_emailed(self):
        bob = make_user('bob')
        foreign = make_card(bob, ['victim@x.com'], person_name='Secret')
        mine = make_card(self.user, ['a@x.com'])

        resp = self.post([mine.id, foreign.id])

        self.assertEqual(resp.status_code, 200)
        foreign_result = resp.data['results'][1]
        self.assertEqual(foreign_result, {'card_id': foreign.id, 'name': '', 'email': '', 'status': 'not_found'})
        self.assertEqual([m.to for m in mail.outbox], [['a@x.com']])

    def test_admin_can_message_any_card(self):
        admin = make_admin('root')
        configure_profile(admin, sender_email='root@example.com')
        card = make_card(self.user, ['a@x.com'])

        resp = self.post([card.id], client=auth_client(admin))

        self.assertEqual(resp.data['sent'], 1)

    def test_failed_delivery_is_reported_per_card(self):
        a = make_card(self.user, ['a@x.com'])
        b = make_card(self.user, ['b@x.com'])
        calls = []

        def flaky(*, to_email, **kwargs):
            calls.append(to_email)
            if to_email == 'a@x.com':
                raise WelcomeEmailError('smtp down')

        with patch('cards.services.card_messages.send_welcome_email', side_effect=flaky):
            resp = self.post([a.id, b.id])

        self.assertEqual(resp.status_code, 200)
        self.assertEqual([r['status'] for r in resp.data['results']], ['failed', 'sent'])
        self.assertEqual(resp.data['sent'], 1)
        self.assertEqual(calls, ['a@x.com', 'b@x.com'])

    def test_sends_without_any_sender_setup(self):
        user = make_user('carol')  # no profile, no sender email
        card = make_card(user, ['a@x.com'])

        resp = self.post([card.id], client=auth_client(user))

        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data['sent'], 1)
        self.assertEqual(mail.outbox[0].from_email, 'platform@example.com')

    def test_validation(self):
        card = make_card(self.user, ['a@x.com'])
        cases = [
            {'card_ids': [], 'subject': 's', 'body': 'b'},
            {'card_ids': [card.id], 'subject': '', 'body': 'b'},
            {'card_ids': [card.id], 'subject': 's', 'body': '   '},
            {'card_ids': list(range(1, MAX_RECIPIENTS + 2)), 'subject': 's', 'body': 'b'},
            {'card_ids': ['abc'], 'subject': 's', 'body': 'b'},
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                resp = self.client.post(URL, payload, format='json')
                self.assertEqual(resp.status_code, 400, resp.data)
                self.assertEqual(resp.data['error_type'], 'validation_error')
                self.assertNotIn('card_ids:', resp.data['detail'])
        self.assertEqual(len(mail.outbox), 0)

    def test_subject_newlines_are_collapsed(self):
        card = make_card(self.user, ['a@x.com'])
        self.post([card.id], subject='سطر\nثانٍ')
        self.assertEqual(mail.outbox[0].subject, 'سطر ثانٍ')

    def test_requires_authentication(self):
        from rest_framework.test import APIClient
        resp = APIClient().post(URL, {'card_ids': [1], 'subject': 's', 'body': 'b'}, format='json')
        self.assertIn(resp.status_code, (401, 403))


def _image_upload(name='poster.png', size=(1600, 2000), mode='RGB', fmt='PNG'):
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buf = io.BytesIO()
    Image.new(mode, size, 'white').save(buf, format=fmt)
    return SimpleUploadedFile(name, buf.getvalue(), content_type=f'image/{fmt.lower()}')


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    WELCOME_FROM_EMAIL='platform@example.com',
)
class SendMessageImageTests(TestCase):
    """An optional image (e.g. an announcement poster) shown inside the email."""

    def setUp(self):
        self.user = make_user('alice')
        self.client = auth_client(self.user)
        self.card = make_card(self.user, ['a@x.com'])

    def post(self, image, **extra):
        data = {'card_ids': [self.card.id], 'subject': 'إعلان', 'body': 'يرجى الاطلاع.', 'image': image}
        data.update(extra)
        return self.client.post(URL, data, format='multipart')

    def inline_parts(self, message):
        return {
            part['Content-ID']: part
            for part in message.message().walk()
            if part.get('Content-ID')
        }

    def test_image_is_embedded_inline_under_the_text(self):
        resp = self.post(_image_upload())

        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data['sent'], 1)
        message = mail.outbox[0]
        html = message.alternatives[0][0]
        self.assertIn('cid:messageimage', html)
        self.assertLess(html.index('يرجى الاطلاع.'), html.index('cid:messageimage'))
        parts = self.inline_parts(message)
        self.assertIn('<messageimage>', parts)
        self.assertIn('<welcomelogo>', parts)

    def test_image_is_scaled_down_and_reencoded(self):
        import io

        from PIL import Image

        self.post(_image_upload(size=(3000, 2000)))

        part = self.inline_parts(mail.outbox[0])['<messageimage>']
        self.assertEqual(part.get_content_type(), 'image/jpeg')
        with Image.open(io.BytesIO(part.get_payload(decode=True))) as img:
            self.assertEqual(img.size, (1200, 800))

    def test_transparent_image_stays_png(self):
        self.post(_image_upload(mode='RGBA'))
        part = self.inline_parts(mail.outbox[0])['<messageimage>']
        self.assertEqual(part.get_content_type(), 'image/png')

    def test_every_recipient_gets_the_image(self):
        other = make_card(self.user, ['b@x.com'])
        resp = self.post(_image_upload(), card_ids=[self.card.id, other.id])
        self.assertEqual(resp.data['sent'], 2)
        for message in mail.outbox:
            self.assertIn('<messageimage>', self.inline_parts(message))

    def test_without_image_has_no_image_block(self):
        resp = self.client.post(
            URL, {'card_ids': [self.card.id], 'subject': 's', 'body': 'b'}, format='multipart',
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertNotIn('cid:messageimage', mail.outbox[0].alternatives[0][0])

    def test_rejects_a_file_that_is_not_an_image(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        fake = SimpleUploadedFile('poster.png', b'not really an image', content_type='image/png')
        resp = self.post(fake)

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['error_type'], 'validation_error')
        self.assertEqual(len(mail.outbox), 0)

    def test_rejects_unsupported_type(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        resp = self.post(SimpleUploadedFile('a.pdf', b'%PDF-1.4', content_type='application/pdf'))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)
