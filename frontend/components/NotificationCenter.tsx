/** 全局通知中心 — 下拉面板 */
import { useState, useCallback } from "react";
import { Bell, X, Check, Trash2 } from "lucide-react";
import { useNotificationStore, NOTIFICATION_STYLES, Notification } from "../store/useNotificationStore";
import { useLanguage } from "../lib/LanguageContext";

export default function NotificationCenter() {
  const [open, setOpen] = useState(false);
  const {
    notifications,
    unreadCount,
    markRead,
    markAllRead,
    removeNotification,
    clearAll,
  } = useNotificationStore();
  const { t, lang } = useLanguage();

  const handleToggle = useCallback(() => setOpen((v) => !v), []);
  const handleItemClick = useCallback(
    (n: Notification) => {
      if (!n.read) markRead(n.id);
      if (n.link && typeof window !== "undefined") {
        window.location.href = n.link;
      }
    },
    [markRead]
  );

  const formatTime = (ts: number) => {
    const d = new Date(ts);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return lang === "zh" ? "刚刚" : "Just now";
    if (mins < 60) return `${mins}m`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h`;
    return d.toLocaleDateString();
  };

  const label = lang === "zh"
    ? { markAll: "全部已读", clear: "清空", empty: "暂无通知" }
    : { markAll: "Mark all read", clear: "Clear all", empty: "No notifications" };

  return (
    <div className="relative">
      {/* Bell Icon */}
      <button
        onClick={handleToggle}
        className="relative flex items-center justify-center w-8 h-8 rounded-lg hover:bg-dark-800 transition-colors"
        title={lang === "zh" ? "通知中心" : "Notifications"}
      >
        <Bell size={16} className="text-dark-300" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full bg-red-500 flex items-center justify-center text-[10px] font-bold text-white">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown Panel */}
      {open && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-30"
            onClick={() => setOpen(false)}
          />

          <div className="absolute right-0 top-full mt-2 w-80 max-h-[420px] bg-dark-900 border border-dark-700 rounded-xl shadow-2xl z-40 overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-dark-700">
              <span className="text-sm font-medium text-white">
                {lang === "zh" ? "通知中心" : "Notifications"}
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={markAllRead}
                  className="flex items-center gap-1 text-xs text-dark-400 hover:text-green-400 transition-colors"
                >
                  <Check size={12} />
                  <span>{label.markAll}</span>
                </button>
                <button
                  onClick={clearAll}
                  className="flex items-center gap-1 text-xs text-dark-400 hover:text-red-400 transition-colors"
                >
                  <Trash2 size={12} />
                  <span>{label.clear}</span>
                </button>
              </div>
            </div>

            {/* Notification List */}
            <div className="overflow-y-auto max-h-[340px]">
              {notifications.length === 0 ? (
                <div className="flex items-center justify-center py-12 text-sm text-dark-500">
                  {label.empty}
                </div>
              ) : (
                notifications.map((n) => {
                  const style = NOTIFICATION_STYLES[n.type];
                  return (
                    <div
                      key={n.id}
                      onClick={() => handleItemClick(n)}
                      className={`relative flex items-start gap-3 px-4 py-3 border-b border-dark-800/50 cursor-pointer
                        hover:bg-dark-800/60 transition-colors ${n.read ? "opacity-60" : ""}`}
                    >
                      {/* Color dot */}
                      <div className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${style.dot}`} />
                      {/* Content */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-medium text-white truncate">
                            {n.title}
                          </span>
                          <span
                            className={`text-[10px] px-1.5 py-0.5 rounded ${style.bg} ${style.border} border`}
                          >
                            {style.label}
                          </span>
                        </div>
                        <p className="text-xs text-dark-400 mt-0.5 line-clamp-2">
                          {n.message}
                        </p>
                        <span className="text-[10px] text-dark-500 mt-1 block">
                          {formatTime(n.timestamp)}
                        </span>
                      </div>
                      {/* Close button */}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          removeNotification(n.id);
                        }}
                        className="flex-shrink-0 p-0.5 rounded hover:bg-dark-700 text-dark-500 hover:text-dark-300 transition-colors"
                      >
                        <X size={12} />
                      </button>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
