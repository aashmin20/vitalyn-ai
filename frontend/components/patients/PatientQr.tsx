"use client";

import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { Printer, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { CameraLink } from "@/lib/types";

interface Props {
  link: CameraLink;
  patientCode: string;
  roomNumber: string | null;
}

/** The patient's camera QR plus a print card that shows only the code and room (no name, no condition). */
export function PatientQr({ link, patientCode, roomNumber }: Props) {
  const [qr, setQr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    QRCode.toDataURL(link.url, { margin: 2, width: 320, errorCorrectionLevel: "M" })
      .then((u) => !cancelled && setQr(u))
      .catch(() => !cancelled && setQr(null));
    return () => {
      cancelled = true;
    };
  }, [link.url]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(link.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* the link is shown below and can be selected */
    }
  };

  return (
    <div className="space-y-3">
      <div className="print-area">
        <div className="mx-auto w-72 rounded-xl border border-slate-300 bg-white p-4 text-center">
          <p className="text-sm font-bold tracking-wide text-slate-900">VITALYN</p>
          <p className="text-xs text-slate-600">
            Patient {patientCode}
            {roomNumber ? ` · Room ${roomNumber}` : ""}
          </p>
          {qr ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={qr} alt={`Camera QR code for patient ${patientCode}`} className="mx-auto my-2 h-56 w-56" />
          ) : (
            <div className="mx-auto my-2 h-56 w-56 animate-pulse rounded bg-slate-100" />
          )}
          <p className="text-[11px] text-slate-500">Scan with the phone camera to start monitoring this patient.</p>
        </div>
      </div>

      <div className="flex flex-wrap justify-center gap-2">
        <Button size="sm" variant="outline" onClick={() => window.print()}>
          <Printer className="mr-1.5 h-4 w-4" /> Print card
        </Button>
        <Button size="sm" variant="outline" onClick={copy}>
          <Copy className="mr-1.5 h-4 w-4" /> {copied ? "Copied" : "Copy link"}
        </Button>
      </div>
      <p className="text-center text-[11px] text-slate-400">
        This QR is shown once and cannot be recovered. Regenerate it from the patient page if it is lost.
      </p>
    </div>
  );
}
