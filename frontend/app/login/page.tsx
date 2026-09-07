'use client';

import { FormEvent, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ApiError } from '@/lib/api';
import { useAuth } from '@/features/auth/AuthProvider';
import { forgotPassword } from '@/features/auth/api';

export default function LoginPage() {
  const { user, loading, login } = useAuth();
  const router = useRouter();
  const [next, setNext] = useState('/dashboard');

  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get('next');
    if (q) setNext(q);
  }, []);

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [forgotMode, setForgotMode] = useState(false);
  const [forgotDone, setForgotDone] = useState(false);

  useEffect(() => {
    if (!loading && user) router.replace(next);
  }, [loading, user, next, router]);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem('bcp_last_username');
      if (saved) setUsername(saved);
    } catch {
      /* ignore */
    }
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      // No "remember me" control: every login persists for the full session
      // lifetime, which is what the checkbox defaulted to.
      await login(username.trim(), password, true);
      try {
        window.localStorage.setItem('bcp_last_username', username.trim());
      } catch {
        /* ignore */
      }
      router.replace(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'تعذّر تسجيل الدخول. حاول مرة أخرى.');
    } finally {
      setSubmitting(false);
    }
  }

  async function submitForgot(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await forgotPassword(username.trim());
      setForgotDone(true);
    } catch {
      setForgotDone(true); // generic, never reveal account existence
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-split">
      {/* Form column — first in the DOM so keyboard and screen readers reach it
          immediately; RTL places it on the reading-start (right) side. */}
      <section className="auth-form-panel">
        <div className="auth-form-inner">
          <div className="auth-form-head">
            <span className="auth-eyebrow">منصة الكروت الشخصية</span>
            <h1>{forgotMode ? 'استعادة كلمة المرور' : 'تسجيل الدخول'}</h1>
            <div className="hero-accent-line" />
            <p>
              {forgotMode
                ? 'أدخل اسم المستخدم أو البريد الإلكتروني وسنرسل لك رابط إعادة التعيين.'
                : 'أدخل اسم المستخدم أو البريد الإلكتروني وكلمة المرور للوصول إلى حسابك.'}
            </p>
          </div>

          {!forgotMode ? (
            <form onSubmit={submit}>
              <label htmlFor="username">اسم المستخدم أو البريد الإلكتروني</label>
              <input id="username" type="text" autoComplete="username" value={username}
                onChange={(e) => setUsername(e.target.value)} required />

              <label htmlFor="password">كلمة المرور</label>
              <input id="password" type="password" autoComplete="current-password" value={password}
                onChange={(e) => setPassword(e.target.value)} required />

              {error && <div className="status-box error" style={{ marginTop: 12 }}>{error}</div>}

              <div className="auth-options">
                <button type="button" className="auth-link-btn"
                  onClick={() => { setForgotMode(true); setError(''); }}>
                  نسيت كلمة المرور؟
                </button>
              </div>

              <div className="button-row">
                <button type="submit" className="btn btn-gold auth-submit" disabled={submitting}>
                  {submitting ? 'جارٍ الدخول…' : 'تسجيل الدخول'}
                </button>
              </div>
            </form>
          ) : (
            <form onSubmit={submitForgot}>
              {forgotDone ? (
                <div className="status-box success">إذا كان الحساب موجوداً فسيتم إرسال رابط إعادة التعيين.</div>
              ) : (
                <>
                  <label htmlFor="forgot">اسم المستخدم أو البريد الإلكتروني</label>
                  <input id="forgot" type="text" value={username} onChange={(e) => setUsername(e.target.value)} required />
                </>
              )}
              <div className="button-row">
                {!forgotDone && (
                  <button type="submit" className="btn btn-gold auth-submit" disabled={submitting}>
                    {submitting ? 'جارٍ الإرسال…' : 'إرسال رابط إعادة التعيين'}
                  </button>
                )}
                <button type="button" className="btn secondary auth-submit"
                  onClick={() => { setForgotMode(false); setForgotDone(false); setError(''); }}>
                  العودة لتسجيل الدخول
                </button>
              </div>
            </form>
          )}

          <p className="auth-footnote">
            الحسابات تُنشأ من قبل مشرف المنصة. للحصول على حساب يرجى التواصل مع الإدارة.
          </p>
        </div>
      </section>

      {/* Brand column — carries the ministry logo, so the global top bar is
          hidden on this route (see SiteHeader). */}
      <aside className="auth-brand-panel">
        <div className="auth-brand-overlay" aria-hidden="true" />
        <div className="auth-brand-inner">
          <img className="auth-brand-logo" src="/header-logo-ar.png" alt="وزارة الاقتصاد والصناعة" />
          <div className="auth-brand-line" aria-hidden="true" />
          <h2 className="auth-brand-title">منصة إدارة الكروت الشخصية</h2>
          <p className="auth-brand-text">
            أرشفة الكروت الشخصية واستخراج بياناتها آلياً، والبحث فيها وإدارتها من مكان واحد.
          </p>
          <span className="header-badge auth-brand-badge">الجمهورية العربية السورية</span>
        </div>
      </aside>
    </main>
  );
}
