"use client";

import { useCallback, useRef, useState } from "react";
import { Upload, Film, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { uploadVideo } from "@/lib/api/jobs";
import type { Room } from "@/lib/types";

interface Props {
  rooms: Room[];
  onJobCreated: (jobId: string) => void;
}

const ALLOWED = [".mp4", ".avi", ".mov", ".mkv"];
const MAX_MB = 500;

export function VideoUploader({ rooms, onJobCreated }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [roomId, setRoomId] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadPct, setUploadPct] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const validateFile = (f: File): string | null => {
    const ext = "." + f.name.split(".").pop()?.toLowerCase();
    if (!ALLOWED.includes(ext)) return `Unsupported format. Allowed: ${ALLOWED.join(", ")}`;
    if (f.size > MAX_MB * 1024 * 1024) return `File exceeds ${MAX_MB} MB limit`;
    return null;
  };

  const handleFile = (f: File) => {
    const err = validateFile(f);
    if (err) { setError(err); return; }
    setFile(f);
    setError(null);
  };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  }, []);

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
  };

  const handleSubmit = async () => {
    if (!file || !roomId) return;
    setUploading(true);
    setError(null);
    try {
      const res = await uploadVideo(roomId, file, setUploadPct);
      onJobCreated(res.job_id);
      setFile(null);
      setRoomId("");
      setUploadPct(0);
      if (inputRef.current) inputRef.current.value = "";
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Room selector */}
      <div>
        <label className="block text-sm font-medium text-slate-700 mb-1.5">
          Room
        </label>
        <Select
          value={roomId}
          onChange={(e) => setRoomId(e.target.value)}
          placeholder="Select a room..."
          disabled={uploading}
        >
          {rooms.map((r) => (
            <option key={r.id} value={r.id}>
              Room {r.room_number} — Floor {r.floor}
            </option>
          ))}
        </Select>
      </div>

      {/* Drop zone */}
      <div
        className={cn(
          "border-2 border-dashed rounded-xl p-8 text-center transition-colors cursor-pointer",
          dragging ? "border-slate-900 bg-slate-50" : "border-slate-200 hover:border-slate-400",
          uploading && "pointer-events-none opacity-60",
        )}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          accept={ALLOWED.join(",")}
          onChange={onInputChange}
        />

        {file ? (
          <div className="flex items-center justify-center gap-3">
            <Film className="w-6 h-6 text-slate-700" />
            <div className="text-left">
              <p className="text-sm font-medium text-slate-800">{file.name}</p>
              <p className="text-xs text-slate-400">
                {(file.size / 1024 / 1024).toFixed(1)} MB
              </p>
            </div>
            <button
              className="ml-2 text-slate-400 hover:text-slate-700"
              onClick={(e) => { e.stopPropagation(); setFile(null); }}
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        ) : (
          <div>
            <Upload className="w-8 h-8 text-slate-300 mx-auto mb-2" />
            <p className="text-sm text-slate-600 font-medium">
              Drag & drop or click to select
            </p>
            <p className="text-xs text-slate-400 mt-1">
              {ALLOWED.join(", ")} · max {MAX_MB} MB
            </p>
          </div>
        )}
      </div>

      {/* Upload progress */}
      {uploading && (
        <div>
          <div className="flex justify-between text-xs text-slate-500 mb-1">
            <span>Uploading…</span>
            <span>{uploadPct}%</span>
          </div>
          <Progress value={uploadPct} />
        </div>
      )}

      {/* Error */}
      {error && (
        <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      {/* Submit */}
      <Button
        onClick={handleSubmit}
        disabled={!file || !roomId || uploading}
        className="w-full"
      >
        {uploading ? "Uploading…" : "Start Analysis"}
      </Button>
    </div>
  );
}
