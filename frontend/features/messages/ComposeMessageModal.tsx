'use client';

import { useEffect, useRef, useState, type ClipboardEvent } from 'react';
import type { BusinessCard } from '@/lib/api';
import { sendCardMessageInBatches, type MessageResult, type SendProgress } from './api';
import { isSettled, summaryTone } from './batches';
import { firstImageFile, messageImageError } from './image';
import { MAX_RECIPIENTS, MESSAGE_STATUS_LABELS, cardsWithoutEmail } from './selection';

function cardName(card: BusinessCard) {
  return (card.person_name || card.company_name || `#${card.sequence_number}`).split(/\r?\n/)[0];
}

/**
 * Write one message and email it to the selected cards. The text is sent as
 * written; each card gets its own email at its first address. An optional
 * image (picked or pasted with Ctrl+V) is shown inside the email under the text.
 */
export default function ComposeMessageModal({
  cards,
  onRemove,
  onClose,
  onSent,
  onNeedsSender,
}: {
  cards: BusinessCard[];
  onRemove: (card: BusinessCard) => void;
  onClose: () => void;
  /** Called once the send finished with the cards to drop from the selection
   *  (failed / not-sent ones stay selected for a retry). */
  onSent: (settledIds: number[]) => void;
  /** The backend says the user has no sender email: ask for it, keeping this window as is. */
  onNeedsSender: () => void;
}) {
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [results, setResults] = useState<MessageResult[] | null>(null);
  const [stoppedError, setStoppedError] = useState('');
  const [progress, setProgress] = useState<SendProgress | null>(null);
  const [image, setImage] = useState<File | null>(null);
  const [imageUrl, setImageUrl] = useState('');
  const fileInput = useRef<HTMLInputElement>(null);

  // Preview URL for the chosen image, released when it changes or on close.
  useEffect(() => {
    if (!image) {
      setImageUrl('');
      return;
    }
    const url = URL.createObjectURL(image);
    setImageUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [image]);

  function chooseImage(file: File | null) {
    if (!file) return;
    const problem = messageImageError(file);
    if (problem) {
      setError(problem);
      return;
    }
    setError('');
    setImage(file);
  }

  function clearImage() {
    setImage(null);
    if (fileInput.current) fileInput.current.value = '';
  }

  // Ctrl+V anywhere in the window: an image on the clipboard becomes the
  // message image; pasting plain text keeps working as usual.
  function handlePaste(event: ClipboardEvent<HTMLDivElement>) {
    if (sending || results) return;
    const file = firstImageFile(event.clipboardData?.files);
    if (!file) return;
    event.preventDefault();
    chooseImage(file);
  }

  const withoutEmail = cardsWithoutEmail(cards);
  const reachable = cards.length - withoutEmail.length;
  const tooMany = cards.length > MAX_RECIPIENTS;
  const canSend = !sending && reachable > 0 && !tooMany && subject.trim() !== '' && body.trim() !== '';

  async function send() {
    if (!canSend) return;
    setSending(true);
    setError('');
    setProgress(null);
    try {
      const res = await sendCardMessageInBatches(cards, subject, body, image, setProgress);
      setResults(res.results);
      setStoppedError(res.stoppedError);
      onSent(res.results.filter((r) => isSettled(r.status)).map((r) => r.card_id));
    } catch (e: any) {
      if (e?.errorType === 'welcome_not_configured') {
        onNeedsSender();
        return;
      }
      setError(e?.message || 'تعذّر إرسال الرسالة.');
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="إرسال رسالة إلى الكروت المحددة">
      <div className="modal-panel compose-message" onPaste={handlePaste}>
        <div className="section-head">
          <h2>{results ? 'نتيجة الإرسال' : 'إرسال رسالة'}</h2>
          <button type="button" className="btn-small" onClick={onClose} disabled={sending}>
            إغلاق
          </button>
        </div>

        {results ? (
          <>
            <p className={`status-box ${summaryTone(results.map((r) => r.status))}`}>
              تم إرسال الرسالة إلى {results.filter((r) => r.status === 'sent').length} من {results.length}.
            </p>
            {stoppedError && (
              <p className="status-box error">
                توقف الإرسال: {stoppedError}. الكروت «غير المؤكدة» قد تكون وصلتها الرسالة؛ تحقّق من البريد
                المُرسَل قبل إعادة الإرسال إليها. الكروت التي لم تُرسل أو فشلت بقيت محددة.
              </p>
            )}
            <ul className="message-results">
              {results.map((r) => (
                <li key={r.card_id}>
                  <span className="message-results-name">{r.name || `#${r.card_id}`}</span>
                  {r.email && <span className="cell-sub ltr-text">{r.email}</span>}
                  <span
                    className={
                      r.status === 'sent' ? 'badge success'
                        : r.status === 'failed' || r.status === 'not_sent' ? 'badge danger'
                          : 'badge warning'
                    }
                  >
                    {MESSAGE_STATUS_LABELS[r.status] ?? r.status}
                  </span>
                  {r.reason && <span className="message-results-reason">{r.reason}</span>}
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
            <div className="message-image">
              <span className="message-image-label">صورة داخل الرسالة (اختياري)</span>
              {imageUrl ? (
                <div className="message-image-preview">
                  <img src={imageUrl} alt="الصورة المرفقة بالرسالة" />
                  <div className="message-image-actions">
                    <button type="button" className="btn-small" onClick={() => fileInput.current?.click()} disabled={sending}>
                      تغيير الصورة
                    </button>
                    <button type="button" className="btn-small danger" onClick={clearImage} disabled={sending}>
                      إزالة الصورة
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  className="message-image-drop"
                  onClick={() => fileInput.current?.click()}
                  disabled={sending}
                >
                  🖼️ اختر صورة، أو الصقها هنا بـ Ctrl+V
                </button>
              )}
              <input
                ref={fileInput}
                type="file"
                accept="image/jpeg,image/png,image/webp,image/gif"
                hidden
                onChange={(event) => chooseImage(event.target.files?.[0] || null)}
              />
            </div>
            <p className="helper-text">
              تُرسل الرسالة كما كتبتها، والصورة تظهر داخلها تحت النص، في بريد مستقل لكل كرت (لا يرى المستلمون
              بعضهم)، من بريد المنصة باسم بريدك المضبوط في ملفك الشخصي، وتصل الردود إليك.
            </p>

            {error && <p className="status-box error">{error}</p>}

            <div className="button-row">
              <button type="button" className="btn-green" onClick={send} disabled={!canSend}>
                {sending
                  ? progress && progress.total > 0
                    ? `جارٍ الإرسال ${progress.done} من ${progress.total}...`
                    : 'جارٍ الإرسال...'
                  : `إرسال إلى ${reachable}`}
              </button>
              <button type="button" onClick={onClose} disabled={sending}>إلغاء</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
