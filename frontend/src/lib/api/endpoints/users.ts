/** Admin user-management endpoints. */

import { apiRequest } from '../client';
import type {
  AdminUserUpdateDTO,
  UserActivityDTO,
  UserAdminDTO,
  UserConsentAdminDTO,
  UserConversationsDTO,
  UserProfileAdminDTO,
  UserStatsDTO,
} from '../types/user';

export const userEndpoints = {
  /** List all users, optionally filtered by name or email. */
  list: (search?: string) => {
    const params = search ? `?search=${encodeURIComponent(search)}` : '';
    return apiRequest<UserAdminDTO[]>('GET', `/admin/users${params}`);
  },

  /** Get aggregate user statistics. */
  stats: () => apiRequest<UserStatsDTO>('GET', '/admin/users/stats'),

  /** Get a single user. */
  get: (id: string) => apiRequest<UserAdminDTO>('GET', `/admin/users/${id}`),

  /** Update a user account. */
  update: (id: string, body: AdminUserUpdateDTO) =>
    apiRequest<UserAdminDTO>('PATCH', `/admin/users/${id}`, body),

  /** Delete a user and all associated data. */
  delete: (id: string) =>
    apiRequest<{ message: string }>('DELETE', `/admin/users/${id}`),

  /** Get a user's demographic profile. */
  getProfile: (id: string) =>
    apiRequest<UserProfileAdminDTO>('GET', `/admin/users/${id}/profile`),

  /** Get a user's consent preferences. */
  getConsent: (id: string) =>
    apiRequest<UserConsentAdminDTO>('GET', `/admin/users/${id}/consent`),

  /** Get a user's conversations. */
  getConversations: (id: string, page = 1, limit = 20) =>
    apiRequest<UserConversationsDTO>(
      'GET',
      `/admin/users/${id}/conversations?page=${page}&limit=${limit}`,
    ),

  /** Get a user's activity statistics. */
  getActivity: (id: string) =>
    apiRequest<UserActivityDTO>('GET', `/admin/users/${id}/activity`),
};
