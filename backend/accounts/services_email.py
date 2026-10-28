"""Welcome-email sending.

Delivery always uses ONE platform mail account configured in .env
(settings.WELCOME_FROM_EMAIL + EMAIL_* for the SMTP connection), and that
address is the only sender shown — the From header carries it alone, with no
per-user display name or Reply-To, so replies reach the platform mailbox:
    From:     <WELCOME_FROM_EMAIL>

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
from dataclasses import dataclass, replace
from email.mime.image import MIMEImage
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

# Default welcome content, used when the user hasn't customised it in their
# profile. They can override both languages in the profile form. The Arabic
# names stay unsuffixed because they are the platform's primary language and are
# imported elsewhere under these names.
DEFAULT_WELCOME_SUBJECT = SUBJECT_AR
DEFAULT_WELCOME_MESSAGE = BODY_AR
DEFAULT_WELCOME_SUBJECT_EN = SUBJECT_EN
DEFAULT_WELCOME_MESSAGE_EN = BODY_EN


class WelcomeEmailError(RuntimeError):
    """Raised when a welcome email cannot be sent. ``message`` is user-safe."""


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


def _welcome_html(sections: list[WelcomeSection], has_logo: bool) -> str:
    """A polished HTML body carrying the platform's visual identity: a green
    header bar with the ministry logo and a gold rule, so the message reads as
    coming from the ministry.

    Each section is rendered in its own direction, so an Arabic block stays RTL
    while an English/German block beside it reads LTR."""
    primary = sections[0] if sections else WelcomeSection(subject='', body='')
    has_latin = any(not s.rtl for s in sections)

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
    body_html = ''.join(blocks)

    footer = 'الجمهورية العربية السورية · وزارة الصناعة والتجارة الداخلية'
    if has_latin:
        footer += (
            '<div style="margin-top:4px">Syrian Arab Republic · '
            'Ministry of Industry and Internal Trade</div>'
        )
    note = 'هذه الرسالة موجّهة إليك شخصياً. يمكنك الردّ عليها مباشرةً للتواصل مع الوزارة.'
    if has_latin:
        note += '<br>This message is addressed to you personally. Reply directly to reach the ministry.'

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
    *,
    to_email: str,
    subject: str = '',
    body: str = '',
    sections: list[WelcomeSection] | None = None,
) -> None:
    """Send the message to ``to_email`` from the single platform address, with
    the ministry logo embedded inline. Raises WelcomeEmailError on failure (user-safe).

    Pass either ``sections`` (one block per language) or a single
    ``subject``/``body`` pair, which is treated as one Arabic block.
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

    logo = _logo_bytes()
    try:
        message = EmailMultiAlternatives(
            subject=mail_subject,
            body=mail_body,  # plain-text fallback = the message as-is
            from_email=platform_from,
            to=[to_email],
            connection=get_connection(),  # platform default (EMAIL_* settings)
        )
        message.attach_alternative(_welcome_html(sections, bool(logo)), 'text/html')
        if logo:
            image = MIMEImage(logo)
            image.add_header('Content-ID', f'<{_LOGO_CID}>')
            image.add_header('Content-Disposition', 'inline', filename='logo.png')
            message.attach(image)
            # multipart/related so the HTML can reference the inline CID image.
            message.mixed_subtype = 'related'
        sent = message.send(fail_silently=False)
    except Exception as exc:
        logger.warning('welcome_email_send_failed error=%s', _sanitize(str(exc)))
        raise WelcomeEmailError('تعذّر إرسال رسالة الترحيب. تحقّق من إعدادات بريد المنصة.') from exc

    if not sent:
        raise WelcomeEmailError('تعذّر إرسال رسالة الترحيب.')
