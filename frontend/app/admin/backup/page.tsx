'use client';

import { useState } from 'react';
import PageHero from '@/components/PageHero';
import { RequireAuth } from '@/features/auth/Guard';
import { useAuth } from '@/features/auth/AuthProvider';
import { downloadDatabaseBackup } from '@/features/backup/api';

function BackupInner() {
  const { user } = useAuth();
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  if (!user?.is_superuser) {
    return (
      <main className="container">
        <p className="status-box error">النسخ الاحتياطي متاح لمدير النظام فقط.</p>
      </main>
    );
  }

  async function download() {
    if (busy) return;
    setBusy(true);
    setStatus(null);
    try {
      const name = await downloadDatabaseBackup();
      setStatus({ type: 'success', text: `تم تنزيل النسخة الاحتياطية: ${name}` });
    } catch (err: any) {
      setStatus({ type: 'error', text: err?.message || 'تعذّر تنزيل النسخة الاحتياطية.' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="container">
      <PageHero
        title="النسخ الاحتياطي"
        description="نزّل نسخة كاملة من بيانات المنصة كملف SQL واحفظها في مكان آمن، لتسترجعها عند الحاجة."
      />

      <section className="card">
        <div className="section-head">
          <h2>تنزيل نسخة احتياطية</h2>
        </div>
        <p>
          تشمل النسخة كل الكروت والمستخدمين والإعدادات ورسائل الترحيب. الملف يحوي بيانات حساسة
          (كلمات المرور مشفّرة)، فاحفظه في مكان آمن ولا تشاركه.
        </p>
        <div className="button-row">
          <button type="button" className="btn-gold" disabled={busy} onClick={download}>
            {busy ? 'جارٍ تجهيز النسخة…' : 'تنزيل نسخة احتياطية (SQL)'}
          </button>
        </div>
        {status && <p className={`status-box ${status.type}`}>{status.text}</p>}
        <p className="status-box warning">
          صور الكروت محفوظة كملفات على الخادم (مجلد <span dir="ltr">media</span>) وليست ضمن ملف SQL؛
          انسخ هذا المجلد أيضًا للاحتفاظ بالصور.
        </p>
      </section>

      <section className="card">
        <div className="section-head">
          <h2>الاسترجاع</h2>
        </div>
        <p>الاسترجاع يستبدل كل البيانات الحالية بمحتوى النسخة، ويتم من الخادم بأمر واحد:</p>
        <pre dir="ltr" className="ltr-input">python manage.py restore_sql_backup business-cards-backup-XXXX.sql --yes</pre>
        <p>
          الأمر يجهّز الجداول أولًا ثم يسترجع البيانات دفعةً واحدة؛ إن فشل أي جزء لا يتغيّر شيء. بعد
          الاسترجاع يلزم تسجيل الدخول من جديد.
        </p>
      </section>
    </main>
  );
}

export default function BackupPage() {
  return (
    <RequireAuth admin>
      <BackupInner />
    </RequireAuth>
  );
}
