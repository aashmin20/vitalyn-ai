import { apiFetch, apiUrl } from "./client";
import type { InferenceJob, JobResults, UploadResponse } from "../types";

export const listJobs = () =>
  apiFetch<InferenceJob[]>("/api/v1/jobs");

export const getJob = (id: string) =>
  apiFetch<InferenceJob>(`/api/v1/jobs/${id}`);

export const getJobResults = (id: string) =>
  apiFetch<JobResults>(`/api/v1/jobs/${id}/results`);

export async function uploadVideo(
  roomId: string,
  file: File,
  onProgress?: (pct: number) => void,
): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("room_id", roomId);
  formData.append("file", file);

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", apiUrl("/api/v1/videos/upload"));
    xhr.withCredentials = true;
    xhr.setRequestHeader("X-Requested-With", "vitalyn");

    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    });

    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText) as UploadResponse);
      } else {
        reject(new Error(`Upload failed: ${xhr.status} ${xhr.statusText}`));
      }
    });

    xhr.addEventListener("error", () => reject(new Error("Network error during upload")));
    xhr.send(formData);
  });
}

export const videoStreamUrl = (jobId: string) =>
  apiUrl(`/api/v1/videos/${jobId}/stream`);
