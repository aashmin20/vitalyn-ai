"use client";

import { useEffect, useRef } from "react";

/**
 * Subscribe to a Server-Sent Events URL while `url` is non-null.
 * The server ends the stream when a session stops; we close instead of
 * letting the browser auto-reconnect into a 409 loop. Reconnection happens
 * when `url` changes (e.g. the live status flips back to "live").
 */
export function useEventSource<T>(url: string | null, onMessage: (msg: T) => void) {
  const handlerRef = useRef(onMessage);
  handlerRef.current = onMessage;

  useEffect(() => {
    if (!url) return;
    const es = new EventSource(url, { withCredentials: true });
    es.onmessage = (e) => {
      try {
        handlerRef.current(JSON.parse(e.data) as T);
      } catch {
        // ignore malformed frames
      }
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, [url]);
}
