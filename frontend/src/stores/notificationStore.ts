import { create } from 'zustand';
import { apiClient } from '@/api/client';

export interface Notification {
  id: number;
  type: string;
  title: string;
  message: string;
  action_url: string | null;
  is_read: boolean;
  created_at: string;
}

interface NotificationState {
  notifications: Notification[];
  unreadCount: number;
  isLoading: boolean;
  error: string | null;

  // Actions
  fetchNotifications: () => Promise<void>;
  markAsRead: (id: number) => Promise<void>;
  markAllAsRead: () => Promise<void>;
  clearNotifications: () => void;
}

export const useNotificationStore = create<NotificationState>((set, get) => ({
  notifications: [],
  unreadCount: 0,
  isLoading: false,
  error: null,

  fetchNotifications: async () => {
    set({ isLoading: true, error: null });
    try {
      const response = await apiClient.get('/notifications');
      set({
        notifications: response.data.recent,
        unreadCount: response.data.unread_count,
        isLoading: false,
      });
    } catch (error) {
      set({ error: 'Failed to fetch notifications', isLoading: false });
    }
  },

  markAsRead: async (id: number) => {
    try {
      await apiClient.post(`/notifications/${id}/read`);
      const { notifications, unreadCount } = get();
      set({
        notifications: notifications.map(n =>
          n.id === id ? { ...n, is_read: true } : n
        ),
        unreadCount: Math.max(0, unreadCount - 1),
      });
    } catch (error) {
      console.error('Failed to mark notification as read:', error);
    }
  },

  markAllAsRead: async () => {
    try {
      await apiClient.post('/notifications/read-all');
      const { notifications } = get();
      set({
        notifications: notifications.map(n => ({ ...n, is_read: true })),
        unreadCount: 0,
      });
    } catch (error) {
      console.error('Failed to mark all notifications as read:', error);
    }
  },

  clearNotifications: () => {
    set({ notifications: [], unreadCount: 0 });
  },
}));
