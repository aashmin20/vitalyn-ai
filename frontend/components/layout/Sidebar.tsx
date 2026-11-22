"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  Monitor,
  Video,
  Users,
  UserPlus,
  Upload,
  BedDouble,
  Building2,
  BarChart2,
  TrendingUp,
  AlertTriangle,
  CheckCircle2,
  Archive,
  ChevronDown,
  ShieldCheck,
  ScrollText,
  CalendarDays,
  Clock,
} from "lucide-react";
import { useState } from "react";
import { useAuth } from "@/components/auth/AuthProvider";
import type { Role } from "@/lib/api/auth";

interface NavItem {
  label: string;
  roles?: Role[];            // visible only to these roles (the server enforces; this just hides)
  href?: string;
  icon: React.ElementType;
  children?: { label: string; href: string; icon: React.ElementType }[];
}

const CLINICAL_ROLES: Role[] = ["admin", "doctor", "nurse"];

const NAV: NavItem[] = [
  {
    label: "Command Centre",
    href: "/dashboard",
    icon: LayoutDashboard,
  },
  {
    label: "Watch Live",
    href: "/monitoring/watch",
    roles: CLINICAL_ROLES,
    icon: Video,
  },
  {
    label: "Patients",
    icon: Users,
    children: [
      { label: "All patients", href: "/patients", icon: Users },
      { label: "Admit patient", href: "/patients/new", icon: UserPlus },
    ],
  },
  {
    label: "Outpatient (OPD)",
    icon: CalendarDays,
    children: [
      { label: "Appointments", href: "/appointments", icon: CalendarDays },
      { label: "Today's queue", href: "/appointments/queue", icon: Users },
      { label: "Doctor schedules", href: "/appointments/schedule", icon: Clock },
    ],
  },
  {
    label: "Hospital Ops",
    icon: Building2,
    children: [
      { label: "Ward board", href: "/ward", icon: BedDouble },
      { label: "Rooms and beds", href: "/operations/rooms", icon: Building2 },
    ],
  },
  {
    label: "Alerts & Events",
    roles: CLINICAL_ROLES,
    icon: AlertTriangle,
    children: [
      { label: "Active", href: "/alerts/active", icon: AlertTriangle },
      { label: "Acknowledged", href: "/alerts/acknowledged", icon: CheckCircle2 },
      { label: "Resolved", href: "/alerts/resolved", icon: Archive },
      { label: "Fall statistics", href: "/analytics/events", icon: BarChart2 },
    ],
  },
  {
    label: "Administration",
    roles: ["admin"],
    icon: ShieldCheck,
    children: [
      { label: "Staff", href: "/admin/staff", icon: ShieldCheck },
      { label: "Audit log", href: "/admin/audit", icon: ScrollText },
    ],
  },
  // The original upload-a-video research flow. Kept, but out of the main hospital workflow.
  {
    label: "Research tools",
    roles: ["admin", "doctor"],
    icon: Monitor,
    children: [
      { label: "Video analysis", href: "/monitoring/analysis", icon: Upload },
      { label: "Video review", href: "/monitoring/live", icon: Video },
      { label: "Occupancy trends", href: "/analytics/occupancy", icon: TrendingUp },
    ],
  },
];

function NavGroup({ item }: { item: NavItem }) {
  const pathname = usePathname();

  const isChildActive = item.children?.some((c) => pathname.startsWith(c.href));
  const [open, setOpen] = useState(isChildActive ?? true);

  if (item.href) {
    const active = pathname === item.href;
    return (
      <Link
        href={item.href}
        className={cn(
          "flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
          active
            ? "bg-slate-900 text-white"
            : "text-slate-700 hover:bg-slate-100 hover:text-slate-900",
        )}
      >
        <item.icon className="w-4 h-4 shrink-0" />
        {item.label}
      </Link>
    );
  }

  return (
    <div>
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-[13px] font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-colors"
      >
        <span className="flex items-center gap-3">
          <item.icon className="w-4 h-4 shrink-0" />
          {item.label}
        </span>
        <ChevronDown
          className={cn("w-3.5 h-3.5 transition-transform", open && "rotate-180")}
        />
      </button>

      {open && (
        <div className="mt-0.5 ml-4 pl-3 border-l border-slate-200 space-y-0.5">
          {item.children?.map((child) => {
            const matches = (h: string) => pathname === h || pathname.startsWith(h + "/");
            // The most specific sibling wins (so /patients/new does not also light up "All patients").
            const best = item.children!.filter((c) => matches(c.href)).sort((a, b) => b.href.length - a.href.length)[0];
            const active = best?.href === child.href;
            return (
              <Link
                key={child.href}
                href={child.href}
                className={cn(
                  "flex items-center gap-2.5 px-2 py-1.5 rounded-md text-sm transition-colors",
                  active
                    ? "bg-white text-slate-900 font-medium ring-1 ring-slate-200"
                    : "text-slate-500 hover:bg-slate-100 hover:text-slate-900",
                )}
              >
                <child.icon className="w-3.5 h-3.5 shrink-0" />
                {child.label}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function Sidebar() {
  const { user } = useAuth();
  const visible = NAV.filter((i) => !i.roles || (user && i.roles.includes(user.role)));
  return (
    <aside className="w-60 shrink-0 bg-slate-50 border-r border-slate-200 flex flex-col overflow-y-auto">
      {/* Wordmark */}
      <Link href="/" className="block px-5 pb-4 pt-5">
        <span className="font-display text-[26px] leading-none tracking-tight text-slate-900">Vitalyn</span>
        <span className="mt-1 block font-mono text-[9px] uppercase tracking-[0.2em] text-slate-500">Intelligence that cares</span>
      </Link>

      {/* Nav */}
      <nav className="flex-1 px-3 pb-4 space-y-1">
        {visible.map((item) => (
          <NavGroup key={item.label} item={item} />
        ))}
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-slate-200">
        <p className="font-mono text-[9px] uppercase tracking-[0.18em] text-slate-500">Academic prototype · v1.0</p>
      </div>
    </aside>
  );
}
