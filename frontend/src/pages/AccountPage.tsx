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
