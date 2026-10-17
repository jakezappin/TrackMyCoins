import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useApp } from "../App";

function AuthCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="center-screen">
      <div className="auth-card">
        <div className="brand auth-brand">
          <span className="brand-mark">◉</span> Coin Collection
        </div>
        <h1>{title}</h1>
        {children}
      </div>
    </div>
  );
}

export function LoginPage() {
  const { setUser } = useApp();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from ?? "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setUser(await api.login(email, password));
      navigate(from, { replace: true });
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <AuthCard title="Log in">
      <form onSubmit={submit} className="stack">
        <label className="field">
          <span>Email</span>
          <input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label className="field">
          <span>Password</span>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="btn btn-primary btn-block" disabled={busy}>
          Log in
        </button>
      </form>
      <p className="muted small">
        No account yet? <Link to="/signup">Create one</Link>
      </p>
    </AuthCard>
  );
}

export function SignupPage() {
  const { setUser } = useApp();
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: "", first_name: "", last_name: "", password: "", confirm: "", invite_code: "" });
  const [mode, setMode] = useState<"open" | "invite" | "closed">("open");
  useEffect(() => {
    api.authConfig().then((c) => setMode(c.signup)).catch(() => undefined);
  }, []);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (form.password !== form.confirm) {
      setError("Passwords don't match");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const { confirm: _confirm, invite_code, ...body } = form;
      setUser(await api.signup(mode === "invite" ? { ...body, invite_code } : body));
      navigate("/", { replace: true });
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  if (mode === "closed")
    return (
      <AuthCard title="Create your account">
        <p className="muted">New accounts aren't being accepted right now.</p>
        <p className="muted small">
          Already have an account? <Link to="/login">Log in</Link>
        </p>
      </AuthCard>
    );

  return (
    <AuthCard title="Create your account">
      <form onSubmit={submit} className="stack">
        {mode === "invite" && (
          <label className="field">
            <span>Invite code</span>
            <input value={form.invite_code} onChange={set("invite_code")} required autoComplete="off" />
          </label>
        )}
        <div className="grid-2">
          <label className="field">
            <span>First name</span>
            <input autoComplete="given-name" value={form.first_name} onChange={set("first_name")} required />
          </label>
          <label className="field">
            <span>Last name</span>
            <input autoComplete="family-name" value={form.last_name} onChange={set("last_name")} required />
          </label>
        </div>
        <label className="field">
          <span>Email</span>
          <input type="email" autoComplete="email" value={form.email} onChange={set("email")} required />
        </label>
        <label className="field">
          <span>Password (at least 10 characters)</span>
          <input
            type="password"
            autoComplete="new-password"
            minLength={10}
            value={form.password}
            onChange={set("password")}
            required
          />
        </label>
        <label className="field">
          <span>Confirm password</span>
          <input type="password" autoComplete="new-password" value={form.confirm} onChange={set("confirm")} required />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="btn btn-primary btn-block" disabled={busy}>
          Create account
        </button>
      </form>
      <p className="muted small">
        Already have an account? <Link to="/login">Log in</Link>
      </p>
    </AuthCard>
  );
}
