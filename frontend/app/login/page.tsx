'use client';

import { FormEvent, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import PageHero from '@/components/PageHero';
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
  const [remember, setRemember] = useState(true);
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
      await login(username.trim(), password, remember);
      try {
        if (remember) window.localStorage.setItem('bcp_last_username', username.trim());
        else window.localStorage.removeItem('bcp_last_username');
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
    <main className="container">
      <PageHero title="تسجيل الدخول" description="أدخل اسم المستخدم أو البريد الإلكتروني وكلمة المرور للوصول إلى حسابك." />

      <div className="card" style={{ maxWidth: 480, margin: '0 auto' }}>
        {!forgotMode ? (
          <form onSubmit={submit}>
            <label htmlFor="username">اسم المستخدم أو البريد الإلكتروني</label>
            <input id="username" type="text" autoComplete="username" value={username}
              onChange={(e) => setUsername(e.target.value)} required />

            <label htmlFor="password">كلمة المرور</label>
            <input id="password" type="password" autoComplete="current-password" value={password}
              onChange={(e) => setPassword(e.target.value)} required />

            {error && <div className="status-box error" style={{ marginTop: 12 }}>{error}</div>}

            <label className="check-row" style={{ marginTop: 14 }}>
              <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
              تذكّرني على هذا الجهاز
            </label>

            <div className="button-row">
              <button type="submit" className="btn btn-gold" disabled={submitting}>
                {submitting ? 'جارٍ الدخول…' : 'تسجيل الدخول'}
              </button>
            </div>

            <p className="helper-text" style={{ marginTop: 16 }}>
              لا تملك حساباً؟ <Link href="/register">إنشاء حساب</Link>
            </p>
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
                <button type="submit" className="btn btn-gold" disabled={submitting}>
                  {submitting ? 'جارٍ الإرسال…' : 'إرسال رابط إعادة التعيين'}
                </button>
              )}
              <button type="button" className="btn secondary" onClick={() => { setForgotMode(false); setForgotDone(false); }}>
                العودة لتسجيل الدخول
              </button>
            </div>
          </form>
        )}
      </div>
    </main>
  );
}
