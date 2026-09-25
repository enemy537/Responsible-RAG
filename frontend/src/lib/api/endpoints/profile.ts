/** Profile, consent, and prompt-generation endpoints. */

import { apiRequest } from '../client';
import type {
  ConsentDTO,
  ConsentUpdateDTO,
  GenerateProfileResponseDTO,
  ProfileDTO,
  ProfileUpdateDTO,
} from '../types/profile';

export const profileEndpoints = {
  /** Get the current user's demographic profile. */
  get: () => apiRequest<ProfileDTO>('GET', '/profile'),

  /** Create or update the current user's profile. */
  upsert: (data: ProfileUpdateDTO) =>
    apiRequest<ProfileDTO>('PUT', '/profile', data),

  /** Get the current user's consent preferences. */
  getConsent: () => apiRequest<ConsentDTO>('GET', '/profile/consent'),

  /** Update the current user's consent preferences. */
  updateConsent: (data: ConsentUpdateDTO) =>
    apiRequest<ConsentDTO>('PUT', '/profile/consent', data),

  /** Generate a personalised system prompt from demographic data. */
  generate: (data: {
    user_profile?: Record<string, string>;
    user_query: string;
    retrieved_documents?: string;
  }) => apiRequest<GenerateProfileResponseDTO>('POST', '/profile/generate', data),
};
