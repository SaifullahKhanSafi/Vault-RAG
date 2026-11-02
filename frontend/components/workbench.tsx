"use client";
import { useState, useEffect, useRef, useCallback, FormEvent, ChangeEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { FileText, Plus, Trash2, Paperclip, ArrowUp, Loader2, X, Settings, Moon, Sun, ThumbsUp, ThumbsDown } from "lucide-react";
import { api, apiFetch, API_URL, responseError } from "../lib/api";
import { consumeEvents, Source } from "../lib/sse";
import { User, Workspace, Conversation, Message, Doc, Job, box, field, button, primary } from "../lib/types";
import SettingsPanel from "./settings";
import ResizablePanel from "./resizable-panel";
import DocumentPermissions from "./document-permissions";
import DocumentCard from "./document-card";
import IndexingProgress from "./indexing-progress";

export default function Workbench({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [chats, setChats] = useState<Conversation[]>([]);
  const [chatSearch, setChatSearch] = useState("");
  const [accessDocument, setAccessDocument] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [input, setInput] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [versionTarget, setVersionTarget] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [method, setMethod] = useState("hybrid");
  const [rerank, setRerank] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [status, setStatus] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [showDocs, setShowDocs] = useState(false);
  const [settings, setSettings] = useState(false);
  const [citation, setCitation] = useState<Source | null>(null);
  const [theme, setTheme] = useState(() => { try { return localStorage.getItem("theme") === "dark" ? "dark" : "light"; } catch { return "light"; } });
  const abort = useRef<AbortController | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const workspace = workspaces.find((w) => w.id === workspaceId);
  const canEdit = workspace?.role === "admin" || workspace?.role === "editor";
  useEffect(() => {
    api<Workspace[]>("/workspaces").then((rows) => { setWorkspaces(rows); setWorkspaceId(rows[0]?.id ?? ""); })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Could not load workspaces."));
    return () => abort.current?.abort();
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("theme", theme); } catch { /* Optional preference. */ }
  }, [theme]);
  useEffect(() => {
    if (!workspaceId) return;
    let cancelled = false;
    Promise.all([api<Doc[]>(`/workspaces/${workspaceId}/documents`), api<Conversation[]>(`/workspaces/${workspaceId}/conversations`), api<Job[]>(`/workspaces/${workspaceId}/jobs`)])
      .then(([d, c, j]) => { if (!cancelled) { setDocs(d); setChats(c); setJobs(j); setActiveId(null); setMessages([]); setFilter(""); } })
      .catch((e: unknown) => { if (!cancelled) setError(e instanceof Error ? e.message : "Could not load workspace."); });
    return () => { cancelled = true; };
  }, [workspaceId]);
  const refresh = useCallback(async () => {
    const [d, j] = await Promise.all([api<Doc[]>(`/workspaces/${workspaceId}/documents`), api<Job[]>(`/workspaces/${workspaceId}/jobs`)]);
    setDocs(d); setJobs(j);
  }, [workspaceId]);
  useEffect(() => {
    if (!jobs.some((j) => ["queued", "processing"].includes(j.status))) return;
    const timer = setInterval(() => { void refresh().catch(() => {}); }, 2500);
    return () => clearInterval(timer);
  }, [jobs, refresh]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, status]);
  const run = async (fn: () => Promise<void>) => {
    setError(""); setNotice("");
    try { await fn(); } catch (e) { setError(e instanceof Error ? e.message : "Request failed."); }
  };
  const openChat = (id: string) => run(async () => {
    const chat = await api<Conversation>(`/conversations/${id}`); setActiveId(id); setMessages(chat.messages ?? []);
  });
  const newChat = () => { setActiveId(null); setMessages([]); setError(""); };
  const pinChat = (chat: Conversation) => run(async () => {
    await api(`/conversations/${chat.id}/pin`, "PATCH", { pinned: !chat.pinned });
    setChats((rows) => rows.map((r) => r.id === chat.id ? { ...r, pinned: !r.pinned } : r));
  });
  const exportChat = () => run(async () => {
    const response = await apiFetch(`/conversations/${activeId}/export`);
    if (!response.ok) throw new Error(await responseError(response));
    const url = URL.createObjectURL(await response.blob()); const a = document.createElement("a"); a.href = url; a.download = `conversation-${activeId}.md`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  const printChat = () => {
    const page = window.open("", "_blank"); if (!page) { setError("Allow pop-ups to print this conversation."); return; }
    page.document.title = chats.find((c) => c.id === activeId)?.title ?? "Conversation";
    const content = page.document.createElement("pre"); content.style.cssText = "white-space:pre-wrap;font:14px/1.6 system-ui;padding:24px;";
    content.textContent = messages.map((m) => `${m.role.toUpperCase()}\n\n${m.content}`).join("\n\n---\n\n"); page.document.body.appendChild(content); page.print();
  };
  const deleteChat = (id: string) => {
    if (window.confirm("Permanently delete this conversation?")) void run(async () => {
      await api(`/conversations/${id}`, "DELETE"); setChats((rows) => rows.filter((c) => c.id !== id)); if (activeId === id) newChat();
    });
  };
  const pickFile = (e: ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected && (!selected.name.toLowerCase().endsWith(".pdf") || selected.size > 50 * 1024 * 1024)) {
      setError("Choose a PDF no larger than 50 MB."); e.target.value = ""; setFile(null);
    } else setFile(selected ?? null);
  };
  const upload = async () => {
    if (!file || !workspaceId) return;
    setUploading(true);
    await run(async () => {
      const body = new FormData(); body.append("file", file);
      const response = await apiFetch(`/workspaces/${workspaceId}/documents` + (versionTarget ? `/${versionTarget}/versions` : ""), { method: "POST", body });
      if (!response.ok) throw new Error(await responseError(response));
      await refresh(); setFile(null); setVersionTarget(null);
      if (fileInput.current) fileInput.current.value = "";
      setNotice("Upload saved. Indexing is queued; progress appears in Documents.");
    });
    setUploading(false);
  };
  const removeDoc = (doc: Doc) => {
    if (window.confirm(`Move ${doc.name} to trash and exclude it from answers?`)) void run(async () => {
      await api(`/documents/${doc.id}`, "DELETE"); await refresh(); setFilter(""); setNotice("Document moved to trash.");
    });
  };
  const viewDoc = (doc: Doc) => run(async () => {
    const versions = await api<{ id: string; version: number; status: string; original_available: boolean }[]>(`/documents/${doc.id}/versions`);
    const v = versions.find((v) => v.status === "ready" && v.original_available);
    if (!v) throw new Error("This old index has no original PDF. Upload a new version to enable viewing.");
    setCitation({ file: doc.name, page: 1, document_id: doc.id, version_id: v.id, original_available: true });
  });
  const send = async (e: FormEvent) => {
    e.preventDefault(); const question = input.trim(); if (!question || busy || !workspaceId) return;
    setBusy(true); setError(""); setStatus("Connecting...");
    const controller = new AbortController(); abort.current = controller;
    let cid = activeId;
    let replyId: string = crypto.randomUUID();
    try {
      if (!cid) {
        const chat = await api<Conversation>(`/workspaces/${workspaceId}/conversations`, "POST", { title: question.slice(0, 80) });
        cid = chat.id; setActiveId(cid); setChats((rows) => [chat, ...rows]);
      }
      const temporary = replyId;
      setMessages((rows) => [...rows, { id: crypto.randomUUID(), role: "user", content: question }, { id: temporary, role: "assistant", content: "", sources: [], status: "streaming" }]);
      setInput("");
      const response = await apiFetch("/query", { method: "POST", signal: controller.signal, headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace_id: workspaceId, conversation_id: cid, request_id: crypto.randomUUID(), question, document_ids: filter ? [filter] : [], method, rerank }) });
      if (!response.ok) throw new Error(await responseError(response));
      if (!response.body) throw new Error("No response stream.");
      await consumeEvents(response.body, (event) => {
        if (event.type === "meta") { replyId = event.data.message_id; setMessages((rows) => rows.map((m) => m.id === temporary ? { ...m, id: replyId } : m)); }
        if (event.type === "status") setStatus(event.data);
        if (event.type === "token") setMessages((rows) => rows.map((m) => m.id === replyId ? { ...m, content: m.content + event.data } : m));
        if (event.type === "sources") setMessages((rows) => rows.map((m) => m.id === replyId ? { ...m, sources: event.data } : m));
      });
      setMessages((await api<Conversation>(`/conversations/${cid}`)).messages ?? []);
    } catch (e) {
      const text = controller.signal.aborted ? "Response stopped." : e instanceof Error ? e.message : "Response failed.";
      setError(text); setMessages((rows) => rows.map((m) => m.id === replyId ? { ...m, status: "failed", content: m.content || text } : m));
    } finally { abort.current = null; setBusy(false); setStatus(""); }
  };
  const feedback = (id: string, rating: number) => run(async () => { await api(`/messages/${id}/feedback`, "POST", { rating }); setNotice("Feedback saved."); });

  return <div className="flex h-screen bg-[var(--bg)] text-[var(--text)]">
    <ResizablePanel side="left" userId={user.id} className="hidden border-r border-[var(--border)] bg-[var(--panel)] md:flex">
      <h1 className="mb-5 flex items-center gap-2 font-semibold"><FileText className="h-5 w-5 text-[var(--accent)]" />Enterprise RAG</h1>
      <label className="text-xs text-[var(--muted)]">Workspace<select className={field + " mt-1 w-full"} value={workspaceId} disabled={busy || uploading} onChange={(e) => setWorkspaceId(e.target.value)}>{workspaces.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}</select></label>
      <button className={button + " my-4 flex items-center gap-2"} onClick={newChat} disabled={busy}><Plus className="h-4 w-4" />New chat</button>
      <p className="mb-2 text-xs text-[var(--muted)]">Your conversations</p>
      <form className="mb-2" onSubmit={(e) => { e.preventDefault(); void run(async () => setChats(await api<Conversation[]>(`/workspaces/${workspaceId}/conversations?q=${encodeURIComponent(chatSearch)}`))); }}><input className={field + " w-full"} aria-label="Search conversations" placeholder="Search chats, then Enter" maxLength={200} value={chatSearch} onChange={(e) => setChatSearch(e.target.value)} /></form>
      <nav className="flex-1 overflow-y-auto" aria-label="Conversations">{[...chats].sort((a, b) => Number(!!b.pinned) - Number(!!a.pinned)).map((c) => <div key={c.id} className={"flex items-center rounded-lg " + (activeId === c.id ? "bg-[var(--hover)]" : "")}>
        <button className="p-1 text-xs" aria-label={`${c.pinned ? "Unpin" : "Pin"} ${c.title}`} onClick={() => void pinChat(c)}>{c.pinned ? "★" : "☆"}</button>
        <button className="min-w-0 flex-1 truncate p-2 text-left text-sm" disabled={busy} onClick={() => void openChat(c.id)}>{c.title}</button><button className="p-2" disabled={busy} aria-label={`Delete conversation ${c.title}`} onClick={() => deleteChat(c.id)}><Trash2 className="h-3.5 w-3.5" /></button>
      </div>)}</nav>
      <p className="mt-4 truncate text-xs text-[var(--muted)]">{user.email} · {workspace?.role}</p>
      <div className="mt-3 flex gap-2"><button className={button} aria-label="Settings" onClick={() => setSettings(true)}><Settings className="h-4 w-4" /></button><button className={button} aria-label="Toggle theme" onClick={() => setTheme((t) => t === "light" ? "dark" : "light")}>{theme === "light" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}</button><button className={button} disabled={busy} onClick={() => void run(async () => { await api("/auth/logout", "POST"); onLogout(); })}>Sign out</button></div>
    </ResizablePanel>
    <main className="flex min-w-0 flex-1 flex-col">
      <header className="flex min-h-14 flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] px-4 py-2">
        <h2 className="max-w-xs truncate text-sm font-medium">{chats.find((c) => c.id === activeId)?.title ?? "New chat"}</h2>
        <div className="flex min-w-0 max-w-full flex-wrap items-center gap-2"><select aria-label="Workspace" className={field + " max-w-32 md:hidden"} value={workspaceId} disabled={busy} onChange={(e) => setWorkspaceId(e.target.value)}>{workspaces.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}</select>
          {activeId && <><button className={button} disabled={busy} onClick={() => void exportChat()}>Export</button><button className={button} disabled={busy} onClick={printChat}>Print / PDF</button></>}
          <select aria-label="Conversation" className={field + " max-w-28 md:hidden"} value={activeId ?? ""} disabled={busy} onChange={(e) => e.target.value ? void openChat(e.target.value) : newChat()}><option value="">New chat</option>{chats.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}</select>
          <button className={button + " md:hidden"} onClick={() => setSettings(true)} aria-label="Settings"><Settings className="h-4 w-4" /></button><button className={button + " xl:hidden"} onClick={() => setShowDocs(true)}>Documents</button><span className="hidden text-xs text-[var(--muted)] sm:block">Private workspace · local AI</span>
        </div>
      </header>
      <div className="flex-1 overflow-y-auto px-4 py-8"><div className="mx-auto max-w-3xl space-y-7">
        {messages.length === 0 && <div className="py-[12vh] text-center"><FileText className="mx-auto mb-5 h-12 w-12 text-[var(--accent)]" /><h2 className="text-3xl font-semibold">What would you like to know?</h2><p className="mx-auto mt-4 max-w-md text-sm text-[var(--muted)]">Ask about your workspace documents and inspect the evidence behind each answer.</p></div>}
        {messages.map((m) => <article key={m.id} className={m.role === "user" ? "flex justify-end" : ""}>{m.role === "user" ? <p className={box + " max-w-[90%] whitespace-pre-wrap px-4 py-3 text-sm"}>{m.content}</p> :
          <div><div className={"prose prose-sm max-w-none " + (theme === "dark" ? "prose-invert" : "")}><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content || (m.status === "streaming" ? "Searching..." : "Response interrupted.")}</ReactMarkdown></div>
            {!!m.sources?.length && <ul className="mt-3 flex flex-wrap gap-2" aria-label="Sources">{m.sources.map((s, i) => <li key={s.chunk_id ?? i}><button className={button + " max-w-xs truncate text-xs"} onClick={() => setCitation(s)} title="Inspect evidence">{s.file} · p. {s.page ?? "?"}</button></li>)}</ul>}
            {m.status === "complete" && <div className="mt-3 flex gap-3 text-[var(--muted)]"><button aria-label="Helpful answer" title="Share positive feedback with workspace administrators" onClick={() => void feedback(m.id, 1)}><ThumbsUp className="h-3.5 w-3.5" /></button><button aria-label="Unhelpful answer" title="Share negative feedback with workspace administrators" onClick={() => void feedback(m.id, -1)}><ThumbsDown className="h-3.5 w-3.5" /></button></div>}
            {["failed", "cancelled"].includes(m.status ?? "") && <p className="mt-2 text-xs text-[var(--danger)]">Incomplete response</p>}
          </div>}</article>)}
        {busy && <p role="status" className="flex items-center gap-2 text-xs text-[var(--muted)]"><Loader2 className="h-3.5 w-3.5 animate-spin" />{status}</p>}<div ref={end} />
      </div></div>
      <div className="mx-auto w-full max-w-3xl px-4 pb-5">
        {error && <p role="alert" className="mb-2 text-sm text-[var(--danger)]">{error} <button className="inline-flex align-middle" onClick={() => setError("")} aria-label="Dismiss error"><X className="h-4 w-4" /></button></p>}{notice && <p role="status" className="mb-2 text-xs text-[var(--ok)]">{notice}</p>}
        <div className="mb-2 flex flex-wrap gap-2"><select aria-label="Search documents" className={field + " max-w-56 text-xs"} value={filter} onChange={(e) => setFilter(e.target.value)} disabled={busy}><option value="">All workspace documents</option>{docs.filter((d) => d.version).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select>
          <select aria-label="Search method" className={field + " text-xs"} value={method} disabled={busy} onChange={(e) => setMethod(e.target.value)}><option value="hybrid">Keyword + meaning</option><option value="vector">Meaning only</option></select>
          <label className="self-center text-xs"><input type="checkbox" checked={rerank} onChange={(e) => setRerank(e.target.checked)} disabled={busy} /> Improve ranking (slower)</label></div>
        <div className={box + " p-2"}>{file && <div className="mb-2 flex items-center gap-2 border-b border-[var(--border)] px-2 pb-2 text-xs"><span className="min-w-0 flex-1 truncate">{versionTarget ? "New version: " : ""}{file.name}</span><button className={primary} onClick={() => void upload()} disabled={uploading}>{uploading ? "Saving..." : "Index"}</button><button aria-label="Remove attachment" disabled={uploading} onClick={() => { setFile(null); setVersionTarget(null); }}><X className="h-4 w-4" /></button></div>}
          <form onSubmit={send} className="flex items-end gap-2"><input ref={fileInput} className="hidden" type="file" accept="application/pdf" onChange={pickFile} />
            {canEdit && <button type="button" className="p-2" aria-label="Attach PDF" disabled={uploading} onClick={() => { setVersionTarget(null); fileInput.current?.click(); }}><Paperclip className="h-5 w-5" /></button>}
            <textarea className="min-h-10 flex-1 resize-none bg-transparent px-1 py-2 text-sm outline-none" aria-label="Your question" placeholder="Ask about your documents" rows={1} maxLength={4000} value={input} onChange={(e) => setInput(e.target.value)} disabled={busy || !workspaceId} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(e); } }} />
            {busy ? <button type="button" className={button} onClick={() => abort.current?.abort()}>Stop</button> : <button className={primary} disabled={!input.trim() || !workspaceId} aria-label="Send question"><ArrowUp className="h-4 w-4" /></button>}
          </form>
        </div><p className="mt-2 text-center text-[11px] text-[var(--muted)]">Verify answers against their evidence. Conversations are saved to your account.</p>
      </div>
    </main>
    <ResizablePanel side="right" userId={user.id} className={(showDocs ? "absolute inset-y-0 right-0 z-30 flex shadow-xl" : "hidden") + " border-l border-[var(--border)] bg-[var(--panel)] xl:static xl:flex"}>
      <div className="mb-4 flex items-center justify-between"><h2 className="font-medium">Documents</h2><button className="xl:hidden" aria-label="Close documents" onClick={() => setShowDocs(false)}><X className="h-4 w-4" /></button></div><button className={button + " mb-3 text-xs"} onClick={() => void run(refresh)}>Refresh library</button>
      {docs.length === 0 && <p className="text-sm text-[var(--muted)]">No documents yet.</p>}
      <ul className="space-y-3" aria-label="Document library">{docs.map((d) => <DocumentCard key={d.id} document={d} canEdit={canEdit} isAdmin={workspace?.role === "admin"} uploading={uploading}
        onView={() => void viewDoc(d)} onAccess={() => setAccessDocument(d.id)}
        onVersion={() => { setVersionTarget(d.id); fileInput.current?.click(); }} onRemove={() => removeDoc(d)} />)}</ul>
      {jobs.length > 0 && <section className="mt-6"><h3 className="mb-3 text-xs font-medium text-[var(--muted)]">Recent ingestion jobs</h3>{jobs.slice(0, 8).map((j) => <div key={j.id} className="ingestion-job"><p className="truncate text-xs font-medium" title={j.name}>{j.name}</p><IndexingProgress name={j.name} status={j.status} progress={j.progress} compact /><p className="mt-1.5 text-[11px] text-[var(--muted)]">Attempt {j.attempts}</p>{j.status === "failed" && canEdit && <button className="document-action mt-2" onClick={() => void run(async () => { await api(`/jobs/${j.id}/retry`, "POST"); await refresh(); })}>Retry indexing</button>}</div>)}</section>}
      <button className={button + " mt-5"} onClick={() => setSettings(true)}>Workspace settings</button>
    </ResizablePanel>
    {settings && workspace && <SettingsPanel user={user} workspace={workspace} onClose={() => setSettings(false)} onWorkspace={(w) => { setWorkspaces((rows) => [...rows, w]); setWorkspaceId(w.id); setSettings(false); }} onRestored={refresh} onLogout={onLogout} />}
    {accessDocument && <DocumentPermissions document={accessDocument} workspace={workspaceId} onClose={() => { setAccessDocument(null); void run(refresh); }} />}
    {citation && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-3" role="dialog" aria-modal="true" aria-label="Citation evidence"><section className={box + " flex h-[90vh] w-full max-w-5xl flex-col overflow-hidden p-4"}>
      <div className="flex items-center justify-between gap-3"><h2 className="truncate font-medium">{citation.file} · p. {citation.page ?? "?"}</h2><button aria-label="Close citation" onClick={() => setCitation(null)}><X /></button></div>
      {citation.excerpt && <blockquote className="my-3 max-h-40 overflow-y-auto border-l-2 border-[var(--accent)] pl-3 text-sm">{citation.excerpt}</blockquote>}
      {citation.original_available && citation.document_id ? <><a className="my-2 text-xs underline" target="_blank" rel="noreferrer" href={`${API_URL}/documents/${citation.document_id}/file?version=${citation.version_id}#page=${citation.page ?? 1}`}>Open PDF in new tab</a><iframe className="min-h-0 flex-1 rounded border border-[var(--border)]" title={citation.file} src={`${API_URL}/documents/${citation.document_id}/file?version=${citation.version_id}#page=${citation.page ?? 1}`} /></> : <p className="mt-5 text-sm text-[var(--muted)]">The original PDF was not retained in the old index. Upload a new version to enable viewing.</p>}
    </section></div>}
  </div>;
}
