import { fetchJson, ensureCsrf } from '@/lib/api';

export type WelcomeEmailConfig = {
  // The only welcome setting a user owns.
  sender_email: string;
  configured: boolean;
  // The platform-wide letter: Arabic (primary) plus the secondary-language
  // letter, sent side by side when the recipient's card is not Arabic. Same for
  // every account — only an admin may change it.
  welcome_subject: string;
  welcome_message: string;
  welcome_subject_en: string;
  welcome_message_en: string;
  is_customized: boolean;
  can_edit_letter: boolean;
};

// The letter fields, editable by admins through the welcome-letter endpoint.
export type WelcomeLetterUpdate = Partial<{
  welcome_subject: string;
  welcome_message: string;
  welcome_subject_en: string;
  welcome_message_en: string;
}>;

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
  welcome_email?: WelcomeEmailConfig;
};

// Fields accepted when saving the welcome-email config on a profile.
export type WelcomeEmailUpdate = Partial<{
  sender_email: string;
}>;

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

export async function updateProfile(payload: Partial<Pick<AuthUser, 'first_name' | 'last_name' | 'email' | 'phone'>> & WelcomeEmailUpdate): Promise<AuthUser> {
  return fetchJson<AuthUser>('/auth/profile', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

/** Admin-only: change the platform-wide welcome letter. */
export async function updateWelcomeLetter(payload: WelcomeLetterUpdate): Promise<WelcomeEmailConfig> {
  await ensureCsrf();
  return fetchJson<WelcomeEmailConfig>('/auth/welcome-letter', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

/** Admin-only: restore the official default letter for every account. */
export async function resetWelcomeLetter(): Promise<WelcomeEmailConfig> {
  await ensureCsrf();
  return fetchJson<WelcomeEmailConfig>('/auth/welcome-letter/reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
}

export async function changePassword(current_password: string, new_password: string, new_password_confirm: string): Promise<void> {
  await fetchJson('/auth/change-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ current_password, new_password, new_password_confirm }),
  });
}

export async function sendWelcomeTest(to: string): Promise<{ detail?: string; sent?: boolean }> {
  return fetchJson('/auth/welcome-test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ to }),
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
