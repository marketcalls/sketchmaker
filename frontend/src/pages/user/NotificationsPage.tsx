import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Bell,
  Loader2,
  Check,
  CheckCheck,
  ImageIcon,
  Video,
  ChevronRight,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Alert } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { apiClient } from '@/api/client';
import { formatRelativeTime, formatLocalDate, formatLocalTime } from '@/lib/dateUtils';
import { cn } from '@/lib/utils';
import { Stagger, StaggerItem } from '@/components/motion';
import { TablePagination } from '@/components/common/TablePagination';

interface NotificationItem {
  id: number;
  type: string;
  title: string;
  message: string;
  action_url: string | null;
  is_read: boolean;
  created_at: string;
}

interface NotificationListResponse {
  notifications: NotificationItem[];
  total: number;
  page: number;
  page_size: number;
}

// Icons stay muted; only problems carry a semantic tint.
const typeConfig: Record<string, { icon: React.ReactNode; className: string }> = {
  image_completed: { icon: <ImageIcon className="h-4 w-4" />, className: 'text-muted-foreground' },
  image_failed: { icon: <ImageIcon className="h-4 w-4" />, className: 'text-destructive' },
  video_completed: { icon: <Video className="h-4 w-4" />, className: 'text-muted-foreground' },
  video_failed: { icon: <Video className="h-4 w-4" />, className: 'text-destructive' },
};

const defaultTypeConfig = {
  icon: <Bell className="h-4 w-4" />,
  className: 'text-muted-foreground',
};

export function NotificationsPage() {
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [isMarkingAll, setIsMarkingAll] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pageSize = 20;

  const unreadCount = notifications.filter(n => !n.is_read).length;

  useEffect(() => {
    loadNotifications();
  }, [page]);

  const loadNotifications = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await apiClient.get<NotificationListResponse>('/notifications/all', {
        params: { page, page_size: pageSize },
      });
      setNotifications(response.data.notifications);
      setTotal(response.data.total);
    } catch {
      setError('Notifications could not be loaded. Refresh the page to try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const markAsRead = async (id: number) => {
    try {
      await apiClient.post(`/notifications/${id}/read`);
      setNotifications(prev =>
        prev.map(n => (n.id === id ? { ...n, is_read: true } : n))
      );
    } catch {
      console.error('Failed to mark notification as read');
    }
  };

  const markAllAsRead = async () => {
    setIsMarkingAll(true);
    try {
      await apiClient.post('/notifications/read-all');
      setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
    } catch {
      console.error('Failed to mark all notifications as read');
    } finally {
      setIsMarkingAll(false);
    }
  };

  const handleNotificationClick = (notification: NotificationItem) => {
    if (!notification.is_read) {
      markAsRead(notification.id);
    }
    if (notification.action_url) {
      navigate(notification.action_url);
    }
  };

  const totalPages = Math.ceil(total / pageSize);
  const showSkeleton = isLoading && notifications.length === 0;

  return (
    <Stagger className="max-w-4xl space-y-6" interval={0.04}>
      <StaggerItem>
        <header className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Notifications</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Finished and failed jobs.
            </p>
          </div>
          {unreadCount > 0 && (
            <Button
              variant="outline"
              onClick={markAllAsRead}
              disabled={isMarkingAll}
            >
              {isMarkingAll ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <CheckCheck className="h-4 w-4" />
              )}
              {isMarkingAll ? 'Marking as read' : 'Mark all as read'}
            </Button>
          )}
        </header>
      </StaggerItem>

      {error && (
        <Alert variant="destructive">{error}</Alert>
      )}

      <StaggerItem>
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <h2 className="text-sm font-semibold">All notifications</h2>
            {!showSkeleton && (
              <span className="tabular text-xs text-muted-foreground">
                {total.toLocaleString()} total{unreadCount > 0 && `, ${unreadCount} unread`}
              </span>
            )}
          </div>

          {showSkeleton ? (
            <div className="divide-y divide-border" aria-busy="true">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="flex items-start gap-4 px-4 py-4">
                  <Skeleton className="h-8 w-8 rounded-md" />
                  <div className="flex-1 space-y-2">
                    <Skeleton className="h-4 w-1/3" />
                    <Skeleton className="h-3 w-2/3" />
                  </div>
                </div>
              ))}
            </div>
          ) : notifications.length === 0 ? (
            <div className="px-4 py-12 text-center">
              <Bell className="mx-auto mb-3 h-6 w-6 text-muted-foreground" />
              <p className="font-semibold">No notifications yet</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Notifications about your jobs appear here.
              </p>
            </div>
          ) : (
            <ul
              className={cn('divide-y divide-border transition-opacity duration-150', isLoading && 'opacity-60')}
              aria-busy={isLoading}
            >
              {notifications.map((notification) => {
                const config = typeConfig[notification.type] || defaultTypeConfig;
                const unread = !notification.is_read;
                return (
                  <li
                    key={notification.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => handleNotificationClick(notification)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        handleNotificationClick(notification);
                      }
                    }}
                    className={cn(
                      'relative flex cursor-pointer items-start gap-4 px-4 py-4 transition-colors duration-150 hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring',
                      unread && 'bg-accent/30'
                    )}
                  >
                    {unread && (
                      <span className="absolute left-0 top-0 h-full w-0.5 bg-primary" aria-hidden="true" />
                    )}
                    <div className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border bg-secondary/40', config.className)}>
                      {config.icon}
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <h3 className={cn('text-sm', unread ? 'font-semibold text-foreground' : 'font-medium text-muted-foreground')}>
                          {notification.title}
                        </h3>
                        {unread && <span className="sr-only">(unread)</span>}
                      </div>
                      <p className={cn('mt-1 text-sm', unread ? 'text-foreground/80' : 'text-muted-foreground')}>
                        {notification.message}
                      </p>
                      <p className="tabular mt-2 text-xs text-muted-foreground">
                        <span title={`${formatLocalDate(notification.created_at)} at ${formatLocalTime(notification.created_at)}`}>
                          {formatRelativeTime(notification.created_at)}
                        </span>
                      </p>
                    </div>

                    <div className="flex shrink-0 items-center gap-1">
                      {unread && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 w-8 p-0"
                          aria-label="Mark as read"
                          title="Mark as read"
                          onClick={(e) => {
                            e.stopPropagation();
                            markAsRead(notification.id);
                          }}
                        >
                          <Check className="h-4 w-4" />
                        </Button>
                      )}
                      {notification.action_url && (
                        <ChevronRight className="h-4 w-4 text-muted-foreground" aria-label="Opens a page" />
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          {totalPages > 1 && (
            <TablePagination
              page={page}
              totalPages={totalPages}
              total={total}
              pageSize={pageSize}
              onPageChange={(p) => setPage(Math.min(Math.max(1, p), totalPages))}
              disabled={isLoading}
            />
          )}
        </div>
      </StaggerItem>
    </Stagger>
  );
}
