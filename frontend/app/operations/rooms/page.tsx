"use client";

import { useCallback, useState } from "react";
import { usePoll } from "@/lib/hooks/usePoll";
import { listRooms, createRoom } from "@/lib/api/rooms";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Building2, Plus } from "lucide-react";

export default function RoomsPage() {
  const { data: rooms, loading, refetch: refresh } = usePoll(
    useCallback(() => listRooms(), []),
    30_000,
  );

  const [dialogOpen, setDialogOpen] = useState(false);
  const [roomNumber, setRoomNumber] = useState("");
  const [floor, setFloor] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCreate = async () => {
    if (!roomNumber.trim() || !floor.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await createRoom({ room_number: roomNumber.trim(), floor: floor.trim() });
      setDialogOpen(false);
      setRoomNumber("");
      setFloor("");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create room");
    } finally {
      setSaving(false);
    }
  };

  const handleClose = () => {
    if (saving) return;
    setDialogOpen(false);
    setRoomNumber("");
    setFloor("");
    setError(null);
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Rooms</h1>
          <p className="text-sm text-slate-500 mt-0.5">All configured hospital rooms</p>
        </div>
        <Button onClick={() => setDialogOpen(true)}>
          <Plus className="w-4 h-4 mr-1.5" />
          New Room
        </Button>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold text-slate-700">
            {loading ? "Loading…" : `${rooms?.length ?? 0} rooms`}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-3">{[1,2,3].map(i => <Skeleton key={i} className="h-14" />)}</div>
          ) : rooms && rooms.length > 0 ? (
            <div className="divide-y divide-slate-100">
              {rooms.map((room) => (
                <div key={room.id} className="flex items-center justify-between py-3">
                  <div className="flex items-center gap-3">
                    <Building2 className="w-4 h-4 text-slate-400" />
                    <div>
                      <p className="text-sm font-medium text-slate-800">Room {room.room_number}</p>
                      <p className="text-xs text-slate-400">Floor {room.floor}</p>
                    </div>
                  </div>
                  <Badge variant={room.status === "active" ? "success" : "muted"}>
                    {room.status}
                  </Badge>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-400 text-center py-8">No rooms configured yet.</p>
          )}
        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={handleClose}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New Room</DialogTitle>
            <DialogDescription>
              Add a room to the system. You can then upload videos against it on the Video Analysis page.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">
                Room number
              </label>
              <input
                type="text"
                value={roomNumber}
                onChange={(e) => setRoomNumber(e.target.value)}
                placeholder="e.g. 101"
                disabled={saving}
                className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-900 disabled:opacity-50"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">
                Floor
              </label>
              <input
                type="text"
                value={floor}
                onChange={(e) => setFloor(e.target.value)}
                placeholder="e.g. 1"
                disabled={saving}
                className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-900 disabled:opacity-50"
              />
            </div>

            {error && (
              <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                {error}
              </p>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={handleClose} disabled={saving}>
              Cancel
            </Button>
            <Button
              onClick={handleCreate}
              disabled={!roomNumber.trim() || !floor.trim() || saving}
            >
              {saving ? "Creating…" : "Create Room"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
