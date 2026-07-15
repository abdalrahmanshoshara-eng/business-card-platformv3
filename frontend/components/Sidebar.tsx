'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/features/auth/AuthProvider';

type Item = { href: string; label: string; icon: React.ReactNode; adminOnly?: boolean };

const svg = (paths: React.ReactNode) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths}</svg>
);

const ICONS = {
  dashboard: svg(<><rect x="3" y="3" width="7" height="9" rx="1" /><rect x="14" y="3" width="7" height="5" rx="1" /><rect x="14" y="12" width="7" height="9" rx="1" /><rect x="3" y="16" width="7" height="5" rx="1" /></>),
  upload: svg(<><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><path d="M12 3v13" /><path d="m7 8 5-5 5 5" /></>),
  users: svg(<><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" /></>),
  profile: svg(<><circle cx="12" cy="8" r="4" /><path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1" /></>),
  logout: svg(<><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><path d="m16 17 5-5-5-5" /><path d="M21 12H9" /></>),
};

const ITEMS: Item[] = [
  { href: '/dashboard', label: 'اللوحة', icon: ICONS.dashboard },
  { href: '/upload', label: 'رفع كرت', icon: ICONS.upload },
  { href: '/admin/users', label: 'المستخدمون', icon: ICONS.users, adminOnly: true },
  { href: '/profile', label: 'الملف الشخصي', icon: ICONS.profile },
];

export default function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { user, loading, isAdmin, logout } = useAuth();
  const pathname = usePathname() || '';
  const router = useRouter();

  if (loading || !user) return null;

  async function doLogout() {
    onNavigate?.();
    await logout();
    router.replace('/login');
  }

  const displayName = [user.first_name, user.last_name].filter(Boolean).join(' ') || user.username;
  const items = ITEMS.filter((it) => !it.adminOnly || isAdmin);

  return (
    <aside className="app-sidebar" aria-label="القائمة الجانبية">
      <div className="app-sidebar-user">
        <div className="app-sidebar-avatar" aria-hidden="true">{displayName.charAt(0)}</div>
        <div className="app-sidebar-user-meta">
          <span className="app-sidebar-name">{displayName}</span>
          <span className="app-sidebar-role">{isAdmin ? 'مدير' : 'مستخدم'}</span>
        </div>
      </div>

      <nav className="app-sidebar-nav">
        {items.map((it) => {
          const active = pathname === it.href || pathname.startsWith(it.href + '/');
          return (
            <Link
              key={it.href}
              href={it.href}
              className={`app-sidebar-link${active ? ' active' : ''}`}
              onClick={() => onNavigate?.()}
            >
              <span className="app-sidebar-icon">{it.icon}</span>
              <span className="app-sidebar-label">{it.label}</span>
            </Link>
          );
        })}
      </nav>

      <button type="button" className="app-sidebar-logout" onClick={doLogout}>
        <span className="app-sidebar-icon">{ICONS.logout}</span>
        <span className="app-sidebar-label">تسجيل الخروج</span>
      </button>
    </aside>
  );
}
