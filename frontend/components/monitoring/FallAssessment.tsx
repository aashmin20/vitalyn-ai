import { AlertTriangle, CheckCircle2, HelpCircle } from "lucide-react";
import type { FallAssessment as Assessment } from "@/lib/types";
import { cn } from "@/lib/utils";

const TONE = {
  normal: { box: "border-emerald-200 bg-emerald-50", text: "text-emerald-800", icon: CheckCircle2 },
  uncertain: { box: "border-amber-200 bg-amber-50", text: "text-amber-800", icon: HelpCircle },
  potential_fall: { box: "border-red-300 bg-red-50", text: "text-red-700", icon: AlertTriangle },
} as const;

function Bar({ label, value, color }: { label: string; value: number | null; color: string }) {
  return (
    <div>
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-slate-600">{label}</span>
        <span className="font-mono text-sm font-medium text-slate-900">{value === null ? "—" : `${value.toFixed(1)}%`}</span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-200">
        <div className={cn("h-full rounded-full transition-all duration-500", color)} style={{ width: `${value ?? 0}%` }} />
      </div>
    </div>
  );
}

/** The live three-way status with the model's own normal / fall percentages. */
export function FallAssessment({ assessment, retrained }: { assessment?: Assessment; retrained?: boolean }) {
  if (!assessment) return null;
  const tone = TONE[assessment.code];
  const Icon = tone.icon;
  return (
    <div className={cn("rounded-2xl border p-4", tone.box)} role="status" aria-live="polite">
      <div className={cn("flex items-center gap-2", tone.text)}>
        <Icon className="h-5 w-5 shrink-0" />
        <p className="font-display text-xl leading-tight">{assessment.label}</p>
      </div>
      <p className="mt-1 text-xs text-slate-600">{assessment.reason}</p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <Bar label="Normal activity confidence" value={assessment.normal_confidence} color="bg-emerald-600" />
        <Bar label="Potential fall confidence" value={assessment.fall_confidence} color="bg-red-500" />
      </div>
      <p className="mt-3 text-[11px] text-slate-500">
        {assessment.fall_confidence === null
          ? "No percentage while the model has no valid prediction."
          : `${retrained === false ? "Original" : "Retrained"} BiLSTM output, averaged over the last two 5-second windows.`}{" "}
        Not a clinical probability. Every alert needs human review.
      </p>
    </div>
  );
}
