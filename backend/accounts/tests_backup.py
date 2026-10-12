"""Full-database .sql backup: who may download it, and that it restores."""

import io
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from cards.models import BusinessCard
from cards.tests import make_card

from .services_backup import restore_backup, write_backup

User = get_user_model()


def client_for(user=None):
    client = APIClient()
    if user is not None:
        client.force_authenticate(user)
    return client


def take_backup() -> str:
    out = io.BytesIO()
    write_backup(out)
    return out.getvalue().decode('utf-8')


class BackupDownloadTests(TestCase):
    def setUp(self):
        self.root = User.objects.create_superuser('root', 'root@x.com', 'StrongPass!234')
        make_card(owner=self.root, company_name="O'Brien & Co", person_name='أحمد الخالد')

    def test_only_superusers_may_download(self):
        staff = User.objects.create_user('staff', password='StrongPass!234', is_staff=True)
        regular = User.objects.create_user('regular', password='StrongPass!234')
        for user in (None, regular, staff):
            with self.subTest(user=getattr(user, 'username', 'anonymous')):
                self.assertEqual(client_for(user).get('/api/admin/backup').status_code, 403)

    def test_superuser_downloads_a_sql_file(self):
        resp = client_for(self.root).get('/api/admin/backup')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('attachment;', resp['Content-Disposition'])
        self.assertRegex(resp['Content-Disposition'], r'business-cards-backup-\d{8}-\d{4}\.sql')
        self.assertEqual(resp['Cache-Control'], 'no-store')
        sql = b''.join(resp.streaming_content).decode('utf-8')
        self.assertTrue(sql.startswith('-- Business card platform — data backup'))
        self.assertIn('INSERT INTO "cards_businesscard"', sql)
        self.assertIn("'O''Brien & Co'", sql)  # quotes escaped
        self.assertIn('أحمد الخالد', sql)
        self.assertNotIn('INSERT INTO "django_session"', sql)
        self.assertTrue(sql.rstrip().endswith('COMMIT;'))


class BackupRestoreTests(TransactionTestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', 'owner@x.com', 'StrongPass!234')
        self.card = make_card(
            owner=self.owner, person_name="Ali 'The' Hassan", company_name='شركة النور\nNour Co',
            emails=['ali@nour.com'], mobile_numbers=['+963944123456'], address='',
        )

    def snapshot(self):
        return sorted(
            BusinessCard.objects.values_list(
                'id', 'sequence_number', 'person_name', 'company_name', 'emails', 'mobile_numbers', 'owner_id',
            )
        )

    def test_restore_brings_back_exactly_the_backed_up_data(self):
        before = self.snapshot()
        sql = take_backup()

        # Lose and change data after the backup.
        BusinessCard.objects.filter(pk=self.card.pk).update(company_name='changed')
        make_card(owner=self.owner, company_name='Added after backup')
        User.objects.create_user('intruder', password='StrongPass!234')

        restore_backup(sql)

        self.assertEqual(self.snapshot(), before)
        self.assertFalse(User.objects.filter(username='intruder').exists())
        self.assertTrue(User.objects.get(username='owner').check_password('StrongPass!234'))
        # New rows after a restore still get fresh ids and numbers.
        newer = make_card(owner=self.owner, company_name='After restore')
        self.assertGreater(newer.id, self.card.id)

    def test_failed_restore_changes_nothing(self):
        sql = take_backup()
        BusinessCard.objects.filter(pk=self.card.pk).update(company_name='kept')
        broken = sql.replace('COMMIT;', 'INSERT INTO no_such_table VALUES (1);\nCOMMIT;')
        with self.assertRaises(Exception):
            restore_backup(broken)
        self.assertEqual(BusinessCard.objects.get(pk=self.card.pk).company_name, 'kept')

    def test_rejects_a_file_that_is_not_a_platform_backup(self):
        with self.assertRaises(ValueError):
            restore_backup('DROP TABLE cards_businesscard;')
        self.assertTrue(BusinessCard.objects.filter(pk=self.card.pk).exists())

    def test_restore_command_requires_confirmation_and_restores(self):
        sql = take_backup()
        BusinessCard.objects.all().delete()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'backup.sql'
            path.write_text(sql, encoding='utf-8')
            with self.assertRaises(CommandError):
                call_command('restore_sql_backup', str(path), '--skip-migrate')
            self.assertFalse(BusinessCard.objects.exists())

            call_command('restore_sql_backup', str(path), '--yes', '--skip-migrate', stdout=io.StringIO())
        self.assertTrue(BusinessCard.objects.filter(pk=self.card.pk).exists())
