/** Auth + user endpoints. */

import { apiRequest } from '../client';
import type {
  AuthUserDTO,
  LoginRequestDTO,
  LoginResponseDTO,
  RegisterRequestDTO,
} from '../types/auth';

export const authEndpoints = {
  /** Register a new user account. */
  register: (body: RegisterRequestDTO) =>
    apiRequest<{ message: string }>('POST', '/auth/register', body),

  /** Log in with email + password. */
  login: (body: LoginRequestDTO) =>
    apiRequest<LoginResponseDTO>('POST', '/auth/login', body),

  /** Admin login via environment-configured credentials. */
  adminLogin: (body: LoginRequestDTO) =>
    apiRequest<LoginResponseDTO>('POST', '/auth/admin/login', body),

  /** Request a password reset email. */
  forgotPassword: (email: string) =>
    apiRequest<{ message: string }>('POST', '/auth/forgot-password', { email }),

  /** Reset a password using a token from the reset email. */
  resetPassword: (token: string, password: string) =>
    apiRequest<{ message: string }>(
      'POST',
      `/auth/reset-password?token=${encodeURIComponent(token)}&password=${encodeURIComponent(password)}`,
    ),

  /** Mark the current user's onboarding as finished. */
  completeOnboarding: () =>
    apiRequest<{ status: string }>('POST', '/auth/onboarding/complete'),

  /** Get the current authenticated user. */
  me: () => apiRequest<AuthUserDTO>('GET', '/auth/me'),
};
