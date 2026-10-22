import './globals.css';
import Link from 'next/link';
import { AuthProvider } from '@/features/auth/AuthProvider';
import AppShell from '@/components/AppShell';

export const dynamic = 'force-dynamic';

export const metadata = {
  title: 'استخراج بيانات الكرت الشخصي – وزارة الصناعة والتجارة الداخلية',
  description: 'منصة رفع وبحث بيانات الكروت الشخصية',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ar" dir="rtl" suppressHydrationWarning>
      <body suppressHydrationWarning>
        <AuthProvider>
        <header className="site-header">
          <div className="header-overlay" aria-hidden="true"></div>
          <div className="header-inner">
            <Link href="/upload" className="header-brand" aria-label="وزارة الصناعة والتجارة الداخلية">
              {/* <div className="header-logo" aria-hidden="true">
                <img src="/image.png" alt="وزارة الصناعة والتجارة الداخلية" />              </div>
              <div>
                <div className="header-title-ar">وزارة الصناعة والتجارة الداخلية</div>
                <div className="header-title-en">Ministry of Industry and Internal Trade</div>
              </div> */}
              <div className="header-logo"  aria-hidden="true">
                <img src="/ministry-logo-header.svg" alt="وزارة الصناعة والتجارة الداخلية" />              
              </div>
            </Link>
            {/* <nav className="header-nav" aria-label="التنقل الرئيسي">
              <Link href="/upload">رفع الصور</Link>
              <Link href="/dashboard">عرض البيانات والبحث</Link>
            </nav> */}
            <span className="header-badge">الجمهورية العربية السورية</span>
          </div>
        </header>
        <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}
