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
    welcome_subject = models.CharField(max_length=255, blank=True)
    welcome_message = models.TextField(blank=True)
    # The secondary-language letter, sent alongside the Arabic one when the
    # recipient's card is not Arabic. Blank means "use the reviewed template for
    # whatever language that card is printed in".
    welcome_subject_en = models.CharField(max_length=255, blank=True)
    welcome_message_en = models.TextField(blank=True)

    def has_welcome_config(self) -> bool:
        """True when the user can send a welcome email — i.e. they set a sender
        email. The message itself falls back to a default when left blank."""
        return bool(self.sender_email)

    def __str__(self):
        return f'Profile<{self.user_id}>'
