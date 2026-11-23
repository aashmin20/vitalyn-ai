"use client";

import { useCallback, useState } from "react";
import { Building2, Plus } from "lucide-react";
import { usePoll } from "@/lib/hooks/usePoll";
import { addBeds, createRoom } from "@/lib/api/rooms";
import { getWardBoard, setBedStatus, setRoomStatus, type BoardBed, type BoardRoom, type WardBoard } from "@/lib/api/adt";
import { describeApiError } from "@/lib/api/patients";
import { useAuth } from "@/components/auth/AuthProvider";
import {
  AvailabilityBar, BED_DOT, BED_LABEL, BED_ORDER, BED_STYLE, BedTile, type SettableBedState,
} from "@/components/beds/BedTile";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

const INPUT =
  "w-full rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-900 disabled:opacity-50";

/** "4" → {count: 4}; "A, B, C" → {bed_numbers: [...]}; "" → null (no beds). */
function parseBeds(text: string): { count?: number; bed_numbers?: string[] } | null | "invalid" {
  const t = text.trim();
  if (!t) return null;
  if (/^\d+$/.test(t)) {
    const n = Number(t);
    return n >= 1 && n <= 50 ? { count: n } : "invalid";
  }
  const names = t.split(",").map((s) => s.trim()).filter(Boolean);
  return names.length && new Set(names).size === names.length ? { bed_numbers: names } : "invalid";
}

const BEDS_HINT = "A number (e.g. 4 → beds 1–4) or different names separated by commas (e.g. A, B, C).";

export default function RoomsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const { data: board, loading, error, refetch } = usePoll<WardBoard>(useCallback(() => getWardBoard(), []), 10_000);

  const [message, setMessage] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  // New room dialog
  const [roomOpen, setRoomOpen] = useState(false);
  const [roomNumber, setRoomNumber] = useState("");
  const [floor, setFloor] = useState("");
  const [roomBeds, setRoomBeds] = useState("");
  const [dialogError, setDialogError] = useState<string | null>(null);

  // Add beds dialog
  const [bedsFor, setBedsFor] = useState<BoardRoom | null>(null);
  const [bedsText, setBedsText] = useState("");

  const run = async (fn: () => Promise<string | void>) => {
    setBusy(true);
    setMessage(null);
    try {
      const text = await fn();
      if (text) setMessage({ kind: "ok", text });
      refetch();
    } catch (e) {
      setMessage({ kind: "err", text: describeApiError(e) });
    } finally {
      setBusy(false);
    }
  };

  const closeRoom = () => {
    if (busy) return;
    setRoomOpen(false);
    setRoomNumber("");
    setFloor("");
    setRoomBeds("");
    setDialogError(null);
  };

  const submitRoom = async () => {
    const beds = parseBeds(roomBeds);
    if (beds === "invalid") return setDialogError(BEDS_HINT);
    setBusy(true);
    setDialogError(null);
    try {
      const room = await createRoom({ room_number: roomNumber.trim(), floor: floor.trim() });
      let added = 0;
      if (beds) added = (await addBeds(room.id, beds)).length;
      setBusy(false);
      closeRoom();
      setMessage({ kind: "ok", text: `Room ${room.room_number} created${added ? ` with ${added} bed${added > 1 ? "s" : ""}` : ""}.` });
      refetch();
    } catch (e) {
      setDialogError(describeApiError(e));
      setBusy(false);
      refetch();
    }
  };

  const submitBeds = async () => {
    if (!bedsFor) return;
    const beds = parseBeds(bedsText);
    if (!beds || beds === "invalid") return setDialogError(BEDS_HINT);
    setBusy(true);
    setDialogError(null);
    try {
      const created = await addBeds(bedsFor.id, beds);
      setMessage({ kind: "ok", text: `Added bed ${created.map((b) => b.bed_number).join(", ")} to room ${bedsFor.room_number}.` });
      setBedsFor(null);
      setBedsText("");
      refetch();
    } catch (e) {
      setDialogError(describeApiError(e));
    } finally {
      setBusy(false);
    }
  };

  const changeBed = (bed: BoardBed, status: SettableBedState) =>
    run(async () => {
      await setBedStatus(bed.id, status);
      return `Bed ${bed.bed_number} is now ${BED_LABEL[status].toLowerCase()}.`;
    });

  const changeRoom = (room: BoardRoom, status: SettableBedState) =>
    run(async () => {
      const r = await setRoomStatus(room.id, status);
      const parts = [
        r.changed.length
          ? `Room ${room.room_number}: ${r.changed.length} bed${r.changed.length > 1 ? "s" : ""} set to ${BED_LABEL[status].toLowerCase()}`
          : `Room ${room.room_number}: no vacant beds to change`,
      ];
      if (r.skipped_occupied.length) parts.push(`bed ${r.skipped_occupied.join(", ")} skipped (occupied)`);
      return parts.join("; ") + ".";
    });

  const totalBeds = board ? BED_ORDER.reduce((n, s) => n + board.counts[s], 0) : 0;

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Rooms and beds</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Bed availability by room. A bed is occupied only while an admitted patient is in it.
          </p>
        </div>
        {isAdmin && (
          <Button onClick={() => setRoomOpen(true)}>
            <Plus className="w-4 h-4 mr-1.5" /> New room
          </Button>
        )}
      </div>

      {board && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {BED_ORDER.map((s) => (
            <div key={s} className={cn("rounded-lg border px-4 py-3", BED_STYLE[s])}>
              <p className="flex items-center gap-1.5 text-xs text-slate-600">
                <span className={cn("h-2 w-2 rounded-full", BED_DOT[s])} /> {BED_LABEL[s]}
              </p>
              <p className="mt-1 text-2xl font-semibold text-slate-900">
                {board.counts[s]}
                <span className="ml-1 text-xs font-normal text-slate-400">/ {totalBeds}</span>
              </p>
            </div>
          ))}
        </div>
      )}

      {message && (
        <p className={cn("rounded px-3 py-2 text-sm",
          message.kind === "ok" ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-600")}>
          {message.text}
        </p>
      )}

      {loading ? (
        <Skeleton className="h-48" />
      ) : error || !board ? (
        <p className="text-sm text-red-600">Could not load rooms. Is the backend running?</p>
      ) : board.rooms.length === 0 ? (
        <p className="py-8 text-center text-sm text-slate-400">
          No rooms yet.{isAdmin ? " Use New room to add one with its beds." : " An admin can add rooms."}
        </p>
      ) : (
        board.rooms.map((room) => (
          <Card key={room.id}>
            <CardContent className="space-y-3 p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <Building2 className="h-5 w-5 text-slate-400" />
                  <div>
                    <p className="text-sm font-semibold text-slate-800">
                      Room {room.room_number} <span className="font-normal text-slate-400">· Floor {room.floor}</span>
                    </p>
                    <p className="text-xs text-slate-500">
                      {room.beds.length} bed{room.beds.length === 1 ? "" : "s"}
                      {room.beds.length > 0 && <> · {room.summary.available} vacant · {room.summary.occupied} occupied</>}
                      {room.summary.cleaning > 0 && <> · {room.summary.cleaning} cleaning</>}
                      {room.summary.maintenance > 0 && <> · {room.summary.maintenance} maintenance</>}
                    </p>
                  </div>
                </div>
                {isAdmin && (
                  <div className="flex flex-wrap gap-1">
                    <Button size="sm" variant="outline" disabled={busy}
                      onClick={() => { setDialogError(null); setBedsText(""); setBedsFor(room); }}>
                      <Plus className="mr-1 h-3.5 w-3.5" /> Add beds
                    </Button>
                    {room.beds.length > 0 && (
                      <>
                        <Button size="sm" variant="ghost" disabled={busy} onClick={() => changeRoom(room, "cleaning")}>Room cleaning</Button>
                        <Button size="sm" variant="ghost" disabled={busy} onClick={() => changeRoom(room, "maintenance")}>Room maintenance</Button>
                        <Button size="sm" variant="ghost" disabled={busy} onClick={() => changeRoom(room, "available")}>Room ready</Button>
                      </>
                    )}
                  </div>
                )}
              </div>
              <AvailabilityBar summary={room.summary} />
              {room.beds.length === 0 ? (
                <p className="text-xs text-slate-400">No beds in this room yet.</p>
              ) : (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {room.beds.map((bed) => (
                    <BedTile key={bed.id} bed={bed} canChange={isAdmin} busy={busy} onChange={changeBed} />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        ))
      )}

      <Dialog open={roomOpen} onOpenChange={closeRoom}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New room</DialogTitle>
            <DialogDescription>Add a room and, optionally, its beds. New beds start vacant.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <label className="block text-sm font-medium text-slate-700">
              Room number
              <input className={cn(INPUT, "mt-1.5")} value={roomNumber} onChange={(e) => setRoomNumber(e.target.value)}
                placeholder="e.g. 201" disabled={busy} />
            </label>
            <label className="block text-sm font-medium text-slate-700">
              Floor
              <input className={cn(INPUT, "mt-1.5")} value={floor} onChange={(e) => setFloor(e.target.value)}
                placeholder="e.g. 2" disabled={busy} />
            </label>
            <label className="block text-sm font-medium text-slate-700">
              Beds (optional)
              <input className={cn(INPUT, "mt-1.5")} value={roomBeds} onChange={(e) => setRoomBeds(e.target.value)}
                placeholder="e.g. 4   or   A, B, C" disabled={busy} />
              <span className="mt-1 block text-xs font-normal text-slate-400">{BEDS_HINT}</span>
            </label>
            {dialogError && (
              <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">{dialogError}</p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={closeRoom} disabled={busy}>Cancel</Button>
            <Button onClick={submitRoom} disabled={!roomNumber.trim() || !floor.trim() || busy}>
              {busy ? "Creating…" : "Create room"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!bedsFor} onOpenChange={() => !busy && setBedsFor(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add beds to room {bedsFor?.room_number}</DialogTitle>
            <DialogDescription>
              Existing beds: {bedsFor?.beds.map((b) => b.bed_number).join(", ") || "none"}. New beds start vacant.
            </DialogDescription>
          </DialogHeader>
          <label className="block text-sm font-medium text-slate-700">
            Beds
            <input className={cn(INPUT, "mt-1.5")} value={bedsText} onChange={(e) => setBedsText(e.target.value)}
              placeholder="e.g. 2   or   C, D" disabled={busy} autoFocus />
            <span className="mt-1 block text-xs font-normal text-slate-400">{BEDS_HINT}</span>
          </label>
          {dialogError && (
            <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">{dialogError}</p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setBedsFor(null)} disabled={busy}>Cancel</Button>
            <Button onClick={submitBeds} disabled={!bedsText.trim() || busy}>{busy ? "Adding…" : "Add beds"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
