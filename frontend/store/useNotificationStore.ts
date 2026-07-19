/** 全局通知中心 — Zustand */

import { create } from "zustand";

export type NotificationType = "network" | "exchange" | "risk" | "success" | "info";

export interface Notification {
  id: string;
  type: NotificationType;
  title: string;
  message: string;
  timestamp: number;
  read: boolean;
  /** 关联路由，可选 */
  link?: string;
}

interface NotificationState {
  notifications: Notification[];
  unreadCount: number;
  /** 添加通知 */
  addNotification: (n: Omit<Notification, "id" | "timestamp" | "read">) => void;
  /** 标记已读 */
  markRead: (id: string) => void;
  /** 全部已读 */
  markAllRead: () => void;
  /** 清除单条 */
  removeNotification: (id: string) => void;
  /** 清除全部 */
  clearAll: () => void;
}

let _counter = 0;

export const useNotificationStore = create<NotificationState>()((set, get) => ({
  notifications: [],
  unreadCount: 0,

  addNotification: (n) => {
    const id = `notif_${Date.now()}_${++_counter}`;
    const notification: Notification = {
      ...n,
      id,
      timestamp: Date.now(),
      read: false,
    };
    set((s) => ({
      notifications: [notification, ...s.notifications].slice(0, 50),
      unreadCount: s.unreadCount + 1,
    }));
  },

  markRead: (id) => {
    set((s) => {
      const updated = s.notifications.map((n) =>
        n.id === id ? { ...n, read: true } : n
      );
      return {
        notifications: updated,
        unreadCount: Math.max(0, s.unreadCount - 1),
      };
    });
  },

  markAllRead: () => {
    set((s) => ({
      notifications: s.notifications.map((n) => ({ ...n, read: true })),
      unreadCount: 0,
    }));
  },

  removeNotification: (id) => {
    set((s) => {
      const removed = s.notifications.find((n) => n.id === id);
      return {
        notifications: s.notifications.filter((n) => n.id !== id),
        unreadCount: removed && !removed.read
          ? Math.max(0, s.unreadCount - 1)
          : s.unreadCount,
      };
    });
  },

  clearAll: () => {
    set({ notifications: [], unreadCount: 0 });
  },
}));

/** 类型对应的颜色和图标 */
export const NOTIFICATION_STYLES: Record<NotificationType, { bg: string; border: string; dot: string; label: string }> = {
  network: { bg: "bg-yellow-500/10", border: "border-yellow-500/30", dot: "bg-yellow-400", label: "网络" },
  exchange: { bg: "bg-orange-500/10", border: "border-orange-500/30", dot: "bg-orange-400", label: "交易所" },
  risk: { bg: "bg-red-500/10", border: "border-red-500/30", dot: "bg-red-400", label: "风控" },
  success: { bg: "bg-green-500/10", border: "border-green-500/30", dot: "bg-green-400", label: "成功" },
  info: { bg: "bg-blue-500/10", border: "border-blue-500/30", dot: "bg-blue-400", label: "信息" },
};
