"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { clientApi } from "@/lib/clientApi";

type Utility = { id: number; utility_type: string; service_description: string; unit: string | null; period_start: string; period_end: string; reading_start: string | null; reading_end: string | null; reading_unit: string; amount_minor: number; currency: string; due_date: string | null; status: string; document_available: boolean };

export default function TenantUtilitiesPage() {
  const [rows, setRows] = useState<Utility[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const result = await clientApi.get<Utility[]>("/api/v1/utilities/me/"); setRows(result.data); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load utility records."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  return <main className="tenant-utilities-page">
    <div className="tenant-utilities-wrap">
      <Link className="workspace-back-link" href="/clients">← Tenant workspace</Link>
      <header className="tenant-utilities-heading"><div><p className="workspace-eyebrow">Tenant services · Utilities</p><h1>Utility records</h1><p>Only tenant-responsibility bills recorded for your current unit appear here. Utilities are separate from rent.</p></div><button type="button" className="workspace-secondary-button" onClick={() => void load()} disabled={loading}>{loading ? "Refreshing…" : "Refresh records"}</button></header>
      {error && <div className="workspace-alert" role="alert"><p>{error}</p><button type="button" onClick={() => void load()}>Try again</button></div>}
      {loading && !rows.length && <p className="workspace-state" role="status">Loading utility records…</p>}
      {!loading && !error && rows.length === 0 && <div className="workspace-state"><strong>No utility bills recorded</strong><p>Tenant-responsibility utility bills will appear here when they are added to your tenancy.</p></div>}
      <section className="tenant-utility-list" aria-label="Utility bills">
        {rows.map(item => <article className="tenant-utility-row" key={item.id}>
          <div className="tenant-utility-title"><span className="workspace-eyebrow">{item.utility_type.replaceAll("_", " ")}{item.unit ? ` · ${item.unit}` : ""}</span><h2>{item.service_description}</h2><p>{item.period_start} – {item.period_end}</p></div>
          <dl className="tenant-utility-meta"><div><dt>Reading</dt><dd>{item.reading_start ?? "—"} → {item.reading_end ?? "—"} {item.reading_unit}</dd></div><div><dt>Due</dt><dd>{item.due_date || "Not recorded"}</dd></div><div><dt>Document</dt><dd>{item.document_available ? "Supporting document on file" : "No document on file"}</dd></div></dl>
          <div className="tenant-utility-amount"><strong>{new Intl.NumberFormat("en-KE", { style: "currency", currency: item.currency, maximumFractionDigits: 0 }).format(item.amount_minor / 100)}</strong><span className={`workspace-status workspace-status-${item.status.toLowerCase()}`}>{item.status.replaceAll("_", " ")}</span></div>
        </article>)}
      </section>
      <p className="workspace-separation-note">Utility records are shown separately from rent and do not indicate a rent payment.</p>
    </div>
  </main>;
}
