import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { Logo } from "../components/ui";

export default function AuthPage({ mode }: { mode: "login" | "register" }) {
  const { login, register } = useAuth();
  const nav = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState(mode === "login" ? "priya@demo.foresight" : "");
  const [password, setPassword] = useState(mode === "login" ? "demo1234" : "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") await login(email, password);
      else await register(name, email, password);
      nav("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <section className="auth-hero">
        <div className="row" style={{ gap: 12, fontWeight: 800, fontSize: 18, color: "#fff" }}><Logo size={32} /> Foresight</div>
        <div>
          <h1>See which work will slip — and why — before it does.</h1>
          <p style={{ maxWidth: 440, color: "#a9bcb8", fontSize: 15 }}>
            Foresight combines a delay model trained on real agile project history with your team's live workload,
            dependencies and deadlines, then explains every risk and recommends what to do next.
          </p>
        </div>
        <div className="small" style={{ color: "#7f9591" }}>Predictive project intelligence · final-year project prototype</div>
      </section>
      <section className="auth-form">
        <form onSubmit={submit} className="stack" style={{ width: "min(380px, 100%)" }}>
          <h1>{mode === "login" ? "Sign in" : "Create account"}</h1>
          {mode === "login" && (
            <div className="banner" style={{ background: "var(--brand-soft)", color: "var(--brand)" }}>
              Demo: priya@demo.foresight / demo1234 (after running the seed)
            </div>
          )}
          {mode === "register" && (
            <label className="field">Full name
              <input className="input" value={name} onChange={(e) => setName(e.target.value)} required minLength={2} autoComplete="name" />
            </label>
          )}
          <label className="field">Email
            <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
          </label>
          <label className="field">Password
            <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
              minLength={mode === "register" ? 8 : 1} maxLength={72} autoComplete={mode === "login" ? "current-password" : "new-password"} />
          </label>
          {error && <div className="small" style={{ color: "var(--overdue)" }} role="alert">{error}</div>}
          <button className="btn primary" disabled={busy}>{busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}</button>
          <div className="small muted">
            {mode === "login" ? <>No account? <Link to="/register">Create one</Link></> : <>Have an account? <Link to="/login">Sign in</Link></>}
          </div>
        </form>
      </section>
    </div>
  );
}
