"""Welcome-email sending.

Delivery always uses ONE platform mail account configured in .env
(settings.WELCOME_FROM_EMAIL + EMAIL_* for the SMTP connection). Each user only
sets their sender email, a subject and a message. The From header shows the
user's email as the display name over the platform address, and Reply-To is the
user's email so replies reach them:
    From:     "<sender_email>" <WELCOME_FROM_EMAIL>
    Reply-To: <sender_email>
"""

from __future__ import annotations

import logging
import re
from email.utils import formataddr

from django.conf import settings
from django.core.mail import EmailMessage, get_connection

logger = logging.getLogger(__name__)


class WelcomeEmailError(RuntimeError):
    """Raised when a welcome email cannot be sent. ``message`` is user-safe."""


def _sanitize(text: str) -> str:
    return re.sub(r'\s+', ' ', text or '')[:200]


def send_welcome_email(profile, *, to_email: str, subject: str, body: str) -> None:
    """Send ``body`` to ``to_email`` from the single platform address, showing
    the profile owner's display name so the recipient knows who sent it.
    Raises WelcomeEmailError on any failure (with a user-safe message)."""
    platform_from = (getattr(settings, 'WELCOME_FROM_EMAIL', '') or getattr(settings, 'DEFAULT_FROM_EMAIL', '')).strip()
    if not platform_from:
        raise WelcomeEmailError('لم يتم ضبط بريد إرسال المنصة (WELCOME_FROM_EMAIL) في إعدادات الخادم.')
    if not (body or '').strip():
        raise WelcomeEmailError('نص رسالة الترحيب غير مضبوط في الملف الشخصي.')
    if not to_email:
        raise WelcomeEmailError('لا يوجد بريد مستلم صالح.')

    user_email = (getattr(profile, 'sender_email', '') or '').strip()
    # Show the user's email as the From display name over the platform address.
    # formataddr quotes the display name so an email-like name (contains '@') is
    # a valid header instead of breaking the address parser.
    from_email = formataddr((user_email, platform_from)) if user_email else platform_from
    try:
        message = EmailMessage(
            subject=subject or 'رسالة ترحيب',
            body=body,
            from_email=from_email,
            to=[to_email],
            reply_to=[user_email] if user_email else None,
            connection=get_connection(),  # platform default (EMAIL_* settings)
        )
        sent = message.send(fail_silently=False)
    except Exception as exc:
        logger.warning('welcome_email_send_failed error=%s', _sanitize(str(exc)))
        raise WelcomeEmailError('تعذّر إرسال رسالة الترحيب. تحقّق من إعدادات بريد المنصة.') from exc

    if not sent:
        raise WelcomeEmailError('تعذّر إرسال رسالة الترحيب.')
