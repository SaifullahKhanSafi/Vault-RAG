import { FileText, ShieldCheck, ExternalLink, Upload, Trash2 } from "lucide-react";
import type { Doc } from "../lib/types";
import IndexingProgress from "./indexing-progress";

type Props = { document: Doc; canEdit: boolean; isAdmin: boolean; uploading: boolean;
  onView: () => void; onAccess: () => void; onVersion: () => void; onRemove: () => void };

export default function DocumentCard({ document: doc, canEdit, isAdmin, uploading, onView, onAccess, onVersion, onRemove }: Props) {
  return <li className="document-card" aria-label={`Document ${doc.name}`}>
    <div className="flex items-start gap-2.5">
      <span className="document-file-icon"><FileText className="h-4 w-4" aria-hidden="true" /></span>
      <div className="min-w-0 flex-1">
        <h3 className="document-name" title={doc.name}>{doc.name}</h3>
        <p className="document-metadata">{doc.version ? <><span>Version {doc.version}</span><span aria-hidden="true">·</span><span>{(doc.chunk_count ?? 0).toLocaleString("en-US")} passages</span></> : "Awaiting first index"}</p>
      </div>
      {canEdit && <button className="document-delete" aria-label={`Delete ${doc.name}`} title="Move document to trash" onClick={onRemove}><Trash2 className="h-3.5 w-3.5" /></button>}
    </div>
    <IndexingProgress name={doc.name} status={doc.job_status} progress={doc.progress} />
    {doc.job_status === "failed" && <p role="alert" className="mt-2 text-xs leading-relaxed text-[var(--danger)]">{doc.error ?? "Indexing failed. Retry from recent jobs below."}{doc.version ? " The previous version is still searchable." : ""}</p>}
    <div className="document-actions">
      <button className="document-view" onClick={onView}><ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />View PDF</button>
      {isAdmin && <button className="document-action" onClick={onAccess}><ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />Manage access</button>}
      {canEdit && <button className="document-action" disabled={uploading} onClick={onVersion}><Upload className="h-3.5 w-3.5" aria-hidden="true" />Upload new version</button>}
    </div>
  </li>;
}
