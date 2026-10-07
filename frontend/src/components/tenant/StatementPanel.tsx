"use client";

import { useCallback, useEffect, useState } from "react";
import { ClientApiError, clientApi } from "@/lib/clientApi";
import { Button } from "@/components/ui/Button";

type StatementLine = {
  date: string;
  kind: "charge" | "payment";
  description: string;
  debit_cents: number;
  credit_cents: number;
  status: string;
};

type Statement = {
  tenant: { name: string; email: string; phone_number: string };
  property: { name: string; city: string } | null;
  unit: { name: string } | null;
  lease: {
    reference: string;
    status: string;
    start_date: string;
    end_date: string | null;
    monthly_rent_minor: number;
  } | null;
  period: { start: string; end: string; label: string; note: string };
  lines: StatementLine[];
  period_charges_cents: number;
  period_payments_cents: number;
  outstanding_cents: number;
  overdue_cents: number;
  credit_cents: number;
  current_balance_cents: number;
  currency: string;
};

type PeriodChoice = "current_month" | "previous_month" | "lease" | "custom";

function kes(cents: number): string {
  const sign = cents < 0 ? "-" : "";
  const absolute = Math.abs(cents);
  const whole = Math.trunc(absolute / 100);
  const fraction = absolute % 100;
  const body = whole.toLocaleString("en-KE");
  return fraction ? `${sign}KES ${body}.${String(fraction).padStart(2, "0")}` : `${sign}KES ${body}`;
}

function statementError(error: unknown): string {
  if (error instanceof ClientApiError) {
    if (error.status === 401) return "Sign in again to view your statement.";
    if (error.status === 403) return "You cannot view this statement.";
    if (error.status === 404) return "No tenant record is linked to this account yet.";
    if (error.status >= 500) return "The statement could not be prepared. Try again in a moment.";
    return error.message || "The statement request was not accepted.";
  }
  if (error instanceof TypeError) return "The statement could not be reached. Check your connection and try again.";
  return error instanceof Error ? error.message : "The statement could not be loaded.";
}

function queryFor(choice: PeriodChoice, from: string, to: string): string {
  if (choice === "custom") {
    const params = new URLSearchParams();
    if (from) params.set("from", from);
    if (to) params.set("to", to);
    return params.toString();
  }
  return `period=${choice}`;
}

export default function StatementPanel() {
  const [choice, setChoice] = useState<PeriodChoice>("current_month");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [statement, setStatement] = useState<Statement | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    if (choice === "custom" && (!from || !to)) {
      setLoading(false);
      setStatement(null);
      setError("");
      return;
    }
    if (choice === "custom" && from > to) {
      setError("The end date must be on or after the start date.");
      setStatement(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    setNotice("");
    try {
      const response = await clientApi.get<Statement>(`/api/v1/billing/statements/me/?${queryFor(choice, from, to)}`);
      setStatement(response.data);
    } catch (reason) {
      setStatement(null);
      setError(statementError(reason));
    } finally {
      setLoading(false);
    }
  }, [choice, from, to]);

  useEffect(() => {
    const timeout = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timeout);
  }, [load]);

  async function downloadPdf() {
    if (choice === "custom" && (!from || !to || from > to)) {
      setError("Choose a valid start and end date before downloading.");
      return;
    }
    setDownloading(true);
    setError("");
    setNotice("");
    try {
      const response = await clientApi.get<Blob>(`/api/v1/billing/statements/me/pdf/?${queryFor(choice, from, to)}`, {
        responseType: "blob",
      });
      const blob = response.data;
      const header = await blob.slice(0, 5).text();
      if (!header.startsWith("%PDF") || blob.size < 80) {
        throw new Error("The download was not a statement PDF.");
      }
      const url = URL.createObjectURL(blob.type ? blob : new Blob([blob], { type: "application/pdf" }));
      const link = document.createElement("a");
      const start = statement?.period.start ?? from;
      const end = statement?.period.end ?? to;
      link.href = url;
      link.download = `hodi-statement-${start}-to-${end}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setNotice("Statement downloaded.");
    } catch (reason) {
      setError(statementError(reason));
    } finally {
      setDownloading(false);
    }
  }

  const balance = statement?.current_balance_cents ?? 0;

  return (
    <section className="dashboard-section portal-section" id="statement" aria-labelledby="statement-title">
      <div className="portal-section-heading">
        <div>
          <span className="portal-eyebrow">Financial report</span>
          <h2 id="statement-title">Statement</h2>
          <p>Posted charges and recorded payments for your own tenancy. Downloading a statement does not make a payment.</p>
        </div>
      </div>
      <div className="statement-toolbar">
        <label>
          Period
          <select value={choice} onChange={event => setChoice(event.target.value as PeriodChoice)}>
            <option value="current_month">Current month</option>
            <option value="previous_month">Previous month</option>
            <option value="lease">Current lease period</option>
            <option value="custom">Custom range</option>
          </select>
        </label>
        {choice === "custom" && (
          <>
            <label>
              From
              <input type="date" value={from} onChange={event => setFrom(event.target.value)} />
            </label>
            <label>
              To
              <input type="date" value={to} onChange={event => setTo(event.target.value)} />
            </label>
          </>
        )}
        <Button type="button" onClick={() => void downloadPdf()} disabled={downloading || loading}>
          {downloading ? "Preparing PDF…" : "Download statement"}
        </Button>
      </div>
      {error && <p className="dashboard-form-error" role="alert">{error}</p>}
      {notice && <p className="statement-notice" role="status">{notice}</p>}
      {loading ? <p className="statement-loading">Loading your statement…</p> : null}
      {!loading && statement && (
        <>
          <p className="statement-meta">
            {statement.tenant.name}
            {statement.property ? ` · ${statement.property.name}` : ""}
            {statement.unit ? ` · ${statement.unit.name}` : ""}
            {statement.lease ? ` · ${statement.lease.reference}` : ""}
            {" · "}
            {statement.period.start} to {statement.period.end}
          </p>
          {statement.period.note ? <p className="statement-meta">{statement.period.note}</p> : null}
          <div className="statement-figures">
            <div><small>Current balance</small><strong>{kes(balance)}</strong></div>
            <div><small>Charges in period</small><strong>{kes(statement.period_charges_cents)}</strong></div>
            <div><small>Payments in period</small><strong>{kes(statement.period_payments_cents)}</strong></div>
            <div><small>Overdue</small><strong>{kes(statement.overdue_cents)}</strong></div>
            <div><small>Unapplied credit</small><strong>{kes(statement.credit_cents)}</strong></div>
          </div>
          {statement.lines.length === 0 ? (
            <p className="statement-empty">No posted charges or recorded payments in this period.</p>
          ) : (
            <div className="statement-table-wrap">
              <table className="statement-table">
                <thead>
                  <tr><th>Date</th><th>Description</th><th>Debit</th><th>Credit</th></tr>
                </thead>
                <tbody>
                  {statement.lines.map((line, index) => (
                    <tr key={`${line.date}-${line.kind}-${index}`}>
                      <td>{line.date}</td>
                      <td>{line.description}</td>
                      <td>{line.debit_cents ? kes(line.debit_cents) : ""}</td>
                      <td>{line.credit_cents ? kes(line.credit_cents) : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
