'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from './AuthProvider';

function LoadingScreen({ text }: { text: string }) {
  return (
    <main className="container">
      <div className="card" style={{ textAlign: 'center' }}>
        <p className="status">{text}</p>
      </div>
    </main>
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
