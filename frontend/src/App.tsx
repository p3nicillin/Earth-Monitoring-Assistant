import { lazy, Suspense, useEffect, useState } from "react";

import { api, tokenStore } from "./lib/api";
import type { User } from "./types";
import { Login } from "./components/Login";

const Dashboard = lazy(() =>
  import("./components/Dashboard").then((module) => ({ default: module.Dashboard })),
);

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [restoring, setRestoring] = useState(true);
  const [localModeUnavailable, setLocalModeUnavailable] = useState(false);

  useEffect(() => {
    if (user) {
      setRestoring(false);
      return;
    }
    let cancelled = false;
    async function establishSession() {
      // 1. Restore an existing token; 2. otherwise ask for a local-appliance
      // session (no credentials); 3. only if both fail, show the login form.
      if (tokenStore.get()) {
        try {
          const restored = await api.me();
          if (!cancelled) setUser(restored);
          return;
        } catch {
          tokenStore.clear();
        }
      }
      try {
        const session = await api.localSession();
        tokenStore.set(session.access_token);
        if (!cancelled) setUser(session.user);
      } catch {
        if (!cancelled) setLocalModeUnavailable(true);
      }
    }
    establishSession().finally(() => {
      if (!cancelled) setRestoring(false);
    });
    return () => {
      cancelled = true;
    };
  }, [user]);

  if (restoring) {
    return <div className="app-loader"><span /><p>Connecting to monitoring core…</p></div>;
  }

  if (!user) {
    if (!localModeUnavailable) {
      return <div className="app-loader"><span /><p>Connecting to monitoring core…</p></div>;
    }
    return <Login onAuthenticated={(authenticatedUser) => { setUser(authenticatedUser); setLocalModeUnavailable(false); }} />;
  }
  return (
    <Suspense fallback={<div className="app-loader"><span /><p>Loading Earth intelligence…</p></div>}>
      <Dashboard user={user} onLogout={() => { setUser(null); setLocalModeUnavailable(true); }} />
    </Suspense>
  );
}
