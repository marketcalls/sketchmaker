import { useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Bell, Check, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Badge } from '@/components/ui/badge';
import { useNotificationStore, type Notification } from '@/stores/notificationStore';
import { cn } from '@/lib/utils';
import { formatRelativeTime } from '@/lib/dateUtils';

function NotificationItem({
  notification,
  onRead,
}: {
  notification: Notification;
  onRead: (id: number) => void;
}) {
  const navigate = useNavigate();

  const handleClick = () => {
    if (!notification.is_read) {
      onRead(notification.id);
    }
    if (notification.action_url) {
      navigate(notification.action_url);
    }
  };

  return (
    <DropdownMenuItem
      className={cn(
        'flex cursor-pointer flex-col items-start gap-1 p-3',
        !notification.is_read && 'bg-accent/40'
      )}
      onClick={handleClick}
    >
      <div className="flex items-start justify-between w-full gap-2">
        <span className={cn('text-sm', notification.is_read ? 'text-muted-foreground' : 'font-medium text-foreground')}>
          {notification.title}
        </span>
        {!notification.is_read && (
          <span className="mt-1.5 h-2 w-2 flex-shrink-0 rounded-full bg-primary" aria-label="Unread" />
        )}
      </div>
      <span className="text-xs text-muted-foreground line-clamp-2">
        {notification.message}
      </span>
      <div className="flex items-center justify-between w-full mt-1">
        <span className="tabular text-xs text-muted-foreground">
          {formatRelativeTime(notification.created_at)}
        </span>
        {notification.action_url && (
          <ExternalLink className="h-3 w-3 text-muted-foreground" />
        )}
      </div>
    </DropdownMenuItem>
  );
}

export function NotificationBell() {
  const {
    notifications,
    unreadCount,
    fetchNotifications,
    markAsRead,
    markAllAsRead,
  } = useNotificationStore();

  useEffect(() => {
    fetchNotifications();
    // Poll for new notifications every 60 seconds
    const interval = setInterval(fetchNotifications, 60000);
    return () => clearInterval(interval);
  }, [fetchNotifications]);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative"
          aria-label={unreadCount > 0 ? `Notifications, ${unreadCount} unread` : 'Notifications'}
        >
          <Bell className="h-5 w-5" />
          {unreadCount > 0 && (
            <Badge
              className="tabular absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full px-1 py-0 text-[10px] leading-none"
            >
              {unreadCount > 9 ? '9+' : unreadCount}
            </Badge>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-80" align="end">
        <DropdownMenuLabel className="flex items-center justify-between text-sm text-foreground">
          <span>Notifications</span>
          {unreadCount > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                markAllAsRead();
              }}
            >
              <Check className="h-3 w-3" />
              Mark all read
            </Button>
          )}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {notifications.length === 0 ? (
          <div className="p-6 text-center text-sm text-muted-foreground">
            You have no notifications.
          </div>
        ) : (
          <>
            <div className="max-h-[60vh] overflow-y-auto">
            {notifications.map((notification) => (
              <NotificationItem
                key={notification.id}
                notification={notification}
                onRead={markAsRead}
              />
            ))}
            </div>
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild className="justify-center">
              <Link to="/notifications" className="text-sm text-foreground">
                View all notifications
              </Link>
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
