import { ClientApiError, clientApi } from "./clientApi";

export type ListPayload<T> = T[] | { results?: T[]; data?: T[] };

export function asList<T>(payload: ListPayload<T> | null | undefined): T[] {
  if (!payload) return [];
  return Array.isArray(payload) ? payload : payload.results ?? payload.data ?? [];
}

export function apiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ClientApiError) {
    const fields = error.fieldErrors();
    const fieldMessages = Object.entries(fields).map(([key, value]) => `${key}: ${value}`);
    if (fieldMessages.length) return fieldMessages.join(" · ");
    return error.message || fallback;
  }
  return error instanceof Error ? error.message : fallback;
}

export function formatCents(cents: number | null | undefined): string {
  const value = Number(cents ?? 0);
  const kes = new Intl.NumberFormat("en-KE", {
    style: "currency",
    currency: "KES",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value / 100);
  return `${kes} (${new Intl.NumberFormat("en-KE").format(value)} cents)`;
}

export function formatWhen(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-KE", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: value.includes("T") ? "2-digit" : undefined,
    minute: value.includes("T") ? "2-digit" : undefined,
  }).format(date);
}

export function humanize(value: string | null | undefined): string {
  if (!value) return "—";
  return value.toLowerCase().replace(/[_-]+/g, " ").replace(/\b\w/g, letter => letter.toUpperCase());
}

export async function getList<T>(path: string, params?: Record<string, string | number | undefined>) {
  const response = await clientApi.get<ListPayload<T>>(path, { params });
  return asList(response.data);
}
