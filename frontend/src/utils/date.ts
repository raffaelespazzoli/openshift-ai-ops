export function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);

  if (diffSeconds < 60) return 'just now';

  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);

  const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });

  if (diffHours < 24) {
    if (diffHours >= 1) return rtf.format(-diffHours, 'hour');
    return rtf.format(-diffMinutes, 'minute');
  }

  return date.toISOString();
}
