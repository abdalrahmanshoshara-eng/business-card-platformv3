from django.conf import settings
from django.db import models


class Profile(models.Model):
    """Extra per-user data not covered by the default User model."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    phone = models.CharField(max_length=30, blank=True)

    # ── Welcome-email settings ─────────────────────────────────────────────
    # Delivery always goes through ONE platform mail account (settings.
    # WELCOME_FROM_EMAIL / EMAIL_*). Each user only sets THREE things: their
    # sender email (shown to the recipient and used as Reply-To), a subject and
    # a message. The other columns below are retained (unused) from the earlier
    # per-user-SMTP design to avoid a destructive migration.
    sender_email = models.EmailField(blank=True)
    sender_name = models.CharField(max_length=150, blank=True)   # unused (kept for history)
    smtp_host = models.CharField(max_length=255, blank=True)
    smtp_port = models.PositiveIntegerField(default=587)
    smtp_use_tls = models.BooleanField(default=True)
    smtp_username = models.CharField(max_length=255, blank=True)
    smtp_password_encrypted = models.TextField(blank=True)
    # Superseded by the platform-wide WelcomeLetter below: the letter is official
    # ministry correspondence, so it is set once for everyone by an admin rather
    # than per user. Kept (unused) to avoid a destructive migration, like the
    # smtp_* columns above.
    welcome_subject = models.CharField(max_length=255, blank=True)
    welcome_message = models.TextField(blank=True)

    def has_welcome_config(self) -> bool:
        """True when the user can send a welcome email — i.e. they set a sender
        email. The message itself falls back to a default when left blank."""
        return bool(self.sender_email)

    def __str__(self):
        return f'Profile<{self.user_id}>'


class WelcomeLetter(models.Model):
    """One account's welcome letter.

    Each user writes their own wording and can put it back to the ministry's
    default at any time. A row exists only while a user has customised
    something: a blank field falls back to the reviewed template for that
    language in ``welcome_templates.py``, and "reset to default" DELETES the row
    rather than copying the template into it — so a reset letter keeps tracking
    the shipped default, and a later correction to the template reaches everyone
    who never customised.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='welcome_letter',
    )
    subject_ar = models.CharField(max_length=255, blank=True)
    body_ar = models.TextField(blank=True)
    subject_en = models.CharField(max_length=255, blank=True)
    body_en = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    LETTER_FIELDS = ('subject_ar', 'body_ar', 'subject_en', 'body_en')

    @classmethod
    def load(cls, user) -> 'WelcomeLetter':
        """This user's letter. Returns an UNSAVED blank instance when they have
        never customised it, so reading the letter while sending never writes."""
        if user is None or not getattr(user, 'pk', None):
            return cls()
        return cls.objects.filter(user=user).first() or cls(user=user)

    @property
    def is_customized(self) -> bool:
        return any(getattr(self, field).strip() for field in self.LETTER_FIELDS)

    @classmethod
    def reset_for(cls, user) -> None:
        """Back to the ministry default: drop the row entirely."""
        cls.objects.filter(user=user).delete()

    def __str__(self):
        return f'WelcomeLetter<{self.user_id}>'
