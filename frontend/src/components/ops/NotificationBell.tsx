"use client";

import { useCallback, useEffect, useState } from "react";
import { clientApi } from "@/lib/clientApi";
import { apiErrorMessage, asList, formatWhen, type ListPayload } from "@/lib/opsApi";
import "./ops.css";

type NotificationRow = {
  id: number | string;
  type: string;
  title: string;
  body: string;
  read_at: string | null;
  created_at: string;
};

export default function NotificationBell({ className = "" }: { className?: string }) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<NotificationRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await clientApi.get<ListPayload<NotificationRow>>("/api/v1/notifications/");
      setRows(asList(response.data));
    } catch (loadError) {
      setError(apiErrorMessage(loadError, "Notifications couldn’t be loaded."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const unread = rows.filter(row => !row.read_at);

  async function markRead(id: number | string) {
    setBusy(true);
    setError("");
    try {
      const response = await clientApi.post<NotificationRow>(`/api/v1/notifications/${id}/read/`, {});
      setRows(current => current.map(row => row.id === id ? response.data : row));
    } catch (markError) {
      setError(apiErrorMessage(markError, "That notification couldn’t be marked read."));
    } finally {
      setBusy(false);
    }
  }

  async function markAll() {
    setBusy(true);
    setError("");
    try {
      await clientApi.post("/api/v1/notifications/read-all/", {});
      const readAt = new Date().toISOString();
      setRows(current => current.map(row => row.read_at ? row : { ...row, read_at: readAt }));
    } catch (markError) {
      setError(apiErrorMessage(markError, "Notifications couldn’t be marked read."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`ops-bell ${className}`}>
      <button
        type="button"
        className="ops-bell-button"
        aria-label={`Notifications, ${unread.length} unread`}
        aria-expanded={open}
        onClick={() => setOpen(value => !value)}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
          <path d="M6 9a6 6 0 1 1 12 0c0 7 3 7 3 9H3c0-2 3-2 3-9" />
          <path d="M10 20a2 2 0 0 0 4 0" />
        </svg>
        {unread.length > 0 && <span className="ops-bell-count">{unread.length}</span>}
      </button>
      {open && (
        <div className="ops-bell-popover" role="dialog" aria-label="Notifications">
          <div className="ops-actions">
            <strong>Notifications</strong>
            <button type="button" className="ops-button" onClick={() => void load()} disabled={loading}>Refresh</button>
            <button type="button" className="ops-button" onClick={() => void markAll()} disabled={busy || unread.length === 0}>Mark all read</button>
          </div>
          {loading && <p className="ops-status">Loading notifications…</p>}
          {error && <p className="ops-alert" role="alert">{error}</p>}
          {!loading && !error && rows.length === 0 && (
            <p className="ops-status">You’re all caught up. New rent and maintenance updates will appear here.</p>
          )}
          {rows.map(row => (
            <button
              type="button"
              key={row.id}
              className={`ops-note-row ${row.read_at ? "" : "is-unread"}`}
              onClick={() => void markRead(row.id)}
              disabled={busy || Boolean(row.read_at)}
            >
              <strong>{row.title}</strong>
              <small>{row.body || row.type}</small>
              <small>{formatWhen(row.created_at)}{row.read_at ? " · Read" : " · Unread"}</small>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
