"""Welcome-email sending.

Delivery always uses ONE platform mail account configured in .env
(settings.WELCOME_FROM_EMAIL + EMAIL_* for the SMTP connection). Each user only
sets their sender email, a subject and a message. The From header shows the
user's email as the display name over the platform address, and Reply-To is the
user's email so replies reach them:
    From:     "<sender_email>" <WELCOME_FROM_EMAIL>
    Reply-To: <sender_email>

The ministry logo is embedded inline (CID) so it appears in the email header.

A message is composed of one or more ``WelcomeSection`` blocks — one per
language printed on the recipient's card. A card printed in Arabic only yields
one Arabic block; a bilingual card yields Arabic first, then the card's other
language, in a single email. See ``cards/services/welcome_text.py`` for how the
blocks are built.
"""

from __future__ import annotations

import logging
import re
import smtplib
import socket
from dataclasses import dataclass, replace
from email.mime.image import MIMEImage
from email.utils import formataddr
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.utils.html import escape

from .welcome_templates import (
    BODY_AR,
    BODY_EN,
    SALUTATION_TOKEN,
    SUBJECT_AR,
    SUBJECT_EN,
    default_salutation,
)

logger = logging.getLogger(__name__)

# Ministry logo bundled with the backend so it can be embedded inline (CID) —
# external recipients can't reach the LAN, so a linked image would not load.
_LOGO_PATH = Path(__file__).resolve().parent / 'assets' / 'welcome-logo.png'
_LOGO_CID = 'welcomelogo'
# Optional image the sender adds to a message (e.g. an announcement poster),
# embedded inline under the text the same way as the logo.
_IMAGE_CID = 'messageimage'

# Default welcome content, used when the user hasn't customised it in their
# profile. They can override both languages in the profile form. The Arabic
# names stay unsuffixed because they are the platform's primary language and are
# imported elsewhere under these names.
DEFAULT_WELCOME_SUBJECT = SUBJECT_AR
DEFAULT_WELCOME_MESSAGE = BODY_AR
DEFAULT_WELCOME_SUBJECT_EN = SUBJECT_EN
DEFAULT_WELCOME_MESSAGE_EN = BODY_EN


class WelcomeEmailError(RuntimeError):
    """Raised when a welcome email cannot be sent. ``message`` is user-safe.

    ``reason`` is a short user-safe Arabic explanation of what the mail server
    said (see ``describe_send_error``), '' when there is no server error."""

    def __init__(self, message: str, reason: str = ''):
        super().__init__(message)
        self.reason = reason


# Enhanced status code inside an SMTP reply, e.g. "5.4.5" or "5.1.1".
_ENHANCED_CODE = re.compile(r'\b[245]\.\d{1,3}\.\d{1,3}\b')
_LIMIT_HINTS = ('limit', 'quota', 'rate', 'too many', 'try again later', '5.4.5', '4.7.0', '4.2.1')


def _smtp_reply(exc) -> tuple[int | None, str]:
    """(code, text) of the server reply carried by an smtplib exception."""
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        code, text = next(iter(exc.recipients.values()), (None, b''))
    else:
        code = getattr(exc, 'smtp_code', None)
        text = getattr(exc, 'smtp_error', b'')
    if isinstance(text, bytes):
        text = text.decode('utf-8', 'replace')
    return code, str(text or '')


def describe_send_error(exc: BaseException) -> str:
    """User-safe Arabic reason for a failed send, with the SMTP code when there
    is one (so it can be looked up), e.g. "تجاوز حساب الإرسال حدّ الإرسال...
    (SMTP 550 5.4.5)". Never includes credentials or message content."""
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        reason = 'رفض خادم البريد تسجيل الدخول لحساب الإرسال (تحقّق من كلمة مرور التطبيق في إعدادات الخادم).'
    elif isinstance(exc, (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, socket.timeout,
                          TimeoutError, ConnectionError)):
        return 'تعذّر الاتصال بخادم البريد أو انقطع الاتصال. حاول لاحقًا.'
    elif isinstance(exc, smtplib.SMTPException):
        code, text = _smtp_reply(exc)
        lowered = text.lower()
        if any(hint in lowered for hint in _LIMIT_HINTS) or code == 421:
            reason = 'تجاوز حساب الإرسال حدّ الإرسال المسموح (اليومي أو المؤقت). حاول لاحقًا.'
        elif isinstance(exc, smtplib.SMTPRecipientsRefused) or '5.1.' in text:
            reason = 'رفض خادم البريد عنوان المستلم (قد يكون العنوان خاطئًا أو غير موجود).'
        else:
            reason = 'رفض خادم البريد الرسالة.'
        enhanced = _ENHANCED_CODE.search(text)
        detail = ' '.join(str(part) for part in (code, enhanced.group(0) if enhanced else '') if part)
        return f'{reason} (SMTP {detail})' if detail else reason
    elif isinstance(exc, OSError):
        return 'تعذّر الاتصال بخادم البريد. حاول لاحقًا.'
    else:
        reason = 'خطأ غير متوقع أثناء الإرسال.'
    return reason


@dataclass(frozen=True)
class WelcomeSection:
    """One language block of a welcome email."""

    subject: str
    body: str
    language: str = 'ar'
    rtl: bool = True


def _sanitize(text: str) -> str:
    return re.sub(r'\s+', ' ', text or '')[:200]


@lru_cache(maxsize=1)
def _logo_bytes() -> bytes:
    try:
        return _LOGO_PATH.read_bytes()
    except Exception:
        logger.warning('welcome_email_logo_missing path=%s', _LOGO_PATH)
        return b''


def combine_subjects(sections: list[WelcomeSection]) -> str:
    """Email subject for a multi-language message: each block's subject once,
    in order, joined by a separator (e.g. "رسالة شكر وتقدير | Message of
    Appreciation")."""
    subjects = [s.subject.strip() for s in sections if s.subject.strip()]
    return ' | '.join(dict.fromkeys(subjects))


def combine_bodies(sections: list[WelcomeSection]) -> str:
    """Plain-text fallback: the blocks in order, separated by a rule. A single
    block is returned untouched so a one-language message is byte-identical to
    the text the user wrote."""
    bodies = [s.body.strip() for s in sections if s.body.strip()]
    if len(bodies) <= 1:
        return bodies[0] if bodies else ''
    return '\n\n\n'.join(bodies)


def _without_placeholder(section: WelcomeSection) -> WelcomeSection:
    """Guarantee no message ever leaves with the raw salutation placeholder in
    it. Normally ``welcome_text`` has already filled it in from the card; this
    covers the fallback paths, where there is no card to draw a salutation from
    and the generic wording is the right answer."""
    if SALUTATION_TOKEN not in section.body:
        return section
    logger.warning('welcome_salutation_placeholder_left language=%s', section.language)
    return replace(section, body=section.body.replace(
        SALUTATION_TOKEN, default_salutation(section.language),
    ))


def _welcome_html(
    sections: list[WelcomeSection], sender_email: str, has_logo: bool, has_image: bool = False,
) -> str:
    """A polished HTML body carrying the platform's visual identity: a green
    header bar with the ministry logo and a gold rule, so the message reads as
    coming from the ministry, while still framing the user as the sender.

    Each section is rendered in its own direction, so an Arabic block stays RTL
    while an English/German block beside it reads LTR."""
    primary = sections[0] if sections else WelcomeSection(subject='', body='')
    has_latin = any(not s.rtl for s in sections)
    initial = escape((sender_email[:1] or '?').upper())
    sender = escape(sender_email)

    if has_logo:
        brand = (
            f'<img src="cid:{_LOGO_CID}" alt="وزارة الصناعة والتجارة الداخلية" '
            'height="54" style="height:54px;width:auto;display:block;margin:0 auto">'
        )
    else:
        brand = (
            '<div style="font-size:20px;font-weight:800;color:#f7f3e8">وزارة الصناعة والتجارة الداخلية</div>'
            '<div style="font-size:11px;letter-spacing:.14em;color:#d9b877;margin-top:4px">'
            'MINISTRY OF INDUSTRY AND INTERNAL TRADE</div>'
        )

    blocks = []
    for index, section in enumerate(sections):
        direction = 'rtl' if section.rtl else 'ltr'
        align = 'right' if section.rtl else 'left'
        safe_body = escape(section.body).replace('\n', '<br>')
        title = escape(section.subject.strip())
        rule = (
            '<div style="height:1px;background:#e6ded0;margin:26px 0"></div>'
            if index else ''
        )
        heading = (
            f'<div style="font-size:18px;font-weight:800;color:#0f5a4e;margin-bottom:14px">{title}</div>'
            if title else ''
        )
        blocks.append(
            f'{rule}<div dir="{direction}" lang="{escape(section.language)}" style="text-align:{align}">'
            f'{heading}'
            f'<div style="font-size:16px;line-height:2;color:#2c2a26">{safe_body}</div>'
            '</div>'
        )
    if has_image:
        blocks.append(
            '<div style="margin-top:22px;text-align:center">'
            f'<img src="cid:{_IMAGE_CID}" alt="" width="500" '
            'style="width:100%;max-width:500px;height:auto;display:block;margin:0 auto;border-radius:10px">'
            '</div>'
        )
    body_html = ''.join(blocks)

    sender_block = ''
    if sender:
        label = 'مُرسَلة من' + (' · Sent by' if has_latin else '')
        sender_block = f"""
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:28px;border-top:1px solid #e6ded0;padding-top:18px">
            <tr>
              <td style="width:46px;vertical-align:middle">
                <div style="width:44px;height:44px;border-radius:50%;background:#0f5a4e;color:#f4e9cf;font-weight:800;font-size:18px;text-align:center;line-height:44px">{initial}</div>
              </td>
              <td style="vertical-align:middle;padding-inline-start:12px">
                <div style="font-size:13px;color:#6b6252">{label}</div>
                <div style="font-size:15px;font-weight:800;color:#0f5a4e;direction:ltr;text-align:right">{sender}</div>
              </td>
            </tr>
          </table>"""

    footer = 'الجمهورية العربية السورية · وزارة الصناعة والتجارة الداخلية'
    if has_latin:
        footer += (
            '<div style="margin-top:4px">Syrian Arab Republic · '
            'Ministry of Industry and Internal Trade</div>'
        )
    note = 'هذه الرسالة موجّهة إليك شخصياً. يمكنك الردّ عليها مباشرةً للوصول إلى المُرسِل.'
    if has_latin:
        note += '<br>This message is addressed to you personally. Reply directly to reach the sender.'

    root_dir = 'rtl' if primary.rtl else 'ltr'
    root_lang = escape(primary.language or 'ar')
    return f"""<!DOCTYPE html>
<html lang="{root_lang}" dir="{root_dir}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f3efe6;font-family:'Segoe UI',Tahoma,Arial,sans-serif">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3efe6;padding:28px 12px">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 8px 26px rgba(15,90,78,.12)">
        <tr><td style="background:linear-gradient(160deg,#0b4a40,#063029);padding:24px 24px 20px;text-align:center">{brand}</td></tr>
        <tr><td style="height:4px;background:linear-gradient(90deg,#0f5a4e,#c7a66b)"></td></tr>
        <tr><td style="padding:32px 30px 26px">
          {body_html}
          {sender_block}
        </td></tr>
        <tr><td style="background:#f7f4ec;padding:14px 24px;text-align:center;font-size:12px;color:#8a8272;border-top:1px solid #ece5d6">
          {footer}
        </td></tr>
      </table>
      <div style="max-width:560px;margin-top:14px;font-size:12px;color:#9a9284">{note}</div>
    </td></tr>
  </table>
</body></html>"""


def send_welcome_email(
    profile,
    *,
    to_email: str,
    subject: str = '',
    body: str = '',
    sections: list[WelcomeSection] | None = None,
    image: tuple[bytes, str] | None = None,
    connection=None,
) -> None:
    """Send the message to ``to_email`` from the single platform address, showing
    the profile owner's email as From display name + Reply-To, with the ministry
    logo embedded inline. Raises WelcomeEmailError on failure (user-safe).

    Pass either ``sections`` (one block per language) or a single
    ``subject``/``body`` pair, which is treated as one Arabic block.
    ``image`` is an optional ``(bytes, subtype)`` pair (subtype 'jpeg'/'png')
    shown inline under the text. ``connection`` lets a caller sending many
    messages reuse one open SMTP connection instead of logging in per email.
    """
    platform_from = (getattr(settings, 'WELCOME_FROM_EMAIL', '') or getattr(settings, 'DEFAULT_FROM_EMAIL', '')).strip()
    if not platform_from:
        raise WelcomeEmailError('لم يتم ضبط بريد إرسال المنصة (WELCOME_FROM_EMAIL) في إعدادات الخادم.')
    if not to_email:
        raise WelcomeEmailError('لا يوجد بريد مستلم صالح.')

    if sections is None:
        # Fall back to the default content when the caller leaves them blank.
        sections = [WelcomeSection(
            subject=(subject or '').strip() or DEFAULT_WELCOME_SUBJECT,
            body=(body or '').strip() or DEFAULT_WELCOME_MESSAGE,
            language='ar',
            rtl=True,
        )]
    sections = [_without_placeholder(s) for s in sections if s.body.strip()]
    if not sections:
        raise WelcomeEmailError('لا يوجد نص لرسالة الترحيب.')

    mail_subject = combine_subjects(sections) or DEFAULT_WELCOME_SUBJECT
    mail_body = combine_bodies(sections)

    user_email = (getattr(profile, 'sender_email', '') or '').strip()
    # formataddr quotes the display name so an email-like name (contains '@') is
    # a valid header instead of breaking the address parser.
    from_email = formataddr((user_email, platform_from)) if user_email else platform_from
    logo = _logo_bytes()
    try:
        message = EmailMultiAlternatives(
            subject=mail_subject,
            body=mail_body,  # plain-text fallback = the message as-is
            from_email=from_email,
            to=[to_email],
            reply_to=[user_email] if user_email else None,
            connection=connection or get_connection(),  # platform default (EMAIL_* settings)
        )
        message.attach_alternative(
            _welcome_html(sections, user_email, bool(logo), has_image=bool(image)), 'text/html',
        )
        inline = []
        if logo:
            inline.append((logo, 'png', _LOGO_CID, 'logo.png'))
        if image:
            data, subtype = image
            inline.append((data, subtype, _IMAGE_CID, f'image.{"jpg" if subtype == "jpeg" else subtype}'))
        for data, subtype, cid, filename in inline:
            part = MIMEImage(data, _subtype=subtype)
            part.add_header('Content-ID', f'<{cid}>')
            part.add_header('Content-Disposition', 'inline', filename=filename)
            message.attach(part)
        if inline:
            # multipart/related so the HTML can reference the inline CID images.
            message.mixed_subtype = 'related'
        sent = message.send(fail_silently=False)
    except Exception as exc:
        logger.warning('welcome_email_send_failed error=%s', _sanitize(str(exc)))
        reason = describe_send_error(exc)
        raise WelcomeEmailError(f'تعذّر إرسال رسالة الترحيب: {reason}', reason=reason) from exc

    if not sent:
        raise WelcomeEmailError('تعذّر إرسال رسالة الترحيب.')
