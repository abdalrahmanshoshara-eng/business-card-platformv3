from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cards', '0009_merge_duplicate_cards'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='businesscard',
            index=models.Index(fields=['owner', '-sequence_number'], name='card_owner_seq_idx'),
        ),
    ]
