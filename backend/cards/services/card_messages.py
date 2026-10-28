"""Send one free-text message, written by the user, to several of their cards.

Delivery reuses the welcome-email transport (``accounts.services_email``): the
single platform address (the ministry's) is the only sender, and the ministry
HTML frame wraps the text. Unlike the
welcome letter, the text is sent exactly as written — no salutation and no
per-language blocks — and nothing is recorded on the card.

Each card gets its own email so recipients never see each other. Cards are
looked up through ``cards_for_user``, so an id the user doesn't own is reported
as ``not_found`` exactly like one that doesn't exist.
"""

from __future__ import annotations

import logging
import re

from accounts.services_email import WelcomeEmailError, WelcomeSection, send_welcome_email

from .access import cards_for_user

logger = logging.getLogger(__name__)

# Upper bound on cards per send. Emails go out one by one inside the request,
# so this keeps a send well under the gunicorn timeout.
MAX_RECIPIENTS = 50

STATUS_SENT = 'sent'
STATUS_FAILED = 'failed'
STATUS_NO_EMAIL = 'no_email'
STATUS_DUPLICATE_EMAIL = 'duplicate_email'
STATUS_NOT_FOUND = 'not_found'

_ARABIC = re.compile(r'[؀-ۿ]')


def _section(subject: str, body: str) -> WelcomeSection:
    # Direction follows the text: any Arabic letter → RTL block, else LTR.
    rtl = bool(_ARABIC.search(subject + body))
    return WelcomeSection(subject=subject, body=body, language='ar' if rtl else 'en', rtl=rtl)


def _first_email(card) -> str:
    for email in card.emails or []:
        email = str(email).strip()
        if email:
            return email
    return ''


def _display_name(card) -> str:
    return (card.person_name or card.company_name or '').strip()


def send_message_to_cards(user, card_ids: list[int], subject: str, body: str) -> list[dict]:
    """Email ``subject``/``body`` to the first address on each of ``card_ids``.

    Returns one result per distinct id, in the order given:
    ``{'card_id', 'name', 'email', 'status'}`` where status is one of
    sent / failed / no_email / duplicate_email / not_found. Two cards sharing an
    address only produce one email.
    """
    ids = list(dict.fromkeys(card_ids))
    cards = {card.id: card for card in cards_for_user(user).filter(id__in=ids)}
    section = _section(subject, body)
    sent_to: set[str] = set()
    results = []

    for card_id in ids:
        card = cards.get(card_id)
        if card is None:
            results.append({'card_id': card_id, 'name': '', 'email': '', 'status': STATUS_NOT_FOUND})
            continue

        email = _first_email(card)
        result = {'card_id': card.id, 'name': _display_name(card), 'email': email}
        if not email:
            result['status'] = STATUS_NO_EMAIL
        elif email.lower() in sent_to:
            result['status'] = STATUS_DUPLICATE_EMAIL
        else:
            try:
                send_welcome_email(to_email=email, sections=[section])
            except WelcomeEmailError:
                logger.warning('card_message_failed card_id=%s', card.id)
                result['status'] = STATUS_FAILED
            else:
                sent_to.add(email.lower())
                result['status'] = STATUS_SENT
        results.append(result)

    logger.info(
        'card_message_sent user_id=%s requested=%s sent=%s',
        user.id, len(ids), sum(r['status'] == STATUS_SENT for r in results),
    )
    return results
