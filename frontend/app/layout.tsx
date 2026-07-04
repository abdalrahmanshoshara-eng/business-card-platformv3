import './globals.css';
import Link from 'next/link';

export const metadata = {
  title: 'استخراج بيانات الكرت الشخصي – وزارة الاقتصاد والصناعة',
  description: 'منصة رفع وبحث بيانات الكروت الشخصية',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ar" dir="rtl" suppressHydrationWarning>
      <body suppressHydrationWarning>
        <header className="site-header">
          <div className="header-overlay" aria-hidden="true"></div>
          <div className="header-inner">
            <Link href="/upload" className="header-brand" aria-label="وزارة الاقتصاد والصناعة">
              {/* <div className="header-logo" aria-hidden="true">
                <img src="/image.png" alt="وزارة الاقتصاد والصناعة" />              </div>
              <div>
                <div className="header-title-ar">وزارة الاقتصاد والصناعة</div>
                <div className="header-title-en">Ministry of Economy and Industry</div>
              </div> */}
              <div className="header-logo"  aria-hidden="true">
                <img src="/header-logo-ar.png" alt="وزارة الاقتصاد والصناعة" />              
              </div>
            </Link>
            {/* <nav className="header-nav" aria-label="التنقل الرئيسي">
              <Link href="/upload">رفع الصور</Link>
              <Link href="/dashboard">عرض البيانات والبحث</Link>
            </nav> */}
            <span className="header-badge">الجمهورية العربية السورية</span>
          </div>
        </header>
        {children}
      </body>
    </html>
  );
}
