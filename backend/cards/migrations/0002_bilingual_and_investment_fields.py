from django.db import migrations, models


def copy_existing_names(apps, schema_editor):
    BusinessCard = apps.get_model('cards', 'BusinessCard')
    for card in BusinessCard.objects.all().iterator():
        changed = False
        if card.person_name and not card.person_name_ar and not card.person_name_en:
            card.person_name_ar = card.person_name
            changed = True
        if card.job_title and not card.job_title_ar and not card.job_title_en:
            card.job_title_ar = card.job_title
            changed = True
        if card.company_name and not card.company_name_ar and not card.company_name_en:
            card.company_name_ar = card.company_name
            changed = True
        if changed:
            card.save(update_fields=['person_name_ar', 'job_title_ar', 'company_name_ar'])


class Migration(migrations.Migration):

    dependencies = [
        ('cards', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='businesscard',
            name='company_name_ar',
            field=models.CharField(blank=True, db_index=True, max_length=255),
        ),
        migrations.AddField(
            model_name='businesscard',
            name='company_name_en',
            field=models.CharField(blank=True, db_index=True, max_length=255),
        ),
        migrations.AddField(
            model_name='businesscard',
            name='investment_type',
            field=models.CharField(blank=True, db_index=True, max_length=255),
        ),
        migrations.AddField(
            model_name='businesscard',
            name='investment_type_other',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='businesscard',
            name='job_title_ar',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='businesscard',
            name='job_title_en',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='businesscard',
            name='person_name_ar',
            field=models.CharField(blank=True, db_index=True, max_length=255),
        ),
        migrations.AddField(
            model_name='businesscard',
            name='person_name_en',
            field=models.CharField(blank=True, db_index=True, max_length=255),
        ),
        migrations.RunPython(copy_existing_names, migrations.RunPython.noop),
    ]
