/**
 * Maps backend DTOs onto the frontend domain models.
 *
 * Keeping this in one place means every code path (fresh responses and
 * reloaded conversations) produces identical `Message`/`Citation` shapes.
 */

import type {
  CitationDTO,
  ConversationListItemDTO,
  ConversationResponseDTO,
  MessageDTO,
} from '@/lib/api';
import type { Citation, Conversation, Message } from '@/types/chat';
import type { ContentSensitivity, Source, SourceType } from '@/types/source';

/** Build a `Source` from citation metadata returned by the API. */
export function toSource(dto: CitationDTO): Source {
  return {
    id: dto.source_id,
    title: dto.source_title,
    type: dto.source_type as SourceType,
    authors: dto.authors ?? [],
    publicationDate: dto.publication_date ?? null,
    publisher: dto.publisher ?? null,
    url: dto.url || '',
    doi: dto.doi || null,
    language: dto.language ?? null,
    description: dto.description ?? null,
    tags: dto.tags ?? [],
    contentSensitivity: (dto.content_sensitivity as ContentSensitivity) ?? 'low',
    internalNotes: null,
    status: 'indexed',
    errorMessage: null,
    chunkCount: 0,
  };
}

export function toCitation(dto: CitationDTO): Citation {
  return {
    id: dto.id,
    sourceId: dto.source_id,
    source: toSource(dto),
    excerpt: dto.excerpt,
    number: dto.number,
  };
}

export function toMessage(dto: MessageDTO): Message {
  return {
    id: dto.id,
    conversationId: dto.conversation_id,
    role: dto.role,
    content: dto.content,
    citations: (dto.citations ?? []).map(toCitation),
    createdAt: dto.created_at,
    isStreaming: dto.is_streaming ?? false,
  };
}

/** Map a conversation list entry onto the sidebar model. */
export function toConversationSummary(dto: ConversationListItemDTO): Conversation {
  return {
    id: dto.id,
    title: dto.title,
    lastMessage: dto.last_message ?? null,
    lastMessageAt: dto.last_message_at ?? dto.created_at,
    createdAt: dto.created_at,
    messageCount: dto.message_count,
  };
}

/** Map a created/fetched conversation onto the sidebar model. */
export function toConversation(dto: ConversationResponseDTO): Conversation {
  return {
    id: dto.id,
    title: dto.title,
    lastMessage: null,
    lastMessageAt: dto.updated_at || dto.created_at,
    createdAt: dto.created_at,
    messageCount: dto.message_count,
  };
}
