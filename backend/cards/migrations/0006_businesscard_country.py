from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cards', '0005_duplicate_hash_per_owner'),
    ]

    operations = [
        migrations.AddField(
            model_name='businesscard',
            name='country',
            field=models.CharField(blank=True, db_index=True, max_length=100),
        ),
    ]
