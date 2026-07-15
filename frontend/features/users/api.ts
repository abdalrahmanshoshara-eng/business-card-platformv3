import { fetchJson } from '@/lib/api';
import { AuthUser } from '@/features/auth/api';

export type ManagedUser = AuthUser & { card_count: number };

export async function listUsers(): Promise<ManagedUser[]> {
  return fetchJson<ManagedUser[]>('/admin/users/');
}

export type CreateUserPayload = {
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  phone: string;
  password: string;
  is_active?: boolean;
};

export async function createUser(payload: CreateUserPayload): Promise<ManagedUser> {
  return fetchJson<ManagedUser>('/admin/users/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function updateUser(id: number, payload: Partial<CreateUserPayload>): Promise<ManagedUser> {
  return fetchJson<ManagedUser>(`/admin/users/${id}/`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function createResetLink(id: number): Promise<{ reset_link: string }> {
  return fetchJson<{ reset_link: string }>(`/admin/users/${id}/reset-link/`, { method: 'POST' });
}

export async function getUser(id: number): Promise<ManagedUser> {
  return fetchJson<ManagedUser>(`/admin/users/${id}/`);
}

export async function setUserPassword(id: number, newPassword: string): Promise<void> {
  await fetchJson(`/admin/users/${id}/set-password/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ new_password: newPassword }),
  });
}
