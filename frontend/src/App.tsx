import { lazy, Suspense, useEffect, useState } from "react";

import { api, tokenStore } from "./lib/api";
import type { User } from "./types";
import { Login } from "./components/Login";

const Dashboard = lazy(() =>
  import("./components/Dashboard").then((module) => ({ default: module.Dashboard })),
);

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [hasToken, setHasToken] = useState(() => Boolean(tokenStore.get()));
  const [restoring, setRestoring] = useState(hasToken);

  useEffect(() => {
    if (!hasToken || user) {
      setRestoring(false);
      return;
    }
    api.me()
      .then(setUser)
      .catch(() => setHasToken(false))
      .finally(() => setRestoring(false));
  }, [hasToken, user]);

  if (restoring) {
    return <div className="app-loader"><span /><p>Restoring secure workspace…</p></div>;
  }

  if (!hasToken || !user) {
    return <Login onAuthenticated={(authenticatedUser) => { setUser(authenticatedUser); setHasToken(true); }} />;
  }
  return (
    <Suspense fallback={<div className="app-loader"><span /><p>Loading Earth intelligence…</p></div>}>
      <Dashboard user={user} onLogout={() => { setUser(null); setHasToken(false); }} />
    </Suspense>
  );
}
