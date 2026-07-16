'use client';

import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import PageHero from '@/components/PageHero';
import { ApiError } from '@/lib/api';
import { RequireAuth } from '@/features/auth/Guard';
import {
  CreateUserPayload, ManagedUser, createUser, deleteUser, listUsers, setUserPassword, updateUser,
} from '@/features/users/api';

const EMPTY: CreateUserPayload = {
  username: '', email: '', first_name: '', last_name: '', phone: '', password: '',
};

const PAGE_SIZE_OPTIONS = [20, 50, 100];

function PasswordCell({ user }: { user: ManagedUser }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState('');
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  async function save() {
    if (!value) return;
    setMsg(null);
    setSaving(true);
    try {
      await setUserPassword(user.id, value);
      setMsg({ type: 'success', text: 'تم' });
      setValue('');
      setEditing(false);
    } catch (err) {
      setMsg({ type: 'error', text: err instanceof ApiError ? err.message : 'خطأ' });
    } finally {
      setSaving(false);
    }
  }
  function cancel() { setEditing(false); setValue(''); setMsg(null); }

  if (!editing) {
    return (
      <div className="pw-cell">
        <span className="pw-dots">••••••••</span>
        <button type="button" className="icon-btn" title="تعديل كلمة المرور" onClick={() => { setEditing(true); setMsg(null); }}>✏️</button>
        {msg && <span className={`pw-msg ${msg.type}`}>{msg.text}</span>}
      </div>
    );
  }

  return (
    <div className="pw-cell">
      <input
        type="password"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') save(); if (e.key === 'Escape') cancel(); }}
        placeholder="كلمة مرور جديدة"
        autoComplete="new-password"
        className="pw-input"
        autoFocus
      />
      <button type="button" className="icon-btn" title="حفظ" disabled={saving || !value} onClick={save}>✔️</button>
      <button type="button" className="icon-btn" title="إلغاء" onClick={cancel}>✖️</button>
      {msg && <span className={`pw-msg ${msg.type}`}>{msg.text}</span>}
    </div>
  );
}

function AdminUsersInner() {
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [form, setForm] = useState<CreateUserPayload>(EMPTY);
  const [creating, setCreating] = useState(false);
  const [createMsg, setCreateMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ManagedUser | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setUsers(await listUsers());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'تعذّر تحميل المستخدمين.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return users;
    return users.filter((u) => {
      const haystack = [u.username, u.email, u.first_name, u.last_name].filter(Boolean).join(' ').toLowerCase();
      return haystack.includes(term);
    });
  }, [users, search]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const paged = filtered.slice((page - 1) * pageSize, page * pageSize);
  const pageStart = filtered.length ? (page - 1) * pageSize + 1 : 0;
  const pageEnd = Math.min(page * pageSize, filtered.length);

  async function submitCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreateMsg(null);
    setCreating(true);
    try {
      await createUser({ ...form, username: form.username.trim(), email: form.email.trim() });
      setForm(EMPTY);
      setCreateMsg({ type: 'success', text: 'تم إنشاء المستخدم.' });
      await load();
    } catch (err) {
      setCreateMsg({ type: 'error', text: err instanceof ApiError ? err.message : 'تعذّر إنشاء المستخدم.' });
    } finally {
      setCreating(false);
    }
  }

  async function toggleActive(user: ManagedUser) {
    try {
      await updateUser(user.id, { is_active: !user.is_active });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'تعذّر تحديث الحالة.');
    }
  }

  async function confirmDeleteUser() {
    if (!deleteTarget) return;
    setDeleting(true);
    setError('');
    try {
      await deleteUser(deleteTarget.id);
      setDeleteTarget(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'تعذّر حذف المستخدم.');
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <main className="container">
      <PageHero title="إدارة المستخدمين" description="إنشاء الحسابات وإدارتها وتعيين كلمات المرور وعرض كروت كل مستخدم." />

      <div className="card">
        <div className="section-head"><h2>إضافة مستخدم</h2></div>
        <form onSubmit={submitCreate}>
          <div className="grid">
            <div>
              <label htmlFor="u-username">اسم المستخدم</label>
              <input id="u-username" value={form.username} onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))} required />
            </div>
            <div>
              <label htmlFor="u-email">البريد الإلكتروني</label>
              <input id="u-email" type="email" value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} required />
            </div>
            <div>
              <label htmlFor="u-first">الاسم الأول</label>
              <input id="u-first" value={form.first_name} onChange={(e) => setForm((f) => ({ ...f, first_name: e.target.value }))} />
            </div>
            <div>
              <label htmlFor="u-last">الاسم الأخير</label>
              <input id="u-last" value={form.last_name} onChange={(e) => setForm((f) => ({ ...f, last_name: e.target.value }))} />
            </div>
            <div>
              <label htmlFor="u-phone">رقم الموبايل (اختياري)</label>
              <input id="u-phone" value={form.phone} onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))} placeholder="+9665xxxxxxxx" />
            </div>
            <div>
              <label htmlFor="u-pass">كلمة المرور</label>
              <input id="u-pass" type="password" value={form.password} onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))} required autoComplete="new-password" />
            </div>
          </div>
          <p className="helper-text" style={{ marginTop: 8 }}>يُنشأ الحساب كمستخدم عادي ونشط مباشرةً.</p>
          {createMsg && <div className={`status-box ${createMsg.type}`} style={{ marginTop: 12 }}>{createMsg.text}</div>}
          <div className="button-row">
            <button type="submit" className="btn btn-gold" disabled={creating}>{creating ? 'جارٍ الإنشاء…' : 'إنشاء المستخدم'}</button>
          </div>
        </form>
      </div>

      <div className="card">
        <div className="section-head">
          <h2>المستخدمون</h2>
          <label className="page-size-control">
            عدد الصفوف
            <select value={pageSize} onChange={(e) => { setPage(1); setPageSize(Number(e.target.value)); }}>
              {PAGE_SIZE_OPTIONS.map((size) => <option key={size} value={size}>{size}</option>)}
            </select>
          </label>
        </div>
        <label htmlFor="user-search">بحث بالاسم أو البريد</label>
        <input
          id="user-search"
          type="search"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          placeholder="اكتب اسماً أو بريداً إلكترونياً…"
          style={{ marginBottom: 14 }}
        />
        {/* <p className="helper-text" style={{ marginBottom: 12 }}>
          كلمات المرور مخزّنة مشفّرة ولا يمكن عرضها؛ استخدم ✏️ لتعيين كلمة مرور جديدة للمستخدم.
        </p> */}
        {error && <div className="status-box error" style={{ marginBottom: 12 }}>{error}</div>}
        {loading ? (
          <p className="status">جارٍ التحميل…</p>
        ) : filtered.length === 0 ? (
          <p className="status">{search.trim() ? 'لا نتائج مطابقة للبحث.' : 'لا يوجد مستخدمون بعد.'}</p>
        ) : (
          <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>المستخدم</th><th>البريد</th><th>الموبايل</th><th>الاسم</th>
                  <th>الحالة</th><th>الكروت</th><th>كلمة المرور</th><th>إجراءات</th>
                </tr>
              </thead>
              <tbody>
                {paged.map((u) => (
                  <tr key={u.id}>
                    <td data-label="المستخدم" className="primary-cell">{u.username}</td>
                    <td data-label="البريد" className="ltr-text">{u.email || '—'}</td>
                    <td data-label="الموبايل" className="ltr-text">{u.phone || '—'}</td>
                    <td data-label="الاسم">{[u.first_name, u.last_name].filter(Boolean).join(' ') || '—'}</td>
                    <td data-label="الحالة">
                      {u.is_active ? <span className="badge success">نشط</span> : <span className="badge warning">معطّل</span>}
                    </td>
                    <td data-label="الكروت">{u.card_count}</td>
                    <td data-label="كلمة المرور"><PasswordCell user={u} /></td>
                    <td data-label="إجراءات">
                      <div className="row-actions">
                        <Link href={`/admin/users/${u.id}`} className="btn-small btn-gold">عرض الكروت</Link>
                        <button type="button" className="btn-small" onClick={() => toggleActive(u)}>
                          {u.is_active ? 'تعطيل' : 'تفعيل'}
                        </button>
                        <button type="button" className="btn-small danger" onClick={() => setDeleteTarget(u)}>
                          حذف
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pagination-info">
            المعروض: <strong>{pageStart}-{pageEnd}</strong> من <strong>{filtered.length}</strong>
          </div>
          <nav className="pagination-bar" aria-label="صفحات المستخدمين">
            <button type="button" className="btn-small" disabled={page <= 1} onClick={() => setPage((c) => Math.max(1, c - 1))}>السابق</button>
            <span>صفحة <strong>{page}</strong> من <strong>{totalPages}</strong></span>
            <button type="button" className="btn-small" disabled={page >= totalPages} onClick={() => setPage((c) => Math.min(totalPages, c + 1))}>التالي</button>
          </nav>
          </>
        )}
      </div>

      {deleteTarget && (
        <div
          className="modal-backdrop"
          role="dialog"
          aria-modal="true"
          onClick={() => { if (!deleting) setDeleteTarget(null); }}
        >
          <div className="modal-panel" style={{ maxWidth: 460 }} onClick={(e) => e.stopPropagation()}>
            <div className="confirm-modal-body">
              <div className="confirm-modal-icon">🗑️</div>
              <h2 style={{ justifyContent: 'center' }}>حذف المستخدم نهائياً</h2>
              <p>
                سيتم حذف المستخدم «{deleteTarget.username}» وجميع كروته
                ({deleteTarget.card_count}) وصورها بشكل نهائي، ولا يمكن التراجع عن هذا الإجراء.
              </p>
            </div>
            <div className="button-row" style={{ marginTop: 20 }}>
              <button type="button" className="btn-small danger" disabled={deleting} onClick={confirmDeleteUser}>
                {deleting ? 'جارٍ الحذف…' : 'حذف نهائي'}
              </button>
              <button type="button" className="btn-small" disabled={deleting} onClick={() => setDeleteTarget(null)}>
                إلغاء
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

export default function AdminUsersPage() {
  return (
    <RequireAuth admin>
      <AdminUsersInner />
    </RequireAuth>  );
}
