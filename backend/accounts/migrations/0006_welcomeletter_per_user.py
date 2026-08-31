"""Turn the welcome letter from one platform-wide row into one row per user.

The letter is now personal: every account writes its own wording and can reset
it back to the ministry default. The previous shape — a single row shared by
everyone — has no per-user meaning, so any existing row is dropped before the
owner column is added. Nothing is lost that a reset would not have produced
anyway: a user with no row simply sends the shipped default letter.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def drop_platform_wide_rows(apps, schema_editor):
    """Clear the old singleton so the non-null owner column can be added."""
    apps.get_model('accounts', 'WelcomeLetter').objects.all().delete()


def noop(apps, schema_editor):
    """Reversing only restores an empty table; the old shared row cannot be
    reconstructed, and re-creating a blank one would be indistinguishable."""


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_remove_profile_welcome_message_en_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(drop_platform_wide_rows, noop),
        migrations.RemoveField(
            model_name='welcomeletter',
            name='updated_by',
        ),
        migrations.AddField(
            model_name='welcomeletter',
            name='user',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='welcome_letter',
                to=settings.AUTH_USER_MODEL,
            ),
            preserve_default=False,
        ),
    ]
