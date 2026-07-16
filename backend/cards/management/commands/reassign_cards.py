"""Reassign ownership of business cards to another user (data-preserving).

Moves only the `owner` foreign key on the card rows. Images, sequence numbers,
contacts and every other field are untouched.

If two cards would end up under the same owner with an identical
`duplicate_hash` (which violates the per-owner unique constraint), the
colliding card's hash is re-salted (base kept, a unique suffix added) so BOTH
cards survive as separate rows — nothing is merged and nothing is lost.

    python manage.py reassign_cards --to newuser               # move ALL cards
    python manage.py reassign_cards --to newuser --from admin  # only admin's cards
    python manage.py reassign_cards --to newuser --dry-run     # preview only
"""
from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cards.models import BusinessCard

User = get_user_model()


def _resalt(existing_hash: str) -> str:
    base = (existing_hash or uuid.uuid4().hex).split(':', 1)[0]
    return f'{base[:64]}:{uuid.uuid4().hex}'[:128]


class Command(BaseCommand):
    help = 'Reassign ownership of business cards to another user (no data/image loss).'

    def add_arguments(self, parser):
        parser.add_argument('--to', dest='to_user', required=True,
                            help='Username of the account that will OWN the cards.')
        parser.add_argument('--from', dest='from_user',
                            help='Only reassign cards currently owned by this username. '
                                 'If omitted, ALL cards are reassigned.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Preview only; write nothing.')

    def handle(self, *args, **opts):
        to_username = opts['to_user']
        from_username = opts.get('from_user')
        dry = opts.get('dry_run')

        try:
            target = User.objects.get(username=to_username)
        except User.DoesNotExist:
            raise CommandError(f'المستخدم الهدف "{to_username}" غير موجود. أنشئه أولاً.')

        qs = BusinessCard.objects.all()
        if from_username:
            try:
                source = User.objects.get(username=from_username)
            except User.DoesNotExist:
                raise CommandError(f'المستخدم المصدر "{from_username}" غير موجود.')
            qs = qs.filter(owner=source)

        movable = qs.exclude(owner=target)
        total = qs.count()
        to_move = movable.count()

        if total == 0:
            self.stdout.write(self.style.WARNING('لا توجد كروت مطابقة.'))
            return

        if dry:
            self.stdout.write(
                f'[dry-run] سيتم نقل ملكية {to_move} كرت إلى "{target.username}" '
                f'(إجمالي الكروت المطابقة: {total}).'
            )
            return

        moved = 0
        resalted = 0
        with transaction.atomic():
            # Hashes already present under the target owner must stay unique.
            seen = set(
                BusinessCard.objects.filter(owner=target)
                .values_list('duplicate_hash', flat=True)
            )
            for card in movable.select_for_update().order_by('sequence_number', 'id'):
                h = card.duplicate_hash or ''
                fields = ['owner']
                if h and h in seen:
                    card.duplicate_hash = _resalt(h)
                    fields.append('duplicate_hash')
                    resalted += 1
                card.owner = target
                card.save(update_fields=fields)
                seen.add(card.duplicate_hash)
                moved += 1

        msg = f'تم نقل ملكية {moved} كرت إلى "{target.username}". الصور والبيانات والترقيم لم تتغيّر.'
        if resalted:
            msg += f' (أُعيد ترميز بصمة {resalted} كرت متكرّر لتفادي التعارض — بدون دمج أو خسارة).'
        self.stdout.write(self.style.SUCCESS(msg))
