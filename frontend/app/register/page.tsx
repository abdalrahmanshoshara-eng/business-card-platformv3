'use client';

import { FormEvent, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import PageHero from '@/components/PageHero';
import { ApiError } from '@/lib/api';
import { useAuth } from '@/features/auth/AuthProvider';
import { register } from '@/features/auth/api';

export default function RegisterPage() {
  const { user, loading, setUser } = useAuth();
  const router = useRouter();

  const [form, setForm] = useState({
    username: '', email: '', password: '', password_confirm: '', first_name: '', last_name: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [disabled, setDisabled] = useState(false);

  useEffect(() => {
    if (!loading && user) router.replace('/dashboard');
  }, [loading, user, router]);

  function update(key: keyof typeof form) {
    return (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [key]: e.target.value }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    if (form.password !== form.password_confirm) {
      setError('كلمتا المرور غير متطابقتين.');
      return;
    }
    setSubmitting(true);
    try {
      const me = await register({ ...form, username: form.username.trim(), email: form.email.trim() });
      setUser(me);
      router.replace('/dashboard');
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setDisabled(true);
      } else {
        setError(err instanceof ApiError ? err.message : 'تعذّر إنشاء الحساب.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="container">
      <PageHero title="إنشاء حساب" description="أنشئ حساباً جديداً للوصول إلى المنصة." />

      <div className="card" style={{ maxWidth: 560, margin: '0 auto' }}>
        {disabled ? (
          <div className="status-box">
            التسجيل الذاتي غير مفعّل حالياً. يرجى التواصل مع المشرف لإنشاء حساب لك.
            <p className="helper-text" style={{ marginTop: 12 }}>
              <Link href="/login">العودة لتسجيل الدخول</Link>
            </p>
          </div>
        ) : (
          <form onSubmit={submit}>
            <label htmlFor="username">اسم المستخدم</label>
            <input id="username" type="text" value={form.username} onChange={update('username')} required />

            <label htmlFor="email">البريد الإلكتروني</label>
            <input id="email" type="email" value={form.email} onChange={update('email')} required />

            <div className="grid">
              <div>
                <label htmlFor="first_name">الاسم الأول</label>
                <input id="first_name" type="text" value={form.first_name} onChange={update('first_name')} />
              </div>
              <div>
                <label htmlFor="last_name">الاسم الأخير</label>
                <input id="last_name" type="text" value={form.last_name} onChange={update('last_name')} />
              </div>
            </div>

            <label htmlFor="password">كلمة المرور</label>
            <input id="password" type="password" autoComplete="new-password" value={form.password} onChange={update('password')} required />

            <label htmlFor="password_confirm">تأكيد كلمة المرور</label>
            <input id="password_confirm" type="password" autoComplete="new-password" value={form.password_confirm} onChange={update('password_confirm')} required />

            {error && <div className="status-box error" style={{ marginTop: 12 }}>{error}</div>}

            <div className="button-row">
              <button type="submit" className="btn btn-gold" disabled={submitting}>
                {submitting ? 'جارٍ الإنشاء…' : 'إنشاء الحساب'}
              </button>
            </div>
            <p className="helper-text" style={{ marginTop: 16 }}>
              لديك حساب بالفعل؟ <Link href="/login">تسجيل الدخول</Link>
            </p>
          </form>
        )}
      </div>
    </main>
  );
}
