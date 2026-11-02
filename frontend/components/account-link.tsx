"use client";
import { FormEvent, useState } from "react";
import { api } from "../lib/api";
import { box, field, primary, Session } from "../lib/types";

export default function AccountLink({ action, token, session, onClose }: { action: string; token: string; session: Session | null; onClose: () => void }) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const needsLogin = action === "invite" && !session;
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setError("");
    try {
      const endpoint = action === "verify" ? "verify-email" : action === "reset" ? "reset-password" : "accept-invitation";
      const result = await api<{ message: string }>(`/auth/${endpoint}`, "POST", { token, ...(action === "reset" ? { password } : {}) });
      setMessage(result.message); setPassword("");
      history.replaceState(null, "", location.pathname);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not complete this action."); }
    finally { setBusy(false); }
  };
  return <main className="flex min-h-screen items-center justify-center bg-[var(--bg)] p-6 text-[var(--text)]"><form onSubmit={submit} className={box + " w-full max-w-md space-y-5 p-8"}>
    <h1 className="text-2xl font-semibold">{action === "verify" ? "Verify your email" : action === "reset" ? "Choose a new password" : "Join your team"}</h1>
    {needsLogin && <p className="text-sm">Sign in or create an account with the invited email address, then reopen this invitation link.</p>}
    {action === "reset" && !message && <label className="block text-sm">New password<input type="password" autoComplete="new-password" required minLength={12} maxLength={256} className={field + " mt-2 w-full"} value={password} onChange={(e) => setPassword(e.target.value)} /></label>}
    {error && <p role="alert" className="text-sm text-[var(--danger)]">{error}</p>}{message && <p role="status" className="text-sm text-[var(--ok)]">{message}</p>}
    {!message && !needsLogin && <button disabled={busy} className={primary}>{busy ? "Please wait..." : "Confirm"}</button>}
    <button type="button" className="ml-3 text-sm underline" onClick={onClose}>{session ? "Open workspace" : "Back to sign in"}</button>
  </form></main>;
}
