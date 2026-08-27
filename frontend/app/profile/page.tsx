'use client';

import { FormEvent, useEffect, useState } from 'react';
import Link from 'next/link';
import PageHero from '@/components/PageHero';
import { ApiError } from '@/lib/api';
import { RequireAuth } from '@/features/auth/Guard';
import { useAuth } from '@/features/auth/AuthProvider';
import { changePassword, updateProfile } from '@/features/auth/api';

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

  const [welcome, setWelcome] = useState({
    sender_email: '',
    welcome_subject: '', welcome_message: '',
    welcome_subject_en: '', welcome_message_en: '',
  });
  const [welcomeMsg, setWelcomeMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [savingWelcome, setSavingWelcome] = useState(false);

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
        setWelcome({
          sender_email: w.sender_email || '',
          welcome_subject: w.welcome_subject || '',
          welcome_message: w.welcome_message || '',
          welcome_subject_en: w.welcome_subject_en || '',
          welcome_message_en: w.welcome_message_en || '',
        });
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
            النصّان أدناه معبّآن بالرسالة الرسمية المعتمدة؛ عدّلهما فقط إذا أردت صياغة خاصة بك،
            وأي نصّ تتركه كما هو يبقى على الصيغة المعتمدة.
          </p>
          <p style={{ color: 'var(--text-muted)', marginTop: 0 }}>
            تُرسَل الرسالة بلغة الكرت: كرت عربي يستلم النصّ العربي وحده، وكرت بلغة أخرى يستلم
            النصّ العربي والنصّ بلغته في بريد واحد، وتبدأ بتحية مناسبة لصاحب الكرت.
            <code style={{ margin: '0 4px' }}>{SALUTATION_TOKEN}</code>
            هو موضع تلك التحية — احتفظ به في بداية النصّ، أو احذفه لإرسال نصّك كما هو دون تحية.
          </p>
          <form onSubmit={saveWelcome}>
            <label htmlFor="sender_email">بريد المُرسِل</label>
            <input id="sender_email" type="email" dir="ltr" value={welcome.sender_email}
              onChange={(e) => setWelcome((w) => ({ ...w, sender_email: e.target.value }))}
              placeholder="you@example.com" />

            <label htmlFor="welcome_subject">عنوان الرسالة (عربي)</label>
            <input id="welcome_subject" type="text" value={welcome.welcome_subject}
              onChange={(e) => setWelcome((w) => ({ ...w, welcome_subject: e.target.value }))} />
            <label htmlFor="welcome_message">نص الرسالة (عربي)</label>
            <textarea id="welcome_message" rows={12} value={welcome.welcome_message}
              onChange={(e) => setWelcome((w) => ({ ...w, welcome_message: e.target.value }))} />

            <label htmlFor="welcome_subject_en">عنوان الرسالة (اللغة الثانية)</label>
            <input id="welcome_subject_en" type="text" dir="ltr" value={welcome.welcome_subject_en}
              onChange={(e) => setWelcome((w) => ({ ...w, welcome_subject_en: e.target.value }))} />
            <label htmlFor="welcome_message_en">نص الرسالة (اللغة الثانية)</label>
            <textarea id="welcome_message_en" rows={12} dir="ltr" value={welcome.welcome_message_en}
              onChange={(e) => setWelcome((w) => ({ ...w, welcome_message_en: e.target.value }))} />
            {welcomeMsg && <div className={`status-box ${welcomeMsg.type}`} style={{ marginTop: 12 }}>{welcomeMsg.text}</div>}
            <div className="button-row">
              <button type="submit" className="btn btn-gold" disabled={savingWelcome}>
                {savingWelcome ? 'جارٍ الحفظ…' : 'حفظ إعدادات الترحيب'}
              </button>
            </div>
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
