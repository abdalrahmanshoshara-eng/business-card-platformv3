'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

/** Routes that render their own full-screen branding and must not sit under
 *  the fixed top bar. */
const BARE_ROUTES = ['/login'];

export default function SiteHeader() {
  const pathname = usePathname();
  if (BARE_ROUTES.includes(pathname)) return null;

  return (
    <header className="site-header">
      <div className="header-overlay" aria-hidden="true"></div>
      <div className="header-inner">
        <Link href="/upload" className="header-brand" aria-label="وزارة الاقتصاد والصناعة">
          <div className="header-logo" aria-hidden="true">
            <img src="/header-logo-ar.png" alt="وزارة الاقتصاد والصناعة" />
          </div>
        </Link>
        <span className="header-badge">الجمهورية العربية السورية</span>
      </div>
    </header>
  );
}
