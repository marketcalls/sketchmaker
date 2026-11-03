import { AxiosError } from 'axios';

/**
 * Error text shown to people.
 *
 * A message from Python, a provider, the proxy or the browser (stack fragments,
 * status codes, a proxy's 502 page) must never reach the screen. The API client
 * runs every failed request through sanitizeApiError, which keeps the server's
 * own wording when it is written for people and otherwise swaps in a plain
 * message. getErrorMessage and friendlyError apply the same check to anything
 * else a page is about to show.
 */

export const GENERIC_ERROR = 'Something went wrong. Please try again.';
const SERVER_ERROR = 'Something went wrong on our side. Please try again in a moment.';
const BUSY_ERROR = 'SketchMaker is busy right now. Please try again in a moment.';
const OFFLINE_ERROR = 'We could not reach SketchMaker. Check your internet connection and try again.';
const TIMEOUT_ERROR = 'This is taking longer than usual. Please try again in a moment.';
const SESSION_ERROR = 'Your session has expired. Please sign in again.';
const INVALID_INPUT_ERROR = 'Some of the details you entered are not valid. Please check them and try again.';

const TECHNICAL_PATTERNS: RegExp[] = [
  /traceback|stack ?trace|errno|exception/i,
  /\b[A-Z][a-zA-Z]+(Error|Exception|Timeout)\b/, // ValueError, JSONDecodeError, ReadTimeout
  /sqlalchemy|psycopg|asyncpg|httpx|urllib|aiohttp|pydantic|fastapi|uvicorn|starlette|ffmpeg|ffprobe|pillow/i,
  /cloudflare|nginx|upstream|origin (web )?server|bad gateway|gateway time-?out|service unavailable|internal server error/i,
  /status code \d{3}|\bhttp\/?\d?\.?\d? \d{3}\b|\b[45]\d\d (error|bad|internal|service|client|server)\b/i,
  /connection (refused|reset|aborted|error|closed)|max retries|\bssl\b|certificate|socket|getaddrinfo|\bdns\b/i,
  /nonetype|has no attribute|not subscriptable|invalid literal|unexpected keyword|positional argument/i,
  /cannot read propert|is not a function|is not defined|unexpected token|failed to execute|request failed|network ?error/i,
  /\bfal(\.ai|\.run|_client)\b|\.py\b|\bline \d+\b|0x[0-9a-f]{4,}/i,
  // Key material. A sentence that merely names a key or fal is fine: the owner sets the keys.
  /\bsk-[\w-]{6,}|\bAIza[\w-]{6,}|\bgsk_\w{6,}|\bxai-\w{6,}|\bBearer\s/,
  /<\/?[a-z][^>]*>|https?:\/\/|[{[]\s*["']/i,
];

/** Whether a message reads like an internal error rather than something written for people. */
export function looksTechnical(text: string): boolean {
  const t = text.trim();
  if (!t || t.length > 400) return true;
  return TECHNICAL_PATTERNS.some((re) => re.test(t));
}

/** The text to show for a stored or thrown message: itself when it is fit for people, otherwise the fallback. */
export function friendlyError(text: string | null | undefined, fallback = GENERIC_ERROR): string {
  if (!text) return fallback;
  return looksTechnical(text) ? fallback : text;
}

/**
 * A provider's content filter blocked the job (backend fal_client
 * CONTENT_FILTER_ERROR). Status responses that carry error_code send
 * CONTENT_FILTER_CODE; every stored job error starts with
 * CONTENT_FILTER_PREFIX, so pages without the code can still tell. The same
 * request on the same model is refused again: offer rewording or a model
 * from another provider, never a retry.
 */
export const CONTENT_FILTER_CODE = 'content_filter';
export const CONTENT_FILTER_PREFIX = "The provider's content filter blocked";

export function isContentFilterError(text: string | null | undefined, code?: string | null): boolean {
  if (code === CONTENT_FILTER_CODE) return true;
  return !!text && text.startsWith(CONTENT_FILTER_PREFIX);
}

/**
 * The content filter sentence with advice that fits the page (a page whose
 * only model cannot switch provider says what else to change). Any other
 * message is returned unchanged.
 */
export function withContentFilterAdvice(text: string, advice: string): string {
  if (!isContentFilterError(text)) return text;
  return `${CONTENT_FILTER_PREFIX} this generation. ${advice}`;
}

/**
 * Models from providers other than the current model's, for a one-click
 * switch after a content filter block (siblings share their provider's
 * filter). Keeps the order given, so list the most permissive first.
 */
export function otherProviderChoices<T extends { id: string; provider: string }>(currentId: string, options: T[]): T[] {
  const current = options.find((o) => o.id === currentId);
  return options.filter((o) => o.id !== currentId && (!current || o.provider !== current.provider));
}

/** ": message" after a "Failed" label when the stored message is fit for people, otherwise `end`. */
export function errorSuffix(text: string | null | undefined, end = ''): string {
  return text && !looksTechnical(text) ? `: ${text}` : end;
}

function messageForStatus(status: number | undefined): string {
  if (status === undefined) return OFFLINE_ERROR;
  if (status === 401) return SESSION_ERROR;
  if (status === 403) return 'This request was blocked. Please refresh the page and try again.';
  if (status === 404) return 'We could not find that. It may have been moved or deleted.';
  if (status === 408) return TIMEOUT_ERROR;
  if (status === 413) return 'That file is too large to upload.';
  if (status === 429) return 'Too many requests. Please wait a moment and try again.';
  if (status === 502 || status === 503 || status === 504 || status >= 520) return BUSY_ERROR;
  if (status >= 500) return SERVER_ERROR;
  return GENERIC_ERROR;
}

// Messages the API itself returns that are accurate but not written for people.
const PLAIN_REWRITES: Record<string, string> = {
  'Not authenticated': SESSION_ERROR,
  'Could not validate credentials': SESSION_ERROR,
  'An unexpected error occurred': SERVER_ERROR,
  'Internal Server Error': SERVER_ERROR,
  'Not Found': 'We could not find that. It may have been moved or deleted.',
};

function humanField(loc: unknown): string | null {
  if (!Array.isArray(loc) || loc.length === 0) return null;
  const last = loc[loc.length - 1];
  if (typeof last !== 'string' || last === 'body') return null;
  return last.replace(/_/g, ' ');
}

/** Rewrites one pydantic validation item's msg in place so the existing readers show something sensible. */
function friendlyValidationItem(item: unknown): void {
  if (!item || typeof item !== 'object') return;
  const entry = item as { msg?: unknown; loc?: unknown };
  if (typeof entry.msg !== 'string') return;
  // Field validators in the API raise ValueError with a sentence written for people.
  if (entry.msg.startsWith('Value error, ')) {
    const text = entry.msg.slice('Value error, '.length);
    entry.msg = friendlyError(text, INVALID_INPUT_ERROR);
    return;
  }
  const field = humanField(entry.loc);
  entry.msg = field ? `Please check the ${field} and try again.` : INVALID_INPUT_ERROR;
}

function report(error: AxiosError, reason: string) {
  if (!import.meta.env.DEV) return;
  const status = error.response?.status;
  const method = (error.config?.method || 'get').toUpperCase();
  // Path only: query strings can carry search terms and tokens.
  const path = (error.config?.url || '').split('?')[0];
  console.warn('[api]', reason, status, method, path, error.response?.data ?? error.message);
}

const SANITIZED = Symbol('sanitized');

/**
 * Makes a failed request safe to show. Afterwards error.message and
 * error.response.data.detail hold text written for people, so every existing
 * reader (getErrorMessage, the page level helpers, err.message) shows it.
 * Structured details (codes, quotes, problem lists) from the API are kept.
 */
export function sanitizeApiError<T>(error: T): T {
  if (!(error instanceof AxiosError)) return error;
  const tagged = error as AxiosError & { [SANITIZED]?: boolean };
  if (tagged[SANITIZED]) return error;
  tagged[SANITIZED] = true;

  // A cancelled request is not an error anyone sees; callers check for it.
  if (error.code === AxiosError.ERR_CANCELED) return error;

  const response = error.response;
  if (!response) {
    const timedOut = error.code === AxiosError.ECONNABORTED || error.code === AxiosError.ETIMEDOUT;
    if (timedOut) report(error, 'timeout');
    error.message = timedOut ? TIMEOUT_ERROR : OFFLINE_ERROR;
    return error;
  }

  const status = response.status;
  const fromApp = response.headers?.['x-sm-origin'] === 'app';
  const data = response.data as Record<string, unknown> | null | undefined;
  const isObject = !!data && typeof data === 'object' && !(typeof Blob !== 'undefined' && data instanceof Blob);

  if (!fromApp) {
    const message = messageForStatus(status);
    report(error, 'proxy');
    error.message = message;
    response.data = { detail: message };
    return error;
  }

  if (!isObject) {
    error.message = status >= 500 ? messageForStatus(status) : GENERIC_ERROR;
    if (status >= 500) report(error, 'app_non_json');
    return error;
  }

  const detail = data.detail;
  if (Array.isArray(detail)) {
    detail.forEach(friendlyValidationItem);
    const first = detail[0] as { msg?: unknown } | undefined;
    error.message = typeof first?.msg === 'string' ? first.msg : INVALID_INPUT_ERROR;
    return error;
  }

  if (typeof detail === 'string' || (detail && typeof detail === 'object')) {
    const holder = typeof detail === 'string' ? null : (detail as { message?: unknown });
    const text = typeof detail === 'string' ? detail : typeof holder?.message === 'string' ? holder.message : null;
    let shown = text;
    if (text !== null) {
      shown = PLAIN_REWRITES[text] ?? (looksTechnical(text) ? messageForStatus(status) : text);
      if (shown !== text) {
        report(error, 'technical_detail');
        if (holder) holder.message = shown;
        else data.detail = shown;
      }
    }
    error.message = shown ?? messageForStatus(status);
    if (status >= 500 && shown === text) report(error, 'server_error');
    return error;
  }

  if (typeof data.message === 'string' && looksTechnical(data.message)) {
    data.message = messageForStatus(status);
  }
  error.message = typeof data.message === 'string' ? data.message : messageForStatus(status);
  if (status >= 500) report(error, 'server_error');
  return error;
}

/**
 * Extract a user-friendly error message from various error types.
 * Handles axios errors with FastAPI detail responses.
 */
export function getErrorMessage(err: unknown, fallback = GENERIC_ERROR): string {
  // Handle axios errors with response data
  if (err instanceof AxiosError) {
    sanitizeApiError(err);
    const data = err.response?.data;
    if (data && typeof data === 'object') {
      // FastAPI returns errors in 'detail' field
      if (typeof data.detail === 'string') {
        return friendlyError(data.detail, fallback);
      }
      // Validation errors come as array
      if (Array.isArray(data.detail) && data.detail.length > 0) {
        return friendlyError(data.detail[0].msg, fallback);
      }
      // Structured details (validation) carry a message
      if (data.detail && typeof data.detail === 'object' && typeof data.detail.message === 'string') {
        return friendlyError(data.detail.message, fallback);
      }
      // Some APIs return 'message' field
      if (typeof data.message === 'string') {
        return friendlyError(data.message, fallback);
      }
    }
    return friendlyError(err.message, fallback);
  }

  // Handle regular Error objects (canvas, decoding and other browser errors are not for people)
  if (err instanceof Error) {
    return friendlyError(err.message, fallback);
  }

  return fallback;
}
