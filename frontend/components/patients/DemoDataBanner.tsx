import { Info } from "lucide-react";

export function DemoDataBanner() {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">
      <Info className="w-4 h-4 mt-0.5 shrink-0" />
      <p>
        <strong>Demo data only.</strong> Do not enter real patient information. This research prototype is not a
        clinical records system and is not clinically validated.
      </p>
    </div>
  );
}
