import './globals.css';
import { AuthProvider } from '@/features/auth/AuthProvider';
import AppShell from '@/components/AppShell';
import SiteHeader from '@/components/SiteHeader';

export const dynamic = 'force-dynamic';

export const metadata = {
  title: 'استخراج بيانات الكرت الشخصي – وزارة الاقتصاد والصناعة',
  description: 'منصة رفع وبحث بيانات الكروت الشخصية',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ar" dir="rtl" suppressHydrationWarning>
      <body suppressHydrationWarning>
        <AuthProvider>
        <SiteHeader />
        <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}
