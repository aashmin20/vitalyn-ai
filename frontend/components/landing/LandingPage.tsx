"use client";

import { useMemo, useRef, type ReactNode, type RefObject } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, BedDouble, CalendarDays, ScrollText, ShieldCheck, Video } from "lucide-react";
import { useAuth } from "@/components/auth/AuthProvider";
import { useChapterProgress } from "./useChapterProgress";

// The 3D scene is loaded only on this page and only in the browser.
const WardCanvas = dynamic(() => import("./WardCanvas"), { ssr: false });

const FEATURES = [
  { icon: ShieldCheck, title: "Staff roles and audit", body: "Sign-in for administrators, doctors, nurses and reception. Accounts are approved by an administrator, and every change is written to an audit log." },
  { icon: BedDouble, title: "Admissions, transfers, discharge", body: "Admit to a free bed, transfer between beds, discharge with a summary. Beds go to cleaning before the next patient." },
  { icon: CalendarDays, title: "Outpatient appointments", body: "Doctor schedules, bookable slots without double-booking, and a queue from check-in to completed consultation." },
  { icon: Video, title: "Live fall monitoring", body: "A phone or webcam registered to each patient. Several patients watched at once, with potential falls raised to staff." },
  { icon: ScrollText, title: "Ward board", body: "Every room and bed at a glance: who is in it, whose camera is live, and where an alert is waiting." },
];

function Reveal({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ amount: 0.4, once: false }}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}

function Chapter({ id, refEl, index, kicker, title, children }: {
  id: string; refEl: RefObject<HTMLElement>; index: string; kicker: string; title: string; children: ReactNode;
}) {
  return (
    <section id={id} ref={refEl} className="flex min-h-screen items-center px-5 sm:px-10 lg:px-16">
      <Reveal className="w-full max-w-md rounded-2xl border border-line bg-paper/90 p-6 backdrop-blur-sm sm:p-8 max-lg:mt-[42vh]">
        <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-muted">
          <span className="text-vital">{index}</span> · {kicker}
        </p>
        <h2 className="mt-3 font-display text-3xl leading-tight text-ink sm:text-4xl">{title}</h2>
        <div className="mt-4 space-y-3 text-[15px] leading-relaxed text-ink-muted">{children}</div>
      </Reveal>
    </section>
  );
}

export default function LandingPage() {
  const { user } = useAuth();
  const signedIn = !!user && user.status === "active";
  const container = useRef<HTMLDivElement>(null);
  const hero = useRef<HTMLElement>(null);
  const admit = useRef<HTMLElement>(null);
  const watch = useRef<HTMLElement>(null);
  const alertRef = useRef<HTMLElement>(null);
  const overview = useRef<HTMLElement>(null);
  const sections = useMemo(() => [hero, admit, watch, alertRef, overview], []);
  const progress = useChapterProgress(container, sections);

  const primary = signedIn
    ? { href: "/dashboard", label: "Open dashboard" }
    : { href: "/login", label: "Sign in" };

  return (
    <div ref={container} className="relative h-screen overflow-y-auto overflow-x-hidden bg-bone font-sans text-ink">
      {/* nav */}
      <header className="sticky top-0 z-30 border-b border-line/70 bg-bone/85 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 sm:px-10">
          <Link href="/" className="flex items-baseline gap-2">
            <span className="font-display text-2xl tracking-tight">Vitalyn</span>
            <span className="hidden font-mono text-[10px] uppercase tracking-[0.2em] text-ink-muted sm:inline">Intelligence that cares</span>
          </Link>
          <nav className="flex items-center gap-1 text-sm sm:gap-6">
            <a href="#admit" className="hidden text-ink-muted hover:text-ink md:inline">How it works</a>
            <a href="#features" className="hidden text-ink-muted hover:text-ink md:inline">Features</a>
            <a href="#safety" className="hidden text-ink-muted hover:text-ink md:inline">Safety</a>
            <Link href={primary.href} className="rounded-full bg-ink px-4 py-2 text-sm font-medium text-paper transition-colors hover:bg-vital">
              {primary.label}
            </Link>
          </nav>
        </div>
      </header>

      {/* the 3D ward stays fixed behind the story */}
      <div className="pointer-events-none sticky top-0 -mt-16 h-screen">
        {/* On wide screens the scene takes the right side; its left edge fades into the page. */}
        <div className="absolute inset-x-0 top-16 bottom-[50%] lg:bottom-0 lg:top-0 lg:left-[34%] lg:[mask-image:linear-gradient(to_right,transparent,black_14%)]">
          <WardCanvas progress={progress} />
        </div>
      </div>

      <div className="relative z-10 -mt-[100vh]">
        {/* hero */}
        <section ref={hero} className="flex min-h-screen items-end px-5 pb-16 pt-24 sm:px-10 lg:items-center lg:px-16 lg:pb-0">
          <div className="max-w-xl">
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-muted">Hospital management · AI fall monitoring</p>
            <h1 className="mt-5 font-display text-5xl leading-[1.02] tracking-tight text-ink sm:text-6xl lg:text-7xl">
              A calmer ward,<br />with an eye on <em className="text-vital">every bed</em>.
            </h1>
            <p className="mt-6 max-w-md text-lg leading-relaxed text-ink-muted">
              Vitalyn runs admissions, beds and appointments, and watches registered patients for potential falls, so staff hear about them sooner.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link href={primary.href} className="inline-flex items-center gap-2 rounded-full bg-ink px-6 py-3 text-sm font-medium text-paper transition-colors hover:bg-vital">
                {primary.label} <ArrowRight className="h-4 w-4" />
              </Link>
              <a href="#admit" className="rounded-full border border-ink/20 px-6 py-3 text-sm font-medium text-ink transition-colors hover:border-ink">
                See how it works
              </a>
            </div>
          </div>
        </section>

        <Chapter id="admit" refEl={admit} index="01" kicker="Admit" title="Register, admit, assign a bed.">
          <p>Reception registers the patient. Admission puts them in a free bed, which turns occupied on the ward board.</p>
          <p>Each admitted patient gets their own camera QR. Scan it once with a phone by the bed and that camera belongs to them.</p>
        </Chapter>

        <Chapter id="watch" refEl={watch} index="02" kicker="Watch" title="Lying in bed is not an emergency.">
          <p>The registered camera reads 17 body keypoints a few times a second. Ordinary rest, turning over and sitting up are expected and stay quiet.</p>
          <p>Several patients can be watched at once, each on their own camera.</p>
        </Chapter>

        <Chapter id="alert" refEl={alertRef} index="03" kicker="Alert" title="A potential fall reaches a person, fast.">
          <p>When the pattern looks like a fall, every signed-in nurse and doctor sees an alert with the patient and room.</p>
          <p>It is a <strong className="font-medium text-ink">potential</strong> event. A member of staff checks, acknowledges and resolves it, and their name is recorded.</p>
        </Chapter>

        {/* overview: the camera pulls back while the feature list scrolls in */}
        <section ref={overview} id="features" className="min-h-screen px-5 pb-24 pt-[55vh] sm:px-10 lg:px-16">
          <div className="mx-auto max-w-7xl rounded-3xl border border-line bg-paper p-6 sm:p-10">
            <Reveal>
              <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-muted"><span className="text-vital">04</span> · The whole hospital</p>
              <h2 className="mt-3 max-w-2xl font-display text-4xl leading-tight sm:text-5xl">One system from the front desk to the bedside.</h2>
            </Reveal>
            <div className="mt-10 grid gap-px overflow-hidden rounded-2xl border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
              {FEATURES.map((f) => (
                <div key={f.title} className="bg-paper p-6">
                  <f.icon className="h-5 w-5 text-vital" strokeWidth={1.6} />
                  <h3 className="mt-4 text-base font-semibold text-ink">{f.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-ink-muted">{f.body}</p>
                </div>
              ))}
              <div className="flex flex-col justify-between bg-ink p-6 text-paper">
                <p className="font-display text-2xl leading-snug">Ready to look around?</p>
                <Link href={primary.href} className="mt-6 inline-flex items-center gap-2 self-start rounded-full bg-paper px-5 py-2.5 text-sm font-medium text-ink transition-colors hover:bg-bone">
                  {primary.label} <ArrowRight className="h-4 w-4" />
                </Link>
              </div>
            </div>
          </div>
        </section>

        {/* honesty band */}
        <section id="safety" className="border-y border-line bg-bone px-5 py-16 sm:px-10 lg:px-16">
          <div className="mx-auto grid max-w-7xl gap-8 lg:grid-cols-[1fr_2fr]">
            <h2 className="font-display text-3xl leading-tight">What Vitalyn is, and is not.</h2>
            <ul className="grid gap-4 text-sm leading-relaxed text-ink-muted sm:grid-cols-2">
              <li className="border-l-2 border-vital pl-4"><span className="font-medium text-ink">A research prototype.</span> Built for demonstration and study, not for clinical use.</li>
              <li className="border-l-2 border-vital pl-4"><span className="font-medium text-ink">Fictional patients only.</span> No real patient information should be entered.</li>
              <li className="border-l-2 border-alert pl-4"><span className="font-medium text-ink">Not clinically validated.</span> Fall detection can miss falls and raise false alarms.</li>
              <li className="border-l-2 border-alert pl-4"><span className="font-medium text-ink">People decide.</span> Every alert is a potential event for staff to review.</li>
            </ul>
          </div>
        </section>

        <footer className="bg-bone px-5 py-10 sm:px-10 lg:px-16">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 text-xs text-ink-muted">
            <span className="font-display text-lg text-ink">Vitalyn</span>
            <span>The 3D ward above is an illustration, not camera footage.</span>
            <span className="font-mono uppercase tracking-[0.18em]">Academic prototype</span>
          </div>
        </footer>
      </div>
    </div>
  );
}
