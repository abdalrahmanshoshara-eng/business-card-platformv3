"""Move accounts still sitting on the OLD default welcome text onto the new one.

The default letter now lives in ``accounts/welcome_templates.py`` and is applied
whenever a profile leaves the message blank. Profiles created before that simply
saved a copy of the old default (the profile form pre-filled it), so they would
have kept sending the superseded wording forever. Clearing that exact copy opts
them back into the default.

Only a byte-for-byte copy of the old default is cleared — a profile whose owner
actually wrote their own letter is left untouched.
"""

from django.db import migrations

OLD_DEFAULT_SUBJECT = 'ترحيب من وزارة الاقتصاد والصناعة'
# The subject the profile form used to pre-fill client-side.
OLD_FORM_SUBJECT = 'رسالة ترحيب'
OLD_DEFAULT_MESSAGE = (
    'وزارة الاقتصاد والصناعة في الجمهورية العربية السورية ترحّب بكم، '
    'وتشكركم على اللقاء الطيّب. يسعدنا أن نكون على تواصل معكم، '
    'ونتطلّع إلى تعاونٍ مثمر يخدم مصالحنا المشتركة.'
)


def reset_defaults(apps, schema_editor):
    Profile = apps.get_model('accounts', 'Profile')
    for profile in Profile.objects.exclude(welcome_message='').iterator():
        if profile.welcome_message.strip() != OLD_DEFAULT_MESSAGE:
            continue  # a letter the owner wrote — never touch it
        profile.welcome_message = ''
        if profile.welcome_subject.strip() in {OLD_DEFAULT_SUBJECT, OLD_FORM_SUBJECT}:
            profile.welcome_subject = ''
        profile.save(update_fields=['welcome_message', 'welcome_subject'])


def noop(apps, schema_editor):
    """Irreversible by design: the old wording is superseded, and restoring it
    would silently undo the new default for every account."""


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_profile_welcome_message_en_and_more'),
    ]

    operations = [
        migrations.RunPython(reset_defaults, noop),
    ]
