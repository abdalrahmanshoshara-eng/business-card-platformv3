"""Restore a ``.sql`` backup downloaded from the platform (Admin → Backup).

    python manage.py restore_sql_backup business-cards-backup-20261011-1200.sql --yes

Migrates the database first (the backup carries data only), then REPLACES the
content of every table with the backup's, in one transaction. Card images are
not part of the backup: restore the MEDIA_ROOT folder separately.
"""
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from accounts.services_backup import restore_backup


class Command(BaseCommand):
    help = 'Restore a .sql data backup downloaded from the platform (replaces all data).'

    def add_arguments(self, parser):
        parser.add_argument('path', help='Path to the .sql backup file.')
        parser.add_argument('--yes', action='store_true',
                            help='Confirm that ALL current data will be replaced by the backup.')
        parser.add_argument('--skip-migrate', action='store_true',
                            help='Do not run migrations before restoring.')

    def handle(self, *args, **opts):
        path = Path(opts['path'])
        if not path.is_file():
            raise CommandError(f'الملف غير موجود: {path}')
        if not opts['yes']:
            raise CommandError('الاسترجاع يستبدل كل البيانات الحالية. أعد التشغيل مع --yes للتأكيد.')

        sql = path.read_text(encoding='utf-8')
        if not opts['skip_migrate']:
            call_command('migrate', interactive=False, verbosity=0)
        try:
            restore_backup(sql)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        except Exception as exc:
            raise CommandError(f'فشل الاسترجاع ولم يتغيّر شيء في قاعدة البيانات: {exc}') from exc
        self.stdout.write(self.style.SUCCESS(f'تم استرجاع النسخة الاحتياطية: {path.name}'))
