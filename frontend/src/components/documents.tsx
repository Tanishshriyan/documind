import { ChevronDown, FileSearch, Filter, LoaderCircle, Search, Trash2, UploadCloud } from "lucide-react";
import { useRef, useState, type ChangeEvent, type DragEvent } from "react";

import type { Document, DocumentStatus, UploadResult } from "../types";
import { FileTypeIcon, formatBytes, formatDate, IconButton, StatusBadge } from "./common";

type UploadHandler = (file: File, onProgress?: (progress: number) => void) => Promise<UploadResult>;

const ACCEPTED_FILES = ".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain";

export function UploadButton({ onUpload, onComplete, onError, label = "Upload documents" }: { onUpload: UploadHandler; onComplete?: (result: UploadResult) => void; onError?: (message: string) => void; label?: string }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);

  async function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy(true);
    setProgress(0);
    try {
      const result = await onUpload(file, setProgress);
      onComplete?.(result);
    } catch (error) {
      onError?.(error instanceof Error ? error.message : "The document could not be uploaded.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <input ref={inputRef} type="file" className="visually-hidden" accept={ACCEPTED_FILES} onChange={(event) => void handleChange(event)} />
      <button className="button button-primary" type="button" onClick={() => inputRef.current?.click()} disabled={busy}>
        {busy ? <><LoaderCircle className="spin" size={16} /> Uploading {progress}%</> : <><UploadCloud size={16} /> {label}</>}
      </button>
    </>
  );
}

export function DocumentUploadZone({ onUpload, onComplete, onError }: { onUpload: UploadHandler; onComplete?: (result: UploadResult) => void; onError?: (message: string) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);

  async function upload(file: File) {
    setBusy(true);
    setProgress(0);
    try {
      const result = await onUpload(file, setProgress);
      onComplete?.(result);
    } catch (error) {
      onError?.(error instanceof Error ? error.message : "The document could not be uploaded.");
    } finally {
      setBusy(false);
    }
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files[0];
    if (file) void upload(file);
  }

  return (
    <div
      className={`upload-zone ${dragging ? "upload-zone-active" : ""}`}
      onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={(event) => { if (event.target !== inputRef.current && !busy) inputRef.current?.click(); }}
      onKeyDown={(event) => { if ((event.key === "Enter" || event.key === " ") && !busy) inputRef.current?.click(); }}
      role="button"
      tabIndex={0}
    >
      <input ref={inputRef} type="file" className="visually-hidden" accept={ACCEPTED_FILES} onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; if (file) void upload(file); }} />
      <span className="upload-zone-icon">{busy ? <LoaderCircle className="spin" size={20} /> : <UploadCloud size={20} />}</span>
      <div>
        <strong>{busy ? `Uploading ${progress}%` : "Drop documents here or browse"}</strong>
        <p>PDF, DOCX, or TXT. Files are validated and indexed securely.</p>
      </div>
      {!busy && <span className="upload-zone-action">Choose files</span>}
    </div>
  );
}

export function DocumentList({ documents, compact = false, onDelete, onPreview }: { documents: Document[]; compact?: boolean; onDelete?: (document: Document) => void; onPreview?: (document: Document) => void }) {
  if (!documents.length) return null;
  return (
    <div className={`document-list ${compact ? "document-list-compact" : ""}`}>
      {documents.map((document) => <DocumentRow key={document.id} document={document} compact={compact} onDelete={onDelete} onPreview={onPreview} />)}
    </div>
  );
}

export function DocumentRow({ document, compact = false, onDelete, onPreview }: { document: Document; compact?: boolean; onDelete?: (document: Document) => void; onPreview?: (document: Document) => void }) {
  const type = document.content_type.split("/").pop()?.toUpperCase() ?? "FILE";
  return (
    <div className={`document-row ${compact ? "document-row-compact" : ""}`}>
      <FileTypeIcon name={document.name} size={compact ? 17 : 18} />
      <div className="document-primary">
        <strong title={document.name}>{document.name}</strong>
        <span>{type} <i /> {formatBytes(document.size_bytes)} <i /> {document.chunk_count ? `${document.chunk_count} chunks` : "Awaiting index"}</span>
      </div>
      <StatusBadge status={document.status} />
      <span className="document-date">{formatDate(document.uploaded_at ?? document.created_at)}</span>
      {(onPreview || onDelete) && <div className="document-actions">
        {onPreview && <IconButton label={`Preview ${document.name}`} onClick={() => onPreview(document)}><FileSearch size={16} /></IconButton>}
        {onDelete && <IconButton label={`Delete ${document.name}`} className="danger-action" onClick={() => onDelete(document)}><Trash2 size={16} /></IconButton>}
      </div>}
    </div>
  );
}

export function DocumentTable({ documents, onDelete, onPreview }: { documents: Document[]; onDelete: (document: Document) => void; onPreview?: (document: Document) => void }) {
  return (
    <div className="document-table-wrap">
      <table className="document-table">
        <thead><tr><th>Document</th><th>Status</th><th>Indexed content</th><th>Added</th><th><span className="visually-hidden">Actions</span></th></tr></thead>
        <tbody>{documents.map((document) => <tr key={document.id}>
          <td><div className="table-document"><FileTypeIcon name={document.name} /><div><strong>{document.name}</strong><span>{document.content_type.split("/").pop()?.toUpperCase()} <i /> {formatBytes(document.size_bytes)}</span></div></div></td>
          <td><StatusBadge status={document.status} /></td>
          <td className="table-muted">{document.chunk_count ? `${document.chunk_count} chunks` : document.status === "READY" ? "No chunks" : "Not ready"}</td>
          <td className="table-muted">{formatDate(document.uploaded_at ?? document.created_at)}</td>
          <td><div className="document-actions table-actions">{onPreview && <IconButton label={`Preview ${document.name}`} onClick={() => onPreview(document)}><FileSearch size={16} /></IconButton>}<IconButton label={`Delete ${document.name}`} className="danger-action" onClick={() => onDelete(document)}><Trash2 size={16} /></IconButton></div></td>
        </tr>)}</tbody>
      </table>
    </div>
  );
}

export function DocumentFilters({ query, onQueryChange, type, onTypeChange, status, onStatusChange, sort, onSortChange }: { query: string; onQueryChange: (value: string) => void; type: string; onTypeChange: (value: string) => void; status: string; onStatusChange: (value: string) => void; sort: string; onSortChange: (value: string) => void }) {
  return (
    <div className="document-filters">
      <label className="search-field"><Search size={16} /><span className="visually-hidden">Search documents</span><input value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="Search documents" /></label>
      <label className="select-field"><Filter size={15} /><span className="visually-hidden">Filter file type</span><select value={type} onChange={(event) => onTypeChange(event.target.value)}><option value="all">All types</option><option value="pdf">PDF</option><option value="docx">DOCX</option><option value="txt">TXT</option></select><ChevronDown size={14} /></label>
      <label className="select-field"><span className="visually-hidden">Filter status</span><select value={status} onChange={(event) => onStatusChange(event.target.value)}><option value="all">All statuses</option><option value="READY">Ready</option><option value="PROCESSING">Indexing</option><option value="PENDING">Queued</option><option value="FAILED">Needs attention</option></select><ChevronDown size={14} /></label>
      <label className="select-field"><span className="visually-hidden">Sort documents</span><select value={sort} onChange={(event) => onSortChange(event.target.value)}><option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="name">Name A–Z</option></select><ChevronDown size={14} /></label>
    </div>
  );
}

export function documentExtension(document: Document) {
  const extension = document.name.split(".").pop()?.toLowerCase();
  return extension === "pdf" || extension === "docx" || extension === "txt" ? extension : "other";
}

export function readyDocuments(documents: Document[]) {
  return documents.filter((document) => document.status === "READY");
}

