'use client';

/**
 * Welcome-email prompt modal.
 * - mode="confirm": the user has a sender email set → ask to send now / cancel.
 * - mode="setup":   no sender email set → tell them, offer to set it now / ignore.
 */
export default function WelcomePrompt({
  open,
  mode,
  busy = false,
  onConfirm,
  onSetupEmail,
  onClose,
}: {
  open: boolean;
  mode: 'confirm' | 'setup';
  busy?: boolean;
  onConfirm?: () => void;
  onSetupEmail?: () => void;
  onClose: () => void;
}) {
  if (!open) return null;

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="رسالة الترحيب">
      <div className="modal-panel welcome-prompt" style={{ maxWidth: 460 }}>
        <div className="welcome-prompt-icon" aria-hidden="true">✉️</div>
        {mode === 'confirm' ? (
          <>
            <h2>إرسال رسالة ترحيب</h2>
            <p>
              سيتم إرسال رسالة ترحيبية إلى بريد الكرت المُضاف، وفق الصياغة المضبوطة
              في ملفك الشخصي. هل تريد الإرسال الآن؟
            </p>
            <div className="button-row welcome-prompt-actions">
              <button type="button" className="btn-green" onClick={onConfirm} disabled={busy}>
                {busy ? 'جارٍ الإرسال...' : 'إرسال ترحيب'}
              </button>
              <button type="button" onClick={onClose} disabled={busy}>إلغاء</button>
            </div>
          </>
        ) : (
          <>
            <h2>لم يتم تعيين بريد المُرسِل</h2>
            <p>
              لن يتم إرسال رسالة ترحيبية لأنه لم يتم تعيين الإيميل المُرسَل منه في
              ملفك الشخصي. يمكنك تعيينه الآن ثم المحاولة مجددًا.
            </p>
            <div className="button-row welcome-prompt-actions">
              <button type="button" className="btn-green" onClick={onSetupEmail}>تعيين الإيميل الآن</button>
              <button type="button" onClick={onClose}>تجاهل</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
