# Generated for Business Card Platform
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone

class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name='BusinessCard',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sequence_number', models.PositiveIntegerField(db_index=True, editable=False, unique=True)),
                ('person_name', models.CharField(blank=True, db_index=True, max_length=255)),
                ('job_title', models.CharField(blank=True, max_length=255)),
                ('company_name', models.CharField(blank=True, db_index=True, max_length=255)),
                ('mobile_numbers', models.JSONField(blank=True, default=list)),
                ('emails', models.JSONField(blank=True, default=list)),
                ('website', models.URLField(blank=True, max_length=500)),
                ('address', models.TextField(blank=True)),
                ('company_activity', models.TextField(blank=True, db_index=True)),
                ('raw_text', models.TextField(blank=True)),
                ('confidence', models.FloatField(default=0.0)),
                ('needs_review', models.BooleanField(db_index=True, default=True)),
                ('review_notes', models.TextField(blank=True)),
                ('website_visit_note', models.TextField(blank=True)),
                ('duplicate_hash', models.CharField(db_index=True, max_length=128, unique=True)),
                ('status', models.CharField(choices=[('new', 'جديد'), ('reviewed', 'تمت المراجعة'), ('needs_review', 'يحتاج مراجعة')], db_index=True, default='new', max_length=20)),
                ('front_image', models.ImageField(blank=True, null=True, upload_to='cards/front/')),
                ('back_image', models.ImageField(blank=True, null=True, upload_to='cards/back/')),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-sequence_number'],
                'indexes': [models.Index(fields=['company_name', 'person_name'], name='cards_busin_company_6ae40c_idx'), models.Index(fields=['created_at', 'status'], name='cards_busin_created_a78cf4_idx')],
            },
        ),
    ]
