'use client';

import { useCallback, useEffect, useState } from 'react';
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

const OPEN_KEY = 'bc-sidebar-open';
const MOBILE_MQ = '(max-width: 860px)';

/**
 * One control for every screen size: the hamburger in the header opens and
 * closes the sidebar. Below 861px the sidebar is an overlay drawer (always
 * starts closed); above it, it sits inline and remembers the last choice.
 */
export default function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const [isMobile, setIsMobile] = useState<boolean | null>(null); // null = not measured yet
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia(MOBILE_MQ);
    const apply = () => {
      setIsMobile(mq.matches);
      if (mq.matches) {
        setOpen(false);
      } else {
        let remembered = true;
        try { remembered = localStorage.getItem(OPEN_KEY) !== '0'; } catch { /* storage unavailable */ }
        setOpen(remembered);
      }
    };
    apply();
    mq.addEventListener('change', apply);
    return () => mq.removeEventListener('change', apply);
  }, []);

  const close = useCallback(() => setOpen(false), []);

  const toggle = useCallback(() => {
    setOpen((o) => {
      const next = !o;
      // Only the desktop choice is worth remembering; the drawer always
      // reopens closed so a phone never loads behind an overlay.
      if (isMobile === false) {
        try { localStorage.setItem(OPEN_KEY, next ? '1' : '0'); } catch { /* ignore */ }
      }
      return next;
    });
  }, [isMobile]);

  // While the drawer covers the page, Escape closes it and the page behind
  // it must not scroll.
  useEffect(() => {
    if (!isMobile || !open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close(); };
    document.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [isMobile, open, close]);

  if (loading || !user) return <div className="app-main">{children}</div>;

  const shellClass = [
    'app-shell',
    isMobile ? 'is-mobile' : '',
    // Held back until the viewport is measured so neither layout flashes.
    isMobile === null ? '' : (open ? 'sidebar-open' : 'sidebar-closed'),
  ].filter(Boolean).join(' ');

  const toggleLabel = open ? 'إغلاق القائمة' : 'فتح القائمة';

  return (
    <div className={shellClass}>
      <button
        type="button"
        className="sidebar-toggle"
        onClick={toggle}
        aria-label={toggleLabel}
        aria-expanded={open}
        aria-controls="app-sidebar"
        title={toggleLabel}
      >
        {open ? <CloseIcon /> : <MenuIcon />}
      </button>

      {isMobile && open && <div className="sidebar-overlay" onClick={close} />}

      <Sidebar onNavigate={() => { if (isMobile) close(); }} />

      <div className="app-main">{children}</div>
    </div>
  );
}
