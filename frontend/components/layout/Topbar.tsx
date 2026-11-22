"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { formatDistanceToNow } from "date-fns";
import Link from "next/link";
import { Bell, LogOut, RefreshCw } from "lucide-react";
import { useAuth } from "@/components/auth/AuthProvider";
import { listAlerts } from "@/lib/api/alerts";
import { getHealth } from "@/lib/api/health";
import type { Alert } from "@/lib/types";
import { cn } from "@/lib/utils";

export function Topbar() {
  const { user, signOut } = useAuth();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [pulsing, setPulsing] = useState(false);
  const [health, setHealth] = useState<"checking" | "online" | "degraded" | "offline">("checking");
  const [healthDetail, setHealthDetail] = useState("Checking backend…");
  const [liveCount, setLiveCount] = useState(0);
  const prevIdsRef = useRef<Set<string>>(new Set());

  const fetchAlerts = useCallback(async () => {
    try {
      const data = await listAlerts();
      const active = data.filter((a) => a.status === "active");

      // Detect new alerts since last poll
      const prevIds = prevIdsRef.current;
      const newIds = active.map((a) => a.id);
      const hasNew = newIds.some((id) => !prevIds.has(id));

      if (hasNew && prevIds.size > 0) {
        setPulsing(true);
        setTimeout(() => setPulsing(false), 3000);
      }
      prevIdsRef.current = new Set(newIds);

      setAlerts(active);
      setLastUpdated(new Date());
    } catch {
      // alert fetch failed; the health check below reports connectivity
    }
  }, []);

  const checkHealth = useCallback(async () => {
    try {
      const h = await getHealth();
      setLiveCount(h.live_sessions ?? (h.components.camera === "live" ? 1 : 0));
      const bad = Object.entries(h.components).filter(([, v]) => !["ok", "idle", "live", "stopped"].includes(v));
      if (h.status === "healthy") {
        setHealth("online");
        setHealthDetail("All components ok");
      } else {
        setHealth(h.status === "unhealthy" ? "offline" : "degraded");
        setHealthDetail(bad.map(([k, v]) => `${k}: ${v}`).join(", "));
      }
    } catch {
      setLiveCount(0);
      setHealth("offline");
      setHealthDetail("Backend unreachable");
    }
  }, []);

  useEffect(() => {
    fetchAlerts();
    checkHealth();
    const id = setInterval(fetchAlerts, 10_000);
    const hid = setInterval(checkHealth, 10_000);
    return () => { clearInterval(id); clearInterval(hid); };
  }, [fetchAlerts, checkHealth]);

  const activeCount = alerts.length;

  return (
    <header className="h-14 shrink-0 bg-slate-50/90 backdrop-blur border-b border-slate-200 flex items-center justify-between px-6">
      <div />

      <div className="flex items-center gap-4">
        {/* Last updated */}
        {lastUpdated && (
          <span className="text-xs text-slate-400 flex items-center gap-1.5">
            <RefreshCw className="w-3 h-3" />
            Updated {formatDistanceToNow(lastUpdated, { addSuffix: true })}
          </span>
        )}

        {liveCount > 0 && (
          <Link
            href="/monitoring/watch"
            className="flex items-center gap-1.5 rounded-full bg-red-50 border border-red-200 px-2.5 py-1 text-[11px] font-semibold text-red-700 hover:bg-red-100"
          >
            <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" /> {liveCount > 1 ? `${liveCount} LIVE CAMERAS` : "LIVE CAMERA"}
          </Link>
        )}

        {/* Alert indicator */}
        <div className="relative">
          <Bell
            className={cn(
              "w-5 h-5 transition-colors",
              activeCount > 0 ? "text-red-500" : "text-slate-400",
            )}
          />
          {activeCount > 0 && (
            <span
              className={cn(
                "absolute -top-1.5 -right-1.5 min-w-[16px] h-4 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center px-1",
                pulsing && "animate-bounce",
              )}
            >
              {activeCount}
            </span>
          )}
        </div>

        {/* Signed-in staff member */}
        {user && (
          <div className="flex items-center gap-2 border-l border-slate-200 pl-4">
            <div className="text-right leading-tight">
              <p className="text-xs font-medium text-slate-800">{user.name}</p>
              <p className="text-[10px] capitalize text-slate-400">{user.auth_off ? "auth off (demo)" : user.role}</p>
            </div>
            {!user.auth_off && (
              <button
                type="button"
                onClick={() => signOut()}
                className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                aria-label="Sign out"
                title="Sign out"
              >
                <LogOut className="h-4 w-4" />
              </button>
            )}
          </div>
        )}

        {/* System status */}
        <div className="flex items-center gap-1.5 text-xs text-slate-500" title={healthDetail}>
          <span
            className={cn(
              "w-2 h-2 rounded-full",
              health === "online" && "bg-emerald-500 animate-pulse",
              health === "degraded" && "bg-amber-500",
              health === "offline" && "bg-red-500",
              health === "checking" && "bg-slate-300",
            )}
          />
          {health === "checking" ? "Checking…" : health === "online" ? "System online" : health === "degraded" ? `Degraded — ${healthDetail}` : "Backend offline"}
        </div>
      </div>
    </header>
  );
}
