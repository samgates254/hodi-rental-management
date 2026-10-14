"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { clientApi, ClientApiError } from "@/lib/clientApi";
import { formatMinor } from "@/lib/money";

type Utility = {
  id: number;
  utility_type: string;
  service_description: string;
  unit: string | null;
  period_start: string;
  period_end: string;
  reading_start: string | null;
  reading_end: string | null;
  reading_unit: string;
  amount_minor: number;
  currency: string;
  due_date: string | null;
  status: string;
  document_available: boolean;
};

export default function TenantUtilitiesPage() {
  const [rows, setRows] = useState<Utility[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    clientApi
      .get<Utility[]>("/api/v1/utilities/me/")
      .then((response) => setRows(response.data))
      .catch((loadError) => {
        if (loadError instanceof ClientApiError && (loadError.status === 401 || loadError.status === 403)) {
          window.location.replace("/signin?type=tenant");
          return;
        }
        setError(loadError instanceof Error ? loadError.message : "Could not load utility records.");
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <main className="hodi-record">
      <div className="hodi-record-wrap">
        <Link className="hodi-record-back" href="/clients">← Tenant dashboard</Link>
        <p className="hodi-record-kicker">Your tenancy</p>
        <h1>Utilities for your tenancy</h1>
        <p className="hodi-record-lead">
          Only tenant-responsibility bills recorded for your current unit appear here. These amounts are separate from rent.
        </p>
        {error && <p className="hodi-record-alert" role="alert">{error}</p>}
        {loading && <p className="hodi-record-note">Loading utility records…</p>}
        {!loading && !error && (
          <div className="hodi-record-table-wrap">
            <table>
              <caption className="hodi-record-note">Recorded utility bills</caption>
              <thead>
                <tr>
                  <th>Service</th>
                  <th>Period</th>
                  <th>Readings</th>
                  <th>Amount</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <strong>{row.utility_type}</strong>
                      <p className="hodi-record-note">{row.service_description}{row.unit ? ` · ${row.unit}` : ""}</p>
                    </td>
                    <td>{row.period_start} to {row.period_end}</td>
                    <td>{row.reading_start ?? "—"} → {row.reading_end ?? "—"} {row.reading_unit}</td>
                    <td>{formatMinor(row.amount_minor, row.currency || "KES")}</td>
                    <td>
                      {row.status}
                      <p className="hodi-record-note">
                        Due: {row.due_date || "Not recorded"} · {row.document_available ? "Supporting document on file" : "No supporting document"}
                      </p>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {!loading && !rows.length && !error && (
          <p className="hodi-record-note">No utility bills have been recorded for your tenancy.</p>
        )}
      </div>
    </main>
  );
}
