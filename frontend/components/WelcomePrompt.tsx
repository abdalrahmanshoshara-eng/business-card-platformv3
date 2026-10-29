'use client';

import { useState, type FormEvent } from 'react';
import { useAuth } from '@/features/auth/AuthProvider';
import { updateProfile } from '@/features/auth/api';
import { senderEmailError } from '@/features/auth/senderEmail';

/**
 * Welcome-email prompt modal.
 * - mode="confirm": the user has a sender email set → ask to send now / cancel.
 * - mode="setup":   no sender email set → let them type it right here; it is
 *   saved on their profile and `onSaved` resumes what they were doing (so a
 *   card selection or a just-extracted card isn't lost by leaving the page).
 */
export default function WelcomePrompt({
  open,
  mode,
  purpose = 'welcome',
  busy = false,
  onConfirm,
  onSaved,
  onSetupEmail,
  onClose,
}: {
  open: boolean;
  mode: 'confirm' | 'setup';
  /** What the sender email is needed for — only changes the wording. */
  purpose?: 'welcome' | 'message';
  busy?: boolean;
  onConfirm?: () => void;
  /** Setup mode: called once the sender email is saved. */
  onSaved?: () => void;
  /** Setup mode: open the profile page instead. */
  onSetupEmail?: () => void;
  onClose: () => void;
}) {
  const { setUser } = useAuth();
  const [email, setEmail] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  if (!open) return null;

  async function saveEmail(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;
    const problem = senderEmailError(email);
    if (problem) {
      setError(problem);
      return;
    }
    setSaving(true);
    setError('');
    try {
      setUser(await updateProfile({ sender_email: email.trim() }));
      setEmail('');
      onSaved?.();
    } catch (err: any) {
      setError(err?.message || 'تعذّر حفظ بريد المُرسِل.');
    } finally {
      setSaving(false);
    }
  }

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
          <form onSubmit={saveEmail} noValidate>
            <h2>لم يتم تعيين بريد المُرسِل</h2>
            <p>
              {purpose === 'message' ? 'لإرسال الرسالة' : 'لإرسال رسالة الترحيب'} اكتب بريدك هنا؛ يظهر
              للمستلم كمُرسِل وتصلك الردود عليه، ويُحفظ في ملفك الشخصي.
            </p>
            <label className="sender-email-field">
              بريد المُرسِل
              <input
                type="email"
                dir="ltr"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
                autoFocus
                disabled={saving}
              />
            </label>
            {error && <p className="status-box error">{error}</p>}
            <div className="button-row welcome-prompt-actions">
              <button type="submit" className="btn-green" disabled={saving}>
                {saving ? 'جارٍ الحفظ...' : 'حفظ ومتابعة'}
              </button>
              <button type="button" onClick={onClose} disabled={saving}>تجاهل</button>
            </div>
            {onSetupEmail && (
              <button type="button" className="link-button" onClick={onSetupEmail} disabled={saving}>
                أو افتح الملف الشخصي
              </button>
            )}
          </form>
        )}
      </div>
    </div>
  );
}
