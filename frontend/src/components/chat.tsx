import { Check, ChevronRight, Copy, Eye, FileText, PanelRightClose, PanelRightOpen, Send, Sparkles, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import type { Citation, Document, DocumentChunk, Message } from "../types";
import { FileTypeIcon, formatDate, formatBytes, IconButton, StatusBadge, timeAgo } from "./common";

function inlineMarkdown(value: string, keyPrefix: string): ReactNode[] {
  const pieces = value.split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g).filter(Boolean);
  return pieces.map((piece, index) => {
    if (piece.startsWith("`") && piece.endsWith("`")) return <code key={`${keyPrefix}-${index}`}>{piece.slice(1, -1)}</code>;
    if (piece.startsWith("**") && piece.endsWith("**")) return <strong key={`${keyPrefix}-${index}`}>{piece.slice(2, -2)}</strong>;
    if (piece.startsWith("*") && piece.endsWith("*")) return <em key={`${keyPrefix}-${index}`}>{piece.slice(1, -1)}</em>;
    const link = piece.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (link) return <span className="markdown-link" key={`${keyPrefix}-${index}`} title={link[2]}>{link[1]}</span>;
    return <span key={`${keyPrefix}-${index}`}>{piece}</span>;
  });
}

export function MarkdownContent({ content }: { content: string }) {
  const lines = content.split("\n");
  const nodes: ReactNode[] = [];
  let codeLines: string[] = [];
  let inCode = false;
  let listItems: string[] = [];

  const flushList = () => {
    if (!listItems.length) return;
    nodes.push(<ul key={`list-${nodes.length}`}>{listItems.map((item, index) => <li key={index}>{inlineMarkdown(item, `list-${index}`)}</li>)}</ul>);
    listItems = [];
  };
  const flushCode = () => {
    if (!codeLines.length) return;
    nodes.push(<pre key={`code-${nodes.length}`}><code>{codeLines.join("\n")}</code></pre>);
    codeLines = [];
  };

  lines.forEach((line, index) => {
    if (line.trim().startsWith("```")) {
      flushList();
      if (inCode) flushCode();
      inCode = !inCode;
      return;
    }
    if (inCode) {
      codeLines.push(line);
      return;
    }
    if (!line.trim()) {
      flushList();
      return;
    }
    const listMatch = line.match(/^\s*[-*]\s+(.+)$/);
    if (listMatch) {
      listItems.push(listMatch[1]);
      return;
    }
    flushList();
    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      const Tag = heading[1].length === 1 ? "h3" : "h4";
      nodes.push(<Tag key={`heading-${index}`}>{inlineMarkdown(heading[2], `heading-${index}`)}</Tag>);
    } else {
      nodes.push(<p key={`paragraph-${index}`}>{inlineMarkdown(line, `paragraph-${index}`)}</p>);
    }
  });
  flushList();
  if (inCode) flushCode();
  return <div className="markdown-content">{nodes}</div>;
}

export function ChatMessage({ message, onCopyCitation, onOpenCitation }: { message: Message; onCopyCitation?: (citation: Citation) => void; onOpenCitation?: (citation: Citation) => void }) {
  const isUser = message.role === "user";
  const openCitation = onOpenCitation ?? ((citation: Citation) => window.dispatchEvent(new CustomEvent("documind:open-citation", { detail: citation })));
  return (
    <article className={`chat-message ${isUser ? "chat-message-user" : "chat-message-assistant"}`}>
      <div className={`message-avatar ${isUser ? "message-avatar-user" : "message-avatar-assistant"}`}>{isUser ? "You" : <Sparkles size={15} />}</div>
      <div className="message-body">
        <div className="message-meta"><strong>{isUser ? "You" : "DocuMind"}</strong><span>{new Date(message.created_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</span></div>
        <div className={`message-content ${isUser ? "message-content-user" : "message-content-assistant"}`}><MarkdownContent content={message.content} /></div>
        {!isUser && message.citations.length > 0 && <div className="citation-list"><div className="citation-label"><span>Evidence</span><span>{message.citations.length} source{message.citations.length === 1 ? "" : "s"}</span></div>{message.citations.map((citation, index) => <CitationCard citation={citation} index={index} key={`${citation.chunk_id ?? citation.document_id}-${index}`} onCopy={onCopyCitation} onOpen={openCitation} />)}</div>}
      </div>
    </article>
  );
}

export function CitationCard({ citation, index, onCopy, onOpen }: { citation: Citation; index: number; onCopy?: (citation: Citation) => void; onOpen?: (citation: Citation) => void }) {
  const [copied, setCopied] = useState(false);
  const sourceLabel = citation.source_label ?? `[S${index + 1}]`;
  async function copyCitation() {
    try {
      await navigator.clipboard.writeText(`Source: ${citation.document_name}${citation.page_number ? `, page ${citation.page_number}` : ""}\n${citation.excerpt}`);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
      onCopy?.(citation);
    } catch {
      onCopy?.(citation);
    }
  }
  return (
    <div className="citation-card">
      <div className="citation-card-head"><button type="button" className="citation-open" onClick={() => onOpen?.(citation)} disabled={!onOpen}><span className="citation-index">{sourceLabel}</span><strong title={citation.document_name}>{citation.document_name}</strong><span className="citation-location">{citation.page_number ? `Page ${citation.page_number}` : "Document"}</span><span className="citation-open-label">Open source</span></button><IconButton label="Copy citation" className="citation-copy" onClick={() => void copyCitation()}>{copied ? <Check size={14} /> : <Copy size={14} />}</IconButton></div>
      <button type="button" className="citation-excerpt" onClick={() => onOpen?.(citation)} disabled={!onOpen}>{citation.excerpt}</button>
      <span className="citation-relevance">Relevance {Math.round(citation.relevance * 100)}%</span>
    </div>
  );
}

export function ChatComposer({ value, onChange, onSubmit, busy, selectedCount, allSources, onOpenSources }: { value: string; onChange: (value: string) => void; onSubmit: () => void; busy: boolean; selectedCount: number; allSources: boolean; onOpenSources: () => void }) {
  return (
    <div className="composer-wrap">
      <div className="composer">
        <textarea value={value} onChange={(event) => onChange(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); onSubmit(); } }} placeholder="Ask a question about your documents..." rows={1} maxLength={8000} aria-label="Ask a question" />
        <div className="composer-actions"><button type="button" className="composer-source" onClick={onOpenSources}><FileText size={15} /> {allSources ? "All sources" : `${selectedCount} source${selectedCount === 1 ? "" : "s"}`}</button><button type="button" className="send-button" onClick={onSubmit} disabled={!value.trim() || busy} aria-label="Send question">{busy ? <span className="send-loader" /> : <Send size={16} />}</button></div>
      </div>
      <div className="composer-footer"><span><kbd>Enter</kbd> to send <i /> <kbd>Shift Enter</kbd> for a new line</span><span className="composer-grounding"><span className="live-dot" /> Grounded in your sources</span></div>
    </div>
  );
}

export function SourcePanel({ documents, selectedDocIds, citations, open, onClose, onToggle, onPreview, onCitationOpen }: { documents: Document[]; selectedDocIds: string[] | null; citations: Citation[]; open: boolean; onClose: () => void; onToggle: (id: string) => void; onPreview: (document: Document) => void; onCitationOpen?: (citation: Citation) => void }) {
  const readyCount = documents.filter((document) => document.status === "READY").length;
  const allSources = selectedDocIds === null;
  const openCitation = onCitationOpen ?? ((citation: Citation) => window.dispatchEvent(new CustomEvent("documind:open-citation", { detail: citation })));
  return (
    <aside className={`source-panel ${open ? "source-panel-open" : ""}`}>
      <div className="source-panel-head"><div><span className="eyebrow">Workspace context</span><h2>Sources</h2></div><IconButton label="Close sources" className="source-close-mobile" onClick={onClose}><X size={17} /></IconButton></div>
      <p className="source-panel-description">Choose which indexed documents should inform the next answer.</p>
      <div className="source-summary"><span className="source-summary-dot" />{allSources ? `All ${readyCount} ready sources` : `${selectedDocIds.length} of ${readyCount} sources selected`}</div>
      <div className="source-list">
        {documents.length ? documents.map((document) => {
          const selected = document.status === "READY" && (allSources || selectedDocIds.includes(document.id));
          return <div className={`source-row ${selected ? "source-row-selected" : ""} ${document.status !== "READY" ? "source-row-disabled" : ""}`} key={document.id}>
            <button className="source-toggle" type="button" onClick={() => onToggle(document.id)} disabled={document.status !== "READY"} aria-pressed={selected}>
              <span className={`source-checkbox ${selected ? "source-checkbox-checked" : ""}`}>{selected && <Check size={12} />}</span><FileTypeIcon name={document.name} size={16} /><span className="source-name"><strong title={document.name}>{document.name}</strong><small>{document.status === "READY" ? `${formatBytes(document.size_bytes)} · ${document.chunk_count} chunks` : document.status}</small></span>
            </button>
            <IconButton label={`Preview ${document.name}`} className="source-preview" onClick={() => onPreview(document)} disabled={document.status !== "READY"}><Eye size={15} /></IconButton>
          </div>;
        }) : <p className="source-empty">Upload a document to start asking grounded questions.</p>}
      </div>
      {citations.length > 0 && <div className="latest-evidence"><div className="latest-evidence-head"><span className="eyebrow">Latest answer</span><span>{citations.length} citations</span></div>{citations.slice(0, 3).map((citation, index) => <button type="button" className="latest-evidence-row" key={`${citation.chunk_id ?? citation.document_id}-${index}`} onClick={() => openCitation(citation)}><span>{citation.source_label ?? `[S${index + 1}]`}</span><div><strong>{citation.document_name}</strong><p>{citation.excerpt}</p></div></button>)}</div>}
      <div className="source-panel-foot"><span><span className="keyboard-key">⌘</span><span className="keyboard-key">K</span></span><span>Search library from the top bar</span></div>
    </aside>
  );
}

export function DocumentPreviewPanel({ document, chunks, loading, error, selectedChunkId, onClose }: { document: Document; chunks: DocumentChunk[]; loading: boolean; error?: string; selectedChunkId?: number | null; onClose: () => void }) {
  const focusedChunk = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (!loading && selectedChunkId !== null && selectedChunkId !== undefined) focusedChunk.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [chunks, loading, selectedChunkId]);
  return (
    <div className="preview-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="preview-panel" role="dialog" aria-modal="true" aria-labelledby="preview-title">
        <header className="preview-head"><div><span className="eyebrow">Source preview</span><h2 id="preview-title">{document.name}</h2><p>{formatBytes(document.size_bytes)} · Added {formatDate(document.uploaded_at ?? document.created_at)}</p></div><IconButton label="Close source preview" onClick={onClose}><X size={18} /></IconButton></header>
        <div className="preview-content">{loading ? <div className="preview-loading"><span className="send-loader" /> Loading indexed chunks...</div> : error ? <p className="source-empty">{error}</p> : chunks.length ? chunks.map((chunk) => <article className={`preview-chunk ${selectedChunkId === chunk.id ? "preview-chunk-focused" : ""}`} ref={selectedChunkId === chunk.id ? focusedChunk : undefined} key={chunk.id}><div><span>Chunk {chunk.chunk_index + 1}</span>{chunk.page_number && <span>Page {chunk.page_number}</span>}</div><p>{chunk.content}</p></article>) : <p className="source-empty">No indexed chunks are available for this document.</p>}</div>
      </section>
    </div>
  );
}

export function ConversationPreview({ title, updatedAt, messageCount }: { title: string; updatedAt: string; messageCount: number }) {
  return <div className="conversation-preview"><span className="conversation-icon"><Sparkles size={15} /></span><div><strong title={title}>{title}</strong><span>{timeAgo(updatedAt)} <i /> {messageCount} messages</span></div><ChevronRight size={15} /></div>;
}

