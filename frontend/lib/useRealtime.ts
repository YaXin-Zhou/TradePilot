import { useEffect, useRef, useCallback, useState } from "react";

type MessageHandler = (msg: unknown) => void;

const WS_URL = "ws://localhost:8000/ws/ticker";

export function useRealtime(handlers: {
  onTicker?: (data: Record<string, unknown>) => void;
  onCandle?: (data: Record<string, unknown>) => void;
}) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [connected, setConnected] = useState(false);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(WS_URL);

      ws.onopen = () => {
        setConnected(true);
        if (reconnectTimerRef.current) {
          clearTimeout(reconnectTimerRef.current);
          reconnectTimerRef.current = null;
        }
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "ticker" && handlers.onTicker) {
            handlers.onTicker(msg);
          } else if (msg.type === "candle" && handlers.onCandle) {
            handlers.onCandle(msg);
          }
        } catch {}
      };

      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;
        reconnectTimerRef.current = setTimeout(connect, 3000);
      };

      ws.onerror = () => {
        ws.close();
      };

      wsRef.current = ws;
    } catch {}
  }, [handlers.onTicker, handlers.onCandle]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [connect]);

  return { connected };
}
