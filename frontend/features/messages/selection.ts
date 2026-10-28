/**
 * Selection of cards for a custom message. Kept as a Map keyed by card id so a
 * selection survives paging/filtering and the compose window can still show
 * the names of cards that are no longer on the current page.
 */

/** Must match backend `cards/services/card_messages.py::MAX_RECIPIENTS`. */
export const MAX_RECIPIENTS = 50;

export type Selection<T extends { id: number }> = ReadonlyMap<number, T>;

export type PageSelectionState = 'none' | 'some' | 'all';

export function toggleCard<T extends { id: number }>(selected: Selection<T>, card: T): Map<number, T> {
  const next = new Map(selected);
  if (next.has(card.id)) next.delete(card.id);
  else next.set(card.id, card);
  return next;
}

/** Select or clear every card on the current page, leaving other pages alone. */
export function setPageSelection<T extends { id: number }>(
  selected: Selection<T>,
  pageCards: readonly T[],
  checked: boolean,
): Map<number, T> {
  const next = new Map(selected);
  for (const card of pageCards) {
    if (checked) next.set(card.id, card);
    else next.delete(card.id);
  }
  return next;
}

export function pageSelectionState<T extends { id: number }>(
  selected: Selection<T>,
  pageCards: readonly T[],
): PageSelectionState {
  const count = pageCards.filter((card) => selected.has(card.id)).length;
  if (!count) return 'none';
  return count === pageCards.length ? 'all' : 'some';
}

export type MessageStatus = 'sent' | 'failed' | 'no_email' | 'duplicate_email' | 'not_found';

export const MESSAGE_STATUS_LABELS: Record<MessageStatus, string> = {
  sent: 'تم الإرسال',
  failed: 'فشل الإرسال',
  no_email: 'لا يوجد بريد',
  duplicate_email: 'بريد مكرر (أُرسل مرة واحدة)',
  not_found: 'غير متاح',
};

/** Selected cards that carry no email — shown as a warning before sending. */
export function cardsWithoutEmail<T extends { id: number; emails?: string[] }>(cards: readonly T[]): T[] {
  return cards.filter((card) => !(card.emails || []).some((email) => email.trim()));
}
