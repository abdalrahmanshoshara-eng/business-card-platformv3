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
from django.core.mail import EmailMultiAlternatives, get_connection
from django.utils.html import escape

logger = logging.getLogger(__name__)


class WelcomeEmailError(RuntimeError):
    """Raised when a welcome email cannot be sent. ``message`` is user-safe."""


def _sanitize(text: str) -> str:
    return re.sub(r'\s+', ' ', text or '')[:200]


def _welcome_html(body: str, sender_email: str) -> str:
    """A polished, RTL HTML body that frames the message as coming from the
    user's own address (sender_email) — the platform address is never shown, so
    the recipient perceives the user as the sender."""
    safe_body = escape(body).replace('\n', '<br>')
    initial = escape((sender_email[:1] or '?').upper())
    sender = escape(sender_email)
    sender_block = ''
    if sender:
        sender_block = f"""
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:28px;border-top:1px solid #e6ded0;padding-top:18px">
            <tr>
              <td style="width:46px;vertical-align:middle">
                <div style="width:44px;height:44px;border-radius:50%;background:#0f5a4e;color:#f4e9cf;font-weight:800;font-size:18px;text-align:center;line-height:44px">{initial}</div>
              </td>
              <td style="vertical-align:middle;padding-inline-start:12px">
                <div style="font-size:13px;color:#6b6252">مُرسَلة من</div>
                <div style="font-size:15px;font-weight:800;color:#0f5a4e;direction:ltr;text-align:right">{sender}</div>
              </td>
            </tr>
          </table>"""
    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f3efe6;font-family:'Segoe UI',Tahoma,Arial,sans-serif">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3efe6;padding:28px 12px">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 8px 26px rgba(15,90,78,.12)">
        <tr><td style="height:6px;background:linear-gradient(90deg,#0f5a4e,#c7a66b)"></td></tr>
        <tr><td style="padding:32px 30px 26px">
          <div style="font-size:19px;font-weight:800;color:#0f5a4e;margin-bottom:14px">مرحباً 👋</div>
          <div style="font-size:16px;line-height:2;color:#2c2a26">{safe_body}</div>
          {sender_block}
        </td></tr>
      </table>
      <div style="max-width:560px;margin-top:14px;font-size:12px;color:#9a9284">هذه الرسالة موجّهة إليك شخصياً. يمكنك الردّ عليها مباشرةً للوصول إلى المُرسِل.</div>
    </td></tr>
  </table>
</body></html>"""


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
        message = EmailMultiAlternatives(
            subject=subject or 'رسالة ترحيب',
            body=body,  # plain-text fallback = the user's message as-is
            from_email=from_email,
            to=[to_email],
            reply_to=[user_email] if user_email else None,
            connection=get_connection(),  # platform default (EMAIL_* settings)
        )
        message.attach_alternative(_welcome_html(body, user_email), 'text/html')
        sent = message.send(fail_silently=False)
    except Exception as exc:
        logger.warning('welcome_email_send_failed error=%s', _sanitize(str(exc)))
        raise WelcomeEmailError('تعذّر إرسال رسالة الترحيب. تحقّق من إعدادات بريد المنصة.') from exc

    if not sent:
        raise WelcomeEmailError('تعذّر إرسال رسالة الترحيب.')
