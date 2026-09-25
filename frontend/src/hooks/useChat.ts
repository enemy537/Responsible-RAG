'use client';

import { useCallback } from 'react';
import { useChatStore } from '@/stores/chatStore';
import { useConsentStore } from '@/stores/consentStore';
import { api, type ChatResponseDTO } from '@/lib/api';
import { describeChatError, isStaleConversationError } from '@/lib/errors';
import {
  toCitation,
  toConversation,
  toConversationSummary,
  toMessage,
} from '@/lib/mappers/chat';

const TITLE_PREVIEW_LENGTH = 50;
const LAST_MESSAGE_PREVIEW_LENGTH = 100;

export function useChat() {
  const chatStore = useChatStore();
  const consentStore = useConsentStore();

  const activeConversation = chatStore.conversations.find(
    (c) => c.id === chatStore.activeConversationId
  );

  /** Create a conversation, add it to the store and make it active. */
  const startConversation = useCallback(async (preview: string): Promise<string | null> => {
    try {
      const conv = await api.conversations.create({});
      const store = useChatStore.getState();
      store.addConversation({
        ...toConversation(conv),
        lastMessage: preview.slice(0, LAST_MESSAGE_PREVIEW_LENGTH),
        lastMessageAt: new Date().toISOString(),
      });
      store.setActiveConversationId(conv.id);
      return conv.id;
    } catch (err) {
      console.error('Failed to create conversation', err);
      return null;
    }
  }, []);

  /** Show the user's message immediately, before the backend answers. */
  const addUserMessage = useCallback((conversationId: string, content: string) => {
    useChatStore.getState().addMessage({
      id: `msg-user-${Date.now()}`,
      conversationId,
      role: 'user',
      content,
      citations: [],
      createdAt: new Date().toISOString(),
    });
  }, []);

  /** Ask the RAG backend one question inside an existing conversation. */
  const ask = useCallback(
    (question: string, conversationId: string) =>
      api.chat.send({
        question,
        conversation_id: conversationId,
        profile_key: consentStore.profileMode?.toLowerCase() ?? null,
      }),
    [consentStore.profileMode]
  );

  /** Send a message to the RAG backend and store the response. */
  const sendMessage = useCallback(
    async (content: string): Promise<void> => {
      let convId = useChatStore.getState().activeConversationId;

      // Auto-create a conversation if none is active
      if (!convId) {
        convId = await startConversation(content);
        if (!convId) return;
      }

      // Add the user message locally (optimistic)
      addUserMessage(convId, content);

      // Update the conversation title from the first message
      const conv = useChatStore.getState().conversations.find((c) => c.id === convId);
      if (conv && conv.title === 'New conversation') {
        useChatStore.getState().renameConversation(
          convId,
          content.slice(0, TITLE_PREVIEW_LENGTH) +
            (content.length > TITLE_PREVIEW_LENGTH ? '…' : '')
        );
      }

      useChatStore.getState().setStreaming(true);
      try {
        let result: ChatResponseDTO;
        try {
          result = await ask(content, convId);
        } catch (err) {
          if (!isStaleConversationError(err)) throw err;
          // The server cannot use this conversation id, so every retry in it
          // would fail the same way. Start a fresh conversation, move the
          // question into it, and answer there instead of dead-ending.
          console.warn('Conversation rejected by the server - retrying in a new conversation', {
            conversationId: convId,
            error: err,
          });
          const staleId = convId;
          const freshId = await startConversation(content);
          if (!freshId) throw err;
          const store = useChatStore.getState();
          store.removeConversation(staleId);
          store.setMessages([]);
          convId = freshId;
          addUserMessage(freshId, content);
          result = await ask(content, freshId);
        }

        useChatStore.getState().addMessage({
          id: result.message_id,
          conversationId: result.conversation_id,
          role: 'assistant',
          content: result.answer,
          citations: result.sources.map(toCitation),
          createdAt: new Date().toISOString(),
        });
      } catch (err) {
        // describeChatError maps the HTTP status to guidance the user can act
        // on, and appends the server's correlation id so a report points at one
        // log line. The full error stays in the console for the same reason.
        const failure = describeChatError(err);
        console.error('Chat API error', {
          status: failure.status,
          requestId: failure.requestId,
          error: err,
        });
        useChatStore.getState().addMessage({
          id: `msg-error-${Date.now()}`,
          conversationId: convId,
          role: 'assistant',
          content: failure.message,
          citations: [],
          createdAt: new Date().toISOString(),
        });
      } finally {
        useChatStore.getState().setStreaming(false);
      }
    },
    [addUserMessage, ask, startConversation]
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
