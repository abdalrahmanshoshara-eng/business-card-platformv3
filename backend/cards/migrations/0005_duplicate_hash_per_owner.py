from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cards', '0004_businesscard_owner'),
    ]

    operations = [
        migrations.AlterField(
            model_name='businesscard',
            name='duplicate_hash',
            field=models.CharField(db_index=True, max_length=128),
        ),
        migrations.AddConstraint(
            model_name='businesscard',
            constraint=models.UniqueConstraint(
                fields=('owner', 'duplicate_hash'),
                name='uniq_owner_duplicate_hash',
            ),
        ),
    ]
