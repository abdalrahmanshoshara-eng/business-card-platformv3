import { fetchJson } from '@/lib/api';
import type { MessageStatus } from './selection';

export type MessageResult = {
  card_id: number;
  name: string;
  email: string;
  status: MessageStatus;
};

export type SendMessageResponse = {
  detail: string;
  sent: number;
  total: number;
  results: MessageResult[];
};

/** Email one message (sent as written) to each selected card, one email per card. */
export async function sendCardMessage(cardIds: number[], subject: string, body: string): Promise<SendMessageResponse> {
  return fetchJson<SendMessageResponse>('/cards/send-message', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ card_ids: cardIds, subject, body }),
  });
}
