/** Toast 分类通知 — 网络/交易所/风控 */
import toast from "react-hot-toast";
import { useNotificationStore, NotificationType } from "../store/useNotificationStore";

type ToastLevel = "network" | "exchange" | "risk";

const TOAST_STYLES: Record<ToastLevel, { bg: string; icon: string }> = {
  network: { bg: "#f0b90b", icon: "🌐" },
  exchange: { bg: "#f97316", icon: "🏦" },
  risk: { bg: "#f6465d", icon: "⚠️" },
};

/**
 * 显示分类 Toast 并同步到通知中心
 */
export function showToast(
  level: ToastLevel,
  title: string,
  message: string,
  link?: string
) {
  const style = TOAST_STYLES[level];

  toast(message, {
    icon: style.icon,
    style: {
      border: `1px solid ${style.bg}40`,
      background: "#1a1a1a",
      color: "#eaecef",
      fontSize: "13px",
    },
    duration: 4000,
  });

  // 同步到通知中心
  const typeMap: Record<ToastLevel, NotificationType> = {
    network: "network",
    exchange: "exchange",
    risk: "risk",
  };

  useNotificationStore.getState().addNotification({
    type: typeMap[level],
    title,
    message,
    link,
  });
}

/** 便捷方法 */
export const notify = {
  network: (title: string, msg: string, link?: string) =>
    showToast("network", title, msg, link),
  exchange: (title: string, msg: string, link?: string) =>
    showToast("exchange", title, msg, link),
  risk: (title: string, msg: string, link?: string) =>
    showToast("risk", title, msg, link),
};
