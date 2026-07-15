"""Apply exact per-card countries (built from the bilingual country sheet).

Runs on ``migrate``. Uses cards/data/country_by_sequence.json to set the
country for existing cards by their sequence_number, overriding the value
derived in 0007 where an exact match exists. Cards not in the map keep
whatever 0007 derived (or stay empty). Non-destructive.
"""
import json
from pathlib import Path

from django.db import migrations

CMAP = Path(__file__).resolve().parent.parent / 'data' / 'country_by_sequence.json'


def forwards(apps, schema_editor):
    if not CMAP.exists():
        return
    mapping = json.loads(CMAP.read_text(encoding='utf-8'))
    if not mapping:
        return
    BusinessCard = apps.get_model('cards', 'BusinessCard')
    to_update = []
    for card in BusinessCard.objects.all().only('id', 'sequence_number', 'country'):
        country = mapping.get(str(card.sequence_number))
        if country and card.country != country:
            card.country = country
            to_update.append(card)
    if to_update:
        BusinessCard.objects.bulk_update(to_update, ['country'], batch_size=200)


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cards', '0007_backfill_country_and_owner'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
