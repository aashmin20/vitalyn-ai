const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Fired when the session is gone for good (refresh failed). The auth provider sends the user to /login. */
export const AUTH_LOST_EVENT = "vitalyn:auth-lost";

let refreshing: Promise<boolean> | null = null;

function tryRefresh(): Promise<boolean> {
  if (!refreshing) {
    refreshing = fetch(`${BASE}/api/v1/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: { "X-Requested-With": "vitalyn" },
    })
      .then((r) => r.ok)
      .catch(() => false)
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

export async function apiFetch<T>(path: string, options?: RequestInit, canRetry = true): Promise<T> {
  const url = `${BASE}${path}`;
  const method = (options?.method ?? "GET").toUpperCase();
  const res = await fetch(url, {
    ...options,
    credentials: "include",              // the session lives in httpOnly cookies
    headers: {
      "Content-Type": "application/json",
      // Changes must carry this header: it is the CSRF guard for cookie sessions.
      ...(method !== "GET" ? { "X-Requested-With": "vitalyn" } : {}),
      ...(options?.headers ?? {}),
    },
  });

  if (res.status === 401 && canRetry && !path.startsWith("/api/v1/auth/")) {
    if (await tryRefresh()) return apiFetch<T>(path, options, false);
    if (typeof window !== "undefined") window.dispatchEvent(new Event(AUTH_LOST_EVENT));
  }

  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new ApiError(res.status, text);
  }

  return res.json() as Promise<T>;
}

export function apiUrl(path: string): string {
  return `${BASE}${path}`;
}
