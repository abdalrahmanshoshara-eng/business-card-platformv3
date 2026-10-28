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
