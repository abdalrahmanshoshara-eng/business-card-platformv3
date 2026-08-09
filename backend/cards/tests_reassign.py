"""Tests for the reassign_cards management command (ownership transfer)."""

from __future__ import annotations

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from .models import BusinessCard
from .services.card_data import prepare_card_data

User = get_user_model()


def make_card(owner, **overrides):
    data = {'person_name': 'P', 'company_name': 'C', 'emails': [], 'mobile_numbers': []}
    data.update(overrides)
    prepared = prepare_card_data(data, infer_missing_investment=False)
    return BusinessCard.objects.create(owner=owner, **prepared)


class ReassignCardsCommandTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin', password='x', email='admin@mei.com', is_staff=True)
        self.target = User.objects.create_user(username='economy', password='x', email='economy.industry@mei.com')

    def test_reassign_from_admin_to_target_by_email(self):
        make_card(self.admin, company_name='Alpha', emails=['a@x.com'])
        make_card(self.admin, company_name='Beta', emails=['b@x.com'])
        self.assertEqual(BusinessCard.objects.filter(owner=self.admin).count(), 2)

        out = StringIO()
        call_command('reassign_cards', '--from', 'admin@mei.com', '--to', 'economy.industry@mei.com', stdout=out)

        self.assertEqual(BusinessCard.objects.filter(owner=self.admin).count(), 0)
        self.assertEqual(BusinessCard.objects.filter(owner=self.target).count(), 2)

    def test_dry_run_changes_nothing(self):
        make_card(self.admin, company_name='Alpha', emails=['a@x.com'])
        out = StringIO()
        call_command('reassign_cards', '--from', 'admin@mei.com', '--to', 'economy.industry@mei.com', '--dry-run', stdout=out)
        self.assertEqual(BusinessCard.objects.filter(owner=self.admin).count(), 1)
        self.assertEqual(BusinessCard.objects.filter(owner=self.target).count(), 0)
        self.assertIn('dry-run', out.getvalue())

    def test_unknown_target_raises(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command('reassign_cards', '--to', 'nobody@nowhere.com')

    def test_duplicate_hash_collision_is_resalted_not_merged(self):
        # Target already owns a card; admin owns an identical-contact card. Moving
        # it must keep BOTH rows (re-salt the hash), never merge/lose data.
        make_card(self.target, company_name='Same', emails=['same@x.com'])
        make_card(self.admin, company_name='Same', emails=['same@x.com'])
        call_command('reassign_cards', '--from', 'admin@mei.com', '--to', 'economy.industry@mei.com', stdout=StringIO())
        self.assertEqual(BusinessCard.objects.filter(owner=self.target).count(), 2)
