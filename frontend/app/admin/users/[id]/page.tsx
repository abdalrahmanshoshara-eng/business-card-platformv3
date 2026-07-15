'use client';

import { FormEvent, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import PageHero from '@/components/PageHero';
import { ApiError, BusinessCard, fetchJson } from '@/lib/api';
import { RequireAuth } from '@/features/auth/Guard';
import { ManagedUser, getUser, setUserPassword } from '@/features/users/api';

type Paginated = { count: number; results: BusinessCard[] };

function UserCardsInner() {
  const params = useParams();
  const id = Number(params?.id);

  const [user, setUser] = useState<ManagedUser | null>(null);
  const [cards, setCards] = useState<BusinessCard[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [pwd, setPwd] = useState('');
  const [pwdMsg, setPwdMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError('');
    try {
      const [u, list] = await Promise.all([
        getUser(id),
        fetchJson<Paginated | BusinessCard[]>(`/cards/?owner=${id}&page_size=100`),
      ]);
      setUser(u);
      if (Array.isArray(list)) {
        setCards(list);
        setTotal(list.length);
      } else {
        setCards(list.results || []);
        setTotal(list.count || 0);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'تعذّر تحميل بيانات المستخدم.');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  async function savePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPwdMsg(null);
    try {
      await setUserPassword(id, pwd);
      setPwd('');
      setPwdMsg({ type: 'success', text: 'تم تعيين كلمة المرور بنجاح.' });
    } catch (err) {
      setPwdMsg({ type: 'error', text: err instanceof ApiError ? err.message : 'تعذّر تعيين كلمة المرور.' });
    }
  }

  const displayName = user ? ([user.first_name, user.last_name].filter(Boolean).join(' ') || user.username) : '';

  return (
    <main className="container">
      <PageHero
        title={user ? `كروت المستخدم: ${displayName}` : 'كروت المستخدم'}
        description="عرض جميع الكروت التابعة لهذا المستخدم وتعيين كلمة مرور جديدة له."
      />

      <p className="helper-text">
        <Link href="/admin/users">← العودة إلى قائمة المستخدمين</Link>
      </p>

      {error && <div className="status-box error">{error}</div>}

      {user && (
        <div className="card" style={{ maxWidth: 640 }}>
          <div className="section-head"><h2>تعيين كلمة مرور جديدة</h2></div>
          <p className="helper-text">
            {user.username} — {user.email || 'بلا بريد'} — {user.is_staff || user.is_superuser ? 'مشرف' : 'مستخدم'} — عدد الكروت: {user.card_count}
          </p>
          <form onSubmit={savePassword}>
            <label htmlFor="np">كلمة المرور الجديدة</label>
            <input id="np" type="password" autoComplete="new-password" value={pwd} onChange={(e) => setPwd(e.target.value)} required />
            {pwdMsg && <div className={`status-box ${pwdMsg.type}`} style={{ marginTop: 10 }}>{pwdMsg.text}</div>}
            <div className="button-row">
              <button type="submit" className="btn btn-gold">تعيين كلمة المرور</button>
            </div>
          </form>
        </div>
      )}

      <div className="card">
        <div className="section-head"><h2>الكروت ({total})</h2></div>
        {loading ? (
          <p className="status">جارٍ التحميل…</p>
        ) : cards.length === 0 ? (
          <p className="status">لا توجد كروت لهذا المستخدم.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>#</th><th>اسم الشخص</th><th>الشركة</th><th>المنصب</th>
                  <th>الموبايل</th><th>الإيميل</th><th>الدولة</th><th>نشاط الشركة</th><th>الحالة</th>
                </tr>
              </thead>
              <tbody>
                {cards.map((card) => (
                  <tr key={card.id}>
                    <td className="seq-cell">{card.sequence_number}</td>
                    <td className="primary-cell">{card.person_name || '-'}</td>
                    <td>{card.company_name || '-'}</td>
                    <td>{card.job_title || '-'}</td>
                    <td className="ltr-text">{(card.mobile_numbers || []).join(' | ') || '-'}</td>
                    <td className="ltr-text">{(card.emails || []).join(' | ') || '-'}</td>
                    <td>{card.country || '-'}</td>
                    <td>{card.company_activity || '-'}</td>
                    <td>{card.needs_review ? <span className="badge warning">مراجعة</span> : <span className="badge success">جاهز</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </main>
  );
}

export default function UserCardsPage() {
  return (
    <RequireAuth admin>
      <UserCardsInner />
    </RequireAuth>
  );
}
