import { fetchJson, ensureCsrf } from '@/lib/api';

export type AuthUser = {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  phone?: string;
  is_active: boolean;
  is_staff: boolean;
  is_superuser: boolean;
  date_joined?: string;
  last_login?: string | null;
};

export function isAdmin(user: AuthUser | null): boolean {
  return !!user && (user.is_staff || user.is_superuser);
}

export async function getMe(): Promise<AuthUser> {
  return fetchJson<AuthUser>('/auth/me');
}

export async function login(username: string, password: string, remember = false): Promise<AuthUser> {
  await ensureCsrf();
  return fetchJson<AuthUser>('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, remember }),
  });
}

export async function logout(): Promise<void> {
  await fetchJson('/auth/logout', { method: 'POST' });
}

export type RegisterPayload = {
  username: string;
  email: string;
  password: string;
  password_confirm: string;
  first_name: string;
  last_name: string;
};

export async function register(payload: RegisterPayload): Promise<AuthUser> {
  await ensureCsrf();
  return fetchJson<AuthUser>('/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function updateProfile(payload: Partial<Pick<AuthUser, 'first_name' | 'last_name' | 'email' | 'phone'>>): Promise<AuthUser> {
  return fetchJson<AuthUser>('/auth/profile', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function changePassword(current_password: string, new_password: string, new_password_confirm: string): Promise<void> {
  await fetchJson('/auth/change-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ current_password, new_password, new_password_confirm }),
  });
}

export async function forgotPassword(identifier: string): Promise<void> {
  await ensureCsrf();
  await fetchJson('/auth/forgot-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: identifier, username: identifier }),
  });
}
