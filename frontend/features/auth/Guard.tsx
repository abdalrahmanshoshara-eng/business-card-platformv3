'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from './AuthProvider';

/** The waiting state every guarded page shows while auth is resolved.
 *
 *  It is deliberately the login screen's twin — full-bleed ministry green,
 *  the logo, a gold progress bar — because this markup is SERVER-RENDERED and
 *  therefore on screen from first paint until the client bundle boots. The
 *  previous version reused `.status`, which is the empty-state style (dashed
 *  border, sunken fill), so a busy app looked like a page with nothing in it. */
function LoadingScreen({ text }: { text: string }) {
  return (
    <div className="auth-splash" role="status" aria-live="polite">
      <div className="auth-splash-overlay" aria-hidden="true" />
      <div className="auth-splash-inner">
        <img className="auth-splash-logo" src="/header-logo-ar.png" alt="وزارة الاقتصاد والصناعة" />
        <div className="auth-splash-bar" aria-hidden="true"><span /></div>
        <p className="auth-splash-text">{text}</p>
      </div>
    </div>
  );
}

/** Renders children only for an authenticated user; otherwise redirects to /login. */
export function RequireAuth({ children, admin = false }: { children: React.ReactNode; admin?: boolean }) {
  const { user, loading, isAdmin } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace('/login');
    } else if (admin && !isAdmin) {
      router.replace('/dashboard');
    }
  }, [loading, user, isAdmin, admin, router]);

  if (loading) return <LoadingScreen text="جارٍ التحقق من الجلسة…" />;
  if (!user) return <LoadingScreen text="يجب تسجيل الدخول. جارٍ التحويل…" />;
  if (admin && !isAdmin) return <LoadingScreen text="هذه الصفحة للمشرفين فقط. جارٍ التحويل…" />;
  return <>{children}</>;
}
