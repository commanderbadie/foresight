import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, tokenStore } from "./api";
import type { User } from "./types";

interface AuthCtx {
  user: User | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const onLogout = () => setUser(null);
    window.addEventListener("foresight:logout", onLogout);
    if (tokenStore.get()) {
      api.me().then(setUser).catch(() => tokenStore.clear()).finally(() => setReady(true));
    } else {
      setReady(true);
    }
    return () => window.removeEventListener("foresight:logout", onLogout);
  }, []);

  const value: AuthCtx = {
    user,
    ready,
    login: async (email, password) => {
      const r = await api.login(email, password);
      tokenStore.set(r.access_token);
      setUser(r.user);
    },
    register: async (name, email, password) => {
      const r = await api.register(name, email, password);
      tokenStore.set(r.access_token);
      setUser(r.user);
    },
    logout: () => {
      tokenStore.clear();
      setUser(null);
    },
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth outside AuthProvider");
  return c;
}
