import { apiFetch } from "./client";
import type { CurrentOccupancy, OccupancyRecord } from "../types";

export const getCurrentOccupancy = () =>
  apiFetch<CurrentOccupancy[]>("/api/v1/occupancy/current");

export const getOccupancyHistory = () =>
  apiFetch<OccupancyRecord[]>("/api/v1/occupancy/history");

export const getBedOccupancy = (bedId: string) =>
  apiFetch<OccupancyRecord[]>(`/api/v1/beds/${bedId}/occupancy`);
