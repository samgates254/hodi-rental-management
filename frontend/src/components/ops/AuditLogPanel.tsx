"use client";

import { useCallback, useEffect, useState } from "react";
import { apiErrorMessage, formatWhen, getList, humanize } from "@/lib/opsApi";
import "./ops.css";

type AuditRow = {
  id: number | string;
  actor: number | null;
  action: string;
  object_type: string;
  object_id: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export default function AuditLogPanel({ organizationId }: { organizationId: string }) {
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!organizationId) return;
    setLoading(true);
    setError("");
    try {
      const data = await getList<AuditRow>("/api/v1/audit/logs/", { organization: organizationId });
      setRows(data);
    } catch (loadError) {
      setRows([]);
      setError(apiErrorMessage(loadError, "Audit logs couldn’t be loaded."));
    } finally {
      setLoading(false);
    }
  }, [organizationId]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section className="ops-panel" id="audit">
      <div className="ops-heading">
        <div>
          <span className="ops-kicker">ORGANIZATION RECORD</span>
          <h2>Audit log</h2>
          <p>Server-written history for this organization. Nothing on this screen creates an audit entry.</p>
        </div>
        <button type="button" className="ops-button" onClick={() => void load()} disabled={loading}>
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>
      {error && <p className="ops-alert" role="alert">{error}</p>}
      {loading && !rows.length && <p className="ops-status">Loading audit log…</p>}
      {!loading && !error && rows.length === 0 && (
        <div className="ops-empty">
          <strong>No audit entries yet</strong>
          <p>Creates and updates that the server records will appear here.</p>
        </div>
      )}
      {rows.length > 0 && (
        <div className="ops-table-wrap">
          <table className="ops-table">
            <thead>
              <tr><th>When</th><th>Actor</th><th>Action</th><th>Resource</th><th>Details</th></tr>
            </thead>
            <tbody>
              {rows.map(row => (
                <tr key={row.id}>
                  <td>{formatWhen(row.created_at)}</td>
                  <td>{row.actor == null ? "System" : `User ${row.actor}`}</td>
                  <td>{humanize(row.action)}</td>
                  <td>{row.object_type} · {row.object_id}</td>
                  <td>{Object.keys(row.metadata ?? {}).length ? JSON.stringify(row.metadata) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
