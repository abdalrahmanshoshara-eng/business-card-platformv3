'use client';

import { FormEvent, useEffect, useState } from 'react';
import PageHero from '@/components/PageHero';
import { ApiError } from '@/lib/api';
import { RequireAuth } from '@/features/auth/Guard';
import { useAuth } from '@/features/auth/AuthProvider';
import {
  fetchWelcomeLetter,
  resetWelcomeLetter,
  sendWelcomeTest,
  updateWelcomeLetter,
} from '@/features/auth/api';

// The backend replaces this placeholder with a salutation tailored to each
// card's holder. Keep it in sync with accounts/welcome_templates.py.
const SALUTATION_TOKEN = '{{salutation}}';

const EMPTY = {
  welcome_subject: '',
  welcome_message: '',
  welcome_subject_en: '',
  welcome_message_en: '',
};

type Note = { type: 'success' | 'error'; text: string } | null;

function WelcomeLetterInner() {
  const { isAdmin } = useAuth();

  const [letter, setLetter] = useState(EMPTY);
  const [canEdit, setCanEdit] = useState(false);
  const [isCustomized, setIsCustomized] = useState(false);
  const [loading, setLoading] = useState(true);

  const [letterMsg, setLetterMsg] = useState<Note>(null);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);

  const [testEmail, setTestEmail] = useState('');
  const [testMsg, setTestMsg] = useState<Note>(null);
  const [sendingTest, setSendingTest] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const cfg = await fetchWelcomeLetter();
        if (cancelled) return;
        setLetter({
          welcome_subject: cfg.welcome_subject || '',
          welcome_message: cfg.welcome_message || '',
          welcome_subject_en: cfg.welcome_subject_en || '',
          welcome_message_en: cfg.welcome_message_en || '',
        });
        setCanEdit(!!cfg.can_edit_letter);
        setIsCustomized(!!cfg.is_customized);
      } catch (err) {
        if (!cancelled) {
          setLetterMsg({
            type: 'error',
            text: err instanceof ApiError ? err.message : 'تعذّر تحميل نصّ الرسالة.',
          });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canEdit) return;
    setLetterMsg(null);
    setSaving(true);
    try {
      const cfg = await updateWelcomeLetter(letter);
      setIsCustomized(!!cfg.is_customized);
      setLetterMsg({ type: 'success', text: 'تم حفظ النصّ. يسري الآن على رسائل جميع الحسابات.' });
    } catch (err) {
      setLetterMsg({ type: 'error', text: err instanceof ApiError ? err.message : 'تعذّر حفظ النصّ.' });
    } finally {
      setSaving(false);
    }
  }

  async function doReset() {
    setLetterMsg(null);
    setResetting(true);
    try {
      const cfg = await resetWelcomeLetter();
      setLetter({
        welcome_subject: cfg.welcome_subject || '',
        welcome_message: cfg.welcome_message || '',
        welcome_subject_en: cfg.welcome_subject_en || '',
        welcome_message_en: cfg.welcome_message_en || '',
      });
      setIsCustomized(!!cfg.is_customized);
      setConfirmReset(false);
      setLetterMsg({ type: 'success', text: 'تمت إعادة الرسالة إلى النصّ الرسمي الافتراضي.' });
    } catch (err) {
      setLetterMsg({ type: 'error', text: err instanceof ApiError ? err.message : 'تعذّرت إعادة الضبط.' });
    } finally {
      setResetting(false);
    }
  }

  async function sendTest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (sendingTest) return;
    setTestMsg(null);
    setSendingTest(true);
    try {
      const res = await sendWelcomeTest(testEmail.trim());
      setTestMsg({ type: 'success', text: res.detail || 'تم إرسال رسالة الاختبار.' });
    } catch (err) {
      setTestMsg({ type: 'error', text: err instanceof ApiError ? err.message : 'تعذّر إرسال رسالة الاختبار.' });
    } finally {
      setSendingTest(false);
    }
  }

  return (
    <main className="container">
      <PageHero
        title="رسالة الترحيب"
        description={
          canEdit
            ? 'النصّ الرسمي الذي يخرج باسم الوزارة إلى ضيوفها. موحّد لكل الحسابات، وأي تعديل هنا يسري على رسائل جميع المستخدمين.'
            : 'النصّ الرسمي الذي يخرج باسم الوزارة إلى ضيوفها. موحّد لكل الحسابات ويضبطه المشرف، وهذا ما سيُرسَل باسمك.'
        }
      />

      <section className="card">
        <div className="section-head">
          <h2>نصّ الرسالة</h2>
          <span className="download" style={{ cursor: 'default' }}>
            {isCustomized ? 'نصّ مخصّص' : 'النصّ الرسمي'}
          </span>
        </div>

        <p style={{ color: 'var(--text-muted)', marginTop: 0 }}>
          تُرسَل الرسالة بلغة الكرت: كرت عربي يستلم النصّ العربي وحده، وكرت بلغة أخرى يستلم النصّ
          العربي والنصّ بلغته في بريد واحد، وتبدأ بتحية مناسبة لصاحب الكرت.
          <code style={{ margin: '0 4px' }}>{SALUTATION_TOKEN}</code>
          {canEdit
            ? 'هو موضع تلك التحية — احتفظ به في بداية النصّ، أو احذفه لإرسال النصّ كما هو دون تحية.'
            : 'هو موضع تلك التحية، ويُستبدل بها تلقائيًا عند الإرسال حسب صاحب الكرت.'}
        </p>

        {loading ? (
          <p className="status">جارٍ تحميل النصّ…</p>
        ) : (
          <form onSubmit={save}>
            <label htmlFor="welcome_subject">عنوان الرسالة (عربي)</label>
            <input
              id="welcome_subject"
              type="text"
              value={letter.welcome_subject}
              readOnly={!canEdit}
              disabled={!canEdit}
              onChange={(e) => setLetter((l) => ({ ...l, welcome_subject: e.target.value }))}
            />
            <label htmlFor="welcome_message">نصّ الرسالة (عربي)</label>
            <textarea
              id="welcome_message"
              rows={14}
              value={letter.welcome_message}
              readOnly={!canEdit}
              disabled={!canEdit}
              onChange={(e) => setLetter((l) => ({ ...l, welcome_message: e.target.value }))}
            />

            <label htmlFor="welcome_subject_en">عنوان الرسالة (اللغة الثانية)</label>
            <input
              id="welcome_subject_en"
              type="text"
              dir="ltr"
              value={letter.welcome_subject_en}
              readOnly={!canEdit}
              disabled={!canEdit}
              onChange={(e) => setLetter((l) => ({ ...l, welcome_subject_en: e.target.value }))}
            />
            <label htmlFor="welcome_message_en">نصّ الرسالة (اللغة الثانية)</label>
            <textarea
              id="welcome_message_en"
              rows={14}
              dir="ltr"
              value={letter.welcome_message_en}
              readOnly={!canEdit}
              disabled={!canEdit}
              onChange={(e) => setLetter((l) => ({ ...l, welcome_message_en: e.target.value }))}
            />

            {letterMsg && (
              <div className={`status-box ${letterMsg.type}`} style={{ marginTop: 12 }}>
                {letterMsg.text}
              </div>
            )}

            {canEdit &&
              (confirmReset ? (
                <div className="status-box error" style={{ marginTop: 12 }}>
                  <div>
                    سيعود النصّ إلى الصيغة الرسمية الافتراضية <strong>لكل الحسابات</strong>، ويُفقد
                    أي تعديل مخصّص. متابعة؟
                  </div>
                  <div className="button-row" style={{ marginTop: 10 }}>
                    <button type="button" className="btn btn-gold" onClick={doReset} disabled={resetting}>
                      {resetting ? 'جارٍ الإرجاع…' : 'نعم، أعد الضبط'}
                    </button>
                    <button type="button" onClick={() => setConfirmReset(false)} disabled={resetting}>
                      تراجع
                    </button>
                  </div>
                </div>
              ) : (
                <div className="button-row">
                  <button type="submit" className="btn btn-gold" disabled={saving}>
                    {saving ? 'جارٍ الحفظ…' : 'حفظ النصّ للمنصة'}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setLetterMsg(null);
                      setConfirmReset(true);
                    }}
                    disabled={saving || !isCustomized}
                    title={isCustomized ? undefined : 'النصّ الحالي هو الافتراضي أصلاً'}
                  >
                    إعادة الضبط للافتراضي
                  </button>
                </div>
              ))}
          </form>
        )}
      </section>

      {isAdmin && (
        <section className="card">
          <div className="section-head">
            <h2>اختبار الإرسال</h2>
          </div>
          <p style={{ color: 'var(--text-muted)', marginTop: 0 }}>
            يرسل النصّ أعلاه فعليًا إلى أي بريد تختاره، بتحية عامة بدل تحية الكرت — للتأكد من
            إعدادات بريد المنصة ومن شكل الرسالة قبل إرسالها إلى ضيف حقيقي. لا يمسّ أي كرت.
          </p>
          <form onSubmit={sendTest}>
            <label htmlFor="test_email">البريد الإلكتروني للمستلم</label>
            <input
              id="test_email"
              type="email"
              dir="ltr"
              required
              value={testEmail}
              onChange={(e) => setTestEmail(e.target.value)}
              placeholder="you@example.com"
            />
            {testMsg && (
              <div className={`status-box ${testMsg.type}`} style={{ marginTop: 12 }}>
                {testMsg.text}
              </div>
            )}
            <div className="button-row">
              <button type="submit" className="btn btn-gold" disabled={sendingTest || !testEmail.trim()}>
                {sendingTest ? 'جارٍ الإرسال…' : 'إرسال رسالة اختبار'}
              </button>
            </div>
          </form>
        </section>
      )}
    </main>
  );
}

export default function WelcomeLetterPage() {
  return (
    <RequireAuth>
      <WelcomeLetterInner />
    </RequireAuth>
  );
}
