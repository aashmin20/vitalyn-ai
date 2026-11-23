import { apiFetch } from "./client";
import type { Room, Bed } from "../types";

export const listRooms = () => apiFetch<Room[]>("/api/v1/rooms");
export const getRoom = (id: string) => apiFetch<Room>(`/api/v1/rooms/${id}`);
export const createRoom = (data: { room_number: string; floor: string; status?: string }) =>
  apiFetch<Room>("/api/v1/rooms", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
export const listRoomBeds = (roomId: string) =>
  apiFetch<Bed[]>(`/api/v1/rooms/${roomId}/beds`);
export const listBeds = () => apiFetch<Bed[]>("/api/v1/beds");
/** Admin: add beds to a room, either by names (["A","B"]) or a count (auto-numbered). */
export const addBeds = (roomId: string, data: { bed_numbers?: string[]; count?: number }) =>
  apiFetch<Bed[]>(`/api/v1/rooms/${roomId}/beds`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
