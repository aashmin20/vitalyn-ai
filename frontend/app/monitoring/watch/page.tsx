"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { format, formatDistanceToNow } from "date-fns";
import {
  AlertTriangle,
  CameraOff,
  Laptop,
  Loader2,
  QrCode,
  Smartphone,
  Square,
  Unplug,
  Wifi,
  WifiOff,
  X,
} from "lucide-react";
import { usePoll } from "@/lib/hooks/usePoll";
import { useEventSource } from "@/lib/hooks/useEventSource";
import {
  getLiveSources,
  getLiveStatus,
  liveEventsUrl,
  liveSnapshotUrl,
  liveStreamUrl,
  startLive,
  stopLive,
} from "@/lib/api/live";
import {
  getPatientEvents,
  listPatients,
  monitorPatient,
  parseApiProblem,
  regenerateCameraLink,
  registerWebcam,
  stopMonitoring,
  unregisterCamera,
  type ApiProblem,
} from "@/lib/api/patients";
import { playAlertSound, primeAlertSound } from "@/lib/alertSound";
import { Select } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DemoDataBanner } from "@/components/patients/DemoDataBanner";
import { PatientQr } from "@/components/patients/PatientQr";
import { parseUtc } from "@/lib/utils";
import type { CameraLink, FallEvent, LiveFallEvent, LiveSources, LiveStatus, Patient } from "@/lib/types";

type SseMessage = ({ type: "fall_detected"; patient_id: string } & LiveFallEvent) | ({ type: "status" } & LiveStatus);

function WatchLive() {
  const params = useSearchParams();
  const [patientId, setPatientId] = useState(params.get("patient") ?? "");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [alarms, setAlarms] = useState<(LiveFallEvent & { patient_id: string })[]>([]);
  const [streamFailed, setStreamFailed] = useState(false);
  const [pairing, setPairing] = useState<{ link: CameraLink | null; note: string | null } | null>(null);
  const [changing, setChanging] = useState(false);          // "Change camera" panel
  const [camMapMac, setCamMapMac] = useState<number | undefined>(undefined);
  const [showSetup, setShowSetup] = useState(false);
  const [snapNonce, setSnapNonce] = useState(0);
  const [rehearsalFile, setRehearsalFile] = useState("");
  const attempted = useRef<string | null>(null);

  const { data: patients, refetch: refetchPatients } = usePoll<Patient[]>(
    useCallback(() => listPatients("admitted"), []),
    3_000,
  );
  const { data: status, refetch: refetchStatus } = usePoll<LiveStatus>(useCallback(() => getLiveStatus(), []), 2_000);
  const { data: sources } = usePoll<LiveSources>(useCallback(() => getLiveSources(), []), 30_000);
  const { data: events } = usePoll<FallEvent[] | null>(
    useCallback(() => (patientId ? getPatientEvents(patientId) : Promise.resolve(null)), [patientId]),
    5_000,
  );

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem("vitalyn.cameraMap") ?? "{}");
      if (typeof saved.mac === "number") setCamMapMac(saved.mac);
    } catch {
      /* automatic choice */
    }
  }, []);
  const saveMacIndex = (index: number) => {
    setCamMapMac(index);
    try {
      localStorage.setItem("vitalyn.cameraMap", JSON.stringify({ mac: index }));
    } catch {
      /* ignore */
    }
  };

  const cameras = sources?.cameras ?? [{ index: 0, label: "Default camera" }];
  const macIndex =
    camMapMac ?? (cameras.find((c) => !/iphone|ipad|android|phone/i.test(c.label)) ?? cameras[0]).index;

  const patient = patients?.find((p) => p.id === patientId) ?? null;
  const sessions = status?.sessions ?? [];
  const mySession = sessions.find((s) => s.patient_id === patientId) ?? null;
  const live = sessions.length > 0;
  const watching = !!mySession;
  const otherSessions = sessions.filter((s) => s.patient_id !== patientId);

  // ── opening the registered camera ─────────────────────────────────────────

  const openMonitoring = useCallback(
    async (target: Patient) => {
      setBusy(true);
      setProblem(null);
      primeAlertSound();
      try {
        await monitorPatient(target.id);
      } catch (e) {
        setProblem(parseApiProblem(e));
      } finally {
        setBusy(false);
        refetchStatus();
        refetchPatients();
      }
    },
    [refetchStatus, refetchPatients],
  );

  // Selecting a patient opens their registered camera straight away, once per selection.
  // It never replaces a session that is already monitoring someone.
  useEffect(() => {
    if (!patient || !status || busy) return;
    if (!patient.camera_kind) return;                                       // needs setup first
    const key = `${patient.id}:${patient.camera_kind}:${patient.camera_index ?? ""}:${patient.phone_online}`;
    if (watching) {                                                         // already live: remember it, so a
      attempted.current = key;                                              // later manual Stop does not reopen it
      return;
    }
    if (patient.camera_kind === "phone" && !patient.phone_online) return;   // wait for the phone to come online
    if (attempted.current === key) return;
    attempted.current = key;
    void openMonitoring(patient);
  }, [patient, status, busy, watching, openMonitoring]);

  useEffect(() => {
    attempted.current = null;
    setProblem(null);
    setStreamFailed(false);
    setPairing(null);
    setChanging(false);
  }, [patientId]);

  useEffect(() => {
    if (!streamFailed || !watching) return;
    const t = setTimeout(() => setStreamFailed(false), 3000);
    return () => clearTimeout(t);
  }, [streamFailed, watching]);

  // One feed for every monitored patient: a fall alarm must show up whichever patient is on screen.
  useEventSource<SseMessage>(live ? liveEventsUrl() : null, (msg) => {
    if (msg.type === "fall_detected" && msg.patient_id) {
      setAlarms((prev) => [msg, ...prev.filter((a) => a.id !== msg.id)].slice(0, 5));
      playAlertSound();
    }
  });

  // ── actions ───────────────────────────────────────────────────────────────

  const useWebcam = async () => {
    if (!patient) return;
    setBusy(true);
    setProblem(null);
    try {
      await registerWebcam(patient.id, macIndex);
      setChanging(false);
      setPairing(null);
      attempted.current = null;
    } catch (e) {
      setProblem(parseApiProblem(e));
    } finally {
      setBusy(false);
      refetchPatients();
    }
  };

  const startPairing = async () => {
    if (!patient) return;
    setBusy(true);
    setProblem(null);
    try {
      const r = await regenerateCameraLink(patient.id);
      setPairing({ link: r.camera_link, note: r.camera_link_note });
      attempted.current = null;
    } catch (e) {
      setProblem(parseApiProblem(e));
    } finally {
      setBusy(false);
      refetchPatients();
    }
  };

  const stop = async () => {
    if (!patient) return;
    setBusy(true);
    try {
      await stopMonitoring(patient.id);
    } catch (e) {
      setProblem(parseApiProblem(e));
    } finally {
      setBusy(false);
      refetchStatus();
    }
  };

  const stopOther = async (otherPatientId: string) => {
    setBusy(true);
    try {
      await stopMonitoring(otherPatientId);
    } catch (e) {
      setProblem(parseApiProblem(e));
    } finally {
      setBusy(false);
      refetchStatus();
    }
  };

  const unregister = async () => {
    if (!patient) return;
    setBusy(true);
    try {
      await unregisterCamera(patient.id);
      attempted.current = null;
    } catch (e) {
      setProblem(parseApiProblem(e));
    } finally {
      setBusy(false);
      refetchPatients();
      refetchStatus();
    }
  };

  const startRehearsal = async () => {
    if (!patient?.room) return setProblem({ message: "Select a patient with a room first." });
    setBusy(true);
    setProblem(null);
    try {
      await startLive(patient.room.id, rehearsalFile.trim(), patient.id);
    } catch (e) {
      setProblem(parseApiProblem(e));
    } finally {
      setBusy(false);
      refetchStatus();
    }
  };

  const warmingUp = watching && (mySession?.window_fill ?? 0) < (mySession?.window_required ?? 30);
  const needsSetup = !!patient && (!patient.camera_kind || changing);

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 flex flex-wrap items-center gap-3">
          Watch live
          {watching && <Badge variant="destructive">LIVE</Badge>}
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">Select a patient and their registered camera opens</p>
      </div>
      <DemoDataBanner />

      <Card>
        <CardContent className="p-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
          <label className="block text-xs font-medium text-slate-600">
            Patient
            <Select className="mt-1" value={patientId} onChange={(e) => setPatientId(e.target.value)}>
              <option value="">Select patient…</option>
              {patients?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.patient_code} · {p.name}
                </option>
              ))}
            </Select>
          </label>
          <div className="text-xs font-medium text-slate-600">
            Room
            <div className="mt-1 flex h-9 items-center rounded-md border border-slate-200 bg-slate-50 px-3 text-sm text-slate-700">
              {patient ? (patient.room ? `Room ${patient.room.room_number}` : "No room assigned") : "Filled in from the patient"}
            </div>
          </div>
        </CardContent>
      </Card>

      {otherSessions.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm">
          <span className="text-xs font-medium text-slate-500">
            {watching ? "Also monitoring" : "Monitoring now"} ({sessions.length}/{status?.max_sessions ?? "?"}):
          </span>
          {otherSessions.map((s) => {
            const who = patients?.find((p) => p.id === s.patient_id);
            return (
              <span key={s.job_id ?? s.patient_id} className="flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 py-1 pl-3 pr-1">
                <button type="button" className="text-xs font-medium text-slate-800" onClick={() => s.patient_id && setPatientId(s.patient_id)}>
                  {s.patient?.patient_code ?? who?.patient_code ?? "Patient"}
                  {s.patient?.room_number ? ` · Room ${s.patient.room_number}` : ""}
                </button>
                <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => s.patient_id && stopOther(s.patient_id)} disabled={busy} aria-label="Stop monitoring this patient">
                  <X className="h-3 w-3" />
                </Button>
              </span>
            );
          })}
        </div>
      )}

      {alarms.length > 0 && (
        <div className="space-y-2">
          {alarms.map((al) => {
            const who = patients?.find((p) => p.id === al.patient_id);
            return (
              <div key={al.id} className="flex items-center justify-between gap-4 rounded-lg border-2 border-red-500 bg-red-50 px-4 py-3">
                <div className="flex items-center gap-3">
                  <AlertTriangle className="h-6 w-6 shrink-0 text-red-600" />
                  <div>
                    <p className="font-semibold text-red-800">
                      Potential fall — {who ? `${who.patient_code}${who.room ? `, Room ${who.room.room_number}` : ""}` : "a monitored patient"}.
                      Human review required
                    </p>
                    <p className="text-xs text-red-700">
                      {al.source === "bilstm" ? "BiLSTM output" : "Posture heuristic score"} {(al.confidence * 100).toFixed(0)}% (not a
                      calibrated probability) · {formatDistanceToNow(parseUtc(al.detected_at), { addSuffix: true })}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {who && who.id !== patientId && (
                    <Button size="sm" variant="outline" onClick={() => setPatientId(who.id)}>View</Button>
                  )}
                  <Link href="/alerts/active">
                    <Button size="sm" variant="destructive">Review alert</Button>
                  </Link>
                  <Button
                    size="icon"
                    variant="ghost"
                    onClick={() => setAlarms((prev) => prev.filter((x) => x.id !== al.id))}
                    aria-label="Dismiss"
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-3">
          <Card>
            <CardContent className="p-0">
              <div className="relative aspect-video bg-slate-900 rounded-lg overflow-hidden flex items-center justify-center">
                {watching && !streamFailed ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    key={mySession?.job_id ?? "stream"}
                    src={liveStreamUrl(mySession?.job_id ?? "0", patientId)}
                    alt={`Live camera for ${patient?.patient_code}`}
                    className="h-full w-full object-contain"
                    onError={() => setStreamFailed(true)}
                  />
                ) : (
                  <div className="max-w-md space-y-3 p-6 text-center text-slate-300">
                    <ViewerMessage
                      patient={patient}
                      status={status}
                      busy={busy}
                      problem={problem}
                      streamFailed={streamFailed}
                      needsSetup={needsSetup}
                      onRetry={() => patient && openMonitoring(patient)}
                    />
                  </div>
                )}
                {watching && (mySession?.frames_captured ?? 0) === 0 && (
                  <div className="absolute inset-0 flex items-center justify-center bg-slate-900/80 text-sm text-slate-200">
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Waiting for the camera&apos;s first frame…
                  </div>
                )}
                {watching && (
                  <span className="absolute right-3 top-3 flex items-center gap-1.5 rounded-full bg-black/60 px-2.5 py-1 text-[11px] font-semibold text-white">
                    <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" /> LIVE
                  </span>
                )}
              </div>
            </CardContent>
          </Card>

          {watching && (
            <div className="flex justify-end">
              <Button size="sm" variant="destructive" onClick={stop} disabled={busy}>
                <Square className="mr-1.5 h-4 w-4" /> Stop monitoring
              </Button>
            </div>
          )}

          {/* One-time camera setup: Mac webcam or pair a phone */}
          {needsSetup && patient && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold text-slate-700">
                  {patient.camera_kind ? "Change camera" : `Register a camera for ${patient.patient_code}`}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-xs text-slate-500">
                  Do this once. Next time you select {patient.patient_code}, their camera opens by itself.
                </p>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <Button variant="outline" className="h-auto flex-col gap-1 py-4" onClick={useWebcam} disabled={busy}>
                    <Laptop className="h-5 w-5" />
                    Use this Mac&apos;s webcam
                    <span className="text-[11px] font-normal text-slate-500">
                      {cameras.find((c) => c.index === macIndex)?.label ?? `camera ${macIndex}`}
                    </span>
                  </Button>
                  <Button variant="outline" className="h-auto flex-col gap-1 py-4" onClick={startPairing} disabled={busy}>
                    <Smartphone className="h-5 w-5" />
                    Pair a phone
                    <span className="text-[11px] font-normal text-slate-500">scan a QR code once</span>
                  </Button>
                </div>
                {pairing && (
                  <div className="space-y-3 rounded-lg border border-slate-200 p-3">
                    {pairing.link ? (
                      <>
                        <PatientQr link={pairing.link} patientCode={patient.patient_code} roomNumber={patient.room?.room_number ?? null} />
                        <ol className="list-decimal space-y-0.5 pl-5 text-[11px] text-slate-500">
                          <li>Scan the QR with the phone&apos;s camera and open it in Safari (compass icon).</li>
                          <li>Accept the one-time certificate warning (Show Details, visit this website).</li>
                          <li>Leave that page open, prop the phone steady and keep the screen on.</li>
                        </ol>
                        <p className={`text-xs font-semibold ${patient.phone_online ? "text-emerald-700" : "text-amber-700"}`}>
                          {patient.phone_online ? "Phone connected. It is now registered to this patient." : "Waiting for the phone to scan…"}
                        </p>
                      </>
                    ) : (
                      <p className="rounded bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-900">
                        {pairing.note ?? "Phone gateway is off. Start the backend with VITALYN_PHONE_GATEWAY=1."}
                      </p>
                    )}
                  </div>
                )}
                {patient.camera_kind && (
                  <Button size="sm" variant="ghost" onClick={() => setChanging(false)}>Cancel</Button>
                )}
              </CardContent>
            </Card>
          )}

          {problem && (
            <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-600 break-words">{problem.message}</p>
          )}
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold text-slate-700">
                {patient ? `${patient.patient_code} · ${patient.name}, ${patient.age}` : "Patient details"}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {patient ? (
                <>
                  <Row label="Condition" value={patient.condition} />
                  <Row label="Doctor" value={patient.doctor?.name ?? "-"} />
                  <Row label="Room" value={patient.room ? `Room ${patient.room.room_number}` : "-"} />
                  <Row label="Admitted" value={format(parseUtc(patient.admitted_at), "MMM d, HH:mm")} />
                  <div className="flex items-start justify-between gap-3 border-t border-slate-100 pt-2">
                    <span className="text-slate-500">Camera</span>
                    <span className="text-right font-medium text-slate-900">
                      {patient.camera_kind ? (
                        <>
                          {patient.camera_label ?? patient.camera_kind}
                          {patient.camera_kind === "phone" && (
                            <span className={`mt-0.5 flex items-center justify-end gap-1 text-[11px] font-normal ${patient.phone_online ? "text-emerald-700" : "text-amber-700"}`}>
                              {patient.phone_online ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
                              {patient.phone_online ? "online" : "offline"}
                            </span>
                          )}
                        </>
                      ) : (
                        <span className="text-amber-700">Not registered</span>
                      )}
                    </span>
                  </div>
                  {patient.camera_kind && (
                    <div className="flex flex-wrap justify-end gap-2 pt-1">
                      <Button size="sm" variant="ghost" onClick={() => setChanging(true)}>Change</Button>
                      <Button size="sm" variant="ghost" className="text-red-600" onClick={unregister} disabled={busy}>
                        <Unplug className="mr-1 h-3.5 w-3.5" /> Unregister
                      </Button>
                    </div>
                  )}
                  {watching && (
                    <div className="space-y-2 border-t border-slate-100 pt-2">
                      <Row label="Person in view" value={mySession?.person_detected ? "Yes" : "No"} />
                      <Row
                        label="Fall model"
                        value={mySession?.model_guarded ? "Paused (no person)" : warmingUp ? "Warming up" : "Active"}
                      />
                      <Row label="Camera FPS" value={String(mySession?.capture_fps ?? 0)} />
                    </div>
                  )}
                  <Link href={`/patients/${patient.id}`} className="block pt-1 text-right text-xs text-slate-500 underline">
                    Full patient record
                  </Link>
                </>
              ) : (
                <p className="text-slate-400">No patient selected.</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                <AlertTriangle className="h-4 w-4" /> Potential falls
              </CardTitle>
            </CardHeader>
            <CardContent>
              {!events || events.length === 0 ? (
                <p className="py-3 text-center text-sm text-slate-400">None recorded.</p>
              ) : (
                <ul className="divide-y divide-slate-100">
                  {events.slice(0, 6).map((ev) => (
                    <li key={ev.id} className="flex items-center justify-between py-2 text-xs">
                      <span className="text-slate-700">
                        Score {(ev.confidence * 100).toFixed(0)}% <Badge variant="muted">{ev.status}</Badge>
                      </span>
                      <span className="text-slate-400">
                        {formatDistanceToNow(parseUtc(ev.started_at ?? ev.created_at), { addSuffix: true })}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              <p className="mt-2 text-[11px] text-slate-400">Every detection needs human review. Not clinically validated.</p>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Advanced camera setup (replaces the old Live Camera page) */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
        <button type="button" className="font-medium text-slate-700" onClick={() => { setShowSetup((v) => !v); setSnapNonce((n) => n + 1); }}>
          {showSetup ? "Hide" : "Show"} camera setup (advanced)
        </button>
        {showSetup && (
          <div className="mt-4 space-y-5">
            <div>
              <p className="text-xs font-medium text-slate-600">Which camera is this Mac&apos;s webcam?</p>
              <p className="text-[11px] text-slate-400">
                Previews open each camera for a few seconds and are not saved. Used when you pick &quot;Use this Mac&apos;s webcam&quot;.
              </p>
              {live ? (
                <p className="mt-2 text-xs text-amber-700">Stop monitoring first to preview cameras.</p>
              ) : (
                <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-3">
                  {cameras.map((c) => (
                    <div key={c.index} className="space-y-1">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={liveSnapshotUrl(c.index, snapNonce)}
                        alt={`Preview of camera ${c.index}`}
                        className="aspect-video w-full rounded bg-slate-100 object-cover"
                      />
                      <Button
                        size="sm"
                        className="w-full"
                        variant={macIndex === c.index ? "default" : "outline"}
                        onClick={() => saveMacIndex(c.index)}
                      >
                        {macIndex === c.index ? "Mac webcam (selected)" : `Camera ${c.index}: use as Mac webcam`}
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div>
              <p className="text-xs font-medium text-slate-600">Rehearse with a video file (no camera)</p>
              <div className="mt-1 flex gap-2">
                <input
                  value={rehearsalFile}
                  onChange={(e) => setRehearsalFile(e.target.value)}
                  placeholder="/path/inside/backend/uploads or datasets/video.mp4"
                  className="min-w-0 flex-1 rounded-md border border-slate-200 px-3 py-2 text-sm"
                />
                <Button size="sm" variant="outline" onClick={startRehearsal} disabled={busy || !rehearsalFile.trim() || !patient || live}>
                  Start
                </Button>
              </div>
              <p className="mt-1 text-[11px] text-slate-400">Plays for the selected patient like a camera. Must be under backend/uploads or datasets/.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ViewerMessage(props: {
  patient: Patient | null;
  status: LiveStatus | null;
  busy: boolean;
  problem: ApiProblem | null;
  streamFailed: boolean;
  needsSetup: boolean;
  onRetry: () => void;
}) {
  const { patient, busy, problem, streamFailed, needsSetup, onRetry } = props;
  const icon = <CameraOff className="mx-auto h-10 w-10 opacity-60" />;

  if (!patient) {
    return (
      <>
        {icon}
        <p className="text-sm">Select a patient to open their live camera.</p>
      </>
    );
  }
  if (streamFailed) {
    return (
      <>
        {icon}
        <p className="text-sm">Video stream interrupted. Reconnecting…</p>
      </>
    );
  }
  if (busy) {
    return (
      <>
        <Loader2 className="mx-auto h-8 w-8 animate-spin opacity-70" />
        <p className="text-sm">Opening {patient.patient_code}&apos;s camera…</p>
      </>
    );
  }
  if (!patient.camera_kind) {
    return (
      <>
        <QrCode className="mx-auto h-10 w-10 opacity-60" />
        <p className="text-sm">
          No camera is registered for {patient.patient_code} yet. Register one below. It is a one-time step.
        </p>
      </>
    );
  }
  if (needsSetup) {
    return (
      <>
        {icon}
        <p className="text-sm">Choose the new camera below.</p>
      </>
    );
  }
  if (patient.camera_kind === "phone" && !patient.phone_online) {
    return (
      <>
        <WifiOff className="mx-auto h-10 w-10 opacity-60" />
        <p className="text-sm">
          {patient.camera_label ?? "The phone"} is offline. Open {patient.patient_code}&apos;s camera link on the phone
          and leave that page open. This screen opens the camera as soon as the phone is back.
        </p>
      </>
    );
  }
  return (
    <>
      {icon}
      <p className="text-sm">{problem?.message ?? `${patient.patient_code}'s camera is not running.`}</p>
      <Button size="sm" onClick={onRetry}>Try again</Button>
    </>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <span className="text-slate-500">{label}</span>
      <span className="text-right font-medium text-slate-900">{value}</span>
    </div>
  );
}

export default function WatchLivePage() {
  return (
    <Suspense fallback={null}>
      <WatchLive />
    </Suspense>
  );
}
