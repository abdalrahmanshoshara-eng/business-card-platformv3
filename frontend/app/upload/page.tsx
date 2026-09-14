'use client';
import { RequireAuth as __RequireAuth } from '@/features/auth/Guard';

import { FormEvent, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import PageHero from '@/components/PageHero';
import WelcomePrompt from '@/components/WelcomePrompt';
import { useAuth } from '@/features/auth/AuthProvider';
import {
  BusinessCard,
  EnrichmentResponse,
  combineBilingual,
  fetchJson,
  newIdempotencyKey,
  sendCardWelcome,
} from '@/lib/api';

type StatusType = 'idle' | 'loading' | 'success' | 'error';
type DuplicateResponse = {
  duplicate: true;
  saved: boolean;
  updated?: boolean;
  updated_fields?: string[];
  reason?: string;
  existing_card?: BusinessCard;
  extracted_data?: Partial<BusinessCard>;
  idempotent_replay?: boolean;
};
type ExtractResponse = {
  duplicate: false;
  saved: true;
  card: BusinessCard;
  message?: string;
  idempotent_replay?: boolean;
  website_visited?: boolean;
  enrichment?: { reused: boolean; status: string };
};
type ProcessingResponse = {
  error_type: 'extraction_in_progress';
  extraction_status: 'processing';
  detail?: string;
};

type StepKey = 'upload' | 'extract' | 'duplicate' | 'save';

// Holds the in-flight upload's idempotency key across a page reload.
const IDEMPOTENCY_STORAGE_KEY = 'cardnest:upload:idempotency-key';

const REVIEW_FIELD_LABELS: Record<string, string> = {
  person_name: 'اسم الشخص',
  person_name_ar: 'اسم الشخص (عربي)',
  person_name_en: 'اسم الشخص (إنجليزي)',
  job_title: 'المنصب',
  company_name: 'اسم الشركة',
  mobile_numbers: 'أرقام الموبايل',
  emails: 'الإيميلات',
  website: 'الموقع الإلكتروني',
  address: 'العنوان',
  company_activity: 'نشاط الشركة',
  investment_type: 'نوع الاستثمار',
};

function UploadPageInner() {
  const { user } = useAuth();
  const router = useRouter();
  const welcomeConfigured = !!user?.welcome_email?.sender_email;
  const [front, setFront] = useState<File | null>(null);
  const [back, setBack] = useState<File | null>(null);
  const frontCameraRef = useRef<HTMLInputElement>(null);
  const frontGalleryRef = useRef<HTMLInputElement>(null);
  const backCameraRef = useRef<HTMLInputElement>(null);
  const backGalleryRef = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<{ type: StatusType; text: string }>({
    type: 'idle',
    text: 'اختر صورة الوجه الأمامي (والخلفي اختيارياً) ثم اضغط استخراج وحفظ.',
  });
  const [currentStep, setCurrentStep] = useState<StepKey>('upload');
  const [doneSteps, setDoneSteps] = useState<StepKey[]>([]);
  const [savedCard, setSavedCard] = useState<BusinessCard | null>(null);
  const [duplicate, setDuplicate] = useState<DuplicateResponse | null>(null);

  // Enrichment (cached per domain; shown after extraction).
  const [enrichLoading, setEnrichLoading] = useState(false);
  const [enrichment, setEnrichment] = useState<EnrichmentResponse | null>(null);

  // Welcome email: a prompt appears after a new card is saved.
  const [welcomePromptOpen, setWelcomePromptOpen] = useState(false);
  const [welcomeSending, setWelcomeSending] = useState(false);
  const [welcomeInfo, setWelcomeInfo] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Guards against double submission: an in-flight ref (survives re-renders /
  // React StrictMode) plus a stable idempotency key per attempt so a refresh or
  // timeout retry never bills Gemini twice.
  const inFlightRef = useRef(false);

  const previewData = useMemo(() => savedCard || duplicate?.existing_card || null, [savedCard, duplicate]);
  const reviewFields = useMemo(() => previewData?.review_fields || [], [previewData]);

  // The key lives in sessionStorage, not in a ref: a ref dies with the page, so
  // reloading mid-extraction used to start a brand-new operation and pay for a
  // second Gemini call. sessionStorage survives the reload and is still scoped
  // to this one tab. Every file-input change clears it, so a different card
  // never reuses the previous card's key.
  function currentIdempotencyKey(): string {
    try {
      const stored = sessionStorage.getItem(IDEMPOTENCY_STORAGE_KEY);
      if (stored) return stored;
      const fresh = newIdempotencyKey();
      sessionStorage.setItem(IDEMPOTENCY_STORAGE_KEY, fresh);
      return fresh;
    } catch {
      // Private mode or blocked storage: fall back to a per-attempt key.
      return newIdempotencyKey();
    }
  }

  function resetIdempotencyKey() {
    try {
      sessionStorage.removeItem(IDEMPOTENCY_STORAGE_KEY);
    } catch {
      /* nothing to clear when storage is unavailable */
    }
  }

  function combinedField(card: BusinessCard, field: 'person_name' | 'job_title' | 'company_name') {
    if (field === 'person_name') return combineBilingual(card.person_name, card.person_name_ar, card.person_name_en);
    if (field === 'job_title') return combineBilingual(card.job_title, card.job_title_ar, card.job_title_en);
    return combineBilingual(card.company_name, card.company_name_ar, card.company_name_en);
  }

  function fieldClass(field: string) {
    return reviewFields.includes(field) ? 'review-flagged' : '';
  }

  function markStep(step: StepKey, done: StepKey[] = []) {
    setCurrentStep(step);
    setDoneSteps(done);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // Hard guards: never run two extractions for the same click / attempt.
    if (loading || inFlightRef.current) return;
    if (!front) {
      setStatus({ type: 'error', text: 'يجب اختيار صورة الوجه الأمامي أولًا.' });
      return;
    }
    const MAX_FILE_BYTES = 10 * 1024 * 1024;
    if (front.size && front.size > MAX_FILE_BYTES) {
      setStatus({ type: 'error', text: 'حجم صورة الوجه الأمامي كبير جدًا. الرجاء اختيار ملف أقل من 10 ميغابايت.' });
      return;
    }

    // Stable key for this attempt: created once, reused across refresh/timeout retries.
    const idempotencyKey = currentIdempotencyKey();

    const fd = new FormData();
    fd.append('front', front);
    if (back) fd.append('back', back);
    fd.append('idempotency_key', idempotencyKey);

    inFlightRef.current = true;
    setLoading(true);
    setSavedCard(null);
    setDuplicate(null);
    setEnrichment(null);
    setWelcomeInfo(null);
    setWelcomePromptOpen(false);
    markStep('upload', []);
    setStatus({ type: 'loading', text: 'جاري رفع الصور إلى الخادم...' });

    try {
      markStep('extract', ['upload']);
      setStatus({ type: 'loading', text: 'جارٍ استخراج البيانات...' });

      const data = await fetchJson<ExtractResponse | DuplicateResponse | ProcessingResponse>('/cards/extract/', {
        method: 'POST',
        body: fd,
        headers: { 'X-Idempotency-Key': idempotencyKey },
      });

      if ((data as ProcessingResponse).extraction_status === 'processing') {
        setStatus({ type: 'loading', text: 'العملية قيد المعالجة حالياً. لا حاجة لإعادة الإرسال؛ سيظهر الناتج عند الاكتمال.' });
        return;
      }

      markStep('duplicate', ['upload', 'extract']);
      const replayNote = (data as any).idempotent_replay ? ' (أُعيد استخدام نتيجة سابقة لنفس العملية دون استدعاء جديد)' : '';

      if ((data as DuplicateResponse).duplicate) {
        const dup = data as DuplicateResponse;
        setDuplicate(dup);
        markStep('save', ['upload', 'extract', 'duplicate']);
        const duplicateMessage = dup.updated
          ? `الكرت موجود سابقًا، وتم ترميم المعلومات أو الصور الناقصة. السبب: ${dup.reason || 'مطابقة مع سجل محفوظ'}`
          : `الكرت موجود سابقًا ولا توجد معلومات ناقصة لترميمها. السبب: ${dup.reason || 'مطابقة مع سجل محفوظ'}`;
        setStatus({ type: dup.updated ? 'success' : 'error', text: duplicateMessage + replayNote });
        // A successful (idempotent) completion: allow a fresh attempt next time.
        resetIdempotencyKey();
        return;
      }

      const ok = data as ExtractResponse;
      setSavedCard(ok.card);
      markStep('save', ['upload', 'extract', 'duplicate', 'save']);
      setStatus({ type: 'success', text: (ok.message || `تم حفظ الكرت كسجل رقم ${ok.card.sequence_number}`) + replayNote });
      resetIdempotencyKey();
      // Prompt to send the welcome email once we have the card's email.
      if ((ok.card.emails || []).length > 0) {
        setWelcomePromptOpen(true);
      }
      // If the website was visited during extraction, surface the cached result.
      if (ok.website_visited && ok.card.website) {
        try {
          const enr = await fetchJson<EnrichmentResponse>(`/cards/${ok.card.id}/enrichment/`);
          setEnrichment(enr);
        } catch { /* non-fatal: the enrich button remains available */ }
      }
    } catch (error: any) {
      // Keep the same idempotency key so a manual retry of a transient failure
      // reuses the in-flight/cached operation instead of double-billing. The one
      // exception is a key the server has already tied to different images:
      // that key can never succeed again, so retire it and let the retry get a
      // fresh one.
      if (error?.errorType === 'idempotency_key_reused') resetIdempotencyKey();
      setStatus({ type: 'error', text: error.message || 'حدث خطأ أثناء المعالجة.' });
    } finally {
      inFlightRef.current = false;
      setLoading(false);
    }
  }

  async function doSendWelcome() {
    if (!savedCard || welcomeSending) return;
    setWelcomeSending(true);
    setWelcomeInfo(null);
    try {
      const resend = savedCard.welcome_status === 'sent';
      const data = await sendCardWelcome(savedCard.id, resend);
      if (data.card) setSavedCard(data.card);
      setWelcomeInfo({ type: 'success', text: data.detail || 'تم إرسال رسالة الترحيب.' });
    } catch (error: any) {
      setWelcomeInfo({ type: 'error', text: error.message || 'تعذّر إرسال رسالة الترحيب.' });
    } finally {
      setWelcomeSending(false);
      setWelcomePromptOpen(false);
    }
  }

  async function runEnrichment(refresh: boolean) {
    if (!savedCard || enrichLoading) return;
    setEnrichLoading(true);
    try {
      const data = await fetchJson<EnrichmentResponse>(`/cards/${savedCard.id}/enrich/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh }),
      });
      setEnrichment(data);
    } catch (error: any) {
      setEnrichment({ card_id: savedCard.id, status: 'failed', reused: false, detail: error.message || 'تعذر إثراء بيانات الشركة.' });
    } finally {
      setEnrichLoading(false);
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
        description="ارفع صورة الوجه الأمامي (والخلفي اختيارياً)، وسيستخرج النظام البيانات في استدعاء واحد ويحفظها مباشرة مع منع التكرار."
      />

      <section className="card">
        <div className="section-head">
          <div>
            <h2>اختر صورة الوجه الأمامي (والخلفي اختيارياً) ثم اضغط استخراج وحفظ.</h2>
          </div>
          <Link href="/dashboard" className="download">عرض قاعدة البيانات</Link>
        </div>

        <form onSubmit={submit}>
          <div className="grid">
            <div className="image-picker">
              <span className="image-picker-title">صورة الوجه الأمامي (إلزامية)</span>
              <input
                ref={frontCameraRef}
                className="file-input-hidden"
                type="file"
                suppressHydrationWarning
                accept="image/*"
                capture="environment"
                onChange={event => { setFront(event.target.files?.[0] || null); resetIdempotencyKey(); }}
              />
              <input
                ref={frontGalleryRef}
                className="file-input-hidden"
                type="file"
                suppressHydrationWarning
                accept="image/png,image/jpeg,image/webp,image/*"
                onChange={event => { setFront(event.target.files?.[0] || null); resetIdempotencyKey(); }}
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
              <span className="image-picker-title">صورة الوجه الخلفي (اختيارية)</span>
              <input
                ref={backCameraRef}
                className="file-input-hidden"
                type="file"
                suppressHydrationWarning
                accept="image/*"
                capture="environment"
                onChange={event => { setBack(event.target.files?.[0] || null); resetIdempotencyKey(); }}
              />
              <input
                ref={backGalleryRef}
                className="file-input-hidden"
                type="file"
                suppressHydrationWarning
                accept="image/png,image/jpeg,image/webp,image/*"
                onChange={event => { setBack(event.target.files?.[0] || null); resetIdempotencyKey(); }}
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
            <button type="submit" className="btn-gold" disabled={loading || !front}>
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
                setEnrichment(null);
                setWelcomeInfo(null);
                setWelcomePromptOpen(false);
                resetIdempotencyKey();
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
          <p className="status-box error">{status.text}</p>
        )}
        {status.type === 'loading' && status.text && (
          <p className="status-box">{status.text}</p>
        )}

        <div className="steps" aria-label="تتبع عملية المعالجة">
          <div className={stepClass('upload')}><span className="step-dot" /> رفع الصور</div>
          <div className={stepClass('extract')}><span className="step-dot" /> استخراج البيانات</div>
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

          {reviewFields.length > 0 && (
            <p className="status-box warning">
              حقول تحتاج مراجعة: {reviewFields.map(f => REVIEW_FIELD_LABELS[f] || f).join('، ')}
            </p>
          )}

          <div className="grid">
            <label className={`full-width ${fieldClass('person_name')}`}>اسم الشخص <textarea readOnly value={combinedField(previewData, 'person_name')} /></label>
            <label className={`full-width ${fieldClass('job_title')}`}>المنصب <textarea readOnly value={combinedField(previewData, 'job_title')} /></label>
            <label className={`full-width ${fieldClass('company_name')}`}>اسم الشركة <textarea readOnly value={combinedField(previewData, 'company_name')} /></label>
            <label className={fieldClass('mobile_numbers')}>أرقام الموبايل <input className="ltr-input" dir="ltr" readOnly value={(previewData.mobile_numbers || []).map(n => String(n).replace(/[^0-9+]/g, '')).join(' | ')} /></label>
            <label className={fieldClass('emails')}>الإيميلات <input readOnly value={(previewData.emails || []).join(' | ')} /></label>
            <label className={fieldClass('website')}>الموقع الالكتروني <input readOnly value={previewData.website || ''} /></label>
            <label className={fieldClass('investment_type')}>نوع الاستثمار <input readOnly value={previewData.investment_type === 'غير ذلك' ? (previewData.investment_type_other || 'غير ذلك') : (previewData.investment_type || '')} /></label>
            <label className={`full-width ${fieldClass('company_activity')}`}>نشاط الشركة <textarea readOnly value={previewData.company_activity || ''} /></label>
            <label className={`full-width ${fieldClass('address')}`}>العنوان <input readOnly value={previewData.address || ''} /></label>
          </div>
        </section>
      )}

      {savedCard && (savedCard.emails || []).length > 0 && (
        <section className="card">
          <div className="section-head">
            <h2>رسالة الترحيب</h2>
            {savedCard.welcome_status === 'sent' && <span className="badge success">تم الإرسال</span>}
            {savedCard.welcome_status === 'failed' && <span className="badge warning">فشل الإرسال</span>}
          </div>
          <p>
            المستلم: <strong dir="ltr">{savedCard.emails[0]}</strong>
          </p>
          <div className="button-row">
            <button
              type="button"
              className={savedCard.welcome_status === 'sent' ? 'btn btn-gold secondary' : 'btn-green'}
              disabled={welcomeSending}
              onClick={() => setWelcomePromptOpen(true)}
            >
              {savedCard.welcome_status === 'sent' ? 'إعادة إرسال الترحيب' : 'إرسال رسالة ترحيب'}
            </button>
          </div>
          {welcomeInfo && <p className={`status-box ${welcomeInfo.type}`}>{welcomeInfo.text}</p>}
        </section>
      )}

      <WelcomePrompt
        open={welcomePromptOpen}
        mode={welcomeConfigured ? 'confirm' : 'setup'}
        busy={welcomeSending}
        onConfirm={doSendWelcome}
        onSetupEmail={() => router.push('/profile')}
        onClose={() => setWelcomePromptOpen(false)}
      />

      {savedCard && savedCard.website && (
        <section className="card">
          <div className="section-head">
            <h2>إثراء بيانات الشركة من الموقع</h2>
            {enrichment?.enrichment && <span className="badge success">{enrichment.reused ? 'من المخزّن' : 'محدّث'}</span>}
          </div>
          <p>تحليل موقع الشركة اختياري ولا يبدأ تلقائياً. اضغط الزر لإثراء البيانات عند الحاجة.</p>
          <div className="button-row">
            <button type="button" className="btn-gold" disabled={enrichLoading} onClick={() => runEnrichment(false)}>
              {enrichLoading ? 'جارٍ الإثراء...' : 'إثراء بيانات الشركة من الموقع'}
            </button>
            {enrichment?.enrichment && (
              <button type="button" className="btn btn-gold secondary" disabled={enrichLoading} onClick={() => runEnrichment(true)}>
                إعادة تحديث بيانات الشركة
              </button>
            )}
          </div>

          {enrichment?.reused && enrichment.status === 'completed' && (
            <p className="status-box">أُعيد استخدام نتيجة محفوظة مسبقاً لنفس نطاق الشركة دون استدعاء جديد.</p>
          )}
          {enrichment && enrichment.status !== 'completed' && (
            <p className={`status-box ${enrichment.status === 'failed' || enrichment.status === 'unavailable' ? 'error' : ''}`}>
              {enrichment.detail || `حالة الإثراء: ${enrichment.status}`}
            </p>
          )}
          {enrichment?.enrichment && enrichment.status === 'completed' && (
            <div className="grid">
              <label className="full-width">وصف الشركة <textarea readOnly value={enrichment.enrichment.company_description || ''} /></label>
              <label>المجال <input readOnly value={enrichment.enrichment.industry || ''} /></label>
              <label>النطاق <input dir="ltr" readOnly value={enrichment.enrichment.canonical_domain || ''} /></label>
              <label className="full-width">الخدمات <input readOnly value={(enrichment.enrichment.services || []).join(' | ')} /></label>
              <label className="full-width">المنتجات <input readOnly value={(enrichment.enrichment.products || []).join(' | ')} /></label>
            </div>
          )}
        </section>
      )}
    </main>
  );
}

export default function UploadPage() {
  return (
    <__RequireAuth>
      <UploadPageInner />
    </__RequireAuth>
  );
}
