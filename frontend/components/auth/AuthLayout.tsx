"use client";

import { useRef, type ReactNode } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";

// Same 3D ward as the landing page, held still on the "watching" view. Wide screens only.
const WardCanvas = dynamic(() => import("@/components/landing/WardCanvas"), { ssr: false });

/** Shared field and button styles for the sign-in pages (landing palette). */
export const authField =
  "mt-1.5 w-full rounded-lg border border-line bg-paper px-3.5 py-2.5 text-[15px] text-ink placeholder:text-ink-muted/60 transition-colors focus:border-ink focus:outline-none disabled:opacity-50";
export const authLabel = "block text-[13px] font-medium text-ink";
export const authButton =
  "inline-flex w-full items-center justify-center gap-2 rounded-full bg-ink px-6 py-3 text-sm font-medium text-paper transition-colors hover:bg-vital disabled:cursor-not-allowed disabled:opacity-50";

export function AuthError({ children }: { children: ReactNode }) {
  return <p role="alert" className="border-l-2 border-alert bg-paper px-3 py-2 text-sm text-alert">{children}</p>;
}

export function AuthLayout({ kicker, title, subtitle, children }: {
  kicker: string; title: string; subtitle: string; children: ReactNode;
}) {
  const still = useRef(2);            // chapter 2 of the landing story: a patient lying in bed, watched

  return (
    <div className="grid min-h-screen bg-bone font-sans text-ink lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
      <div className="flex flex-col px-6 py-6 sm:px-12">
        <header className="flex items-center justify-between">
          <Link href="/" className="font-display text-2xl tracking-tight">Vitalyn</Link>
          <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-ink-muted transition-colors hover:text-ink">
            <ArrowLeft className="h-4 w-4" /> Back to site
          </Link>
        </header>

        <main className="flex flex-1 items-center py-12">
          <div className="w-full max-w-sm">
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-muted">{kicker}</p>
            <h1 className="mt-3 font-display text-4xl leading-tight tracking-tight">{title}</h1>
            <p className="mt-3 text-[15px] leading-relaxed text-ink-muted">{subtitle}</p>
            <div className="mt-8">{children}</div>
          </div>
        </main>

        <footer className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-muted">
          Research prototype · fictional data · not clinically validated
        </footer>
      </div>

      <aside className="relative hidden border-l border-line bg-bone lg:block" aria-hidden>
        <div className="absolute inset-0">
          <WardCanvas progress={still} />
        </div>
        <p className="absolute bottom-6 left-8 max-w-xs font-display text-xl leading-snug text-ink">
          Lying in bed is normal. <em className="text-vital">A fall is not.</em>
        </p>
      </aside>
    </div>
  );
}
