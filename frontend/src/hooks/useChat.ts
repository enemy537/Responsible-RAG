'use client';

import { useCallback } from 'react';
import { useChatStore } from '@/stores/chatStore';
import { useConsentStore } from '@/stores/consentStore';
import { api, type ChatResponseDTO } from '@/lib/api';
import { isQuotaError } from '@/lib/errors';
import {
  toCitation,
  toConversation,
  toConversationSummary,
  toMessage,
} from '@/lib/mappers/chat';

const TITLE_PREVIEW_LENGTH = 50;
const LAST_MESSAGE_PREVIEW_LENGTH = 100;

const QUOTA_ERROR_MESSAGE =
  'The document search engine is temporarily unavailable due to an API quota limit. ' +
  "I can still answer from my general knowledge, but responses won't include citations " +
  'to specific sources. Please try again later for source-grounded answers.';

export function useChat() {
  const chatStore = useChatStore();
  const consentStore = useConsentStore();

  const activeConversation = chatStore.conversations.find(
    (c) => c.id === chatStore.activeConversationId
  );

  /** Send a message to the RAG backend and store the response. */
  const sendMessage = useCallback(
    async (content: string): Promise<void> => {
      const store = useChatStore.getState();
      let convId = store.activeConversationId;

      // Auto-create a conversation if none is active
      if (!convId) {
        try {
          const conv = await api.conversations.create({});
          store.addConversation({
            ...toConversation(conv),
            lastMessage: content.slice(0, LAST_MESSAGE_PREVIEW_LENGTH),
            lastMessageAt: new Date().toISOString(),
          });
          store.setActiveConversationId(conv.id);
          convId = conv.id;
        } catch (err) {
          console.error('Failed to create conversation', err);
          return;
        }
      }

      // Add the user message locally (optimistic)
      store.addMessage({
        id: `msg-${Date.now()}`,
        conversationId: convId,
        role: 'user',
        content,
        citations: [],
        createdAt: new Date().toISOString(),
      });

      // Update the conversation title from the first message
      const conv = store.conversations.find((c) => c.id === convId);
      if (conv && conv.title === 'New conversation') {
        store.renameConversation(
          convId,
          content.slice(0, TITLE_PREVIEW_LENGTH) +
            (content.length > TITLE_PREVIEW_LENGTH ? '…' : '')
        );
      }

      store.setStreaming(true);
      try {
        const result: ChatResponseDTO = await api.chat.send({
          question: content,
          conversation_id: convId,
          profile_key: consentStore.profileMode?.toLowerCase() ?? null,
        });

        store.addMessage({
          id: result.message_id,
          conversationId: result.conversation_id,
          role: 'assistant',
          content: result.answer,
          citations: result.sources.map(toCitation),
          createdAt: new Date().toISOString(),
        });
      } catch (err) {
        console.error('Chat API error', err);
        store.addMessage({
          id: `msg-${Date.now() + 1}`,
          conversationId: convId,
          role: 'assistant',
          content: isQuotaError(err)
            ? QUOTA_ERROR_MESSAGE
            : 'Sorry, something went wrong. Please try again.',
          citations: [],
          createdAt: new Date().toISOString(),
        });
      } finally {
        store.setStreaming(false);
      }
    },
    [consentStore.profileMode]
  );

  /** Load the conversation list into the store. */
  const loadConversations = useCallback(async () => {
    try {
      const res = await api.conversations.list();
      chatStore.setConversations(res.conversations.map(toConversationSummary));
    } catch (err) {
      console.error('Failed to load conversations', err);
    }
  }, [chatStore]);

  /** Load the messages of one conversation into the store. */
  const loadMessages = useCallback(
    async (conversationId: string) => {
      try {
        const conv = await api.conversations.get(conversationId);
        chatStore.setMessages(conv.messages.map(toMessage));
      } catch (err) {
        console.error('Failed to load messages', err);
      }
    },
    [chatStore]
  );

  return {
    ...chatStore,
    activeConversation,
    privacyMode: consentStore.profileMode,
    /** Send a message and get a RAG response. */
    sendMessage,
    /** Fetch the conversation list from the backend. */
    loadConversations,
    /** Fetch the messages of a conversation. */
    loadMessages,
  };
}
