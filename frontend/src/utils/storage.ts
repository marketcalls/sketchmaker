// Storage sizes as the plans and the storage meter show them (binary units,
// matching app/services/storage_quota.py on the server).

const MB = 1024 * 1024;
const GB = 1024 * MB;

/** 512 KB, 340 MB, 1.2 GB. */
export function formatStorageSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 MB';
  if (bytes >= GB) {
    const gb = bytes / GB;
    return `${gb >= 10 ? Math.round(gb) : Number(gb.toFixed(1))} GB`;
  }
  if (bytes >= MB) return `${Math.round(bytes / MB)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/** A plan quota in MB as a label: 500 MB, 5 GB, 25 GB. */
export function formatQuotaMb(mb: number | null | undefined): string {
  if (!mb || mb <= 0) return '';
  return formatStorageSize(mb * MB);
}
