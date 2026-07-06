'use client';

import { FormEvent, useRef, useState } from 'react';
import Link from 'next/link';
import PageHero from '@/components/PageHero';
import { BusinessCard, fetchJson } from '@/lib/api';
import { INVESTMENT_TYPES } from '@/lib/constants';

export default function ManualAddPage() {
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<{ type: 'idle' | 'success' | 'error'; text?: string }>({ type: 'idle' });
  const [saved, setSaved] = useState<BusinessCard | null>(null);
  const frontRef = useRef<HTMLInputElement | null>(null);
  const backRef = useRef<HTMLInputElement | null>(null);
  const [investmentType, setInvestmentType] = useState<string>('');
  const [investmentTypeOther, setInvestmentTypeOther] = useState<string>('');

  function splitMultiValue(value: string) {
    return value
      .split(/[|\n,]+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setStatus({ type: 'idle' });
    const form = e.currentTarget;
    const fd = new FormData();
    const fields = ['person_name','person_name_ar','person_name_en','job_title','job_title_ar','job_title_en','company_name','company_name_ar','company_name_en','website','address','company_activity','raw_text'];
    for (const name of fields) {
      const el = form.elements.namedItem(name) as HTMLInputElement | HTMLTextAreaElement | null;
      if (el && el.value) fd.append(name, el.value);
    }
    const mobileField = form.elements.namedItem('mobile_numbers') as HTMLInputElement | null;
    const emailField = form.elements.namedItem('emails') as HTMLInputElement | null;
    const mobileNumbers = mobileField ? splitMultiValue(mobileField.value) : [];
    const emails = emailField ? splitMultiValue(emailField.value) : [];
    if (mobileNumbers.length) {
      fd.append('mobile_numbers', JSON.stringify(mobileNumbers));
    }
    if (emails.length) {
      fd.append('emails', JSON.stringify(emails));
    }
    // ensure investment type values come from React state
    fd.append('investment_type', investmentType || '');
    if (investmentType === 'غير ذلك') {
      fd.append('investment_type_other', investmentTypeOther || '');
    }
    if (frontRef.current?.files?.[0]) fd.append('front', frontRef.current.files[0]);
    if (backRef.current?.files?.[0]) fd.append('back', backRef.current.files[0]);

    setLoading(true);
    try {
      const data = await fetchJson<{ card?: BusinessCard; duplicate?: boolean; existing_card?: BusinessCard; updated?: boolean }>('/cards', { method: 'POST', body: fd });
      if (data.duplicate) {
        const existingCard = data.existing_card;
        setSaved(existingCard || null);
        setStatus({
          type: 'success',
          text: data.updated
            ? `تم تحديث الكرت الموجود (#${existingCard?.sequence_number}).`
            : `تم العثور على كرت مطابق بالفعل (#${existingCard?.sequence_number}).`,
        });
      } else if (data.card) {
        setSaved(data.card);
        setStatus({ type: 'success', text: `تم حفظ الكرت كسجل رقم ${data.card.sequence_number}` });
      } else {
        setStatus({ type: 'error', text: 'الاستجابة من الخادم غير صحيحة.' });
      }
      form.reset();
    } catch (err: any) {
      setStatus({ type: 'error', text: err.message || 'فشل الحفظ' });
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="container">
      <PageHero title="إضافة كرت يدوياً" description="أدخل بيانات الكرت يدوياً أو ارفع صورة للحفظ مباشرة." />

      <section className="card">
        <div className="section-head">
          <h2>نموذج إضافة كرت</h2>
          <Link href="/upload" className="download">استخراج تلقائي من صورة</Link>
        </div>

        <form onSubmit={submit}>
          <div className="grid">
            <label>اسم الشخص (عربي)<input name="person_name_ar" /></label>
            <label>اسم الشخص (إنجليزي)<input name="person_name_en" /></label>
            <label>المنصب (عربي)<input name="job_title_ar" /></label>
            <label>المنصب (إنجليزي)<input name="job_title_en" /></label>
            <label>اسم الشركة (عربي)<input name="company_name_ar" /></label>
            <label>اسم الشركة (إنجليزي)<input name="company_name_en" /></label>
            <label>الموبايلات (افصل بين الأرقام بـ | )<input name="mobile_numbers" placeholder="+9665xxxxxxx | 055xxxxxxx" /></label>
            <label>الإيميلات (افصل بـ | )<input name="emails" placeholder="a@example.com | b@example.com" /></label>
            <label>الموقع الالكتروني<input name="website" /></label>
            <label>العنوان<textarea name="address" /></label>
            <label>نشاط الشركة<textarea name="company_activity" /></label>
            <label>نوع الاستثمار
              <select name="investment_type" value={investmentType} onChange={(e) => setInvestmentType(e.target.value)}>
                <option value="">-- اختر نوع الاستثمار --</option>
                {INVESTMENT_TYPES.map((type) => (
                  <option key={type} value={type}>{type}</option>
                ))}
              </select>
            </label>
            {investmentType === 'غير ذلك' && (
              <label className="full-width">تفاصيل نوع الاستثمار<textarea value={investmentTypeOther} onChange={(e) => setInvestmentTypeOther(e.target.value)} name="investment_type_other" /></label>
            )}
            <label>ملاحظات أو نص خام<textarea name="raw_text" /></label>
            <label>صورة الوجه الأمامي<input ref={frontRef} type="file" name="front" accept="image/*" /></label>
            <label>صورة الوجه الخلفي<input ref={backRef} type="file" name="back" accept="image/*" /></label>
          </div>

          <div className="button-row">
            <button className="btn-gold" disabled={loading}>{loading ? 'جاري الحفظ...' : 'حفظ الكرت'}</button>
            <button type="button" onClick={() => { setStatus({ type: 'idle' }); setSaved(null); (document.querySelector('form') as HTMLFormElement)?.reset(); }} disabled={loading}>إفراغ النموذج</button>
          </div>
        </form>

        {status.type === 'error' && <p className="status-box error">{status.text}</p>}
        {status.type === 'success' && <p className="status-box success">{status.text}</p>}

        {saved && (
          <div className="card">
            <h3>تم الحفظ: سجل #{saved.sequence_number}</h3>
            <p>الاسم: {saved.person_name || `${saved.person_name_ar} ${saved.person_name_en}`}</p>
            <p>الشركة: {saved.company_name || `${saved.company_name_ar} ${saved.company_name_en}`}</p>
            <p>الهاتف: {(saved.mobile_numbers || []).join(' | ')}</p>
            <p>الإيميل: {(saved.emails || []).join(' | ')}</p>
            <Link href={`/dashboard`}>عرض قاعدة البيانات</Link>
          </div>
        )}

      </section>
    </main>
  );
}
