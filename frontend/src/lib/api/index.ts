/**
 * Typed client for the Responsible RAG backend.
 *
 * Split into `client` (transport), `types` (DTOs), and `endpoints` (one module
 * per API area). Everything is re-exported here so call sites can keep using
 * `import { api, type SomeDTO } from '@/lib/api'`.
 */

import { alertEndpoints } from './endpoints/alerts';
import { authEndpoints } from './endpoints/auth';
import { chatEndpoints, conversationEndpoints, healthEndpoints } from './endpoints/chat';
import { profileEndpoints } from './endpoints/profile';
import { dashboardEndpoints, sourceEndpoints } from './endpoints/sources';
import { userEndpoints } from './endpoints/users';

export {
  ApiError,
  BASE_URL,
  apiRequest,
  apiUpload,
  readAuthToken,
} from './client';

export * from './types/alert';
export * from './types/auth';
export * from './types/chat';
export * from './types/profile';
export * from './types/source';
export * from './types/user';

export const api = {
  /** Health check. */
  health: healthEndpoints,

  /** Authentication. */
  auth: authEndpoints,

  /** Profile and consent. */
  profile: profileEndpoints,

  /** Chat / RAG. */
  chat: chatEndpoints,

  /** Conversation history. */
  conversations: conversationEndpoints,

  /** Knowledge-base sources. */
  sources: sourceEndpoints,

  /** Admin dashboard. */
  dashboard: dashboardEndpoints,

  /** Admin alerts and embedding cooldown. */
  alerts: alertEndpoints,

  /** Admin user management. */
  users: userEndpoints,
};
