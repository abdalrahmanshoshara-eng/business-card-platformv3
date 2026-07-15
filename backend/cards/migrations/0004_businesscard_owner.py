import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('cards', '0003_rename_cards_busin_company_6ae40c_idx_cards_busin_company_120b35_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='businesscard',
            name='owner',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='business_cards',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
