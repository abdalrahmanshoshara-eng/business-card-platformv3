'use client';

/**
 * Welcome-email prompt modal: ask to send now / cancel. Mail always goes from
 * the platform (ministry) address, so there is nothing to set up first.
 */
export default function WelcomePrompt({
  open,
  busy = false,
  onConfirm,
  onClose,
}: {
  open: boolean;
  busy?: boolean;
  onConfirm?: () => void;
  onClose: () => void;
}) {
  if (!open) return null;

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="رسالة الترحيب">
      <div className="modal-panel welcome-prompt" style={{ maxWidth: 460 }}>
        <div className="welcome-prompt-icon" aria-hidden="true">✉️</div>
        <h2>إرسال رسالة ترحيب</h2>
        <p>
          سيتم إرسال رسالة ترحيبية من بريد الوزارة إلى بريد الكرت المُضاف، وفق
          الصياغة المضبوطة في صفحة «رسالة الترحيب». هل تريد الإرسال الآن؟
        </p>
        <div className="button-row welcome-prompt-actions">
          <button type="button" className="btn-green" onClick={onConfirm} disabled={busy}>
            {busy ? 'جارٍ الإرسال...' : 'إرسال ترحيب'}
          </button>
          <button type="button" onClick={onClose} disabled={busy}>إلغاء</button>
        </div>
      </div>
    </div>
  );
}
