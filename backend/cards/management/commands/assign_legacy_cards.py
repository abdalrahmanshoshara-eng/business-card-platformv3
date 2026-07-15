from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from cards.models import BusinessCard

User = get_user_model()


class Command(BaseCommand):
    help = (
        'Assign legacy business cards that have no owner to an admin user. '
        'Cards without an owner remain visible to admins only until assigned.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            help='Username of the admin to receive the legacy cards. '
                 'If omitted and exactly one superuser exists, it is used automatically.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report what would change without writing anything.',
        )

    def handle(self, *args, **options):
        username = options.get('username')
        dry_run = options.get('dry_run')

        if username:
            try:
                target = User.objects.get(username=username)
            except User.DoesNotExist:
                raise CommandError(f'المستخدم "{username}" غير موجود.')
            if not (target.is_staff or target.is_superuser):
                raise CommandError(f'المستخدم "{username}" ليس مشرفاً (is_staff/is_superuser).')
        else:
            superusers = list(User.objects.filter(is_superuser=True))
            if len(superusers) == 1:
                target = superusers[0]
                self.stdout.write(f'لم يُحدَّد مستخدم؛ سيتم الإسناد تلقائياً إلى المشرف الوحيد: {target.username}')
            elif len(superusers) == 0:
                raise CommandError('لا يوجد أي superuser. أنشئ حساب مشرف أولاً أو مرّر --username.')
            else:
                raise CommandError('يوجد أكثر من superuser. حدّد المستخدم عبر --username.')

        legacy = BusinessCard.objects.filter(owner__isnull=True)
        count = legacy.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS('لا توجد كروت بلا مالك.'))
            return

        if dry_run:
            self.stdout.write(f'[dry-run] سيتم إسناد {count} كرت إلى "{target.username}".')
            return

        updated = legacy.update(owner=target)
        self.stdout.write(self.style.SUCCESS(f'تم إسناد {updated} كرت إلى "{target.username}".'))
