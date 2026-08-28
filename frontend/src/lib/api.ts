/**
 * lib/api.ts — Thin fetch wrapper for the RAG backend API
 * =========================================================
 * Every function returns parsed JSON or throws on error.
 * Auth tokens are read from localStorage (set after login).
 *
 * Usage:
 *   import { api } from '@/lib/api';
 *   const res = await api.chat.send("What is RAG?");
 */

// ── Helpers ────────────────────────────────────────────────────────────────

export const BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

/** Read a Bearer token from localStorage (set by the auth store). */
export function _readAuthToken(): string | undefined {
  try {
    const raw = localStorage.getItem('auth-store');
    if (raw) {
      const parsed = JSON.parse(raw);
      return parsed?.state?.token;
    }
  } catch {
    // localStorage not available or corrupt
  }
  return undefined;
}

function getHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const token = _readAuthToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const res = await fetch(url, {
    method,
    headers: getHeaders(),
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

// ── Types (mirroring the backend Pydantic schemas in camelCase) ────────────

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

export interface MessageDTO {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant';
  content: string;
  citations: CitationDTO[];
  is_streaming: boolean;
  created_at: string;
}

// ── API methods ────────────────────────────────────────────────────────────

// ── Auth DTOs ──────────────────────────────────────────────

export interface LoginRequestDTO {
  email: string;
  password: string;
}

export interface RegisterRequestDTO {
  email: string;
  password: string;
  name: string;
}

export interface AuthUserDTO {
  id: string;
  email: string;
  name: string;
  provider: string;
  role: 'user' | 'admin';
  verified: boolean;
  created_at: string;
}

export interface LoginResponseDTO {
  access_token: string;
  token_type: string;
}

// ── API methods ────────────────────────────────────────────

export const api = {
  /** Health check */
  health: {
    ping: () => request<{ status: string }>('GET', '/health'),
  },

  /** Authentication (simplified — matches fastapi_auth) */
  auth: {
    /** Register a new user account */
    register: (body: RegisterRequestDTO) =>
      request<{ message: string }>('POST', '/auth/register', body),

    /** Log in with email + password */
    login: (body: LoginRequestDTO) =>
      request<LoginResponseDTO>('POST', '/auth/login', body),

    /** Admin login via .env credentials */
    adminLogin: (body: LoginRequestDTO) =>
      request<LoginResponseDTO>('POST', '/auth/admin/login', body),

    /** Request password reset email */
    forgotPassword: (email: string) =>
      request<{ message: string }>('POST', '/auth/forgot-password', { email, password: '' }),

    /** Reset password with token */
    resetPassword: (token: string, password: string) =>
      request<{ message: string }>('POST', `/auth/reset-password?token=${token}&password=${password}`),

    /** Mark onboarding as complete */
    completeOnboarding: () => request<{ status: string }>('POST', '/auth/onboarding/complete'),

    /** Get current user profile */
    me: () => request<AuthUserDTO>('GET', '/auth/me'),
  },

  /** Profile */
  profile: {
    /** Get user demographic profile */
    get: () => request<any>('GET', '/profile'),

    /** Create or update profile */
    upsert: (data: any) => request<any>('PUT', '/profile', data),

    /** Get consent preferences */
    getConsent: () => request<any>('GET', '/profile/consent'),

    /** Update consent preferences */
    updateConsent: (data: { profile_mode?: string; research_data_consent?: boolean }) =>
      request<any>('PUT', '/profile/consent', data),

    /** Generate personalised system prompt from demographic data */
    generate: (data: {
      user_profile?: Record<string, string>;
      user_query: string;
      retrieved_documents?: string;
    }) => request<GenerateProfileResponseDTO>('POST', '/profile/generate', data),
  },

  /** Chat / RAG */
  chat: {
    /** Send a question and get a RAG answer back */
    send: (body: ChatRequestDTO) =>
      request<ChatResponseDTO>('POST', '/chat/', body),
  },

  /** Conversations */
  conversations: {
    /** List the user's conversations */
    list: (page = 1, limit = 20) =>
      request<ConversationListResponseDTO>(
        'GET', `/chat/conversations?page=${page}&limit=${limit}`,
      ),

    /** Create a new conversation */
    create: (body: CreateConversationDTO = {}) =>
      request<ConversationResponseDTO>('POST', '/chat/conversations', body),

    /** Get a conversation with all its messages */
    get: (id: string) =>
      request<ConversationResponseDTO>('GET', `/chat/conversations/${id}`),

    /** Rename a conversation */
    rename: (id: string, title: string) =>
      request<ConversationResponseDTO>('PUT', `/chat/conversations/${id}`, { title }),

    /** Delete a conversation */
    delete: (id: string) =>
      request<{ status: string }>('DELETE', `/chat/conversations/${id}`),
  },

  /** Admin sources management */
  sources: {
    /** List all sources */
    list: (page = 1, limit = 20, status?: string) => {
      const params = new URLSearchParams({ page: String(page), limit: String(limit) });
      if (status) params.set('status', status);
      return request<SourceListResponseDTO>('GET', `/admin/sources?${params}`);
    },

    /** Get a single source */
    get: (id: string) =>
      request<SourceResponseDTO>('GET', `/admin/sources/${id}`),

    /** Create a new source (metadata only) */
    create: (body: SourceCreateRequestDTO) =>
      request<SourceResponseDTO>('POST', '/admin/sources', body),

    /** Update source metadata */
    update: (id: string, body: SourceUpdateRequestDTO) =>
      request<SourceResponseDTO>('PUT', `/admin/sources/${id}`, body),

    /** Delete a source */
    delete: (id: string) =>
      request<{ status: string; source_id: string }>('DELETE', `/admin/sources/${id}`),

    /** Upload a file for ingestion */
    upload: async (file: File) => {
      const url = `${BASE_URL}/admin/sources/upload`;
      const formData = new FormData();
      formData.append('file', file);
      const headers: Record<string, string> = {};
      const token = _readAuthToken();
      if (token) headers['Authorization'] = `Bearer ${token}`;
      const res = await fetch(url, {
        method: 'POST',
        headers,
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      return res.json() as Promise<UploadResponseDTO>;
    },

    /** Submit a YouTube URL for background transcription & ingestion */
    uploadYouTube: (body: YouTubeUploadRequestDTO) =>
      request<UploadResponseDTO>('POST', '/admin/sources/youtube', body),

    /** Submit a webpage URL for background scraping & ingestion */
    uploadWebpage: (body: WebPageUploadRequestDTO) =>
      request<UploadResponseDTO>('POST', '/admin/sources/webpage', body),

    /** Get dashboard stats */
    stats: () =>
      request<StatsResponseDTO>('GET', '/admin/dashboard/stats'),
  },

  /** Admin alerts & embedding cooldown */
  alerts: {
    /** List all system alerts */
    list: () =>
      request<AdminAlertListResponseDTO>('GET', '/admin/alerts'),

    /** Mark an alert as resolved */
    resolve: (alertId: string) =>
      request<{ status: string; alert_id: string }>('POST', `/admin/alerts/resolve?alert_id=${alertId}`),

    /** Get current embedding cooldown status */
    cooldown: () =>
      request<CooldownStatusDTO>('GET', '/admin/alerts/cooldown'),
  },

  /** Admin users management */
  users: {
    /** List all users (optionally search by name/email) */
    list: (search?: string) => {
      const params = search ? `?search=${encodeURIComponent(search)}` : '';
      return request<UserAdminDTO[]>('GET', `/admin/users${params}`);
    },

    /** Get aggregate user statistics */
    stats: () =>
      request<UserStatsDTO>('GET', '/admin/users/stats'),

    /** Get a single user */
    get: (id: string) =>
      request<UserAdminDTO>('GET', `/admin/users/${id}`),

    /** Update a user */
    update: (id: string, body: AdminUserUpdateDTO) =>
      request<UserAdminDTO>('PATCH', `/admin/users/${id}`, body),

    /** Delete a user and all associated data */
    delete: (id: string) =>
      request<{ message: string }>('DELETE', `/admin/users/${id}`),

    /** Get user's demographic profile */
    getProfile: (id: string) =>
      request<UserProfileAdminDTO>('GET', `/admin/users/${id}/profile`),

    /** Get user's consent preferences */
    getConsent: (id: string) =>
      request<UserConsentAdminDTO>('GET', `/admin/users/${id}/consent`),

    /** Get user's conversations */
    getConversations: (id: string, page = 1, limit = 20) =>
      request<UserConversationsDTO>('GET', `/admin/users/${id}/conversations?page=${page}&limit=${limit}`),

    /** Get user's activity stats */
    getActivity: (id: string) =>
      request<UserActivityDTO>('GET', `/admin/users/${id}/activity`),
  },
};

// ── Admin / Source DTOs ──────────────────────────────────────

export interface SourceResponseDTO {
  id: string;
  title: string;
  source_type: string;
  authors: string[];
  publication_date: string | null;
  publisher: string | null;
  url: string;
  doi: string | null;
  language: string | null;
  description: string | null;
  tags: string[];
  content_sensitivity: string;
  internal_notes: string | null;
  status: 'processing' | 'indexed' | 'error';
  error_message: string | null;
  chunk_count: number;
}

export interface SourceListResponseDTO {
  sources: SourceResponseDTO[];
  total: number;
  page: number;
  limit: number;
}

export interface SourceCreateRequestDTO {
  title: string;
  source_type: string;
  authors?: string[];
  publication_date?: string | null;
  publisher?: string | null;
  url: string;
  doi?: string | null;
  language?: string | null;
  description?: string | null;
  tags?: string[];
  content_sensitivity?: string;
  internal_notes?: string | null;
}

export interface SourceUpdateRequestDTO {
  title?: string;
  authors?: string[];
  publication_date?: string | null;
  publisher?: string | null;
  url?: string | null;
  doi?: string | null;
  language?: string | null;
  description?: string | null;
  tags?: string[];
  content_sensitivity?: string;
  internal_notes?: string | null;
}

export interface WebPageUploadRequestDTO {
  url: string;
  title: string;
  source_type?: string;
  authors?: string[];
  publication_date?: string | null;
  publisher?: string | null;
  language?: string | null;
  description?: string | null;
  tags?: string[];
  content_sensitivity?: string;
  internal_notes?: string | null;
}

export interface YouTubeUploadRequestDTO {
  url: string;
  title: string;
  authors?: string[];
  publication_date?: string | null;
  publisher?: string | null;
  language?: string | null;
  description?: string | null;
  tags?: string[];
  content_sensitivity?: string;
  internal_notes?: string | null;
}

export interface UploadResponseDTO {
  id: string;
  filename: string;
  source_type: string;
  status: 'processing' | 'indexed' | 'error';
  chunk_count: number;
}

export interface StatsResponseDTO {
  total_sources: number;
  indexed_sources: number;
  processing_sources: number;
  error_sources: number;
  incomplete_metadata: number;
  /** Whether the embedding API is in cooldown (quota exceeded). */
  embedding_cooldown_active: boolean;
  /** Seconds remaining in the current cooldown (0 if none). */
  embedding_cooldown_remaining_seconds: number;
  /** Number of unresolved system alerts. */
  unresolved_alerts: number;
}

// ── Admin Alert DTOs ───────────────────────────────────────────

export interface AdminAlertDTO {
  id: string;
  type: string;
  severity: 'info' | 'warning' | 'critical';
  title: string;
  message: string;
  cooldown_until: string | null;
  timestamp: string;
  resolved: string;
}

export interface AdminAlertListResponseDTO {
  alerts: AdminAlertDTO[];
  total: number;
  unresolved_count: number;
}

export interface CooldownStatusDTO {
  in_cooldown: boolean;
  remaining_seconds: number;
  remaining_minutes: number;
  cooldown_duration_seconds: number;
}

export interface AdaptationFieldDTO {
  field: string;
  label: string;
  value: string;
  evidence_found: boolean;
}

export interface GenerateProfileResponseDTO {
  prompt: string;
  prompt_length: number;
  fields_provided: number;
  sources_used: string[];
  adaptation_fields: AdaptationFieldDTO[];
}

// ── Admin / User DTOs ─────────────────────────────────────────

export interface UserAdminDTO {
  id: string;
  email: string;
  name: string;
  provider: string;
  role: 'user' | 'admin';
  verified: boolean;
  onboarding_completed: boolean;
  created_at: string;
  has_profile: boolean;
  profile_mode: 'full' | 'general';
  has_consent: boolean;
  research_data_consent: boolean;
  conversation_count: number;
  message_count: number;
}

export interface AdminUserUpdateDTO {
  name?: string;
  password?: string;
  role?: 'user' | 'admin';
  verified?: boolean;
}

export interface UserStatsDTO {
  total_users: number;
  admin_users: number;
  verified_users: number;
  onboarding_completed: number;
  users_with_profiles: number;
  full_privacy_mode: number;
  consent_granted: number;
  research_data_consent: number;
  total_conversations: number;
  total_messages: number;
}

export interface UserProfileAdminDTO {
  user_id: string;
  has_profile: boolean;
  profile_mode: 'full' | 'general';
  research_data_consent: boolean;
  data: {
    preferred_name: string | null;
    age_range: string | null;
    gender_identity: string[] | null;
    pronouns: string | null;
    primary_language: string | null;
    disability: string[] | null;
    immigration_status: string | null;
    indigenous_identity: string | null;
    education_level: string | null;
    literacy_comfort_ai: number | null;
  } | null;
  redacted: boolean;
}

export interface UserConsentAdminDTO {
  user_id: string;
  has_consented: boolean;
  profile_mode: 'full' | 'general';
  research_data_consent: boolean;
  consented_at: string | null;
  updated_at: string | null;
}

export interface UserConversationItemDTO {
  id: string;
  title: string;
  profile_key: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface UserConversationsDTO {
  conversations: UserConversationItemDTO[];
  total: number;
  page: number;
  limit: number;
}

export interface UserActivityDTO {
  conversation_count: number;
  message_count: number;
  last_conversation_at: string | null;
  last_message_at: string | null;
}
