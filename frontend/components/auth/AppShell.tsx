"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Clock, LogOut, RefreshCw, ShieldOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { useAuth } from "./AuthProvider";

const PUBLIC_PATHS = ["/login", "/signup"];
const LANDING = "/";                 // public for everyone, full-bleed, no app chrome

/** Signed-out visitors see only the login/sign-up pages; pending accounts see a waiting screen. */
export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading, signOut, refreshUser } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const isPublic = PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(p + "/"));
  const isLanding = pathname === LANDING;

  useEffect(() => {
    if (loading || isLanding) return;
    if (!user && !isPublic) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    if (user && user.status === "active" && isPublic) router.replace("/dashboard");
  }, [loading, user, isPublic, isLanding, pathname, router]);

  // The landing page does not wait for the session check: it renders at once and adapts its buttons.
  if (isLanding) return <div className="w-full">{children}</div>;

  if (loading) {
    return <div className="flex min-h-screen w-full items-center justify-center text-sm text-slate-400">Loading…</div>;
  }
  if (!user) {
    return isPublic ? <div className="w-full overflow-y-auto">{children}</div> : null;
  }
  if (user.status !== "active") {
    const disabled = user.status === "disabled";
    return (
      <div className="flex min-h-screen w-full items-center justify-center p-6">
        <div className="max-w-md space-y-4 rounded-xl border border-slate-200 bg-white p-8 text-center shadow-sm">
          {disabled ? <ShieldOff className="mx-auto h-10 w-10 text-red-500" /> : <Clock className="mx-auto h-10 w-10 text-amber-500" />}
          <h1 className="text-lg font-semibold text-slate-900">
            {disabled ? "Account disabled" : "Waiting for approval"}
          </h1>
          <p className="text-sm text-slate-500">
            {disabled
              ? "An administrator has disabled this account. Contact them if this is a mistake."
              : `Hello ${user.name}. Your account (${user.email}) must be approved by an administrator and given a role before you can use VITALYN.`}
          </p>
          <div className="flex justify-center gap-2">
            {!disabled && (
              <Button variant="outline" onClick={() => refreshUser()}>
                <RefreshCw className="mr-2 h-4 w-4" /> Check again
              </Button>
            )}
            <Button variant="ghost" onClick={() => signOut()}>
              <LogOut className="mr-2 h-4 w-4" /> Sign out
            </Button>
          </div>
        </div>
      </div>
    );
  }
  if (isPublic) return null;       // redirecting to the dashboard

  return (
    <>
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Topbar />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </>
  );
}
