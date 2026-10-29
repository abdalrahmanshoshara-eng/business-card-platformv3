/**
 * A message to many cards is sent in small batches — one request each — so no
 * single request runs long enough for the reverse proxy to time it out (a 504),
 * and the user sees progress. Cards that can't receive anything (no email, or an
 * address already covered by an earlier card) are settled here without a request,
 * which also keeps the "same address only once" rule across batches.
 */
import type { MessageStatus } from './selection';

/** Cards per request. One SMTP session sends these in a few seconds. */
export const BATCH_SIZE = 5;

type CardLike = { id: number; emails?: string[]; person_name?: string; company_name?: string };

export type PlannedResult = { card_id: number; name: string; email: string; status: MessageStatus };

export type SendPlan = {
  /** Card ids to send, grouped per request, in selection order. */
  batches: number[][];
  /** Cards settled without a request (no_email / duplicate_email). */
  skipped: PlannedResult[];
};

export function firstEmail(card: CardLike): string {
  return (card.emails || []).map((email) => email.trim()).find(Boolean) || '';
}

export function cardDisplayName(card: CardLike): string {
  return ((card.person_name || card.company_name || '').split(/\r?\n/)[0] || '').trim();
}

export function planSend(cards: readonly CardLike[], size = BATCH_SIZE): SendPlan {
  const seen = new Set<string>();
  const toSend: number[] = [];
  const skipped: PlannedResult[] = [];
  for (const card of cards) {
    const email = firstEmail(card);
    const base = { card_id: card.id, name: cardDisplayName(card), email };
    if (!email) {
      skipped.push({ ...base, status: 'no_email' });
    } else if (seen.has(email.toLowerCase())) {
      skipped.push({ ...base, status: 'duplicate_email' });
    } else {
      seen.add(email.toLowerCase());
      toSend.push(card.id);
    }
  }
  const batches: number[][] = [];
  for (let i = 0; i < toSend.length; i += size) batches.push(toSend.slice(i, i + size));
  return { batches, skipped };
}

/**
 * Statuses after which a card leaves the selection. Failed / not-sent cards
 * stay selected for a retry; "unknown" ones leave it, since resending could
 * deliver the message twice.
 */
export function isSettled(status: MessageStatus): boolean {
  return status !== 'failed' && status !== 'not_sent';
}
