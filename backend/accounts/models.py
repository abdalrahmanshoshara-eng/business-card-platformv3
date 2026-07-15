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

    def __str__(self):
        return f'Profile<{self.user_id}>'
