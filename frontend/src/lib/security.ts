/**
 * Guards for values that reach navigation or the DOM from a query string or an
 * API response.
 */

/**
 * Returns a same-origin path for post-login navigation, or `fallback`.
 *
 * Parsing against the current origin (rather than string checks alone) catches
 * every form a browser would turn into another host: `https://evil`, `//evil`,
 * `/\evil`, and variants hidden behind tabs or newlines that the URL parser strips.
 */
export function safeRedirectPath(value: string | null | undefined, fallback: string): string {
  if (!value || !value.startsWith('/')) return fallback;
  try {
    const url = new URL(value, window.location.origin);
    if (url.origin !== window.location.origin) return fallback;
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return fallback;
  }
}

/**
 * Returns `value` as an absolute http(s) URL, or null. Use before handing an
 * API-supplied URL to `window.open` or `window.location`, where a `javascript:`
 * URL would run in this origin.
 */
export function safeExternalUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value, window.location.origin);
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null;
  } catch {
    return null;
  }
}

/** Opens an http(s) URL in a new tab without giving it `window.opener`. */
export function openInNewTab(value: string | null | undefined): void {
  const url = safeExternalUrl(value);
  if (url) window.open(url, '_blank', 'noopener,noreferrer');
}
