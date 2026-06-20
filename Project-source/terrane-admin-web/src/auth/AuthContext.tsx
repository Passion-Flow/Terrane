/** 鉴权上下文 —— 挂载即 refresh()（GET /me 被动恢复登录态）；
 *  logout 调后端清 cookie 并清本地态。包在 RouterProvider 外层（见 App.tsx）。 */

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { type AdminUser, fetchMe, logout as apiLogout } from "@/lib/auth";

interface AuthState {
  user: AdminUser | null;
  /** 首屏 /me 拉取中（用于 RequireAuth 显示 loading，避免闪重定向）。 */
  loading: boolean;
  /** 重新拉取 /me（登录成功后调用以落地用户态）。 */
  refresh: () => Promise<void>;
  /** 登出（后端清 cookie + 本地清态）。 */
  logout: () => Promise<void>;
  /** 权限判定（通配 "*" 或精确命中）。 */
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
      // 401 AUTH_REQUIRED / 403 LICENSE_REQUIRED 等 → 视为未登录，交给守卫处置。
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
