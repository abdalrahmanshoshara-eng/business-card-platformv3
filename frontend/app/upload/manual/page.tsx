'use client';
import { RequireAuth as __RequireAuth } from '@/features/auth/Guard';

import { FormEvent, useRef, useState } from 'react';
import Link from 'next/link';
import PageHero from '@/components/PageHero';
import { ApiError, BusinessCard, fetchJson } from '@/lib/api';
import { INVESTMENT_TYPES } from '@/lib/constants';

type DuplicateCandidate = {
  id: number;
  sequence_number: number;
  person_name: string;
  company_name: string;
  reason: string;
  score: number;
};

function ManualAddPageInner() {
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<{ type: 'idle' | 'success' | 'error' | 'warning'; text?: string }>({ type: 'idle' });
  const [saved, setSaved] = useState<BusinessCard | null>(null);
  const [duplicateCandidates, setDuplicateCandidates] = useState<DuplicateCandidate[]>([]);
  const formRef = useRef<HTMLFormElement | null>(null);
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

  function buildFormData(confirmDuplicate = false) {
    const form = formRef.current;
    if (!form) return null;
    const fd = new FormData();
    const fields = ['person_name','person_name_ar','person_name_en','job_title','job_title_ar','job_title_en','company_name','company_name_ar','company_name_en','website','address','country','company_activity','raw_text'];
    for (const name of fields) {
      const el = form.elements.namedItem(name) as HTMLInputElement | HTMLTextAreaElement | null;
      if (el && el.value) fd.append(name, el.value);
    }
    const mobileField = form.elements.namedItem('mobile_numbers') as HTMLInputElement | null;
    const emailField = form.elements.namedItem('emails') as HTMLInputElement | null;
    const mobileNumbers = mobileField ? splitMultiValue(mobileField.value) : [];
    const emails = emailField ? splitMultiValue(emailField.value) : [];
    fd.append('mobile_numbers', JSON.stringify(mobileNumbers));
    fd.append('emails', JSON.stringify(emails));
    fd.append('investment_type', investmentType || '');
    fd.append('investment_type_other', investmentType === 'غير ذلك' ? (investmentTypeOther || '') : '');
    if (confirmDuplicate) fd.append('confirm_duplicate', 'true');
    if (frontRef.current?.files?.[0]) fd.append('front', frontRef.current.files[0]);
    if (backRef.current?.files?.[0]) fd.append('back', backRef.current.files[0]);
    return fd;
  }

  async function submit(e?: FormEvent<HTMLFormElement>, confirmDuplicate = false) {
    e?.preventDefault();
    setStatus({ type: 'idle' });
    setSaved(null);
    if (!confirmDuplicate) setDuplicateCandidates([]);
    const fd = buildFormData(confirmDuplicate);
    if (!fd) return;

    setLoading(true);
    try {
      const data = await fetchJson<{ card?: BusinessCard; duplicate?: boolean; existing_card?: BusinessCard; updated?: boolean; message?: string }>('/cards', { method: 'POST', body: fd });
      if (data.card) {
        setSaved(data.card);
        setDuplicateCandidates([]);
        setStatus({ type: 'success', text: data.message || `تم حفظ الكرت كسجل رقم ${data.card.sequence_number}` });
        formRef.current?.reset();
        setInvestmentType('');
        setInvestmentTypeOther('');
      } else if (data.duplicate && data.existing_card) {
        setSaved(data.existing_card);
        setStatus({ type: 'success', text: data.updated ? `تم تحديث الكرت الموجود (#${data.existing_card.sequence_number}).` : `تم العثور على كرت مطابق بالفعل (#${data.existing_card.sequence_number}).` });
      } else {
        setStatus({ type: 'error', text: 'الاستجابة من الخادم غير صحيحة.' });
      }
    } catch (err: any) {
      if (err instanceof ApiError && err.data?.duplicate_conflict) {
        setDuplicateCandidates(err.data.duplicate_candidates || []);
        setStatus({ type: 'warning', text: err.message || 'يوجد كرت مشابه. راجع النتائج ثم اختر الحفظ رغم التكرار عند الحاجة.' });
      } else {
        setStatus({ type: 'error', text: err.message || 'فشل الحفظ' });
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="container">
      <PageHero title="إضافة كرت يدوياً" description="أدخل بيانات الكرت يدوياً أو ارفع صورة للحفظ مباشرة بدون الحاجة إلى Gemini." />

      <section className="card">
        <div className="section-head">
          <h2>نموذج إضافة كرت</h2>
          <Link href="/upload" className="download">استخراج تلقائي من صورة</Link>
        </div>

        <form ref={formRef} onSubmit={(event) => submit(event)}>
          <div className="grid">
            <label>اسم الشخص (عربي)<input name="person_name_ar" /></label>
            <label>اسم الشخص (إنجليزي)<input name="person_name_en" /></label>
            <label>المنصب (عربي)<input name="job_title_ar" /></label>
            <label>المنصب (إنجليزي)<input name="job_title_en" /></label>
            <label>اسم الشركة (عربي)<input name="company_name_ar" /></label>
            <label>اسم الشركة (إنجليزي)<input name="company_name_en" /></label>
            <label>الموبايلات (افصل بين الأرقام بـ | )<input name="mobile_numbers" placeholder="+9665xxxxxxx | 055xxxxxxx" /></label>
            <label>الإيميلات (افصل بـ | )<input name="emails" placeholder="a@example.com | b@example.com" /></label>
            <label>الموقع الالكتروني<input name="website" placeholder="example.com" /></label>
            <label>العنوان<textarea name="address" /></label>
            <label>الدولة<input name="country" placeholder="سوريا، تركيا، السعودية..." /></label>
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
            <button
              type="button"
              onClick={() => {
                setStatus({ type: 'idle' });
                setSaved(null);
                setDuplicateCandidates([]);
                formRef.current?.reset();
                setInvestmentType('');
                setInvestmentTypeOther('');
              }}
              disabled={loading}
            >
              إفراغ النموذج
            </button>
          </div>
        </form>

        {status.type === 'error' && <p className="status-box error">{status.text}</p>}
        {status.type === 'warning' && <p className="status-box error">{status.text}</p>}
        {status.type === 'success' && <p className="status-box success">{status.text}</p>}

        {duplicateCandidates.length > 0 && (
          <div className="card">
            <h3>كروت مشابهة محتملة</h3>
            <ul>
              {duplicateCandidates.map((candidate) => (
                <li key={candidate.id}>
                  #{candidate.sequence_number} — {candidate.person_name || 'بدون اسم'} — {candidate.company_name || 'بدون شركة'} — {candidate.reason}
                </li>
              ))}
            </ul>
            <button type="button" className="btn-gold" disabled={loading} onClick={() => submit(undefined, true)}>
              حفظ رغم التكرار
            </button>
          </div>
        )}

        {saved && (
          <div className="card">
            <h3>تم الحفظ: سجل #{saved.sequence_number}</h3>
            <p>الاسم: {saved.person_name || `${saved.person_name_ar} ${saved.person_name_en}`}</p>
            <p>الشركة: {saved.company_name || `${saved.company_name_ar} ${saved.company_name_en}`}</p>
            <p>الهاتف: {(saved.mobile_numbers || []).join(' | ')}</p>
            <p>الإيميل: {(saved.emails || []).join(' | ')}</p>
            <Link href="/dashboard">عرض قاعدة البيانات</Link>
          </div>
        )}

      </section>
    </main>
  );
}

export default function ManualAddPage() {
  return (
    <__RequireAuth>
      <ManualAddPageInner />
    </__RequireAuth>
  );
}
