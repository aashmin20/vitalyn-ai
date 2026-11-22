import { apiFetch } from "./client";
import type { DashboardOverview, OccupancyTrend, EventSummary } from "../types";

export const getOverview = () =>
  apiFetch<DashboardOverview>("/api/v1/dashboard/overview");

export const getOccupancyTrends = () =>
  apiFetch<OccupancyTrend[]>("/api/v1/dashboard/occupancy-trends");

export const getEventSummary = () =>
  apiFetch<EventSummary>("/api/v1/dashboard/event-summary");
