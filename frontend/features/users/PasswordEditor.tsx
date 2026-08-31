'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { ApiError } from '@/lib/api';
import { ManagedUser, setUserPassword } from './api';
import { generateSecurePassword } from './password';

type Feedback = { type: 'success' | 'error'; text: string } | null;

function Icon({ name }: { name: 'edit' | 'generate' | 'copy' | 'eye' | 'eyeOff' | 'close' }) {
  const paths = {
    edit: <><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z" /></>,
    generate: <><path d="m12 3-1.2 3.3L7.5 7.5l3.3 1.2L12 12l1.2-3.3 3.3-1.2-3.3-1.2Z" /><path d="m5 13-.8 2.2L2 16l2.2.8L5 19l.8-2.2L8 16l-2.2-.8Z" /><path d="M17 14h4v7h-7v-4" /></>,
    copy: <><rect width="13" height="13" x="9" y="9" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></>,
    eye: <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></>,
    eyeOff: <><path d="m3 3 18 18" /><path d="M10.6 10.6a2 2 0 0 0 2.8 2.8" /><path d="M9.9 4.2A10.8 10.8 0 0 1 12 4c6.5 0 10 8 10 8a17 17 0 0 1-2 3" /><path d="M6.6 6.6C3.7 8.5 2 12 2 12s3.5 8 10 8a10 10 0 0 0 4.3-1" /></>,
    close: <><path d="m18 6-12 12" /><path d="m6 6 12 12" /></>,
  };
  return <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">{paths[name]}</svg>;
}

async function copyText(value: string, input: HTMLInputElement | null): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }

  if (!input) throw new Error('Copy is unavailable.');
  input.focus();
  input.select();
  if (!document.execCommand('copy')) throw new Error('Copy failed.');
}

export function PasswordEditor({ user }: { user: ManagedUser }) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState('');
  const [visible, setVisible] = useState(false);
  const [saving, setSaving] = useState(false);
  const [generated, setGenerated] = useState(false);
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<Feedback>(null);

  function close() {
    if (saving) return;
    setOpen(false);
    setValue('');
    setVisible(false);
    setGenerated(false);
    setCopied(false);
  }

  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') close();
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, saving]);

  function generate() {
    const password = generateSecurePassword();
    setValue(password);
    setGenerated(true);
    setVisible(true);
    setCopied(false);
    setFeedback(null);
    requestAnimationFrame(() => inputRef.current?.focus());
  }

  async function copy() {
    if (!value) return;
    try {
      await copyText(value, inputRef.current);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2200);
    } catch {
      setFeedback({ type: 'error', text: 'تعذّر النسخ تلقائياً. حدّد الكلمة وانسخها يدوياً.' });
    }
  }

  async function save() {
    if (!value) return;
    setFeedback(null);
    setSaving(true);
    try {
      await setUserPassword(user.id, value);
      setFeedback({ type: 'success', text: 'تم تحديث كلمة المرور بنجاح.' });
      setOpen(false);
      setValue('');
      setGenerated(false);
      setVisible(false);
    } catch (error) {
      setFeedback({ type: 'error', text: error instanceof ApiError ? error.message : 'تعذّر تحديث كلمة المرور.' });
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="pw-cell">
        <span className="pw-dots" aria-label="كلمة المرور مخفية">••••••••</span>
        <button
          type="button"
          className="pw-edit-trigger"
          onClick={() => { setOpen(true); setFeedback(null); }}
          aria-label={`تغيير كلمة مرور ${user.username}`}
        >
          <Icon name="edit" />
          تغيير
        </button>
        {feedback && <span className={`pw-msg ${feedback.type}`} role="status">{feedback.text}</span>}
      </div>

      {open && (
        <div className="modal-backdrop pw-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby={`${inputId}-title`} onMouseDown={close}>
          <div className="modal-panel pw-modal" onMouseDown={(event) => event.stopPropagation()}>
            <div className="pw-modal-head">
              <div className="pw-modal-title-wrap">
                <span className="pw-key-mark" aria-hidden="true">•••</span>
                <div>
                  <span className="pw-eyebrow">أمان الحساب</span>
                  <h2 id={`${inputId}-title`}>تغيير كلمة المرور</h2>
                </div>
              </div>
              <button type="button" className="pw-close" onClick={close} disabled={saving} aria-label="إغلاق">
                <Icon name="close" />
              </button>
            </div>

            <div className="pw-user-strip">
              <span>الحساب</span>
              <strong dir="ltr">{user.username}</strong>
            </div>

            <label htmlFor={inputId}>كلمة المرور الجديدة</label>
            <div className={`pw-field-shell ${generated ? 'is-generated' : ''}`}>
              <input
                ref={inputRef}
                id={inputId}
                type={visible ? 'text' : 'password'}
                value={value}
                onChange={(event) => { setValue(event.target.value); setGenerated(false); setCopied(false); }}
                onKeyDown={(event) => { if (event.key === 'Enter') save(); }}
                placeholder="اكتب كلمة مرور أو قم بتوليدها"
                autoComplete="new-password"
                autoFocus
                dir="ltr"
              />
              <button type="button" className="pw-field-action" onClick={() => setVisible((current) => !current)} aria-label={visible ? 'إخفاء كلمة المرور' : 'إظهار كلمة المرور'}>
                <Icon name={visible ? 'eyeOff' : 'eye'} />
              </button>
            </div>

            <div className="pw-tools">
              <button type="button" className="pw-generate" onClick={generate}>
                <Icon name="generate" />
                توليد كلمة قوية
              </button>
              <button type="button" className={`pw-copy ${copied ? 'is-copied' : ''}`} onClick={copy} disabled={!value}>
                <Icon name="copy" />
                {copied ? 'تم النسخ' : 'نسخ الكلمة'}
              </button>
            </div>

            <p className="pw-security-note">
              <span aria-hidden="true">✓</span>
              التوليد يتم داخل جهازك ويستخدم 16 رمزاً تتضمن أحرفاً وأرقاماً ورموزاً خاصة.
            </p>

            {feedback && <div className={`status-box ${feedback.type}`} role="alert">{feedback.text}</div>}

            <div className="pw-modal-actions">
              <button type="button" className="btn btn-green" disabled={saving || !value} onClick={save}>
                {saving ? 'جارٍ الحفظ…' : 'حفظ كلمة المرور'}
              </button>
              <button type="button" disabled={saving} onClick={close}>إلغاء</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
