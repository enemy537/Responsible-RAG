/** Chat, conversation, and citation DTOs (mirroring the backend schemas). */

export interface CitationDTO {
  id: string;
  source_id: string;
  source_title: string;
  source_type: string;
  authors: string[];
  publication_date: string | null;
  publisher: string | null;
  url: string;
  doi: string;
  language: string | null;
  description: string | null;
  tags: string[];
  content_sensitivity: string;
  excerpt: string;
  number: number;
}

export interface ChatRequestDTO {
  question: string;
  conversation_id?: string | null;
  profile_key?: string | null;
}

export interface ChatResponseDTO {
  answer: string;
  sources: CitationDTO[];
  conversation_id: string;
  message_id: string;
  profile_key?: string | null;
}

export interface MessageDTO {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant';
  content: string;
  citations: CitationDTO[];
  is_streaming: boolean;
  created_at: string;
}

export interface ConversationListItemDTO {
  id: string;
  title: string;
  last_message?: string | null;
  last_message_at?: string | null;
  created_at: string;
  message_count: number;
}

export interface ConversationListResponseDTO {
  conversations: ConversationListItemDTO[];
  total: number;
  page: number;
  limit: number;
}

export interface CreateConversationDTO {
  title?: string | null;
  profile_key?: string | null;
}

export interface ConversationResponseDTO {
  id: string;
  title: string;
  profile_key?: string | null;
  messages: MessageDTO[];
  message_count: number;
  created_at: string;
  updated_at: string;
}
