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
  country: string;
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

export class ApiError extends Error {
  status: number;
  errorType?: string;
  data: any;

  constructor(message: string, status: number, data: any = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.errorType = data?.error_type;
    this.data = data;
  }
}

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

function formatApiError(data: any, fallback: string) {
  if (!data) return fallback;
  if (typeof data === 'string') return data || fallback;
  if (data.detail) return String(data.detail);
  if (data.message) return String(data.message);
  if (data.errors && typeof data.errors === 'object') {
    const fieldMessages = Object.entries(data.errors).map(([field, value]) => {
      if (Array.isArray(value)) return `${field}: ${value.join(' ')}`;
      if (value && typeof value === 'object') return `${field}: ${JSON.stringify(value)}`;
      return `${field}: ${String(value)}`;
    });
    if (fieldMessages.length) return fieldMessages.join('؛ ');
  }
  if (typeof data === 'object') {
    const fieldMessages = Object.entries(data).map(([field, value]) => {
      if (Array.isArray(value)) return `${field}: ${value.join(' ')}`;
      if (typeof value === 'string') return `${field}: ${value}`;
      return '';
    }).filter(Boolean);
    if (fieldMessages.length) return fieldMessages.join('؛ ');
  }
  return fallback;
}

export function getCookie(name: string): string {
  if (typeof document === 'undefined') return '';
  const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
  return match ? decodeURIComponent(match[1]) : '';
}

// Prime the CSRF cookie so the first unsafe request can echo the token back.
export async function ensureCsrf(): Promise<void> {
  if (getCookie('csrftoken')) return;
  await fetch(apiUrl('/auth/csrf'), { credentials: 'include', cache: 'no-store' });
}

export async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const method = (options?.method || 'GET').toUpperCase();
  const headers = new Headers(options?.headers || {});
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    if (!getCookie('csrftoken')) {
      try { await ensureCsrf(); } catch { /* offline: let the request fail normally */ }
    }
    const token = getCookie('csrftoken');
    if (token) headers.set('X-CSRFToken', token);
  }
  const res = await fetch(apiUrl(path), {
    ...options,
    headers,
    credentials: 'include',
    cache: 'no-store',
    redirect: 'follow',
  });
  const text = await res.text();
  let data: any = {};
  try { data = text ? JSON.parse(text) : {}; } catch { data = { detail: text }; }
  if (!res.ok) {
    throw new ApiError(formatApiError(data, 'فشل تنفيذ الطلب.'), res.status, data);
  }
  return data as T;
}
