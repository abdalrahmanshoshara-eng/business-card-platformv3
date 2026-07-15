"""Data migration for existing/legacy cards.

Runs automatically on ``migrate`` (e.g. after ``git pull`` on the server):
1. Backfills ``country`` from each card's address/phone.
2. Assigns any card without an owner to the earliest superuser (the admin),
   so legacy cards — and their already-present images — become owned by admin
   without any data loss. No cards or images are deleted.

If no superuser exists yet, ownership assignment is skipped (cards stay
admin-only until a superuser is created and ``assign_legacy_cards`` is run).
"""
from django.db import migrations


def forwards(apps, schema_editor):
    from cards.services.normalization import derive_country

    BusinessCard = apps.get_model('cards', 'BusinessCard')
    User = apps.get_model('auth', 'User')

    # 1) Backfill country where empty.
    to_update = []
    for card in BusinessCard.objects.all().only('id', 'address', 'mobile_numbers', 'country'):
        if (card.country or '').strip():
            continue
        country = derive_country({'address': card.address, 'mobile_numbers': card.mobile_numbers})
        if country:
            card.country = country
            to_update.append(card)
    if to_update:
        BusinessCard.objects.bulk_update(to_update, ['country'], batch_size=200)

    # 2) Assign ownerless (legacy) cards to the earliest superuser.
    admin = User.objects.filter(is_superuser=True).order_by('date_joined', 'id').first()
    if admin:
        BusinessCard.objects.filter(owner__isnull=True).update(owner=admin)


def backwards(apps, schema_editor):
    # Non-destructive: keep derived country and ownership.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cards', '0006_businesscard_country'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
