/** Base URL for the backend API. */
export const BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

/** Where the auth store persists its state in localStorage. */
const AUTH_STORAGE_KEY = 'auth-store';

/** Error thrown for any non-2xx API response. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    /** Server-side correlation id (``X-Request-ID``), when the API sent one. */
    readonly requestId?: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/** Read the Bearer token persisted by the auth store. */
export function readAuthToken(): string | undefined {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY);
    return raw ? JSON.parse(raw)?.state?.token : undefined;
  } catch {
    // localStorage unavailable or corrupt
    return undefined;
  }
}

function authHeaders(): Record<string, string> {
  const token = readAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function raiseForStatus(res: Response): Promise<never> {
  const body = await res.json().catch(() => ({ detail: res.statusText }));
  // The id is in the body so it survives CORS and non-header-aware clients;
  // the header is the fallback for responses that predate the body field.
  const requestId =
    (typeof body?.request_id === 'string' ? body.request_id : undefined) ??
    res.headers.get('X-Request-ID') ??
    undefined;
  throw new ApiError(body.detail || `HTTP ${res.status}`, res.status, requestId);
}

/** Perform a JSON request and return the parsed response. */
export async function apiRequest<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (!res.ok) await raiseForStatus(res);
  return res.json() as Promise<T>;
}

/** Perform a multipart upload and return the parsed response. */
export async function apiUpload<T>(path: string, formData: FormData): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: authHeaders(),
    body: formData,
  });

  if (!res.ok) await raiseForStatus(res);
  return res.json() as Promise<T>;
}
