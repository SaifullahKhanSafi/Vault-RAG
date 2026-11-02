"use client";
import { useState, useEffect, FormEvent } from "react";
import { X, RotateCcw } from "lucide-react";
import { api } from "../lib/api";
import { User, Workspace, Doc, Member, box, field, button, primary } from "../lib/types";
type Overview = { documents: number; members: number; failed_jobs: number; negative_feedback: number; last_24_hours: { requests: number; successful: number; average_ms: number | null; p95_ms: number | null; average_first_token_ms: number | null } };
type Audit = { action: string; created_at: string };
export default function SettingsPanel({ user, workspace, onClose, onWorkspace, onRestored, onLogout }: {
  user: User; workspace: Workspace; onClose: () => void; onWorkspace: (w: Workspace) => void; onRestored: () => Promise<void>; onLogout: () => void;
}) {
  const [members, setMembers] = useState<Member[]>([]);
  const [trash, setTrash] = useState<Doc[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [audit, setAudit] = useState<Audit[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [workspaceName, setWorkspaceName] = useState("");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("reader");
  const [existing, setExisting] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("reader");
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [working, setWorking] = useState(false);
  const admin = workspace.role === "admin";
  useEffect(() => {
    api<Doc[]>(`/workspaces/${workspace.id}/documents?deleted=true`).then(setTrash).catch(() => {});
    if (admin) Promise.all([api<Member[]>(`/workspaces/${workspace.id}/members`), api<Overview>(`/workspaces/${workspace.id}/overview`), api<Audit[]>(`/workspaces/${workspace.id}/audit`)])
      .then(([m, o, a]) => { setMembers(m); setOverview(o); setAudit(a); }).catch((e: unknown) => setError(e instanceof Error ? e.message : "Could not load settings."));
  }, [workspace.id, admin]);
  const run = async (action: () => Promise<void>) => {
    setWorking(true); setError(""); setNotice("");
    try { await action(); } catch (e) { setError(e instanceof Error ? e.message : "Request failed."); }
    finally { setWorking(false); }
  };
  const addMember = (event: FormEvent) => {
    event.preventDefault();
    void run(async () => {
      await api(`/workspaces/${workspace.id}/${existing ? "members" : "users"}`, "POST", { email, role, ...(!existing ? { name, password } : {}) });
      setMembers(await api<Member[]>(`/workspaces/${workspace.id}/members`)); setEmail(""); setName(""); setPassword("");
      setNotice("Account or membership created. Share credentials through your approved private channel.");
    });
  };
  return <div className="fixed inset-0 z-40 overflow-y-auto bg-black/50 p-4" role="dialog" aria-modal="true" aria-label="Workspace settings">
    <section className={box + " mx-auto max-w-3xl space-y-7 p-6"}>
      <div className="flex items-center justify-between"><h2 className="text-xl font-semibold">Workspace settings</h2><button aria-label="Close settings" onClick={onClose}><X /></button></div>
      <p className="text-sm text-[var(--muted)]">{workspace.name} ? {user.email} ? {workspace.role}</p>
      {error && <p role="alert" className="text-sm text-[var(--danger)]">{error}</p>}{notice && <p role="status" className="text-sm text-[var(--ok)]">{notice}</p>}
      {admin && <form className="grid gap-2 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); void run(async () => { const result = await api<{ message: string }>(`/workspaces/${workspace.id}/invitations`, "POST", { email: inviteEmail, role: inviteRole }); setNotice(result.message); setInviteEmail(""); }); }}><h3 className="col-span-full font-medium">Invite by email</h3><input className={field} aria-label="Invitation email" type="email" required placeholder="teammate@company.com" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} /><select className={field} aria-label="Invitation role" value={inviteRole} onChange={(e) => setInviteRole(e.target.value)}><option value="reader">Reader</option><option value="editor">Editor</option></select><button className={primary} disabled={working}>Send invitation</button></form>}
      {admin && <section><h3 className="mb-3 font-medium">Members and permissions</h3><ul className="space-y-2">{members.map((member) => <li key={member.id} className="flex flex-wrap items-center gap-2 text-sm">
        <span className="min-w-0 flex-1 truncate">{member.name} ? {member.email}</span>
        <select aria-label={`Role for ${member.email}`} className={field} value={member.role} disabled={working} onChange={(event) => {
          const selected = event.target.value;
          void run(async () => { await api(`/workspaces/${workspace.id}/members/${member.id}`, "PATCH", { role: selected }); setMembers(await api<Member[]>(`/workspaces/${workspace.id}/members`)); setNotice("Role updated. Refresh to update your own controls."); });
        }}><option value="reader">Reader</option><option value="editor">Editor</option><option value="admin">Administrator</option></select>
        <button className={button} disabled={working} onClick={() => {
          if (window.confirm("Remove this member's workspace access?")) void run(async () => {
            await api(`/workspaces/${workspace.id}/members/${member.id}`, "DELETE"); setMembers((rows) => rows.filter((m) => m.id !== member.id));
          });
        }}>Remove</button>
      </li>)}</ul>
      <form className="mt-4 grid gap-2 sm:grid-cols-2" onSubmit={addMember}>
        <label className="col-span-full text-xs"><input type="checkbox" checked={existing} onChange={(e) => setExisting(e.target.checked)} /> Add an existing account</label>
        <input className={field} aria-label="Member email" type="email" placeholder="Email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <select className={field} aria-label="New member role" value={role} onChange={(e) => setRole(e.target.value)}><option value="reader">Reader</option><option value="editor">Editor</option><option value="admin">Administrator</option></select>
        {!existing && <><input className={field} aria-label="Member name" placeholder="Name" required value={name} onChange={(e) => setName(e.target.value)} /><input className={field} aria-label="Member password" type="password" autoComplete="new-password" placeholder="Password (12+ characters)" minLength={12} required value={password} onChange={(e) => setPassword(e.target.value)} /></>}
        <button className={primary} disabled={working}>{existing ? "Add member" : "Create account"}</button>
      </form></section>}
      {workspace.role !== "reader" && <section><h3 className="mb-3 font-medium">Document trash</h3>{trash.length === 0 ? <p className="text-sm text-[var(--muted)]">Trash is empty.</p> :
        trash.map((doc) => <div key={doc.id} className="mb-2 flex items-center justify-between gap-2 text-sm"><span className="truncate">{doc.name}</span><button className={button} disabled={working} onClick={() => void run(async () => {
          await api(`/documents/${doc.id}/restore`, "POST"); setTrash((rows) => rows.filter((d) => d.id !== doc.id)); await onRestored();
        })}><RotateCcw className="mr-1 inline h-3 w-3" />Restore</button></div>)}</section>}
      {overview && <section><h3 className="mb-3 font-medium">Operations ? last 24 hours</h3><div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        {[["Documents", overview.documents], ["Members", overview.members], ["Failed jobs", overview.failed_jobs], ["Queries", overview.last_24_hours.requests], ["Successful", overview.last_24_hours.successful],
          ["Average answer", overview.last_24_hours.average_ms === null ? "?" : (Number(overview.last_24_hours.average_ms) / 1000).toFixed(1) + "s"],
          ["P95 answer", overview.last_24_hours.p95_ms === null ? "?" : (overview.last_24_hours.p95_ms / 1000).toFixed(1) + "s"], ["Negative feedback", overview.negative_feedback]]
          .map(([label, value]) => <div className={box + " p-3"} key={label}><p className="text-xs text-[var(--muted)]">{label}</p><p className="mt-1 font-medium">{value}</p></div>)}</div>
        <p className="mt-2 text-xs text-[var(--muted)]">Includes cold starts and failures. Timings are observations, not quality scores.</p>
      </section>}
      {admin && audit.length > 0 && <section><h3 className="mb-2 font-medium">Recent audit events</h3><ul className="max-h-40 overflow-y-auto text-xs text-[var(--muted)]">{audit.slice(0, 20).map((a, i) => <li key={i} className="py-1">{new Date(a.created_at).toLocaleString()} ? {a.action}</li>)}</ul></section>}
      <form className="space-y-2" onSubmit={(event) => { event.preventDefault(); void run(async () => onWorkspace(await api<Workspace>("/workspaces", "POST", { name: workspaceName }))); }}>
        <h3 className="font-medium">Create workspace</h3><input className={field + " w-full"} aria-label="New workspace name" placeholder="Workspace name" required maxLength={120} value={workspaceName} onChange={(e) => setWorkspaceName(e.target.value)} /><button className={button} disabled={working}>Create workspace</button>
      </form>
      <form className="space-y-2" onSubmit={(event) => { event.preventDefault(); void run(async () => { await api("/auth/password", "POST", { current_password: oldPassword, new_password: newPassword }); onLogout(); }); }}>
        <h3 className="font-medium">Change your password</h3><input className={field + " w-full"} aria-label="Current password" type="password" autoComplete="current-password" required value={oldPassword} onChange={(e) => setOldPassword(e.target.value)} /><input className={field + " w-full"} aria-label="New password" type="password" autoComplete="new-password" minLength={12} required value={newPassword} onChange={(e) => setNewPassword(e.target.value)} /><button className={button} disabled={working}>Change password and sign out</button>
      </form>
      <button className={button} disabled={working} onClick={() => void run(async () => { await api("/auth/logout", "POST"); onLogout(); })}>Sign out</button>
    </section>
  </div>;
}
