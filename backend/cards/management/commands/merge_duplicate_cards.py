"""Merge duplicate business cards (same contact) into one, without data loss.

    python manage.py merge_duplicate_cards --dry-run   # preview only
    python manage.py merge_duplicate_cards             # apply
"""
from django.core.management.base import BaseCommand

from cards.models import BusinessCard
from cards.services.merge import merge_duplicate_cards, resequence_cards


class Command(BaseCommand):
    help = 'Merge duplicate cards (grouped by owner + base duplicate hash).'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Preview without writing.')

    def handle(self, *args, **opts):
        dry = opts.get('dry_run')
        result = merge_duplicate_cards(BusinessCard.objects.all(), apply=not dry)
        if not dry:
            resequence_cards(BusinessCard.objects.all())
        prefix = '[dry-run] ' if dry else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}مجموعات مكررة: {result["duplicate_groups"]} — '
            f'كروت سيتم دمجها/حُذفت بعد الدمج: {result["cards_removed"]}'
        ))
