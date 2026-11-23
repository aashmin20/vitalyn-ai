import { AlertTriangle, CheckCircle2, HelpCircle, ShieldAlert, Eye } from "lucide-react";
import type { FallAssessment as Assessment } from "@/lib/types";
import { cn } from "@/lib/utils";

const TONE = {
  normal: { box: "border-emerald-200 bg-emerald-50", text: "text-emerald-800", bar: "bg-emerald-600", icon: CheckCircle2, tag: "NORMAL" },
  low: { box: "border-amber-200 bg-amber-50", text: "text-amber-800", bar: "bg-amber-500", icon: Eye, tag: "LOW RISK" },
  medium: { box: "border-orange-400 bg-orange-50 ring-2 ring-orange-300", text: "text-orange-800", bar: "bg-orange-500", icon: AlertTriangle, tag: "MEDIUM RISK" },
  high: { box: "border-red-500 bg-red-600 text-white ring-4 ring-red-300 animate-pulse", text: "text-white", bar: "bg-white", icon: ShieldAlert, tag: "HIGH RISK" },
  uncertain: { box: "border-slate-200 bg-slate-50", text: "text-slate-700", bar: "bg-slate-400", icon: HelpCircle, tag: "UNCERTAIN" },
} as const;

const SOURCE: Record<string, string> = {
  bilstm: "BiLSTM fall probability",
  posture: "posture score",
  alert: "raised alert",
};

function Bar({ label, value, color, hint }: { label: string; value: number | null; color: string; hint?: string }) {
  return (
    <div>
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-slate-600">{label}</span>
        <span className="font-mono text-sm font-medium text-slate-900">{value === null ? "—" : `${value.toFixed(1)}%`}</span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-200">
        <div className={cn("h-full rounded-full transition-all duration-300", color)} style={{ width: `${value ?? 0}%` }} />
      </div>
      {hint && <p className="mt-1 text-[11px] text-slate-500">{hint}</p>}
    </div>
  );
}

/** Live fall-risk level (normal / low / medium / high) with the real signals behind it. */
export function FallAssessment({ assessment, retrained }: { assessment?: Assessment; retrained?: boolean }) {
  if (!assessment) return null;
  const tone = TONE[assessment.code] ?? TONE.uncertain;
  const Icon = tone.icon;
  const high = assessment.code === "high";
  return (
    <div className="space-y-3">
      <div className={cn("rounded-2xl border p-4 transition-colors", tone.box)} role={high ? "alert" : "status"} aria-live="assertive">
        <div className="flex items-start justify-between gap-3">
          <div className={cn("flex items-center gap-2", tone.text)}>
            <Icon className={cn("shrink-0", high ? "h-7 w-7" : "h-5 w-5")} />
            <div>
              <p className="font-mono text-[11px] tracking-widest opacity-80">FALL RISK · {tone.tag}</p>
              <p className={cn("font-display leading-tight", high ? "text-2xl font-semibold" : "text-xl")}>{assessment.label}</p>
            </div>
          </div>
          <div className={cn("text-right", tone.text)}>
            <p className={cn("font-mono font-semibold leading-none", high ? "text-4xl" : "text-3xl")}>
              {assessment.risk === null ? "—" : `${Math.round(assessment.risk)}%`}
            </p>
            {assessment.risk_source && (
              <p className="mt-1 text-[11px] opacity-80">from {SOURCE[assessment.risk_source] ?? assessment.risk_source}</p>
            )}
          </div>
        </div>
        <div className={cn("mt-3 h-2 overflow-hidden rounded-full", high ? "bg-white/30" : "bg-black/10")}>
          <div className={cn("h-full rounded-full transition-all duration-300", tone.bar)} style={{ width: `${assessment.risk ?? 0}%` }} />
        </div>
        <p className={cn("mt-2 text-xs", high ? "text-white/90" : "text-slate-600")}>{assessment.reason}</p>
      </div>

      <div className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 sm:grid-cols-2">
        <Bar
          label="BiLSTM fall probability"
          value={assessment.fall_confidence}
          color="bg-red-500"
          hint={assessment.fall_confidence === null
            ? "No value while the model has no valid window."
            : `${retrained === false ? "Original" : "Retrained"} model, mean of last two 5 s windows.`}
        />
        <Bar
          label="Posture score (lying lower than resting level)"
          value={assessment.posture?.score ?? null}
          color="bg-orange-500"
          hint={assessment.posture ? assessment.posture.reason : "Learning the person's resting position."}
        />
        <p className="text-[11px] text-slate-500 sm:col-span-2">
          Risk = the higher of the two. Bands: low 25%, medium 45%, high 75%. The posture score is a heuristic from body
          keypoints, not a probability. Not clinically validated — every alert needs human review.
        </p>
      </div>
    </div>
  );
}
