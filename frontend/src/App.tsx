import {
  ArrowUpRight,
  ChevronRight,
  Files,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquare,
  MoreHorizontal,
  PanelLeftClose,
  PanelRightOpen,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  X,
} from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { BrowserRouter, NavLink, Navigate, Route, Routes, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { api } from "./api/client";
import { ChatMessage, ChatComposer, ConversationPreview, DocumentPreviewPanel, SourcePanel } from "./components/chat";
import { DocumentFilters, DocumentList, DocumentTable, DocumentUploadZone, UploadButton, documentExtension, readyDocuments } from "./components/documents";
import { Brand, EmptyState, formatBytes, IconButton, InlineNotice, LoadingRows, Toast, ToastStack } from "./components/common";
import type { AuthUser, Citation, Conversation, Document, DocumentChunk, Message, UploadResult } from "./types";

const navItems = [
  { label: "Overview", to: "/", icon: LayoutDashboard, end: true },
  { label: "Documents", to: "/documents", icon: Files },
  { label: "Conversations", to: "/chat", icon: MessageSquare },
];

type ToastInput = Omit<Toast, "id">;
const ToastContext = createContext<(toast: ToastInput) => void>(() => undefined);

function useToast() {
  return useContext(ToastContext);
}

type AuthContextValue = { user: AuthUser };
const AuthContext = createContext<AuthContextValue | null>(null);

function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside the authenticated application.");
  return context;
}

function App() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.me().then(setUser).catch(() => setUser(null)).finally(() => setLoading(false));
    const handleExpiredSession = () => setUser(null);
    window.addEventListener("documind:session-expired", handleExpiredSession);
    return () => window.removeEventListener("documind:session-expired", handleExpiredSession);
  }, []);

  return (
    <BrowserRouter>
      {loading ? <AuthLoading /> : user ? (
        <AuthContext.Provider value={{ user }}>
          <AppShell onLogout={async () => { try { await api.logout(); } finally { setUser(null); } }}>
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/documents" element={<DocumentsPage />} />
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/chat/:conversationId" element={<ChatPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </AppShell>
        </AuthContext.Provider>
      ) : (
        <Routes>
          <Route path="/login" element={<LoginPage onAuthenticated={setUser} />} />
          <Route path="/register" element={<RegisterPage onAuthenticated={setUser} />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      )}
    </BrowserRouter>
  );
}

function AuthLoading() {
  return <div className="auth-loading"><Brand /><span>Loading your workspace</span></div>;
}

function AuthLayout({ children, eyebrow, title, subtitle }: { children: ReactNode; eyebrow: string; title: string; subtitle: string }) {
  return (
    <div className="auth-layout">
      <div className="auth-side"><Brand /><div className="auth-side-copy"><span className="eyebrow eyebrow-light">Private document intelligence</span><h1>Turn your knowledge base into a place you can think.</h1><p>DocuMind keeps the source in view while you work through the answer.</p></div><div className="auth-side-foot"><ShieldCheck size={15} /> Evidence-backed by design</div></div>
      <main className="auth-main"><div className="auth-card"><div className="mobile-auth-brand"><Brand /></div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2><p className="auth-subtitle">{subtitle}</p>{children}<p className="auth-security"><ShieldCheck size={14} /> Your session is protected with HttpOnly cookies.</p></div></main>
    </div>
  );
}

function LoginPage({ onAuthenticated }: { onAuthenticated: (user: AuthUser) => void }) {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try { const user = await api.login(email, password); onAuthenticated(user); navigate("/", { replace: true }); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Unable to sign in."); }
    finally { setSubmitting(false); }
  }

  return <AuthLayout eyebrow="Welcome back" title="Your documents, in focus." subtitle="Sign in to continue your private research workspace."><form className="auth-form" onSubmit={(event) => void submit(event)}><label>Email<input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label><label>Password<input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>{error && <InlineNotice message={error} />}<button className="button button-primary button-wide" disabled={submitting}>{submitting ? "Signing in..." : "Sign in"}<ArrowUpRight size={16} /></button></form><p className="auth-switch">New to DocuMind? <NavLink to="/register">Create an account</NavLink></p></AuthLayout>;
}

function RegisterPage({ onAuthenticated }: { onAuthenticated: (user: AuthUser) => void }) {
  const navigate = useNavigate();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try { const user = await api.register(email, password, displayName); onAuthenticated(user); navigate("/", { replace: true }); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Unable to create your account."); }
    finally { setSubmitting(false); }
  }

  return <AuthLayout eyebrow="Create your workspace" title="A clearer way to work with sources." subtitle="Keep documents, conversations, and evidence in one secure workspace."><form className="auth-form" onSubmit={(event) => void submit(event)}><label>Name<input type="text" autoComplete="name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} required /></label><label>Email<input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label><label>Password<input type="password" autoComplete="new-password" minLength={8} value={password} onChange={(event) => setPassword(event.target.value)} required /><small>8–128 characters</small></label>{error && <InlineNotice message={error} />}<button className="button button-primary button-wide" disabled={submitting}>{submitting ? "Creating account..." : "Create account"}<ArrowUpRight size={16} /></button></form><p className="auth-switch">Already have an account? <NavLink to="/login">Sign in</NavLink></p></AuthLayout>;
}

function AppShell({ children, onLogout }: { children: ReactNode; onLogout: () => Promise<void> }) {
  const { user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [search, setSearch] = useState("");
  const { documents } = useDocuments();
  const { conversations, refresh: refreshConversations } = useConversations();

  const notify = useCallback((toast: ToastInput) => {
    const id = Date.now() + Math.floor(Math.random() * 1000);
    setToasts((current) => [...current, { ...toast, id }]);
    window.setTimeout(() => setToasts((current) => current.filter((item) => item.id !== id)), 4500);
  }, []);

  useEffect(() => { setSearch(new URLSearchParams(location.search).get("search") ?? ""); }, [location.search]);
  useEffect(() => {
    const handler = () => void refreshConversations();
    window.addEventListener("documind:conversations-updated", handler);
    return () => window.removeEventListener("documind:conversations-updated", handler);
  }, [refreshConversations]);

  const initials = user.display_name.split(" ").map((part) => part[0]).join("").slice(0, 2).toUpperCase();
  const pageName = location.pathname.startsWith("/documents") ? "Documents" : location.pathname.startsWith("/chat") ? "Conversations" : "Overview";

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    const value = search.trim();
    navigate(value ? `/documents?search=${encodeURIComponent(value)}` : "/documents");
  }

  return (
    <ToastContext.Provider value={notify}>
      <div className="app-shell">
        <aside className={`app-sidebar ${sidebarOpen ? "app-sidebar-open" : ""}`}>
          <div className="sidebar-top"><NavLink to="/" className="brand-link" onClick={() => setSidebarOpen(false)}><Brand /></NavLink><IconButton label="Close navigation" className="mobile-only" onClick={() => setSidebarOpen(false)}><X size={18} /></IconButton></div>
          <div className="workspace-pill"><span className="workspace-pulse" /><span>Personal workspace</span><MoreHorizontal size={15} /></div>
          <nav className="sidebar-nav" aria-label="Primary navigation">{navItems.map(({ label, to, icon: Icon, end }) => <NavLink key={label} to={to} end={end} onClick={() => setSidebarOpen(false)} className={({ isActive }) => `sidebar-nav-item ${isActive ? "sidebar-nav-item-active" : ""}`}><Icon size={17} /><span>{label}</span>{label === "Documents" && <em>{documents.length}</em>}</NavLink>)}</nav>
          <div className="sidebar-section"><div className="sidebar-section-heading"><span>Recent conversations</span><NavLink to="/chat" aria-label="Start a new conversation"><Plus size={14} /></NavLink></div>{conversations.length ? conversations.slice(0, 5).map((conversation) => <NavLink key={conversation.id} to={`/chat/${conversation.id}`} onClick={() => setSidebarOpen(false)} className="sidebar-conversation"><MessageSquare size={14} /><span title={conversation.title}>{conversation.title}</span></NavLink>) : <p className="sidebar-muted">Your saved threads will appear here.</p>}</div>
          <div className="sidebar-bottom"><div className="sidebar-trust"><ShieldCheck size={15} /><span>Private by default</span></div><div className="profile-row"><span className="avatar">{initials}</span><span className="profile-copy"><strong>{user.display_name}</strong><small>{user.email}</small></span><IconButton label="Open account menu" onClick={() => setAccountOpen((current) => !current)}><MoreHorizontal size={16} /></IconButton></div>{accountOpen && <div className="account-menu"><div><strong>{user.display_name}</strong><span>{user.email}</span></div><button type="button" onClick={() => void onLogout()}><LogOut size={15} /> Sign out</button></div>}</div>
        </aside>
        {sidebarOpen && <button className="sidebar-overlay" type="button" aria-label="Close navigation" onClick={() => setSidebarOpen(false)} />}
        <main className="main-content">
          <header className="app-header"><IconButton label="Open navigation" className="mobile-only" onClick={() => setSidebarOpen(true)}><Menu size={19} /></IconButton><div className="breadcrumb"><span>Workspace</span><ChevronRight size={14} /><strong>{pageName}</strong></div><form className="global-search" onSubmit={submitSearch}><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search documents" aria-label="Search documents" /><kbd>⌘ K</kbd></form><div className="header-actions"><span className="connection-status"><span /> Connected</span><button type="button" className="header-avatar" onClick={() => setAccountOpen((current) => !current)}>{initials}</button></div></header>
          {children}
        </main>
        <ToastStack toasts={toasts} onDismiss={(id) => setToasts((current) => current.filter((toast) => toast.id !== id))} />
      </div>
    </ToastContext.Provider>
  );
}

function useDocuments() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const refresh = useCallback(() => {
    setLoading(true);
    return api.listDocuments().then((items) => { setDocuments(items); setError(""); return items; }).catch((requestError) => { setError(requestError instanceof Error ? requestError.message : "Documents could not be loaded."); throw requestError; }).finally(() => setLoading(false));
  }, []);
  useEffect(() => { void refresh().catch(() => undefined); }, [refresh]);
  useEffect(() => {
    if (!documents.some((document) => document.status === "PENDING" || document.status === "PROCESSING")) return;
    const timer = window.setInterval(() => { void api.listDocuments().then(setDocuments).catch(() => undefined); }, 2500);
    return () => window.clearInterval(timer);
  }, [documents]);
  return { documents, loading, error, refresh };
}

function useConversations() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const refresh = useCallback(() => {
    setLoading(true);
    return api.listConversations().then((items) => { setConversations(items); setError(""); return items; }).catch((requestError) => { setError(requestError instanceof Error ? requestError.message : "Conversations could not be loaded."); throw requestError; }).finally(() => setLoading(false));
  }, []);
  useEffect(() => { void refresh().catch(() => undefined); }, [refresh]);
  return { conversations, loading, error, refresh };
}

function useDocumentPreview() {
  const [document, setDocument] = useState<Document | null>(null);
  const [chunks, setChunks] = useState<DocumentChunk[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedChunkId, setSelectedChunkId] = useState<number | null>(null);
  async function openPreview(target: Document, chunkId: number | null = null) {
    setDocument(target);
    setChunks([]);
    setError("");
    setSelectedChunkId(chunkId);
    setLoading(true);
    try { setChunks(await api.listDocumentChunks(target.id)); }
    catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "The source preview could not be loaded.";
      setError(message);
      throw requestError;
    }
    finally { setLoading(false); }
  }
  return { document, chunks, loading, error, selectedChunkId, openPreview, closePreview: () => { setDocument(null); setError(""); setSelectedChunkId(null); } };
}

function DashboardPage() {
  const notify = useToast();
  const { documents, loading, error, refresh } = useDocuments();
  const { conversations } = useConversations();
  const [uploadError, setUploadError] = useState("");
  const upload = (file: File, onProgress?: (progress: number) => void) => api.uploadDocument(file, onProgress);
  const readyCount = documents.filter((document) => document.status === "READY").length;
  const onComplete = (result: UploadResult) => { void refresh().catch(() => undefined); notify({ tone: result.duplicate ? "info" : "success", title: result.duplicate ? "Document already in your library" : "Document uploaded", message: result.duplicate ? result.document.name : `${result.document.name} is queued for indexing.` }); };
  const onError = (message: string) => { setUploadError(message); notify({ tone: "error", title: "Upload failed", message }); };
  return <div className="page-container"><div className="page-heading"><div><span className="eyebrow">Overview</span><h1>Your workspace</h1><p>Manage your documents and explore information across your knowledge base.</p></div><UploadButton onUpload={upload} onComplete={onComplete} onError={onError} /></div>{uploadError && <InlineNotice message={uploadError} />}{error && <InlineNotice message={error} />}<section className="metrics-strip" aria-label="Workspace summary"><div><span>Documents</span><strong>{loading ? "—" : documents.length}</strong></div><div><span>Ready to explore</span><strong>{loading ? "—" : readyCount}</strong></div><div><span>Conversations</span><strong>{conversations.length}</strong></div><div><span>Library size</span><strong>{loading ? "—" : formatBytes(documents.reduce((total, document) => total + document.size_bytes, 0))}</strong></div></section><section className="upload-card"><div className="section-heading"><div><span className="eyebrow">Add to your knowledge base</span><h2>Upload documents</h2><p>Bring in the sources you want to search and reason over.</p></div><span className="upload-card-mark"><UploadCloud size={19} /></span></div><DocumentUploadZone onUpload={upload} onComplete={onComplete} onError={onError} /></section><div className="overview-grid"><section className="surface-panel"><div className="section-heading section-heading-row"><div><span className="eyebrow">Library</span><h2>Recent documents</h2></div><NavLink className="text-link" to="/documents">View library <ArrowUpRight size={14} /></NavLink></div>{loading ? <LoadingRows count={4} /> : documents.length ? <DocumentList documents={documents.slice(0, 5)} compact /> : <EmptyState icon={<Files size={20} />} title="Your library is empty" description="Upload a source to begin building your private knowledge base." action={<UploadButton onUpload={upload} onComplete={onComplete} onError={onError} label="Upload a document" />} />}</section><section className="surface-panel"><div className="section-heading section-heading-row"><div><span className="eyebrow">History</span><h2>Recent conversations</h2></div><NavLink className="text-link" to="/chat">Open chat <ArrowUpRight size={14} /></NavLink></div>{conversations.length ? <div className="conversation-list">{conversations.slice(0, 5).map((conversation) => <NavLink to={`/chat/${conversation.id}`} key={conversation.id}><ConversationPreview title={conversation.title} updatedAt={conversation.updated_at} messageCount={conversation.message_count} /></NavLink>)}</div> : <EmptyState icon={<MessageSquare size={20} />} title="No conversations yet" description="Ask your first question once a document is ready." />}</section></div></div>;
}

function DocumentsPage() {
  const notify = useToast();
  const { documents, loading, error, refresh } = useDocuments();
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState(searchParams.get("search") ?? "");
  const [type, setType] = useState("all");
  const [status, setStatus] = useState("all");
  const [sort, setSort] = useState("newest");
  const [uploadError, setUploadError] = useState("");
  const preview = useDocumentPreview();
  const filtered = useMemo(() => documents.filter((document) => document.name.toLowerCase().includes(query.toLowerCase().trim()) && (type === "all" || documentExtension(document) === type) && (status === "all" || document.status === status)).sort((first, second) => { if (sort === "name") return first.name.localeCompare(second.name); const firstTime = new Date(first.uploaded_at ?? first.created_at).getTime(); const secondTime = new Date(second.uploaded_at ?? second.created_at).getTime(); return sort === "oldest" ? firstTime - secondTime : secondTime - firstTime; }), [documents, query, sort, status, type]);
  const upload = (file: File, onProgress?: (progress: number) => void) => api.uploadDocument(file, onProgress);
  const onComplete = (result: UploadResult) => { void refresh().catch(() => undefined); notify({ tone: result.duplicate ? "info" : "success", title: result.duplicate ? "Document already in your library" : "Document uploaded", message: result.document.name }); };
  const onError = (message: string) => { setUploadError(message); notify({ tone: "error", title: "Upload failed", message }); };
  const updateQuery = (value: string) => { setQuery(value); const next = new URLSearchParams(searchParams); if (value) next.set("search", value); else next.delete("search"); setSearchParams(next, { replace: true }); };
  async function deleteDocument(document: Document) { if (!window.confirm(`Remove ${document.name} from your library?`)) return; try { await api.deleteDocument(document.id); await refresh(); notify({ tone: "success", title: "Document removed", message: document.name }); } catch (requestError) { const message = requestError instanceof Error ? requestError.message : "The document could not be removed."; setUploadError(message); notify({ tone: "error", title: "Could not remove document", message }); } }
  return <div className="page-container"><div className="page-heading"><div><span className="eyebrow">Knowledge base</span><h1>Document library</h1><p>Search, inspect, and manage the sources behind your answers.</p></div><UploadButton onUpload={upload} onComplete={onComplete} onError={onError} /></div>{uploadError && <InlineNotice message={uploadError} />}{error && <InlineNotice message={error} />}<section className="surface-panel library-panel"><div className="library-toolbar"><div><span className="eyebrow">All sources</span><h2>{documents.length} document{documents.length === 1 ? "" : "s"}</h2></div><DocumentFilters query={query} onQueryChange={updateQuery} type={type} onTypeChange={setType} status={status} onStatusChange={setStatus} sort={sort} onSortChange={setSort} /></div>{loading ? <LoadingRows count={6} /> : filtered.length ? <DocumentTable documents={filtered} onDelete={deleteDocument} onPreview={(document) => { void preview.openPreview(document).catch(() => notify({ tone: "error", title: "Could not load source preview" })); }} /> : <EmptyState icon={<Search size={20} />} title="No matching documents" description={documents.length ? "Try a different search or clear one of the filters." : "Upload your first source to begin exploring your knowledge base."} action={!documents.length ? <UploadButton onUpload={upload} onComplete={onComplete} onError={onError} label="Upload a document" /> : undefined} />}</section>{preview.document && <DocumentPreviewPanel document={preview.document} chunks={preview.chunks} loading={preview.loading} error={preview.error} selectedChunkId={preview.selectedChunkId} onClose={preview.closePreview} />}</div>;
}

function ChatPage() {
  const { conversationId } = useParams<{ conversationId: string }>();
  const navigate = useNavigate();
  const notify = useToast();
  const { documents } = useDocuments();
  const { conversations, refresh: refreshConversations } = useConversations();
  const [messages, setMessages] = useState<Message[]>([]);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [selectedDocIds, setSelectedDocIds] = useState<string[] | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sourceOpen, setSourceOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const preview = useDocumentPreview();
  const ready = readyDocuments(documents);
  const latestCitations = [...messages].reverse().find((message) => message.role === "assistant" && message.citations.length > 0)?.citations ?? [];
  const selectedCount = selectedDocIds === null ? ready.length : selectedDocIds.length;

  useEffect(() => { let active = true; setError(""); if (!conversationId) { setMessages([welcomeMessage]); setSelectedDocIds(null); setMessagesLoading(false); return () => { active = false; }; } setMessagesLoading(true); setMessages([]); setSelectedDocIds(null); api.listMessages(conversationId).then((items) => { if (!active) return; setMessages(items); const latestUserMessage = [...items].reverse().find((message) => message.role === "user"); setSelectedDocIds(latestUserMessage?.document_ids ?? null); }).catch((requestError) => { if (active) setError(requestError instanceof Error ? requestError.message : "This conversation could not be loaded."); }).finally(() => { if (active) setMessagesLoading(false); }); return () => { active = false; }; }, [conversationId]);
  useEffect(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" }); }, [messages, busy]);
  useEffect(() => {
    const handleCitationOpen = (event: Event) => {
      const citation = (event as CustomEvent<Citation>).detail;
      if (citation) openCitation(citation);
    };
    window.addEventListener("documind:open-citation", handleCitationOpen);
    return () => window.removeEventListener("documind:open-citation", handleCitationOpen);
  }, [documents]);

  function toggleDocument(id: string) { if (!ready.some((document) => document.id === id)) return; const readyIds = ready.map((document) => document.id); if (selectedDocIds === null) { setSelectedDocIds(readyIds.filter((documentId) => documentId !== id)); return; } const next = selectedDocIds.includes(id) ? selectedDocIds.filter((documentId) => documentId !== id) : [...selectedDocIds, id]; setSelectedDocIds(next.length === readyIds.length ? null : next); }
  async function submitQuestion() { const content = input.trim(); if (!content || busy) return; setInput(""); setError(""); setBusy(true); const selected = selectedDocIds === null ? null : selectedDocIds.filter((id) => ready.some((document) => document.id === id)); const optimisticId = -Date.now(); setMessages((current) => [...current, { id: optimisticId, role: "user", content, citations: [], document_ids: selected, created_at: new Date().toISOString() }]); try { let activeId = conversationId; if (!activeId) { const initial = await api.createConversationWithMessage(content, selected); activeId = initial.conversation.id; setMessages((current) => [...current.filter((message) => message.id !== optimisticId), ...initial.messages]); } else { const response = await api.sendMessage(activeId, content, selected); setMessages((current) => [...current.filter((message) => message.id !== optimisticId), response.user_message, response.assistant_message]); } await refreshConversations().catch(() => undefined); window.dispatchEvent(new Event("documind:conversations-updated")); if (!conversationId) navigate(`/chat/${activeId}`, { replace: true }); } catch (requestError) { setMessages((current) => current.filter((message) => message.id !== optimisticId)); setError(requestError instanceof Error ? requestError.message : "The assistant could not answer right now."); } finally { setBusy(false); } }
  async function openPreview(document: Document, chunkId: number | null = null) { try { await preview.openPreview(document, chunkId); } catch { notify({ tone: "error", title: "Could not load source preview" }); } }
  function openCitation(citation: Citation) { const document = documents.find((item) => item.id === citation.document_id); if (!document) { notify({ tone: "error", title: "Source is no longer available" }); return; } void openPreview(document, citation.chunk_id); }

  return <div className="chat-page page-container"><div className="chat-heading page-heading"><div><span className="eyebrow">Research workspace</span><h1>{conversationId ? conversations.find((conversation) => conversation.id === conversationId)?.title ?? "Conversation" : "Ask your knowledge base"}</h1><p>Ask focused questions and keep the evidence close to the answer.</p></div><div className="chat-heading-actions"><button className="button button-secondary mobile-source-button" type="button" onClick={() => setSourceOpen(true)}><PanelRightOpen size={15} /> Sources</button><button className="button button-secondary" type="button" onClick={() => navigate("/chat")}><Plus size={15} /> New conversation</button></div></div><div className="chat-layout"><section className="chat-surface"><div className="chat-surface-head"><div><span className="chat-surface-label"><span className="live-dot" /> Grounded conversation</span><span className="chat-surface-note">{selectedDocIds === null ? "Searching all ready sources" : `Searching ${selectedCount} selected source${selectedCount === 1 ? "" : "s"}`}</span></div><IconButton label="Toggle source panel" className="desktop-source-button" onClick={() => setSourceOpen((current) => !current)}><PanelLeftClose size={17} /></IconButton></div><div className="chat-scroll" ref={scrollRef}>{messagesLoading ? <LoadingRows count={3} /> : messages.map((message) => <ChatMessage key={message.id} message={message} onCopyCitation={() => notify({ tone: "success", title: "Citation copied" })} />)}{busy && <div className="typing-row"><span className="message-avatar message-avatar-assistant"><Sparkles size={15} /></span><div className="typing-indicator"><span /><span /><span /></div></div>}</div>{error && <div className="chat-error"><InlineNotice message={error} /></div>}<ChatComposer value={input} onChange={setInput} onSubmit={() => void submitQuestion()} busy={busy} selectedCount={selectedCount} allSources={selectedDocIds === null} onOpenSources={() => setSourceOpen(true)} /></section><SourcePanel documents={documents} selectedDocIds={selectedDocIds} citations={latestCitations} open={sourceOpen} onClose={() => setSourceOpen(false)} onToggle={toggleDocument} onPreview={(document) => void openPreview(document)} /></div>{preview.document && <DocumentPreviewPanel document={preview.document} chunks={preview.chunks} loading={preview.loading} error={preview.error} selectedChunkId={preview.selectedChunkId} onClose={preview.closePreview} />}</div>;
}

const welcomeMessage: Message = { id: 0, role: "assistant", content: "Welcome to your research workspace. Select the sources you want to use, then ask a question. I’ll keep the answer grounded in the documents you choose.", citations: [], document_ids: null, created_at: new Date().toISOString() };

export default App;
