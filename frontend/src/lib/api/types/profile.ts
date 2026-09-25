/** Profile-generation DTOs. */

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

/** Writable profile fields (snake_case, mirroring the backend schema). */
export interface ProfileUpdateDTO {
  preferred_name?: string | null;
  age_range?: string | null;
  gender_identity?: string[] | null;
  pronouns?: string | null;
  primary_language?: string | null;
  disability?: string[] | null;
  immigration_status?: string | null;
  indigenous_identity?: string | null;
  education_level?: string | null;
  literacy_comfort_ai?: number | null;
  profile_mode?: string | null;
}

/** Stored profile as returned by the API. */
export interface ProfileDTO {
  id: string;
  user_id: string;
  preferred_name: string;
  age_range: string | null;
  gender_identity: string[];
  pronouns: string | null;
  primary_language: string | null;
  disability: string[];
  immigration_status: string | null;
  indigenous_identity: string | null;
  education_level: string | null;
  literacy_comfort_ai: number | null;
  profile_mode: string;
  created_at: string;
  updated_at: string;
}

/** Consent record as returned by the API. */
export interface ConsentDTO {
  id: string;
  user_id: string;
  profile_mode: string;
  research_data_consent: boolean;
  chat_history_consent: boolean;
  has_consented: boolean;
  consented_at: string | null;
  updated_at: string | null;
}

export interface ConsentUpdateDTO {
  profile_mode?: string;
  research_data_consent?: boolean;
  chat_history_consent?: boolean;
}
