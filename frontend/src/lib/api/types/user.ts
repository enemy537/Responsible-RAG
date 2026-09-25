/** Admin user-management DTOs. */

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
