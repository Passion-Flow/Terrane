/** Auth context — calls refresh() on mount (GET /me passively restores the session);
 *  logout calls the backend to clear the cookie and clears local state. Wraps RouterProvider (see App.tsx). */

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { type AdminUser, fetchMe, logout as apiLogout } from "@/lib/auth";

interface AuthState {
  user: AdminUser | null;
  /** Initial /me fetch in progress (used by RequireAuth to show loading and avoid a redirect flash). */
  loading: boolean;
  /** Re-fetch /me (called after a successful login to commit the user state). */
  refresh: () => Promise<void>;
  /** Logout (backend clears the cookie + local state is cleared). */
  logout: () => Promise<void>;
  /** Permission check (wildcard "*" or an exact match). */
  has: (perm: string) => boolean;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AdminUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setUser(await fetchMe());
    } catch {
      // 401 AUTH_REQUIRED / 403 LICENSE_REQUIRED etc. → treat as not logged in and let the guards handle it.
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    await apiLogout().catch(() => undefined);
    setUser(null);
  }, []);

  const has = useCallback(
    (perm: string) => !!user && (user.permissions.includes("*") || user.permissions.includes(perm)),
    [user],
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return <Ctx.Provider value={{ user, loading, refresh, logout, has }}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
