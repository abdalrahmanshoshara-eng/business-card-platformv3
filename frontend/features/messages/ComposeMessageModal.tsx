'use client';

import { useState } from 'react';
import type { BusinessCard } from '@/lib/api';
import { sendCardMessage, type MessageResult } from './api';
import { MAX_RECIPIENTS, MESSAGE_STATUS_LABELS, cardsWithoutEmail } from './selection';

function cardName(card: BusinessCard) {
  return (card.person_name || card.company_name || `#${card.sequence_number}`).split(/\r?\n/)[0];
}

/**
 * Write one message and email it to the selected cards. The text is sent as
 * written; each card gets its own email at its first address.
 */
export default function ComposeMessageModal({
  cards,
  onRemove,
  onClose,
  onSent,
}: {
  cards: BusinessCard[];
  onRemove: (card: BusinessCard) => void;
  onClose: () => void;
  /** Called once the send finished, so the caller can clear the selection. */
  onSent: () => void;
}) {
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [results, setResults] = useState<MessageResult[] | null>(null);
  const [summary, setSummary] = useState('');

  const withoutEmail = cardsWithoutEmail(cards);
  const reachable = cards.length - withoutEmail.length;
  const tooMany = cards.length > MAX_RECIPIENTS;
  const canSend = !sending && reachable > 0 && !tooMany && subject.trim() !== '' && body.trim() !== '';

  async function send() {
    if (!canSend) return;
    setSending(true);
    setError('');
    try {
      const res = await sendCardMessage(cards.map((card) => card.id), subject, body);
      setResults(res.results);
      setSummary(res.detail);
      onSent();
    } catch (e: any) {
      setError(e?.message || 'تعذّر إرسال الرسالة.');
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="إرسال رسالة إلى الكروت المحددة">
      <div className="modal-panel compose-message">
        <div className="section-head">
          <h2>{results ? 'نتيجة الإرسال' : 'إرسال رسالة'}</h2>
          <button type="button" className="btn-small" onClick={onClose} disabled={sending}>
            إغلاق
          </button>
        </div>

        {results ? (
          <>
            <p className="status-box success">{summary}</p>
            <ul className="message-results">
              {results.map((r) => (
                <li key={r.card_id}>
                  <span className="message-results-name">{r.name || `#${r.card_id}`}</span>
                  {r.email && <span className="cell-sub ltr-text">{r.email}</span>}
                  <span className={r.status === 'sent' ? 'badge success' : r.status === 'failed' ? 'badge danger' : 'badge warning'}>
                    {MESSAGE_STATUS_LABELS[r.status] ?? r.status}
                  </span>
                </li>
              ))}
            </ul>
            <div className="button-row">
              <button type="button" className="btn-green" onClick={onClose}>تم</button>
            </div>
          </>
        ) : (
          <>
            <div className="message-recipients-head">
              <span>
                المستلمون: <strong>{cards.length}</strong>
                {withoutEmail.length > 0 && (
                  <> — سيُرسل إلى <strong>{reachable}</strong> فقط</>
                )}
              </span>
            </div>
            <ul className="message-recipients" aria-label="الكروت المحددة">
              {cards.map((card) => {
                const email = (card.emails || []).find((e) => e.trim());
                return (
                  <li key={card.id} className={email ? 'message-chip' : 'message-chip no-email'}>
                    <span>{cardName(card)}</span>
                    <span className="ltr-text">{email || 'لا يوجد بريد'}</span>
                    <button
                      type="button"
                      onClick={() => onRemove(card)}
                      disabled={sending}
                      aria-label={`إزالة ${cardName(card)}`}
                      title="إزالة من المستلمين"
                    >
                      ×
                    </button>
                  </li>
                );
              })}
            </ul>
            {tooMany && (
              <p className="status-box warning">
                يمكن الإرسال إلى {MAX_RECIPIENTS} كرتًا كحد أقصى في المرة الواحدة. أزل بعض الكروت.
              </p>
            )}
            {withoutEmail.length > 0 && !tooMany && (
              <p className="status-box warning">
                {withoutEmail.length === 1 ? 'كرت واحد' : `${withoutEmail.length} كروت`} بلا بريد إلكتروني ولن تصلها الرسالة.
              </p>
            )}

            <label>
              عنوان الرسالة
              <input
                value={subject}
                onChange={(event) => setSubject(event.target.value)}
                maxLength={200}
                disabled={sending}
              />
            </label>
            <label>
              نص الرسالة
              <textarea
                value={body}
                onChange={(event) => setBody(event.target.value)}
                maxLength={10000}
                rows={9}
                disabled={sending}
              />
            </label>
            <p className="helper-text">
              تُرسل الرسالة كما كتبتها، في بريد مستقل لكل كرت (لا يرى المستلمون بعضهم)، من بريد المنصة باسم بريدك
              وتصل الردود إليك.
            </p>

            {error && <p className="status-box error">{error}</p>}

            <div className="button-row">
              <button type="button" className="btn-green" onClick={send} disabled={!canSend}>
                {sending ? 'جارٍ الإرسال...' : `إرسال إلى ${reachable}`}
              </button>
              <button type="button" onClick={onClose} disabled={sending}>إلغاء</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
