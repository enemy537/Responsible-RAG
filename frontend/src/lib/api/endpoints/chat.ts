/** Chat (RAG) and conversation endpoints. */

import { apiRequest } from '../client';
import type {
  ChatRequestDTO,
  ChatResponseDTO,
  ConversationListResponseDTO,
  ConversationResponseDTO,
  CreateConversationDTO,
} from '../types/chat';

export const chatEndpoints = {
  /** Send a question and receive a RAG answer with citations. */
  send: (body: ChatRequestDTO) =>
    apiRequest<ChatResponseDTO>('POST', '/chat', body),
};

export const conversationEndpoints = {
  /** List the current user's conversations. */
  list: (page = 1, limit = 20) =>
    apiRequest<ConversationListResponseDTO>(
      'GET',
      `/chat/conversations?page=${page}&limit=${limit}`,
    ),

  /** Create an empty conversation. */
  create: (body: CreateConversationDTO = {}) =>
    apiRequest<ConversationResponseDTO>('POST', '/chat/conversations', body),

  /** Get a conversation with all of its messages. */
  get: (id: string) =>
    apiRequest<ConversationResponseDTO>('GET', `/chat/conversations/${id}`),

  /** Rename a conversation. */
  rename: (id: string, title: string) =>
    apiRequest<ConversationResponseDTO>('PUT', `/chat/conversations/${id}`, {
      title,
    }),

  /** Delete a conversation and its messages. */
  delete: (id: string) =>
    apiRequest<{ status: string }>('DELETE', `/chat/conversations/${id}`),
};

export const healthEndpoints = {
  /** Backend liveness probe. */
  ping: () => apiRequest<{ status: string }>('GET', '/health'),
};
