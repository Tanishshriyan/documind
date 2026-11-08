export type DocumentStatus = "PENDING" | "PROCESSING" | "READY" | "FAILED";

export type Document = {
  id: string;
  name: string;
  original_name: string;
  content_type: string;
  size_bytes: number;
  page_count: number;
  char_count: number;
  status: DocumentStatus;
  error_message: string | null;
  failure_reason: string | null;
  uploaded_at: string | null;
  processing_started_at: string | null;
  processing_completed_at: string | null;
  created_at: string;
  updated_at: string;
  chunk_count: number;
};

export type DocumentChunk = {
  id: number;
  document_id: string;
  document_name: string;
  chunk_index: number;
  page_number: number | null;
  content: string;
};

export type Citation = {
  chunk_id: number | null;
  source_label: string | null;
  document_id: string;
  document_name: string;
  page_number: number | null;
  excerpt: string;
  relevance: number;
};

export type Message = {
  id: number;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  document_ids: string[] | null;
  created_at: string;
};

export type Conversation = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
};

export type AuthUser = {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  created_at: string;
};

export type ChatResponse = {
  user_message: Message;
  assistant_message: Message;
};

export type ConversationWithMessagesResponse = {
  conversation: Conversation;
  messages: Message[];
};

export type UploadResult = {
  document: Document;
  duplicate: boolean;
};

