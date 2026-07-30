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
// Desktop collapse handle: a chevron; CSS rotates it 180° when collapsed.
const ChevronIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M15 6l-6 6 6 6" />
  </svg>
);

const COLLAPSE_KEY = 'bc-sidebar-collapsed';

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const [isMobile, setIsMobile] = useState(false);
  const [open, setOpen] = useState(false);          // mobile drawer
  const [collapsed, setCollapsed] = useState(false); // desktop collapse

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

  // Remember the desktop collapse preference across sessions.
  useEffect(() => {
    try {
      if (localStorage.getItem(COLLAPSE_KEY) === '1') setCollapsed(true);
    } catch { /* storage unavailable: ignore */ }
  }, []);

  function toggleDesktop() {
    setCollapsed((c) => {
      const next = !c;
      try { localStorage.setItem(COLLAPSE_KEY, next ? '1' : '0'); } catch { /* ignore */ }
      return next;
    });
  }

  if (loading || !user) return <div className="app-main">{children}</div>;

  const shellClass = [
    'app-shell',
    isMobile ? 'is-mobile' : '',
    isMobile ? (open ? 'sidebar-open' : 'sidebar-closed') : (collapsed ? 'sidebar-collapsed' : ''),
  ].filter(Boolean).join(' ');

  const toggleLabel = isMobile
    ? (open ? 'إغلاق القائمة' : 'فتح القائمة')
    : (collapsed ? 'إظهار القائمة الجانبية' : 'إخفاء القائمة الجانبية');

  return (
    <div className={shellClass}>
      <button
        type="button"
        className="sidebar-toggle"
        onClick={() => (isMobile ? setOpen((o) => !o) : toggleDesktop())}
        aria-label={toggleLabel}
        aria-expanded={isMobile ? open : !collapsed}
        title={toggleLabel}
      >
        {isMobile ? (open ? <CloseIcon /> : <MenuIcon />) : <ChevronIcon />}
      </button>

      {isMobile && open && <div className="sidebar-overlay" onClick={() => setOpen(false)} />}

      <Sidebar onNavigate={() => { if (isMobile) setOpen(false); }} />

      <div className="app-main">{children}</div>
    </div>
  );
}
