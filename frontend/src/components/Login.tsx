import { useState, type FormEvent } from "react";
import { ArrowRight, Eye, EyeOff, Globe2, Radar, ShieldCheck, Sparkles } from "lucide-react";

import { api, tokenStore } from "../lib/api";
import type { User } from "../types";

interface LoginProps {
  onAuthenticated: (user: User) => void;
}

export function Login({ onAuthenticated }: LoginProps) {
  const [email, setEmail] = useState("analyst@example.com");
  const [password, setPassword] = useState("ChangeMe123!");
  const [showPassword, setShowPassword] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const response = await api.login(email, password);
      tokenStore.set(response.access_token);
      onAuthenticated(response.user);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to sign in");
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="login-shell">
      <section className="login-story">
        <div className="brand-lockup">
          <span className="brand-mark"><Globe2 size={21} /></span>
          <span>TerraLens</span>
        </div>
        <div className="story-copy">
          <div className="eyebrow"><span /> PLANETARY INTELLIGENCE</div>
          <h1>See the signal.<br /><em>Understand the change.</em></h1>
          <p>
            Turn open Earth-observation data into evidence-backed events, maps, and reports
            your team can act on.
          </p>
          <div className="signal-list">
            <div><Radar size={18} /><span><strong>Continuous monitoring</strong> across saved areas</span></div>
            <div><ShieldCheck size={18} /><span><strong>Auditable detections</strong> with source provenance</span></div>
            <div><Sparkles size={18} /><span><strong>Natural-language analysis</strong> grounded in your data</span></div>
          </div>
        </div>
        <div className="orbital orbital-one" />
        <div className="orbital orbital-two" />
        <div className="earth-glow" />
      </section>

      <section className="login-panel">
        <form className="login-card" onSubmit={submit}>
          <div>
            <div className="mobile-brand"><Globe2 size={19} /> TerraLens</div>
            <p className="kicker">SECURE WORKSPACE</p>
            <h2>Welcome back</h2>
            <p className="muted">Sign in to continue to your monitoring console.</p>
          </div>
          <label>
            Work email
            <input
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              type="email"
              autoComplete="username"
              required
            />
          </label>
          <label>
            Password
            <span className="password-field">
              <input
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                required
              />
              <button type="button" onClick={() => setShowPassword((value) => !value)} aria-label="Toggle password visibility">
                {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
              </button>
            </span>
          </label>
          {error && <div className="form-error" role="alert">{error}</div>}
          <button className="primary-button" disabled={pending}>
            {pending ? "Opening workspace…" : "Open workspace"}<ArrowRight size={17} />
          </button>
          <div className="demo-note">
            <span>DEMO</span>
            The form is prefilled for the seeded local environment.
          </div>
        </form>
        <p className="login-footer">Protected by rate limiting, scoped access, and auditable requests.</p>
      </section>
    </main>
  );
}
