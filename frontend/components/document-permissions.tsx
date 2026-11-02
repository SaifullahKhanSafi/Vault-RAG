"use client";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { box, button, Member, primary } from "../lib/types";
export default function DocumentPermissions({ document, workspace, onClose }: { document: string; workspace: string; onClose: () => void }) {
  const [members, setMembers] = useState<Member[]>([]);
  const [restricted, setRestricted] = useState(false);
  const [ids, setIds] = useState<string[]>([]);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { Promise.all([api<Member[]>(`/workspaces/${workspace}/members`), api<{ restricted: boolean; user_ids: string[] }>(`/documents/${document}/permissions`)])
    .then(([m, p]) => { setMembers(m); setRestricted(p.restricted); setIds(p.user_ids); setReady(true); }).catch((e: Error) => setError(e.message)); }, [document, workspace]);
  return <div role="dialog" aria-modal="true" aria-label="Document permissions" className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-5"><section className={box + " w-full max-w-md space-y-4 p-6"}>
    <h2 className="text-lg font-semibold">Document access</h2><p className="text-sm text-[var(--muted)]">Administrators and the uploader always retain access. Selected users must remain workspace members.</p>
    {error && <p role="alert" className="text-sm text-[var(--danger)]">{error}</p>}
    <label className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={!ready || busy} checked={restricted} onChange={(e) => setRestricted(e.target.checked)} />Restrict to selected members</label>
    {restricted && <div className="max-h-64 space-y-2 overflow-auto">{members.filter((m) => m.role !== "admin").map((m) => <label key={m.id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={ids.includes(m.id)} onChange={(e) => setIds((rows) => e.target.checked ? [...rows, m.id] : rows.filter((id) => id !== m.id))} />{m.email}</label>)}</div>}
    <div className="flex gap-2"><button disabled={!ready || busy} className={primary} onClick={async () => { setBusy(true); try { await api(`/documents/${document}/permissions`, "PUT", { restricted, user_ids: ids }); onClose(); } catch (e) { setError(e instanceof Error ? e.message : "Could not save."); } finally { setBusy(false); } }}>Save access</button><button className={button} onClick={onClose}>Close</button></div>
  </section></div>;
}
