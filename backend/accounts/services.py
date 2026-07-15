from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

User = get_user_model()


def build_reset_link(user) -> str:
    """Build a SPA-facing password reset link (uid + token)."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    base = getattr(settings, 'FRONTEND_BASE_URL', '').rstrip('/')
    return f'{base}/reset-password?uid={uid}&token={token}'


def send_reset_email(user, reset_link: str) -> None:
    subject = 'إعادة تعيين كلمة المرور'
    body = (
        f'مرحباً {user.first_name or user.username}،\n\n'
        'لإعادة تعيين كلمة المرور الخاصة بك، افتح الرابط التالي:\n'
        f'{reset_link}\n\n'
        'إذا لم تطلب ذلك يمكنك تجاهل هذه الرسالة.'
    )
    send_mail(
        subject,
        body,
        getattr(settings, 'DEFAULT_FROM_EMAIL', None),
        [user.email],
        fail_silently=True,
    )
