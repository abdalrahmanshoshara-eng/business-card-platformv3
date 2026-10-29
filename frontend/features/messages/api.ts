import { fetchJson } from '@/lib/api';
import { cardDisplayName, firstEmail, planSend, type PlannedResult } from './batches';
import type { MessageStatus } from './selection';

export type MessageResult = {
  card_id: number;
  name: string;
  email: string;
  status: MessageStatus;
  /** Why it failed, in plain Arabic (only on failed cards). */
  reason?: string;
};

export type SendMessageResponse = {
  detail: string;
  sent: number;
  total: number;
  results: MessageResult[];
};

/**
 * Email one message (sent as written) to each selected card, one email per card.
 * An optional image is shown inside the email under the text.
 */
export async function sendCardMessage(
  cardIds: number[],
  subject: string,
  body: string,
  image?: File | null,
): Promise<SendMessageResponse> {
  const form = new FormData();
  for (const id of cardIds) form.append('card_ids', String(id));
  form.append('subject', subject);
  form.append('body', body);
  if (image) form.append('image', image, image.name || 'image.png');
  // No Content-Type header: the browser sets the multipart boundary itself.
  return fetchJson<SendMessageResponse>('/cards/send-message', { method: 'POST', body: form });
}

export type SendProgress = { done: number; total: number };

export type BatchedSendResult = {
  /** One result per selected card, in selection order. */
  results: MessageResult[];
  /** Why sending stopped early ('' when every batch went through). */
  stoppedError: string;
};

type CardForSend = { id: number; emails?: string[]; person_name?: string; company_name?: string };

/**
 * Send to many cards in small batches (see batches.ts) so no request outlasts
 * the proxy timeout, reporting progress after each batch. A "no sender email"
 * answer is rethrown so the caller can ask for it; any other failure stops the
 * send and is reported per card instead of being thrown.
 */
export async function sendCardMessageInBatches(
  cards: readonly CardForSend[],
  subject: string,
  body: string,
  image: File | null,
  onProgress: (progress: SendProgress) => void,
): Promise<BatchedSendResult> {
  const plan = planSend(cards);
  const total = plan.batches.reduce((n, batch) => n + batch.length, 0);
  const byId = new Map<number, MessageResult | PlannedResult>(plan.skipped.map((r) => [r.card_id, r]));
  const cardsById = new Map(cards.map((card) => [card.id, card]));
  const settle = (ids: number[], status: MessageStatus) => {
    for (const id of ids) {
      const card = cardsById.get(id);
      const email = card ? firstEmail(card) : '';
      const name = card ? cardDisplayName(card) : '';
      byId.set(id, { card_id: id, name, email, status });
    }
  };

  let done = 0;
  let stoppedError = '';
  onProgress({ done, total });
  for (let i = 0; i < plan.batches.length; i++) {
    const batch = plan.batches[i];
    try {
      const res = await sendCardMessage(batch, subject, body, image);
      for (const r of res.results) byId.set(r.card_id, r);
    } catch (e: any) {
      if (e?.errorType === 'welcome_not_configured') throw e;
      stoppedError = e?.message || 'تعذّر إرسال الرسالة.';
      settle(batch, 'unknown');
      settle(plan.batches.slice(i + 1).flat(), 'not_sent');
      break;
    }
    done += batch.length;
    onProgress({ done, total });
  }

  return {
    results: cards.map((card) => byId.get(card.id)).filter((r): r is MessageResult => Boolean(r)),
    stoppedError,
  };
}
