'use client';

import { FormEvent, useState } from 'react';
import Link from 'next/link';
import PageHero from '@/components/PageHero';
import { ApiError } from '@/lib/api';
import { RequireAuth } from '@/features/auth/Guard';
import { sendWelcomeTest } from '@/features/auth/api';

function WelcomeTestInner() {
  const [email, setEmail] = useState('');
  const [sending, setSending] = useState(false);
  const [msg, setMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (sending) return;
    setMsg(null);
    setSending(true);
    try {
      const res = await sendWelcomeTest(email.trim());
      setMsg({ type: 'success', text: res.detail || 'تم إرسال رسالة الاختبار.' });
    } catch (err) {
      setMsg({ type: 'error', text: err instanceof ApiError ? err.message : 'تعذّر إرسال رسالة الاختبار.' });
    } finally {
      setSending(false);
    }
  }

  return (
    <main className="container">
      <PageHero
        title="اختبار إرسال البريد"
        description="أدخل بريدًا إلكترونيًا واضغط إرسال للتأكد من عمل إعدادات بريد المنصة. تُستخدم رسالة الترحيب من ملفك الشخصي إن كانت مضبوطة."
      />

      <section className="card">
        <div className="section-head">
          <h2>إرسال رسالة اختبار</h2>
          <Link href="/profile" className="download">إعدادات رسالة الترحيب</Link>
        </div>
        <form onSubmit={submit}>
          <label htmlFor="test_email">البريد الإلكتروني للمستلم</label>
          <input
            id="test_email"
            type="email"
            dir="ltr"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
          {msg && <div className={`status-box ${msg.type}`} style={{ marginTop: 12 }}>{msg.text}</div>}
          <div className="button-row">
            <button type="submit" className="btn-gold" disabled={sending || !email.trim()}>
              {sending ? 'جارٍ الإرسال...' : 'إرسال'}
            </button>
          </div>
        </form>
        <p className="status-box" style={{ marginTop: 12 }}>
          نصيحة: أرسل إلى بريدك الشخصي أولًا للتأكد من الوصول. إن فشل الإرسال تحقّق من إعدادات
          <span dir="ltr"> WELCOME_FROM_EMAIL / EMAIL_* </span> في الخادم.
        </p>
      </section>
    </main>
  );
}

export default function WelcomeTestPage() {
  return (
    <RequireAuth>
      <WelcomeTestInner />
    </RequireAuth>
  );
}
