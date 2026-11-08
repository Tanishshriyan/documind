import type { AuthUser, ChatResponse, Conversation, ConversationWithMessagesResponse, Document, DocumentChunk, Message, UploadResult } from "../types";

const API_BASE = import.meta.env.VITE_API_URL ?? "/api/v1";
const CSRF_COOKIE = "documind_csrf";
let csrfRequest: Promise<void> | null = null;

function readCookie(name: string): string | null {
  const match = document.cookie.split("; ").find((item) => item.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

async function ensureCsrfCookie(): Promise<void> {
  if (readCookie(CSRF_COOKIE)) return;
  if (!csrfRequest) {
    csrfRequest = fetch(`${API_BASE}/auth/csrf`, { credentials: "include" })
      .then((response) => {
        if (!response.ok) throw new Error("Could not initialize the security session.");
      })
      .finally(() => { csrfRequest = null; });
  }
  await csrfRequest;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const method = (options?.method ?? "GET").toUpperCase();
  const headers = new Headers(options?.headers);
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    await ensureCsrfCookie();
    const csrfToken = readCookie(CSRF_COOKIE);
    if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers, credentials: "include" });
  if (response.status === 401) {
    window.dispatchEvent(new Event("documind:session-expired"));
  }
  if (!response.ok) {
    let detail = "Something went wrong. Please try again.";
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail ?? detail;
    } catch {
      // Keep the safe fallback when the server does not return JSON.
    }
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  me: () => request<AuthUser>("/auth/me"),
  register: (email: string, password: string, displayName: string) => request<AuthUser>("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, display_name: displayName }),
  }),
  login: (email: string, password: string) => request<AuthUser>("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  listDocuments: (page = 1, pageSize = 100) => request<Document[]>(`/documents?page=${page}&page_size=${pageSize}`),
  uploadDocument: (file: File, onProgress?: (progress: number) => void) => new Promise<UploadResult>(async (resolve, reject) => {
    try {
      await ensureCsrfCookie();
      const csrfToken = readCookie(CSRF_COOKIE);
      const form = new FormData();
      form.append("file", file);
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_BASE}/documents/upload`);
      xhr.withCredentials = true;
      if (csrfToken) xhr.setRequestHeader("X-CSRF-Token", csrfToken);
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100));
      };
      xhr.onload = () => {
        let payload: { detail?: string } & Partial<Document>;
        try { payload = JSON.parse(xhr.responseText) as typeof payload; } catch { payload = {}; }
        if (xhr.status === 401) window.dispatchEvent(new Event("documind:session-expired"));
        if (xhr.status >= 200 && xhr.status < 300) resolve({
          document: payload as Document,
          duplicate: xhr.getResponseHeader("X-Documind-Duplicate") === "true",
        });
        else reject(new Error(payload.detail ?? "The document could not be uploaded."));
      };
      xhr.onerror = () => reject(new Error("The document upload failed. Check your connection and try again."));
      xhr.send(form);
    } catch (error) { reject(error); }
  }),
  deleteDocument: (id: string) => request<void>(`/documents/${id}`, { method: "DELETE" }),
  listDocumentChunks: (id: string) => request<DocumentChunk[]>(`/documents/${id}/chunks`),
  listConversations: () => request<Conversation[]>("/conversations"),
  createConversation: (title = "New conversation") => request<Conversation>("/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  }),
  createConversationWithMessage: (content: string, documentIds: string[] | null) => request<ConversationWithMessagesResponse>("/conversations/with-message", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, document_ids: documentIds }),
  }),
  listMessages: (id: string) => request<Message[]>(`/conversations/${id}/messages`),
  sendMessage: (id: string, content: string, documentIds: string[] | null) => request<ChatResponse>(`/conversations/${id}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, document_ids: documentIds }),
  }),
};

