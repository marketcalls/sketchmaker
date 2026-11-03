/**
 * Timezone-aware date utilities for global SaaS application
 *
 * Backend stores all timestamps in UTC. This utility ensures proper
 * conversion to local timezone for display.
 */

/**
 * Parse a timestamp string and ensure it's treated as UTC
 * Handles timestamps with or without timezone suffix
 */
export function parseUTCDate(timestamp: string | Date | null | undefined): Date | null {
  if (!timestamp) return null;

  if (timestamp instanceof Date) {
    return timestamp;
  }

  // If timestamp doesn't have timezone info, treat as UTC
  let dateStr = timestamp;
  // Check for explicit timezone: Z suffix or ±HH:MM offset pattern
  const hasTimezone = dateStr.endsWith('Z') || /[+-]\d{2}:?\d{2}$/.test(dateStr);
  if (!hasTimezone) {
    dateStr = dateStr + 'Z';
  }

  const date = new Date(dateStr);
  return isNaN(date.getTime()) ? null : date;
}

/**
 * Format relative time (e.g., "5m ago", "2h ago", "3d ago")
 * Properly handles UTC timestamps
 */
export function formatRelativeTime(timestamp: string | Date | null | undefined): string {
  const date = parseUTCDate(timestamp);
  if (!date) return 'Unknown';

  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  // Handle future dates (shouldn't happen, but be safe)
  if (seconds < 0) return 'Just now';

  if (seconds < 60) return 'Just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
  if (seconds < 2592000) return `${Math.floor(seconds / 604800)}w ago`;

  // For older dates, show the actual date
  return formatLocalDate(timestamp);
}

/**
 * Format date only (e.g., "Jan 8, 2026")
 * Converts UTC to local timezone
 */
export function formatLocalDate(
  timestamp: string | Date | null | undefined,
  options?: Intl.DateTimeFormatOptions
): string {
  const date = parseUTCDate(timestamp);
  if (!date) return 'Unknown';

  const defaultOptions: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  };

  return date.toLocaleDateString(undefined, options || defaultOptions);
}

/**
 * Format date with time (e.g., "Jan 8, 2026, 1:30 PM")
 * Converts UTC to local timezone
 */
export function formatLocalDateTime(
  timestamp: string | Date | null | undefined,
  options?: Intl.DateTimeFormatOptions
): string {
  const date = parseUTCDate(timestamp);
  if (!date) return 'Unknown';

  const defaultOptions: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  };

  return date.toLocaleString(undefined, options || defaultOptions);
}

/**
 * Format time only (e.g., "1:30 PM")
 * Converts UTC to local timezone
 */
export function formatLocalTime(
  timestamp: string | Date | null | undefined,
  options?: Intl.DateTimeFormatOptions
): string {
  const date = parseUTCDate(timestamp);
  if (!date) return 'Unknown';

  const defaultOptions: Intl.DateTimeFormatOptions = {
    hour: 'numeric',
    minute: '2-digit',
  };

  return date.toLocaleTimeString(undefined, options || defaultOptions);
}
