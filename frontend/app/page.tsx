"use client";
import { useState, useEffect, useSyncExternalStore, FormEvent } from "react";
import { ArrowRight, Check, Eye, EyeOff, FileText, ShieldCheck } from "lucide-react";
import dynamic from "next/dynamic";
import { api, API_URL, setCsrf } from "../lib/api";
import AccountLink from "../components/account-link";
import { Session, box, field, primary } from "../lib/types";
const Workbench = dynamic(() => import("../components/workbench"), {
  loading: () => <main className="p-8" role="status">Opening your workspace...</main>,
});
const subscribe = () => () => {};
export default function Page() {
  const hydrated = useSyncExternalStore(subscribe, () => true, () => false);
  return hydrated ? <Application /> : <main className="p-8" role="status">Loading workspace...</main>;
}
function Application() {
  const [link, setLink] = useState(() => { const p = new URLSearchParams(location.hash.slice(1)); return { action: p.get("action") ?? "", token: p.get("token") ?? "" }; });
  const [showLink, setShowLink] = useState(true);
  useEffect(() => {
    const update = () => { const p = new URLSearchParams(location.hash.slice(1)); setLink({ action: p.get("action") ?? "", token: p.get("token") ?? "" }); setShowLink(true); };
    window.addEventListener("hashchange", update); return () => window.removeEventListener("hashchange", update);
  }, []);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    api<Session>("/auth/me").then((s) => { setCsrf(s.csrf_token); setSession(s); })
      .catch(() => setSession(null)).finally(() => setLoading(false));
    const logout = () => { setSession(null); setCsrf(""); };
    window.addEventListener("rag-signout", logout);
    return () => window.removeEventListener("rag-signout", logout);
  }, []);
  if (loading) return <main className="p-8" role="status">Checking session...</main>;
  if (showLink && ["verify", "reset", "invite"].includes(link.action) && link.token) return <AccountLink {...link} session={session} onClose={() => { history.replaceState(null, "", location.pathname); setShowLink(false); if (session) location.reload(); }} />;
  return session ? <Workbench key={session.user.id} user={session.user} onLogout={() => { setSession(null); setCsrf(""); }} /> :
    <Login onLogin={(s) => { setCsrf(s.csrf_token); setSession(s); }} />;
}
function Login({ onLogin }: { onLogin: (s: Session) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [register, setRegister] = useState(false);
  const [visible, setVisible] = useState(false);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sso, setSso] = useState(false);
  useEffect(() => { void api<{ sso_enabled: boolean }>("/auth/options").then((o) => setSso(o.sso_enabled)).catch(() => {}); }, []);
  const requestEmail = async (path: string) => {
    if (!email) { setError("Enter your email address first."); return; }
    setBusy(true); setError("");
    try { const result = await api<{ message: string }>(path, "POST", { email }); setNotice(result.message); }
    catch (e) { setError(e instanceof Error ? e.message : "Request failed."); }
    finally { setBusy(false); }
  };
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      if (register) {
        const result = await api<{ message: string }>("/auth/register", "POST", { name, email, password });
        setRegister(false); setPassword(""); setVisible(false);
        setNotice(result.message);
      } else onLogin(await api<Session>("/auth/login", "POST", { email, password }));
    }
    catch (error) { setError(error instanceof Error ? error.message : "Sign-in failed."); }
    finally { setBusy(false); }
  };
  return <main className="grid min-h-screen bg-[var(--bg)] text-[var(--text)] lg:grid-cols-2">
    <section className="relative hidden flex-col justify-between overflow-hidden bg-slate-950 p-12 text-white lg:flex xl:p-16">
      <div className="pointer-events-none absolute -right-32 top-20 h-96 w-96 rounded-full bg-indigo-500/20 blur-3xl" />
      <div className="relative flex items-center gap-3 text-lg font-semibold"><span className="rounded-xl bg-white/10 p-3"><FileText className="h-6 w-6" /></span>Enterprise RAG</div>
      <div className="relative max-w-lg py-16"><p className="mb-5 text-xs font-medium tracking-[0.2em] text-indigo-300">YOUR KNOWLEDGE, CONNECTED</p><h1 className="text-5xl font-semibold leading-tight tracking-tight">Turn your documents into clear answers.</h1><p className="mt-6 text-base leading-7 text-slate-300">A focused workspace to explore documents, ask follow-up questions, and trace answers back to their sources.</p>
        <ul className="mt-10 space-y-4 text-sm text-slate-200">{["Answers with document and page references", "Private conversations and workspace access", "Local AI for your document workflow"].map((text) => <li key={text} className="flex items-center gap-3"><Check className="h-4 w-4 shrink-0 text-indigo-300" />{text}</li>)}</ul>
      </div><p className="relative flex items-center gap-2 text-xs text-slate-400"><ShieldCheck className="h-4 w-4" />Knowledge you can inspect. A workspace you control.</p>
    </section>
    <section className="flex items-center justify-center px-6 py-12 sm:px-12"><div className="w-full max-w-md">
      <div className="mb-10 flex items-center gap-2 font-semibold lg:hidden"><FileText className="h-6 w-6 text-[var(--accent)]" />Enterprise RAG</div>
      <p className="mb-3 text-xs font-medium uppercase tracking-widest text-[var(--accent)]">Document intelligence</p><h2 className="text-3xl font-semibold tracking-tight">{register ? "Create your account" : "Welcome back"}</h2>
      <p className="mb-8 mt-3 text-sm leading-6 text-[var(--muted)]">{register ? "Start with a private workspace. Join a team when its administrator adds you." : "Sign in to continue to your document workspace."}</p>
      <form onSubmit={submit} className={box + " space-y-5 p-6 shadow-sm sm:p-8"}>
        {register && <label className="block text-sm font-medium">Full name<input className={field + " mt-2 w-full"} autoComplete="name" required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} /></label>}
        <label className="block text-sm font-medium">Email address<input className={field + " mt-2 w-full"} type="email" placeholder="you@company.com" autoComplete="username" required maxLength={254} value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        <label className="block text-sm font-medium" htmlFor="password">Password</label><div className="relative -mt-3"><input id="password" className={field + " w-full pr-12"} type={visible ? "text" : "password"} autoComplete={register ? "new-password" : "current-password"} required minLength={register ? 12 : undefined} maxLength={256} value={password} onChange={(e) => setPassword(e.target.value)} /><button type="button" className="absolute inset-y-0 right-0 px-3 text-[var(--muted)]" aria-label={visible ? "Hide password" : "Show password"} onClick={() => setVisible(!visible)}>{visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}</button></div>
        {register && <p className="text-xs text-[var(--muted)]">Use at least 12 characters for your password.</p>}
        {notice && <p role="status" className="text-sm text-[var(--ok)]">{notice}</p>}{error && <p role="alert" className="text-sm text-[var(--danger)]">{error}</p>}
        <button className={primary + " flex w-full items-center justify-center gap-2 py-3 font-medium"} disabled={busy}>{busy ? "Please wait..." : register ? "Create account" : "Sign in"}<ArrowRight className="h-4 w-4" /></button>
      </form>
      {!register && <div className="mt-4 flex flex-wrap justify-between gap-3 text-xs text-[var(--accent)]"><button disabled={busy} onClick={() => void requestEmail("/auth/forgot-password")}>Forgot password?</button><button disabled={busy} onClick={() => void requestEmail("/auth/resend-verification")}>Resend verification</button></div>}
      {sso && <a href={`${API_URL}/auth/sso/login`} className="mt-5 block rounded-lg border border-[var(--border)] p-3 text-center text-sm font-medium">Continue with organization SSO</a>}
      <p className="mt-6 text-center text-sm text-[var(--muted)]">{register ? "Already have an account?" : "New to Enterprise RAG?"} <button className="font-medium text-[var(--accent)] hover:underline" disabled={busy} onClick={() => { setRegister(!register); setError(""); setNotice(""); setPassword(""); setVisible(false); }}>{register ? "Sign in" : "Create an account"}</button></p>
    </div></section>
  </main>;
}
