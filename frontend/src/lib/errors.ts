/** Shared error helpers for API failures. */

import { ApiError } from './api/client';

/** True when a request failed because the embedding API is in cooldown. */
export function isQuotaError(error: unknown): boolean {
  if (error instanceof ApiError) {
    return error.status === 503;
  }
  const message = error instanceof Error ? error.message : '';
  return /cooldown|quota|503/i.test(message);
}

/** Human-readable message for an unknown thrown value. */
export function toErrorMessage(
  error: unknown,
  fallback = 'Something went wrong. Please try again.',
): string {
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}
