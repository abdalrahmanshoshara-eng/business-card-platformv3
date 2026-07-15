'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/features/auth/AuthProvider';
import Sidebar from './Sidebar';

const MenuIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
    <path d="M4 6h16M4 12h16M4 18h16" />
  </svg>
);
const CloseIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
    <path d="M6 6l12 12M18 6 6 18" />
  </svg>
);

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const [isMobile, setIsMobile] = useState(false);
  const [open, setOpen] = useState(false); // mobile drawer only

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 860px)');
    const apply = () => {
      setIsMobile(mq.matches);
      if (mq.matches) setOpen(false);
    };
    apply();
    mq.addEventListener('change', apply);
    return () => mq.removeEventListener('change', apply);
  }, []);

  if (loading || !user) return <div className="app-main">{children}</div>;

  // Desktop: static open sidebar (no collapse). Mobile: full drawer.
  const shellClass = isMobile
    ? `app-shell is-mobile ${open ? 'sidebar-open' : 'sidebar-closed'}`
    : 'app-shell';

  return (
    <div className={shellClass}>
      {isMobile && (
        <button
          type="button"
          className="sidebar-toggle"
          onClick={() => setOpen((o) => !o)}
          aria-label={open ? 'إغلاق القائمة' : 'فتح القائمة'}
          aria-expanded={open}
        >
          {open ? <CloseIcon /> : <MenuIcon />}
        </button>
      )}

      {isMobile && open && <div className="sidebar-overlay" onClick={() => setOpen(false)} />}

      <Sidebar onNavigate={() => { if (isMobile) setOpen(false); }} />

      <div className="app-main">{children}</div>
    </div>
  );
}
