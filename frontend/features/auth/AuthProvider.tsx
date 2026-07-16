'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { AuthUser, getMe, login as apiLogin, logout as apiLogout, isAdmin as computeIsAdmin } from './api';

type AuthState = {
  user: AuthUser | null;
  loading: boolean;
  isAdmin: boolean;
  login: (username: string, password: string, remember?: boolean) => Promise<AuthUser>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  setUser: (user: AuthUser | null) => void;
};

const AuthContext = createContext<AuthState | null>(null);

const CACHE_KEY = 'bcp_auth_user';

function readCachedUser(): AuthUser | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(CACHE_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

function writeCachedUser(user: AuthUser | null) {
  if (typeof window === 'undefined') return;
  try {
    if (user) window.localStorage.setItem(CACHE_KEY, JSON.stringify(user));
    else window.localStorage.removeItem(CACHE_KEY);
  } catch {
    /* ignore storage errors (quota / private mode) */
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUserState] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  // Setter that also keeps the localStorage cache in sync.
  const setUser = useCallback((next: AuthUser | null) => {
    setUserState(next);
    writeCachedUser(next);
  }, []);

  // 1) Instant hydrate from the last known user so reloads render immediately
  //    (no blank/loading flash and no login-redirect flicker).
  useEffect(() => {
    const cached = readCachedUser();
    if (cached) {
      setUserState(cached);
      setLoading(false);
    }
  }, []);

  // 2) Revalidate against the server in the background and reconcile.
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const me = await getMe();
        if (active) setUser(me);
      } catch {
        if (active) setUser(null);
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, [setUser]);

  const refresh = useCallback(async () => {
    try {
      const me = await getMe();
      setUser(me);
    } catch {
      setUser(null);
    }
  }, [setUser]);

  const login = useCallback(async (username: string, password: string, remember = false) => {
    const me = await apiLogin(username, password, remember);
    setUser(me);
    return me;
  }, [setUser]);

  const logout = useCallback(async () => {
    try { await apiLogout(); } finally { setUser(null); }
  }, [setUser]);

  const value = useMemo<AuthState>(() => ({
    user,
    loading,
    isAdmin: computeIsAdmin(user),
    login,
    logout,
    refresh,
    setUser,
  }), [user, loading, login, logout, refresh, setUser]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
