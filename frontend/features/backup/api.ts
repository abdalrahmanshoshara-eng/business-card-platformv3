import { API_BASE } from '@/lib/api';
import { filenameFromDisposition } from './filename';

/** Download the full database backup (.sql) and hand it to the browser to save. */
export async function downloadDatabaseBackup(): Promise<string> {
  const res = await fetch(`${API_BASE}/admin/backup`, { credentials: 'include', cache: 'no-store' });
  if (!res.ok) {
    let detail = 'تعذّر تنزيل النسخة الاحتياطية.';
    try {
      const data = await res.json();
      if (data?.detail) detail = data.detail;
    } catch {
      /* not JSON — keep the generic message */
    }
    throw new Error(detail);
  }
  const name = filenameFromDisposition(res.headers.get('Content-Disposition'), 'business-cards-backup.sql');
  const url = URL.createObjectURL(await res.blob());
  try {
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    // Give the browser a moment to start the save before releasing the blob.
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  }
  return name;
}
