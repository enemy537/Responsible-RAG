/** Shared error helpers for API failures. */

import { ApiError } from './api/client';

/**
 * Shown when the embedding backend reports a quota/cooldown condition.
 *
 * Note this is *not* a generic 503 handler: the API returns 503 for an
 * unavailable database, and reporting that as an embedding quota problem sends
 * users (and maintainers) after the wrong subsystem.
 */
export const QUOTA_ERROR_MESSAGE =
  'The document search engine is temporarily unavailable due to an API quota limit. ' +
  "I can still answer from my general knowledge, but responses won't include citations " +
  'to specific sources. Please try again later for source-grounded answers.';

const NETWORK_ERROR_MESSAGE =
  "I couldn't reach the server, so your message was not sent. Check your connection and " +
  'try again. On a VPN or campus network, try disconnecting it in case it is blocking the request.';

/** A failed chat request, described for display. */
export interface ChatErrorInfo {
  /** Text to show in the chat. */
  message: string;
  /** HTTP status, when the failure came from the API. */
  status?: number;
  /** Server correlation id, when the response carried one. */
  requestId?: string;
}

/** True when the failure is the embedding backend being rate-limited. */
export function isQuotaError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : '';
  return /quota|cooldown|rate.?limit/i.test(message);
}

/**
 * Append the reference a maintainer needs to find this failure in the logs.
 *
 * The server logs the same id with the traceback, so a user who copies this
 * line identifies one exact log entry without anyone having to reproduce it.
 */
function withReference(message: string, status?: number, requestId?: string): ChatErrorInfo {
  const parts: string[] = [];
  if (requestId) parts.push(`ref ${requestId}`);
  if (status) parts.push(`HTTP ${status}`);
  const suffix = parts.length
    ? `\n\nIf it keeps happening, send this reference on: ${parts.join(' · ')}`
    : '';
  return { message: `${message}${suffix}`, status, requestId };
}

/**
 * Turn a thrown value from the chat request into something a user can act on
 * and report. The HTTP status drives the guidance, because each status means a
 * different failure mode with a different fix.
 */
export function describeChatError(error: unknown): ChatErrorInfo {
  // Not an ApiError: fetch itself threw, so no response was received at all.
  // That is a client-side problem (offline, DNS, TLS interception, proxy),
  // never something the backend can log.
  if (!(error instanceof ApiError)) {
    return { message: NETWORK_ERROR_MESSAGE };
  }

  const { status, requestId } = error;
  const detail = error.message?.trim();

  if (isQuotaError(error)) {
    return withReference(QUOTA_ERROR_MESSAGE, status, requestId);
  }

  switch (status) {
    case 401:
      return withReference('Your session has expired. Please sign in again.', status, requestId);
    case 403:
      return withReference(
        "You don't have access to this conversation. Try starting a new one.",
        status,
        requestId
      );
    case 404:
      return withReference(
        'This conversation is no longer stored on the server, so the message could not be added. ' +
          'It may have expired or been deleted. Start a new chat to continue.',
        status,
        requestId
      );
    case 409:
      return withReference('That conflicted with a newer change. Reload the page and try again.', status, requestId);
    case 413:
      return withReference('That request was too large for the server to accept.', status, requestId);
    case 429:
      return withReference('You are sending messages too quickly. Wait a few seconds and try again.', status, requestId);
    case 503:
      return withReference(
        'The database is temporarily unavailable, so this answer could not be saved or retrieved. ' +
          'Please try again in a moment.',
        status,
        requestId
      );
    case 500:
    case 502:
    case 504:
      return withReference(
        'The server failed while answering. This is not caused by your message - please try again.',
        status,
        requestId
      );
    default:
      break;
  }

  if (status >= 500) {
    return withReference('The server failed while answering. Please try again.', status, requestId);
  }
  return withReference(
    detail ? `The server rejected that request: ${detail}` : 'The server rejected that request.',
    status,
    requestId
  );
}

/** Human-readable message for an unknown thrown value. */
export function toErrorMessage(
  error: unknown,
  fallback = 'Something went wrong. Please try again.',
): string {
  if (error instanceof ApiError) return describeChatError(error).message;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}
