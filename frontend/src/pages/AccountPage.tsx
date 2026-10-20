import { useState } from "react";
import { api } from "../api";
import { useApp } from "../App";
import PriceDataCard from "../components/PriceDataCard";

export default function AccountPage() {
  const { user, setUser } = useApp();
  const [profile, setProfile] = useState({
    first_name: user?.first_name ?? "",
    last_name: user?.last_name ?? "",
    email: user?.email ?? "",
    current_password: "",
  });
  const [profileMsg, setProfileMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [savingProfile, setSavingProfile] = useState(false);

  const [pw, setPw] = useState({ current: "", next: "", confirm: "" });
  const [pwMsg, setPwMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [savingPw, setSavingPw] = useState(false);

  const emailChanged = profile.email.trim().toLowerCase() !== (user?.email ?? "").toLowerCase();

  async function saveProfile(e: React.FormEvent) {
    e.preventDefault();
    setSavingProfile(true);
    setProfileMsg(null);
    try {
      const updated = await api.updateProfile({
        first_name: profile.first_name,
        last_name: profile.last_name,
        email: profile.email.trim(),
        current_password: emailChanged ? profile.current_password : undefined,
      });
      setUser(updated);
      setProfile((p) => ({ ...p, current_password: "" }));
      setProfileMsg({ ok: true, text: "Saved." });
    } catch (err) {
      setProfileMsg({ ok: false, text: (err as Error).message });
    } finally {
      setSavingProfile(false);
    }
  }

  async function savePassword(e: React.FormEvent) {
    e.preventDefault();
    if (pw.next !== pw.confirm) {
      setPwMsg({ ok: false, text: "New passwords don't match." });
      return;
    }
    setSavingPw(true);
    setPwMsg(null);
    try {
      await api.changePassword(pw.current, pw.next);
      setPw({ current: "", next: "", confirm: "" });
      setPwMsg({ ok: true, text: "Password changed." });
    } catch (err) {
      setPwMsg({ ok: false, text: (err as Error).message });
    } finally {
      setSavingPw(false);
    }
  }

  return (
    <div className="page account-page">
      <div className="page-head">
        <h1>Account</h1>
      </div>

      <form className="card form-section" onSubmit={saveProfile}>
        <h2>Profile</h2>
        <div className="grid-2">
          <label className="field">
            <span>First name</span>
            <input
              autoComplete="given-name"
              value={profile.first_name}
              onChange={(e) => setProfile({ ...profile, first_name: e.target.value })}
              required
              maxLength={100}
            />
          </label>
          <label className="field">
            <span>Last name</span>
            <input
              autoComplete="family-name"
              value={profile.last_name}
              onChange={(e) => setProfile({ ...profile, last_name: e.target.value })}
              required
              maxLength={100}
            />
          </label>
        </div>
        <label className="field">
          <span>Email</span>
          <input
            type="email"
            autoComplete="email"
            value={profile.email}
            onChange={(e) => setProfile({ ...profile, email: e.target.value })}
            required
          />
        </label>
        {emailChanged && (
          <label className="field">
            <span>Current password (required to change your email)</span>
            <input
              type="password"
              autoComplete="current-password"
              value={profile.current_password}
              onChange={(e) => setProfile({ ...profile, current_password: e.target.value })}
              required
            />
          </label>
        )}
        {profileMsg && <p className={profileMsg.ok ? "pos" : "error"}>{profileMsg.text}</p>}
        <div className="row-end">
          <button className="btn btn-primary" disabled={savingProfile}>
            {savingProfile ? "Saving…" : "Save profile"}
          </button>
        </div>
      </form>

      <DetailsDefault />

      <PriceCodeCard />

      <AskingPriceSetting />

      <form className="card form-section" onSubmit={savePassword}>
        <h2>Change Password</h2>
        <label className="field">
          <span>Current password</span>
          <input
            type="password"
            autoComplete="current-password"
            value={pw.current}
            onChange={(e) => setPw({ ...pw, current: e.target.value })}
            required
          />
        </label>
        <div className="grid-2">
          <label className="field">
            <span>New password (at least 10 characters)</span>
            <input
              type="password"
              autoComplete="new-password"
              minLength={10}
              value={pw.next}
              onChange={(e) => setPw({ ...pw, next: e.target.value })}
              required
            />
          </label>
          <label className="field">
            <span>Confirm new password</span>
            <input
              type="password"
              autoComplete="new-password"
              value={pw.confirm}
              onChange={(e) => setPw({ ...pw, confirm: e.target.value })}
              required
            />
          </label>
        </div>
        {pwMsg && <p className={pwMsg.ok ? "pos" : "error"}>{pwMsg.text}</p>}
        <div className="row-end">
          <button className="btn btn-primary" disabled={savingPw}>
            {savingPw ? "Saving…" : "Change password"}
          </button>
        </div>
      </form>

      <PriceDataCard />
    </div>
  );
}

/** The share of straight-grade CPG that Details (problem) coins are valued at, unless a coin sets its own. */
function DetailsDefault() {
  const { user, setUser } = useApp();
  const [pct, setPct] = useState(String(user?.details_pct ?? 70));
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const n = Number(pct);
    if (!/^\d+$/.test(pct.trim()) || n < 1 || n > 100) return setMsg({ ok: false, text: "Enter a whole number from 1 to 100." });
    setBusy(true);
    setMsg(null);
    try {
      setUser(await api.setPreferences({ details_pct: n }));
      setMsg({ ok: true, text: "Saved. Details coins are revalued everywhere." });
    } catch (err) {
      setMsg({ ok: false, text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card form-section" onSubmit={save}>
      <h2>Details Coins</h2>
      <p className="muted small">
        A Details grade (e.g. “AU Details – Cleaned”) means a genuine coin with a problem. Price guides only cover
        problem-free coins, so Details coins are valued at this share of the CPG for the same straight grade (for a grade
        without a number, the bottom of its range: AU Details is priced from AU50), never below melt. A coin can set its
        own % on its edit page.
      </p>
      <label className="field w-auto">
        <span>Value at % of straight CPG</span>
        <input type="number" min={1} max={100} step={1} value={pct} onChange={(e) => setPct(e.target.value)} />
      </label>
      {msg && <p className={`small ${msg.ok ? "ok" : "error"}`}>{msg.text}</p>}
      <div className="row-end">
        <button className="btn btn-primary" disabled={busy}>
          {busy ? "Saving…" : "Save"}
        </button>
      </div>
    </form>
  );
}

/** Letters in a phrase, in order, without spaces or repeats (as the server counts them). */
function codeLetters(phrase: string): string[] {
  const out: string[] = [];
  for (const ch of phrase.toUpperCase()) if (ch >= "A" && ch <= "Z" && !out.includes(ch)) out.push(ch);
  return out;
}

/** The price code for labels: the phrase (hidden unless shown), whether it starts at 0 or 1, and the code length. */
function PriceCodeCard() {
  const { user, setUser } = useApp();
  const [phrase, setPhrase] = useState(user?.price_code_phrase ?? "");
  const [start, setStart] = useState<0 | 1 | null>(user?.price_code_start ?? null);
  const [length, setLength] = useState(String(user?.price_code_length ?? 6));
  const [show, setShow] = useState(false);
  const [tryPrice, setTryPrice] = useState("145.60");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const letters = codeLetters(phrase);
  const ready = letters.length === 10 && start !== null;
  const digitOf = (i: number) => (i + (start ?? 0)) % 10;
  const startChanged = user?.price_code_start != null && start !== user.price_code_start;
  const len = Math.min(10, Math.max(3, Number(length) || 6));

  function example(): string {
    const n = Number(tryPrice.replace(/[$,\s]/g, ""));
    if (!ready || !tryPrice.trim() || !Number.isFinite(n) || n < 0) return "";
    const dollars = String(Math.round(n));
    const code = [...dollars].map((d) => letters[(Number(d) - start! + 10) % 10]);
    // Filler before and after the real letters (the printed labels pick their own per coin; this shows the idea).
    const filler = [..."ABCDEFGHIJKLMNOPQRSTUVWXYZ"].filter((c) => !letters.includes(c));
    const pad = Math.max(0, len - code.length);
    const before = pad >= 2 ? Math.ceil(pad / 2) : 0;
    const picks = Array.from({ length: pad }, (_, i) => filler[(i * 7 + dollars.length * 3) % filler.length]);
    return `${[...picks.slice(0, before), ...code, ...picks.slice(before)].join("")} ($${Number(dollars).toLocaleString()})`;
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (phrase.trim() && letters.length !== 10) return setMsg({ ok: false, text: `Your phrase has ${letters.length} different letters. It needs exactly 10.` });
    if (phrase.trim() && start === null) return setMsg({ ok: false, text: "Choose whether your phrase starts at 0 or at 1." });
    if (startChanged && !confirm("Labels you've already printed were coded with your old setting, so they'll read differently from new ones. Change it anyway?")) return;
    setBusy(true);
    setMsg(null);
    try {
      setUser(await api.setPriceCode({ phrase: phrase.trim() || null, start: phrase.trim() ? start : null, length: len }));
      setMsg(phrase.trim() ? null : { ok: true, text: "Price code removed." });
    } catch (err) {
      setMsg({ ok: false, text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  const ex = example();
  return (
    <form className="card form-section price-code" onSubmit={save}>
      <h2>Price Code</h2>
      <p className="muted small">
        A price code lets you put what you paid (and when) on a coin's label without anyone else being able to read it.
        Pick a phrase with exactly 10 different letters, like I LOVE FRANK. Its letters stand for the digits in order
        (spaces and repeated letters don't count), starting at 0 or at 1, whichever you choose below. Prices are
        rounded to the nearest whole dollar (no cents), then each digit becomes its letter. If that's shorter than your
        code length, letters that aren't in your phrase are added before and after it as filler (your letters stay
        together): when you read a code, skip any letter that isn't in your phrase. Purchase dates are coded the same way as month, day and 2-digit year (03/15/25).
      </p>
      <div className="grid-2">
        <label className="field">
          <span>Code phrase</span>
          <div className="row nowrap">
            <input
              className="grow"
              type={show ? "text" : "password"}
              value={phrase}
              onChange={(e) => (setPhrase(e.target.value.toUpperCase()), setMsg(null))}
              maxLength={60}
              autoComplete="off"
              spellCheck={false}
              placeholder="10 different letters"
            />
            <button type="button" className="btn small" onClick={() => setShow(!show)}>
              {show ? "Hide" : "Show"}
            </button>
          </div>
          {phrase.trim() && (
            <small className={letters.length === 10 ? "muted" : "error"}>
              {letters.length} of 10 different letters{letters.length > 10 ? " (too many)" : ""}
            </small>
          )}
        </label>
        <label className="field w-auto">
          <span>Code length</span>
          <input type="number" min={3} max={10} step={1} value={length} onChange={(e) => setLength(e.target.value)} />
          <small className="muted">Letters per coded price, with filler</small>
        </label>
      </div>
      <fieldset className="field">
        <span>Your phrase's first letter stands for</span>
        <div className="row wrap">
          <label className="check">
            <input type="radio" name="code-start" checked={start === 0} onChange={() => (setStart(0), setMsg(null))} /> 0 (0123456789)
          </label>
          <label className="check">
            <input type="radio" name="code-start" checked={start === 1} onChange={() => (setStart(1), setMsg(null))} /> 1 (1234567890)
          </label>
        </div>
      </fieldset>
      {letters.length === 10 && start !== null && show && (
        <div className="code-key" aria-label="Your code key">
          {letters.map((l, i) => (
            <span key={l}>
              <strong>{l}</strong>
              {digitOf(i)}
            </span>
          ))}
        </div>
      )}
      {ready && (
        <label className="field w-auto">
          <span>Try a price</span>
          <div className="row">
            <input type="text" inputMode="decimal" value={tryPrice} onChange={(e) => setTryPrice(e.target.value)} style={{ maxWidth: 130 }} />
            <span className="mono">{ex ? `→ ${ex}` : ""}</span>
          </div>
        </label>
      )}
      {startChanged && <p className="small warn">Labels already printed were coded with your old setting.</p>}
      {msg && <p className={`small ${msg.ok ? "ok" : "error"}`}>{msg.text}</p>}
      <div className="row-end">
        <button className="btn btn-primary" disabled={busy}>
          {busy ? "Saving…" : "Save price code"}
        </button>
      </div>
    </form>
  );
}

/** Asking prices on coins and bullion: off unless the owner sells. */
function AskingPriceSetting() {
  const { user, setUser } = useApp();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <section className="card form-section">
      <h2>Asking Prices</h2>
      <label className="check">
        <input
          type="checkbox"
          checked={user?.asking_price_on ?? false}
          disabled={busy}
          onChange={async (e) => {
            setBusy(true);
            setError(null);
            try {
              setUser(await api.setPreferences({ asking_price_on: e.target.checked }));
            } catch (err) {
              setError((err as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        />{" "}
        Show an Asking price field on each coin and bullion item
      </label>
      <p className="muted small">
        For selling: the price you'd take, filled in on its label when you print one. You can always type an asking
        price when printing labels, with this on or off.
      </p>
      {error && <p className="small error">{error}</p>}
    </section>
  );
}
