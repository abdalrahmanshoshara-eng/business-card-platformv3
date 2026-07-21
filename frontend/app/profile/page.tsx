'use client';

import { FormEvent, useEffect, useState } from 'react';
import PageHero from '@/components/PageHero';
import { ApiError } from '@/lib/api';
import { RequireAuth } from '@/features/auth/Guard';
import { useAuth } from '@/features/auth/AuthProvider';
import { changePassword, updateProfile } from '@/features/auth/api';

function ProfileInner() {
  const { user, setUser, isAdmin } = useAuth();

  const [profile, setProfile] = useState({ first_name: '', last_name: '', email: '', phone: '' });
  const [profileMsg, setProfileMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [savingProfile, setSavingProfile] = useState(false);

  const [pwd, setPwd] = useState({ current_password: '', new_password: '', new_password_confirm: '' });
  const [pwdMsg, setPwdMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [savingPwd, setSavingPwd] = useState(false);

  useEffect(() => {
    if (user) {
      setProfile({
        first_name: user.first_name,
        last_name: user.last_name,
        email: user.email,
        phone: user.phone || '',
      });
    }
  }, [user]);

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
