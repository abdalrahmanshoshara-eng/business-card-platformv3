'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import PageHero from '@/components/PageHero';
import { ApiError, BusinessCard, fetchJson } from '@/lib/api';
import { RequireAuth } from '@/features/auth/Guard';
import { ManagedUser, getUser } from '@/features/users/api';

type Paginated = { count: number; results: BusinessCard[] };
const PAGE_SIZE_OPTIONS = [20, 50, 100];

function UserCardsInner() {
  const params = useParams();
  const id = Number(params?.id);

  const [user, setUser] = useState<ManagedUser | null>(null);
  const [cards, setCards] = useState<BusinessCard[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError('');
    try {
      const [u, list] = await Promise.all([
        getUser(id),
        fetchJson<Paginated | BusinessCard[]>(`/cards/?owner=${id}&page=${page}&page_size=${pageSize}`),
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
  }, [id, page, pageSize]);

  useEffect(() => { load(); }, [load]);

  const displayName = user ? ([user.first_name, user.last_name].filter(Boolean).join(' ') || user.username) : '';
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const pageStart = total ? (page - 1) * pageSize + 1 : 0;
  const pageEnd = Math.min(page * pageSize, total);

  return (
    <main className="container">
      <PageHero
        title={user ? `كروت المستخدم: ${displayName}` : 'كروت المستخدم'}
        description="عرض جميع الكروت التابعة لهذا المستخدم."
      />

      <p className="helper-text">
        <Link href="/admin/users">← العودة إلى قائمة المستخدمين</Link>
      </p>

      {error && <div className="status-box error">{error}</div>}

      <div className="card">
        <div className="section-head">
          <h2>الكروت ({total})</h2>
          <label className="page-size-control">
            عدد الصفوف
            <select
              value={pageSize}
              onChange={(event) => { setPage(1); setPageSize(Number(event.target.value)); }}
            >
              {PAGE_SIZE_OPTIONS.map((size) => <option key={size} value={size}>{size}</option>)}
            </select>
          </label>
        </div>

        {loading ? (
          <p className="status">جارٍ التحميل…</p>
        ) : cards.length === 0 ? (
          <p className="status">لا توجد كروت لهذا المستخدم.</p>
        ) : (
          <>
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
                      <td data-label="#" className="seq-cell">{card.sequence_number}</td>
                      <td data-label="اسم الشخص" className="primary-cell">{card.person_name || '-'}</td>
                      <td data-label="الشركة">{card.company_name || '-'}</td>
                      <td data-label="المنصب">{card.job_title || '-'}</td>
                      <td data-label="الموبايل" className="ltr-text">{(card.mobile_numbers || []).join(' | ') || '-'}</td>
                      <td data-label="الإيميل" className="ltr-text">{(card.emails || []).join(' | ') || '-'}</td>
                      <td data-label="الدولة">{card.country || '-'}</td>
                      <td data-label="نشاط الشركة">{card.company_activity || '-'}</td>
                      <td data-label="الحالة">
                        {card.needs_review ? <span className="badge warning">مراجعة</span> : <span className="badge success">جاهز</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="pagination-info">
              المعروض: <strong>{pageStart}-{pageEnd}</strong> من <strong>{total}</strong>
            </div>
            <nav className="pagination-bar" aria-label="التنقل بين صفحات الكروت">
              <button type="button" className="btn-small" disabled={loading || page <= 1}
                onClick={() => setPage((c) => Math.max(1, c - 1))}>السابق</button>
              <span>صفحة <strong>{page}</strong> من <strong>{totalPages}</strong></span>
              <button type="button" className="btn-small" disabled={loading || page >= totalPages}
                onClick={() => setPage((c) => Math.min(totalPages, c + 1))}>التالي</button>
            </nav>
          </>
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
