export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || '/api';

export type BusinessCard = {
  id: number;
  sequence_number: number;
  person_name: string;
  person_name_ar: string;
  person_name_en: string;
  job_title: string;
  job_title_ar: string;
  job_title_en: string;
  company_name: string;
  company_name_ar: string;
  company_name_en: string;
  mobile_numbers: string[];
  emails: string[];
  website: string;
  address: string;
  company_activity: string;
  investment_type: string;
  investment_type_other: string;
  raw_text: string;
  confidence: number;
  needs_review: boolean;
  review_notes: string;
  website_visit_note: string;
  status: string;
  front_image_url: string;
  back_image_url: string;
  created_at: string;
};

export function toMediaUrl(url?: string) {
  if (!url) return '';
  if (url.startsWith('/media/')) return url;
  try {
    const parsed = new URL(url);
    if (parsed.pathname.startsWith('/media/')) return parsed.pathname;
  } catch {}
  return url;
}

export function combineBilingual(primary?: string, arabic?: string, english?: string) {
  const parts = (primary || '').split(/\r?\n/).map(item => item.trim()).filter(Boolean);
  if (parts.length) return parts.join('\n');
  return [arabic, english].map(item => (item || '').trim()).filter(Boolean).join('\n');
}

function normalizeApiPath(path: string) {
  // Keep query string untouched, and make Django endpoints work with or without trailing slash.
  const [pathname, query = ''] = path.split('?');
  let clean = pathname.startsWith('/') ? pathname : `/${pathname}`;
  if (!clean.endsWith('/')) clean += '/';
  return query ? `${clean}?${query}` : clean;
}

function apiUrl(path: string) {
  const base = API_BASE.endsWith('/') ? API_BASE.slice(0, -1) : API_BASE;
  return `${base}${normalizeApiPath(path)}`;
}

export async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path), {
    ...options,
    cache: 'no-store',
    redirect: 'follow',
  });
  const text = await res.text();
  let data: any = {};
  try { data = text ? JSON.parse(text) : {}; } catch { data = { detail: text }; }
  if (!res.ok) throw new Error(data.detail || data.message || 'Request failed');
  return data as T;
}
