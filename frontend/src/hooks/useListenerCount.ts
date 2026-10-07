import { useEffect, useState } from "react";

export function listenerSocketUrl(protocol: string, host: string): string {
  const scheme = protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${host}/api/ws/listeners`;
}

const MIN_RETRY_MS = 1000;
const MAX_RETRY_MS = 30000;

export function useListenerCount(): number {
  const [count, setCount] = useState(0);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let closed = false;
    let reconnectTimer: number | null = null;
    let retryDelay = MIN_RETRY_MS;

    const scheduleReconnect = () => {
      if (closed) return;
      const jitter = 0.85 + Math.random() * 0.3;
      const delay = Math.min(MAX_RETRY_MS, retryDelay) * jitter;
      retryDelay = Math.min(MAX_RETRY_MS, retryDelay * 2);
      reconnectTimer = window.setTimeout(connect, delay);
    };

    function connect() {
      if (closed) return;
      let next: WebSocket;
      try {
        next = new WebSocket(listenerSocketUrl(location.protocol, location.host));
      } catch {
        scheduleReconnect();
        return;
      }
      socket = next;
      next.onopen = () => {
        retryDelay = MIN_RETRY_MS;
      };
      next.onmessage = (event) => {
        if (closed) return;
        try {
          const data = JSON.parse(event.data) as { count?: unknown };
          if (typeof data.count === "number") {
            setCount(data.count);
          }
        } catch {
          // ignore malformed frames
        }
      };
      next.onclose = () => {
        if (socket === next) socket = null;
        scheduleReconnect();
      };
    }

    connect();
    return () => {
      closed = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, []);

  return count;
}
