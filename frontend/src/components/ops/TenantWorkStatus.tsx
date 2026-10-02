"use client";

import { useEffect, useState } from "react";
import { apiErrorMessage, formatWhen, getList, humanize } from "@/lib/opsApi";
import "./ops.css";

type WorkOrder = {
  id: number | string;
  status: string;
  assigned_at?: string | null;
  completed_at?: string | null;
};

type MaintenanceRequestRow = {
  id: number | string;
  title: string;
  description: string;
  status: string;
  priority_class: number;
  emergency_override: boolean;
  created_at: string;
  completed_at?: string | null;
  closed_at?: string | null;
  work_order?: WorkOrder | null;
};

export default function TenantWorkStatus() {
  const [rows, setRows] = useState<MaintenanceRequestRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    void getList<MaintenanceRequestRow>("/api/v1/maintenance/requests/")
      .then(data => {
        if (!cancelled) setRows(data);
      })
      .catch(loadError => {
        if (!cancelled) setError(apiErrorMessage(loadError, "Work order status couldn’t be loaded."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="ops-panel" id="work-orders">
      <div className="ops-heading">
        <div>
          <span className="ops-kicker">WORK ORDERS</span>
          <h2>Request status</h2>
          <p>Priority and progress recorded by your property team. You can’t assign or close these yourself.</p>
        </div>
      </div>
      {loading && <p className="ops-status">Loading work orders…</p>}
      {error && <p className="ops-alert" role="alert">{error}</p>}
      {!loading && !error && rows.length === 0 && (
        <div className="ops-empty">
          <strong>No work orders yet</strong>
          <p>When the office opens a maintenance request for your home, its status will show here.</p>
        </div>
      )}
      {rows.length > 0 && (
        <div className="ops-table-wrap">
          <table className="ops-table">
            <thead>
              <tr><th>Request</th><th>Priority</th><th>Status</th><th>Work order</th><th>Updated</th></tr>
            </thead>
            <tbody>
              {rows.map(row => (
                <tr key={row.id}>
                  <td>
                    <strong>{row.title}</strong>
                    <div className="ops-note">{row.description}</div>
                  </td>
                  <td>
                    <span className={`ops-pill ${row.emergency_override ? "is-hot" : ""}`}>
                      {row.emergency_override ? "Emergency · " : ""}Class {row.priority_class}
                    </span>
                  </td>
                  <td>{humanize(row.status)}</td>
                  <td>{row.work_order ? humanize(row.work_order.status) : "—"}</td>
                  <td>{formatWhen(row.closed_at || row.completed_at || row.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
