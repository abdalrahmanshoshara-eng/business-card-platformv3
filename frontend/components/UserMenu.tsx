'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/features/auth/AuthProvider';

export default function UserMenu() {
  const { user, loading, isAdmin, logout } = useAuth();
  const router = useRouter();

  if (loading || !user) return null;

  async function doLogout() {
    await logout();
    router.replace('/login');
  }

  const displayName = [user.first_name, user.last_name].filter(Boolean).join(' ') || user.username;

  return (
    <nav className="header-nav" aria-label="حساب المستخدم">
      <Link href="/dashboard">اللوحة</Link>
      {isAdmin && <Link href="/admin/users">المستخدمون</Link>}
      <Link href="/profile">{displayName}</Link>
      <button type="button" className="btn-small" onClick={doLogout}>خروج</button>
    </nav>
  );
}
