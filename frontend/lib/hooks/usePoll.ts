"use client";

import { useState, useEffect, useCallback, useRef } from "react";

interface UsePollOptions<T> {
  stopWhen?: (data: T) => boolean;
  enabled?: boolean;
}

interface UsePollResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function usePoll<T>(
  fetcher: () => Promise<T>,
  intervalMs: number,
  options?: UsePollOptions<T>,
): UsePollResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const enabled = options?.enabled ?? true;

  // Stable ref for the stopWhen callback so it doesn't cause re-renders
  const stopWhenRef = useRef(options?.stopWhen);
  stopWhenRef.current = options?.stopWhen;

  const run = useCallback(async () => {
    try {
      const result = await fetcher();
      setData(result);
      setError(null);
      if (stopWhenRef.current?.(result)) {
        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }, [fetcher]);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    run();
    timerRef.current = setInterval(run, intervalMs);
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [run, intervalMs, enabled]);

  return { data, loading, error, refetch: run };
}
