'use client';

import { FormEvent, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import PageHero from '@/components/PageHero';
import { BusinessCard, combineBilingual, fetchJson } from '@/lib/api';

type StatusType = 'idle' | 'loading' | 'success' | 'error';
type DuplicateResponse = {
  duplicate: true;
  saved: boolean;
  updated?: boolean;
  updated_fields?: string[];
  reason?: string;
  existing_card?: BusinessCard;
  extracted_data?: Partial<BusinessCard>;
};
type ExtractResponse = {
  duplicate: false;
  saved: true;
  card: BusinessCard;
  message?: string;
};

type StepKey = 'upload' | 'extract' | 'duplicate' | 'save';

export default function UploadPage() {
  const [front, setFront] = useState<File | null>(null);
  const [back, setBack] = useState<File | null>(null);
  const frontCameraRef = useRef<HTMLInputElement>(null);
  const frontGalleryRef = useRef<HTMLInputElement>(null);
  const backCameraRef = useRef<HTMLInputElement>(null);
  const backGalleryRef = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<{ type: StatusType; text: string }>({
    type: 'idle',
    text: "'اختر صورة الوجه الأمامي والخلفي ثم اضغط استخراج وحفظ.'",
  });
  const [currentStep, setCurrentStep] = useState<StepKey>('upload');
  const [doneSteps, setDoneSteps] = useState<StepKey[]>([]);
  const [savedCard, setSavedCard] = useState<BusinessCard | null>(null);
  const [duplicate, setDuplicate] = useState<DuplicateResponse | null>(null);

  const previewData = useMemo(() => savedCard || duplicate?.existing_card || null, [savedCard, duplicate]);

  function combinedField(card: BusinessCard, field: 'person_name' | 'job_title' | 'company_name') {
    if (field === 'person_name') return combineBilingual(card.person_name, card.person_name_ar, card.person_name_en);
    if (field === 'job_title') return combineBilingual(card.job_title, card.job_title_ar, card.job_title_en);
    return combineBilingual(card.company_name, card.company_name_ar, card.company_name_en);
  }

  function markStep(step: StepKey, done: StepKey[] = []) {
    setCurrentStep(step);
    setDoneSteps(done);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!front) {
      setStatus({ type: 'error', text: 'يجب اختيار صورة الوجه الأمامي أولًا.' });
      return;
    }
      // basic client-side file size validation (6MB limit)
      const MAX_FILE_BYTES = 6 * 1024 * 1024;
      if (front.size && front.size > MAX_FILE_BYTES) {
        setStatus({ type: 'error', text: 'حجم صورة الوجه الأمامي كبير جدًا. الرجاء اختيار ملف أقل من 6 ميغابايت.' });
        return;
      }

    const fd = new FormData();
    fd.append('front', front);
    if (back) fd.append('back', back);

    setLoading(true);
    setSavedCard(null);
    setDuplicate(null);
    markStep('upload', []);
    setStatus({ type: 'loading', text: 'جاري رفع الصور إلى الخادم...' });

    try {
      await new Promise(resolve => setTimeout(resolve, 200));
      markStep('extract', ['upload']);
      setStatus({ type: 'loading', text: 'جاري استخراج البيانات وزيارة موقع الشركة عند الحاجة...' });

      const data = await fetchJson<ExtractResponse | DuplicateResponse>('/cards/extract/', {
        method: 'POST',
        body: fd,
      });

      markStep('duplicate', ['upload', 'extract']);
      if (data.duplicate) {
        setDuplicate(data);
        markStep('save', ['upload', 'extract', 'duplicate']);
        const duplicateMessage = data.updated
          ? `الكرت موجود سابقًا، وتم ترميم المعلومات أو الصور الناقصة في السجل المحفوظ. السبب: ${data.reason || 'مطابقة مع سجل محفوظ'}`
          : `الكرت موجود سابقًا ولا توجد معلومات أو صور ناقصة لترميمها. السبب: ${data.reason || 'مطابقة مع سجل محفوظ'}`;
        setStatus({
          type: data.updated ? 'success' : 'error',
          text: duplicateMessage,
        });
        return;
      }

      setSavedCard(data.card);
      markStep('save', ['upload', 'extract', 'duplicate', 'save']);
      setStatus({ type: 'success', text: data.message || `تم حفظ الكرت كسجل رقم ${data.card.sequence_number}` });
    } catch (error: any) {
      setStatus({ type: 'error', text: error.message || 'حدث خطأ أثناء المعالجة.' });
    } finally {
      setLoading(false);
    }
  }

  function stepClass(step: StepKey) {
    if (doneSteps.includes(step)) return 'step done';
    if (currentStep === step && loading) return 'step active';
    return 'step';
  }

  function selectedFileName(file: File | null) {
    return file ? file.name : 'لم يتم اختيار صورة بعد';
  }

  return (
    <main className="container">
      <PageHero
        title="استخراج بيانات الكرت الشخصي"
        description="ارفع صورة الوجه الأمامي والخلفي للبطاقة، وسيقوم النظام باستخراج البيانات وحفظها مباشرة في قاعدة البيانات مع منع التكرار."
      />

      <section className="card">
        <div className="section-head">
          <div>
          <h2>اختر صورة الوجه الأمامي والخلفي ثم اضغط استخراج وحفظ. </h2>

          </div>
          <Link href="/dashboard" className="download">عرض قاعدة البيانات</Link>
        </div>

        <form onSubmit={submit}>
          <div className="grid">
            <div className="image-picker">
              <span className="image-picker-title">صورة الوجه الأمامي</span>
              <input
                ref={frontCameraRef}
                className="file-input-hidden"
                type="file"
                suppressHydrationWarning
                accept="image/*"
                capture="environment"
                onChange={event => setFront(event.target.files?.[0] || null)}
              />
              <input
                ref={frontGalleryRef}
                className="file-input-hidden"
                type="file"
                suppressHydrationWarning
                accept="image/png,image/jpeg,image/webp,image/*"
                onChange={event => setFront(event.target.files?.[0] || null)}
              />
              <div className="image-picker-actions">
                <button type="button" className="file-action" onClick={() => frontCameraRef.current?.click()} disabled={loading}>
                  تصوير بالكاميرا
                </button>
                <button type="button" className="file-action secondary" onClick={() => frontGalleryRef.current?.click()} disabled={loading}>
                  اختيار من المعرض
                </button>
              </div>
              <span className={`selected-file ${front ? 'has-file' : ''}`}>{selectedFileName(front)}</span>
            </div>
            <div className="image-picker">
              <span className="image-picker-title">صورة الوجه الخلفي</span>
              <input
                ref={backCameraRef}
                className="file-input-hidden"
                type="file"
                suppressHydrationWarning
                accept="image/*"
                capture="environment"
                onChange={event => setBack(event.target.files?.[0] || null)}
              />
              <input
                ref={backGalleryRef}
                className="file-input-hidden"
                type="file"
                suppressHydrationWarning
                accept="image/png,image/jpeg,image/webp,image/*"
                onChange={event => setBack(event.target.files?.[0] || null)}
              />
              <div className="image-picker-actions">
                <button type="button" className="file-action" onClick={() => backCameraRef.current?.click()} disabled={loading}>
                  تصوير بالكاميرا
                </button>
                <button type="button" className="file-action secondary" onClick={() => backGalleryRef.current?.click()} disabled={loading}>
                  اختيار من المعرض
                </button>
              </div>
              <span className={`selected-file ${back ? 'has-file' : ''}`}>{selectedFileName(back)}</span>
            </div>
          </div>

          <div className="button-row">
            <button type="submit" className="btn-gold" disabled={loading}>
              {loading ? 'جاري المعالجة...' : 'استخراج وحفظ'}
            </button>
            <Link href="/upload/manual" className="btn btn-gold secondary" aria-label="رفع كرت يدويا">
              رفع كرت يدوياً
            </Link>
            <button
              type="button"
              disabled={loading}
              onClick={() => {
                setFront(null);
                setBack(null);
                setSavedCard(null);
                setDuplicate(null);
                setStatus({ type: 'idle', text: 'تمت إعادة ضبط النموذج. اختر صورًا جديدة.' });
                markStep('upload', []);
                const inputs = document.querySelectorAll<HTMLInputElement>('input[type="file"]');
                inputs.forEach(input => { input.value = ''; });
              }}
            >
              ادخال كرت جديد
            </button>
          </div>
        </form>

        {status.type === 'error' && status.text && (
          <p className="status-box error">
            {status.text}
          </p>
        )}

        <div className="steps" aria-label="تتبع عملية المعالجة">
          <div className={stepClass('upload')}><span className="step-dot" /> رفع الصور</div>
          <div className={stepClass('extract')}><span className="step-dot" /> استخراج البيانات وتحليل الموقع</div>
          <div className={stepClass('duplicate')}><span className="step-dot" /> فحص التكرار</div>
          <div className={stepClass('save')}><span className="step-dot" /> حفظ السجل في قاعدة البيانات</div>
        </div>
      </section>

      {previewData && (
        <section className="card">
          <div className="section-head">
            <h2>{duplicate ? 'الكرت موجود سابقًا' : 'تم حفظ الكرت بنجاح'}</h2>
            <span className={duplicate ? 'badge warning' : 'badge success'}>
              {duplicate ? 'مكرر' : `سجل #${previewData.sequence_number}`}
            </span>
          </div>

          <div className="grid">
            <label className="full-width">اسم الشخص <textarea readOnly value={combinedField(previewData, 'person_name')} /></label>
            <label className="full-width">المنصب <textarea readOnly value={combinedField(previewData, 'job_title')} /></label>
            <label className="full-width">اسم الشركة <textarea readOnly value={combinedField(previewData, 'company_name')} /></label>
            <label>أرقام الموبايل <input className="ltr-input" dir="ltr" readOnly value={(previewData.mobile_numbers || []).map(n => String(n).replace(/[^0-9+]/g, '')).join(' | ')} /></label>
            <label>الإيميلات <input readOnly value={(previewData.emails || []).join(' | ')} /></label>
            <label>الموقع الالكتروني <input readOnly value={previewData.website || ''} /></label>
            <label>نوع الاستثمار <input readOnly value={previewData.investment_type === 'غير ذلك' ? (previewData.investment_type_other || 'غير ذلك') : (previewData.investment_type || '')} /></label>
            <label className="full-width">نشاط الشركة <textarea readOnly value={previewData.company_activity || ''} /></label>
            <label className="full-width">العنوان <input readOnly value={previewData.address || ''} /></label>
          </div>
        </section>
      )}
    </main>
  );
}
