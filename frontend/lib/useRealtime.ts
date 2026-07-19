import { useEffect, useRef, useCallback, useState } from "react";

type MessageHandler = (msg: unknown) => void;

// Phase 8: 支持环境变量配置 WS URL（生产 wss）
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws/ticker";

// Phase 8: 指数退避重连间隔（上限 30s）
const RECONNECT_INTERVALS = [2000, 4000, 8000, 16000, 30000];

export function useRealtime(handlers: {
  onTicker?: (data: Record<string, unknown>) => void;
  onCandle?: (data: Record<string, unknown>) => void;
}) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectIdxRef = useRef(0);
  const handlersRef = useRef(handlers);
  const [connected, setConnected] = useState(false);

  // 保持 handlers 引用最新（避免重连时回调丢失）
  handlersRef.current = handlers;

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(WS_URL);

      ws.onopen = () => {
        setConnected(true);
        reconnectIdxRef.current = 0; // 重置退避
        if (reconnectTimerRef.current) {
          clearTimeout(reconnectTimerRef.current);
          reconnectTimerRef.current = null;
        }
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "ticker" && handlersRef.current.onTicker) {
            handlersRef.current.onTicker(msg);
          } else if (msg.type === "candle" && handlersRef.current.onCandle) {
            handlersRef.current.onCandle(msg);
          }
        } catch {
          /* ignore parse error */
        }
      };

      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;
        // Phase 8: 指数退避重连
        const idx = reconnectIdxRef.current;
        const interval = RECONNECT_INTERVALS[Math.min(idx, RECONNECT_INTERVALS.length - 1)];
        reconnectIdxRef.current = Math.min(idx + 1, RECONNECT_INTERVALS.length - 1);
        reconnectTimerRef.current = setTimeout(connect, interval);
      };

      ws.onerror = () => {
        ws.close();
      };

      wsRef.current = ws;
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [connect]);

  return { connected };
}
