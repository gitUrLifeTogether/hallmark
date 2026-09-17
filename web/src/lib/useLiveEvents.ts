/* Live decisions from the realtime gateway.
 *
 * The socket is a read-only feed. Events arrive already reduced to handles, enums and
 * provenance labels, and this hook does not resolve, enrich or re-derive any of it — doing
 * so here would quietly undo the isolation the rest of the system maintains.
 *
 * Reconnection backs off rather than retrying tightly: the gateway being down is not an
 * emergency, and a console hammering a dead socket is worse than a console that waits.
 */

import { useEffect, useRef, useState } from "react";

export interface LiveEvent {
  type: string;
  runId: string;
  at: string;
  payload: Record<string, unknown>;
}

export type ConnectionState = "connecting" | "open" | "closed";

const MAX_EVENTS = 200;
const FIRST_RETRY_MS = 1000;
const MAX_RETRY_MS = 15000;

export function useLiveEvents(url: string, runId?: string) {
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [state, setState] = useState<ConnectionState>("connecting");
  const retryRef = useRef(FIRST_RETRY_MS);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const connect = () => {
      if (cancelled) return;

      const target = runId ? `${url}?runId=${encodeURIComponent(runId)}` : url;
      const socket = new WebSocket(target);
      socketRef.current = socket;
      setState("connecting");

      socket.onopen = () => {
        if (cancelled) return;
        retryRef.current = FIRST_RETRY_MS;
        setState("open");
      };

      socket.onmessage = (message) => {
        if (cancelled) return;
        try {
          const event = JSON.parse(String(message.data)) as LiveEvent;
          // Bounded: a long run must not grow the tab's memory without limit.
          setEvents((previous) => [event, ...previous].slice(0, MAX_EVENTS));
        } catch {
          // A malformed frame is dropped rather than breaking the feed.
        }
      };

      socket.onclose = () => {
        if (cancelled) return;
        setState("closed");
        timer = window.setTimeout(connect, retryRef.current);
        retryRef.current = Math.min(retryRef.current * 2, MAX_RETRY_MS);
      };

      socket.onerror = () => socket.close();
    };

    connect();

    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
      socketRef.current?.close();
    };
  }, [url, runId]);

  return { events, state, clear: () => setEvents([]) };
}
