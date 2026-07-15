"""Merge duplicate cards on migrate (e.g. after git pull on the server).

Data-preserving: unions contacts, fills blanks, keeps conflicting values in
review_notes, preserves images. Only duplicate rows are removed.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    from cards.services.merge import merge_duplicate_cards, resequence_cards

    BusinessCard = apps.get_model('cards', 'BusinessCard')
    merge_duplicate_cards(BusinessCard.objects.all(), apply=True)
    resequence_cards(BusinessCard.objects.all())


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cards', '0008_apply_exact_country_map'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
