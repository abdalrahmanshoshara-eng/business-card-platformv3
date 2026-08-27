'use client';

import { FormEvent, useEffect, useState } from 'react';
import Link from 'next/link';
import PageHero from '@/components/PageHero';
import { ApiError } from '@/lib/api';
import { RequireAuth } from '@/features/auth/Guard';
import { useAuth } from '@/features/auth/AuthProvider';
import {
  changePassword,
  resetWelcomeLetter,
  updateProfile,
  updateWelcomeLetter,
} from '@/features/auth/api';

// The backend replaces this placeholder with a salutation tailored to each
// card's holder. Keep it in sync with accounts/welcome_templates.py.
const SALUTATION_TOKEN = '{{salutation}}';

function ProfileInner() {
  const { user, setUser, isAdmin } = useAuth();

  const [profile, setProfile] = useState({ first_name: '', last_name: '', email: '', phone: '' });
  const [profileMsg, setProfileMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [savingProfile, setSavingProfile] = useState(false);

  const [pwd, setPwd] = useState({ current_password: '', new_password: '', new_password_confirm: '' });
  const [pwdMsg, setPwdMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [savingPwd, setSavingPwd] = useState(false);

  // The sender email belongs to this account; the letter is platform-wide and
  // only an admin may change it, so the two are saved separately.
  const [welcome, setWelcome] = useState({ sender_email: '' });
  const [letter, setLetter] = useState({
    welcome_subject: '', welcome_message: '',
    welcome_subject_en: '', welcome_message_en: '',
  });
  const [canEditLetter, setCanEditLetter] = useState(false);
  const [letterIsCustom, setLetterIsCustom] = useState(false);
  const [welcomeMsg, setWelcomeMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [letterMsg, setLetterMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [savingWelcome, setSavingWelcome] = useState(false);
  const [savingLetter, setSavingLetter] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);

  useEffect(() => {
    if (user) {
      setProfile({
        first_name: user.first_name,
        last_name: user.last_name,
        email: user.email,
        phone: user.phone || '',
      });
      const w = user.welcome_email;
      if (w) {
        setWelcome({ sender_email: w.sender_email || '' });
        setLetter({
          welcome_subject: w.welcome_subject || '',
          welcome_message: w.welcome_message || '',
          welcome_subject_en: w.welcome_subject_en || '',
          welcome_message_en: w.welcome_message_en || '',
        });
        setCanEditLetter(!!w.can_edit_letter);
        setLetterIsCustom(!!w.is_customized);
      }
    }
  }, [user]);

  async function saveWelcome(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWelcomeMsg(null);
    setSavingWelcome(true);
    try {
      const updated = await updateProfile(welcome);
      setUser(updated);
      setWelcomeMsg({ type: 'success', text: 'تم حفظ إعدادات رسالة الترحيب.' });
    } catch (err) {
      setWelcomeMsg({ type: 'error', text: err instanceof ApiError ? err.message : 'تعذّر حفظ الإعدادات.' });
    } finally {
      setSavingWelcome(false);
    }
  }

  async function saveLetter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLetterMsg(null);
    setSavingLetter(true);
    try {
      const cfg = await updateWelcomeLetter(letter);
      setLetterIsCustom(!!cfg.is_customized);
      setLetterMsg({ type: 'success', text: 'تم حفظ نصّ الرسالة لكل الحسابات.' });
    } catch (err) {
      setLetterMsg({ type: 'error', text: err instanceof ApiError ? err.message : 'تعذّر حفظ النصّ.' });
    } finally {
      setSavingLetter(false);
    }
  }

  async function doResetLetter() {
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
      setLetterIsCustom(!!cfg.is_customized);
      setConfirmReset(false);
      setLetterMsg({ type: 'success', text: 'تمت إعادة الرسالة إلى النصّ الرسمي الافتراضي.' });
    } catch (err) {
      setLetterMsg({ type: 'error', text: err instanceof ApiError ? err.message : 'تعذّرت إعادة الضبط.' });
    } finally {
      setResetting(false);
    }
  }

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setProfileMsg(null);
    setSavingProfile(true);
    try {
      const updated = await updateProfile(profile);
      setUser(updated);
      setProfileMsg({ type: 'success', text: 'تم حفظ بيانات الحساب.' });
    } catch (err) {
      setProfileMsg({ type: 'error', text: err instanceof ApiError ? err.message : 'تعذّر حفظ البيانات.' });
    } finally {
      setSavingProfile(false);
    }
  }

  async function savePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPwdMsg(null);
    if (pwd.new_password !== pwd.new_password_confirm) {
      setPwdMsg({ type: 'error', text: 'كلمتا المرور غير متطابقتين.' });
      return;
    }
    setSavingPwd(true);
    try {
      await changePassword(pwd.current_password, pwd.new_password, pwd.new_password_confirm);
      setPwd({ current_password: '', new_password: '', new_password_confirm: '' });
      setPwdMsg({ type: 'success', text: 'تم تغيير كلمة المرور بنجاح.' });
    } catch (err) {
      setPwdMsg({ type: 'error', text: err instanceof ApiError ? err.message : 'تعذّر تغيير كلمة المرور.' });
    } finally {
      setSavingPwd(false);
    }
  }

  return (
    <main className="container">
      <PageHero title="الملف الشخصي" description="إدارة بيانات حسابك وتغيير كلمة المرور." />

      <div className="profile-grid">
        <div className="card profile-card-main">
          <div className="section-head"><h2>بيانات الحساب</h2></div>
          <form onSubmit={saveProfile}>
            <label>اسم المستخدم</label>
            <input type="text" value={user?.username || ''} disabled />
            <div className="grid">
              <div>
                <label htmlFor="first_name">الاسم الأول</label>
                <input id="first_name" type="text" value={profile.first_name}
                  onChange={(e) => setProfile((p) => ({ ...p, first_name: e.target.value }))} />
              </div>
              <div>
                <label htmlFor="last_name">الاسم الأخير</label>
                <input id="last_name" type="text" value={profile.last_name}
                  onChange={(e) => setProfile((p) => ({ ...p, last_name: e.target.value }))} />
              </div>
            </div>
            <label htmlFor="email">البريد الإلكتروني</label>
            <input id="email" type="email" value={profile.email}
              onChange={(e) => setProfile((p) => ({ ...p, email: e.target.value }))} required />
            <label htmlFor="phone">رقم الموبايل</label>
            <input id="phone" type="tel" value={profile.phone}
              onChange={(e) => setProfile((p) => ({ ...p, phone: e.target.value }))} placeholder="09xxxxxxxx" />
            {profileMsg && <div className={`status-box ${profileMsg.type}`} style={{ marginTop: 12 }}>{profileMsg.text}</div>}
            <div className="button-row">
              <button type="submit" className="btn btn-gold" disabled={savingProfile}>
                {savingProfile ? 'جارٍ الحفظ…' : 'حفظ البيانات'}
              </button>
              {isAdmin && <span className="badge">مدير</span>}
            </div>
          </form>
        </div>

        <div className="card profile-card-side">
          <div className="section-head"><h2>تغيير كلمة المرور</h2></div>
          <form onSubmit={savePassword}>
            <label htmlFor="current_password">كلمة المرور الحالية</label>
            <input id="current_password" type="password" autoComplete="current-password" value={pwd.current_password}
              onChange={(e) => setPwd((p) => ({ ...p, current_password: e.target.value }))} required />
            <label htmlFor="new_password">كلمة المرور الجديدة</label>
            <input id="new_password" type="password" autoComplete="new-password" value={pwd.new_password}
              onChange={(e) => setPwd((p) => ({ ...p, new_password: e.target.value }))} required />
            <label htmlFor="new_password_confirm">تأكيد كلمة المرور الجديدة</label>
            <input id="new_password_confirm" type="password" autoComplete="new-password" value={pwd.new_password_confirm}
              onChange={(e) => setPwd((p) => ({ ...p, new_password_confirm: e.target.value }))} required />
            {pwdMsg && <div className={`status-box ${pwdMsg.type}`} style={{ marginTop: 12 }}>{pwdMsg.text}</div>}
            <div className="button-row">
              <button type="submit" className="btn btn-gold" disabled={savingPwd}>
                {savingPwd ? 'جارٍ الحفظ…' : 'تغيير كلمة المرور'}
              </button>
            </div>
          </form>
        </div>

        <div className="card profile-card-main" style={{ gridColumn: '1 / -1' }}>
          <div className="section-head">
            <h2>إعدادات رسالة الترحيب</h2>
            {isAdmin && <Link href="/welcome-test" className="download">اختبار الإرسال</Link>}
          </div>
          <p style={{ color: 'var(--text-muted)', marginTop: 0 }}>
            أدخل بريد المُرسِل. تُرسَل الرسالة عبر بريد المنصة ويظهر بريدك كمُرسِل وكعنوان للرد.
          </p>
          <form onSubmit={saveWelcome}>
            <label htmlFor="sender_email">بريد المُرسِل</label>
            <input id="sender_email" type="email" dir="ltr" value={welcome.sender_email}
              onChange={(e) => setWelcome({ sender_email: e.target.value })}
              placeholder="you@example.com" />
            {welcomeMsg && <div className={`status-box ${welcomeMsg.type}`} style={{ marginTop: 12 }}>{welcomeMsg.text}</div>}
            <div className="button-row">
              <button type="submit" className="btn btn-gold" disabled={savingWelcome}>
                {savingWelcome ? 'جارٍ الحفظ…' : 'حفظ بريد المُرسِل'}
              </button>
            </div>
          </form>
        </div>

        <div className="card profile-card-main" style={{ gridColumn: '1 / -1' }}>
          <div className="section-head">
            <h2>نصّ رسالة الترحيب</h2>
            {letterIsCustom
              ? <span className="download" style={{ cursor: 'default' }}>نصّ مخصّص</span>
              : <span className="download" style={{ cursor: 'default' }}>النصّ الرسمي</span>}
          </div>
          <p style={{ color: 'var(--text-muted)', marginTop: 0 }}>
            هذا النصّ <strong>موحّد للمنصة كلها</strong> ويخرج باسم الوزارة، لذلك
            {canEditLetter ? ' يعدّله المشرفون فقط — وأي تعديل هنا يسري على رسائل جميع الحسابات.'
                           : ' لا يمكن تعديله إلا من قِبل المشرف. هذا ما سيُرسَل باسمك.'}
          </p>
          <p style={{ color: 'var(--text-muted)', marginTop: 0 }}>
            تُرسَل الرسالة بلغة الكرت: كرت عربي يستلم النصّ العربي وحده، وكرت بلغة أخرى يستلم
            النصّ العربي والنصّ بلغته في بريد واحد، وتبدأ بتحية مناسبة لصاحب الكرت.
            <code style={{ margin: '0 4px' }}>{SALUTATION_TOKEN}</code>
            هو موضع تلك التحية — احتفظ به في بداية النصّ، أو احذفه لإرسال النصّ كما هو دون تحية.
          </p>
          <form onSubmit={saveLetter}>
            <label htmlFor="welcome_subject">عنوان الرسالة (عربي)</label>
            <input id="welcome_subject" type="text" value={letter.welcome_subject}
              readOnly={!canEditLetter} disabled={!canEditLetter}
              onChange={(e) => setLetter((l) => ({ ...l, welcome_subject: e.target.value }))} />
            <label htmlFor="welcome_message">نص الرسالة (عربي)</label>
            <textarea id="welcome_message" rows={12} value={letter.welcome_message}
              readOnly={!canEditLetter} disabled={!canEditLetter}
              onChange={(e) => setLetter((l) => ({ ...l, welcome_message: e.target.value }))} />

            <label htmlFor="welcome_subject_en">عنوان الرسالة (اللغة الثانية)</label>
            <input id="welcome_subject_en" type="text" dir="ltr" value={letter.welcome_subject_en}
              readOnly={!canEditLetter} disabled={!canEditLetter}
              onChange={(e) => setLetter((l) => ({ ...l, welcome_subject_en: e.target.value }))} />
            <label htmlFor="welcome_message_en">نص الرسالة (اللغة الثانية)</label>
            <textarea id="welcome_message_en" rows={12} dir="ltr" value={letter.welcome_message_en}
              readOnly={!canEditLetter} disabled={!canEditLetter}
              onChange={(e) => setLetter((l) => ({ ...l, welcome_message_en: e.target.value }))} />

            {letterMsg && <div className={`status-box ${letterMsg.type}`} style={{ marginTop: 12 }}>{letterMsg.text}</div>}

            {canEditLetter && (
              confirmReset ? (
                <div className="status-box error" style={{ marginTop: 12 }}>
                  <div>سيعود النصّ إلى الصيغة الرسمية الافتراضية <strong>لكل الحسابات</strong>، ويُفقد أي تعديل مخصّص. متابعة؟</div>
                  <div className="button-row" style={{ marginTop: 10 }}>
                    <button type="button" className="btn btn-gold" onClick={doResetLetter} disabled={resetting}>
                      {resetting ? 'جارٍ الإرجاع…' : 'نعم، أعد الضبط'}
                    </button>
                    <button type="button" onClick={() => setConfirmReset(false)} disabled={resetting}>تراجع</button>
                  </div>
                </div>
              ) : (
                <div className="button-row">
                  <button type="submit" className="btn btn-gold" disabled={savingLetter}>
                    {savingLetter ? 'جارٍ الحفظ…' : 'حفظ النصّ للمنصة'}
                  </button>
                  <button type="button" onClick={() => { setLetterMsg(null); setConfirmReset(true); }}
                    disabled={savingLetter || !letterIsCustom}
                    title={letterIsCustom ? undefined : 'النصّ الحالي هو الافتراضي أصلاً'}>
                    إعادة الضبط للافتراضي
                  </button>
                </div>
              )
            )}
          </form>
        </div>
      </div>
    </main>
  );
}

export default function ProfilePage() {
  return (
    <RequireAuth>
      <ProfileInner />
    </RequireAuth>
  );
}
