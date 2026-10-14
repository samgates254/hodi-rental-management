"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ClientApiError, clientApi } from "@/lib/clientApi";
import { formatMinor, shillingsToCents } from "@/lib/money";

type UtilityAccount = {
  id: number;
  organization: number;
  property: number;
  property_name: string;
  unit: number | null;
  unit_name: string;
  service_type: string;
  provider_name: string;
  service_reference: string;
  meter_reference: string;
  responsible_party: "LANDLORD" | "TENANT";
  is_active: boolean;
};

type UtilityBill = {
  id: number;
  account: number;
  account_name: string;
  property_name: string;
  unit_name: string;
  service_type: string;
  responsible_party: "LANDLORD" | "TENANT";
  period_start: string;
  period_end: string;
  due_date: string | null;
  amount_minor: number;
  currency: string;
  reading_start: string | null;
  reading_end: string | null;
  reading_unit: string;
  document_reference: string;
};

type ApiList<T> = T[] | { results?: T[] };
type PropertyOption = { id: number | string; name: string };
type BuildingOption = { id: number | string; property: number | string; name: string };
type UnitOption = { id: number | string; building: number | string; name: string };

function rows<T>(value: ApiList<T>): T[] {
  return Array.isArray(value) ? value : value.results ?? [];
}

function message(error: unknown, fallback: string): string {
  return error instanceof ClientApiError || error instanceof Error ? error.message : fallback;
}

function money(minor: number, currency: string): string {
  return formatMinor(minor, currency);
}

function serviceName(value: string): string {
  return value.charAt(0) + value.slice(1).toLowerCase();
}

export default function UtilitiesWorkspace({
  organizationId,
  canWrite,
  properties,
  buildings,
  units,
}: {
  organizationId: string;
  canWrite: boolean;
  properties: PropertyOption[];
  buildings: BuildingOption[];
  units: UnitOption[];
}) {
  const [accounts, setAccounts] = useState<UtilityAccount[]>([]);
  const [bills, setBills] = useState<UtilityBill[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [accountFormOpen, setAccountFormOpen] = useState(false);
  const [billFormOpen, setBillFormOpen] = useState(false);

  const load = useCallback(async () => {
    if (!organizationId) return;
    setLoading(true);
    setError("");
    try {
      const [accountResponse, billResponse] = await Promise.all([
        clientApi.get<ApiList<UtilityAccount>>("/api/v1/utilities/accounts/", {
          params: { organization: organizationId },
        }),
        clientApi.get<ApiList<UtilityBill>>("/api/v1/utilities/bills/", {
          params: { organization: organizationId },
        }),
      ]);
      setAccounts(rows(accountResponse.data));
      setBills(rows(billResponse.data));
    } catch (loadError) {
      setError(message(loadError, "Utility records could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, [organizationId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function createAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await clientApi.post<UtilityAccount>("/api/v1/utilities/accounts/", {
        organization: Number(organizationId),
        property: Number(form.get("property")),
        unit: form.get("unit") ? Number(form.get("unit")) : null,
        service_type: String(form.get("service_type")),
        provider_name: String(form.get("provider_name")).trim(),
        service_reference: String(form.get("service_reference")).trim(),
        meter_reference: String(form.get("meter_reference")).trim(),
        responsible_party: String(form.get("responsible_party")),
      });
      setAccountFormOpen(false);
      setNotice("Utility account recorded.");
      await load();
    } catch (saveError) {
      setError(message(saveError, "The utility account could not be saved."));
    } finally {
      setSaving(false);
    }
  }

  async function createBill(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSaving(true);
    setError("");
    setNotice("");
    const cents = shillingsToCents(String(form.get("amount") ?? ""));
    if (cents == null || cents <= 0) {
      setError("Enter a bill amount in KES greater than zero, with at most two decimal places.");
      setSaving(false);
      return;
    }
    try {
      await clientApi.post<UtilityBill>("/api/v1/utilities/bills/", {
        account: Number(form.get("account")),
        period_start: String(form.get("period_start")),
        period_end: String(form.get("period_end")),
        due_date: String(form.get("due_date")) || null,
        amount_minor: cents,
        currency: "KES",
        reading_start: String(form.get("reading_start")) || null,
        reading_end: String(form.get("reading_end")) || null,
        reading_unit: String(form.get("reading_unit")).trim(),
        document_reference: String(form.get("document_reference")).trim(),
        notes: String(form.get("notes")).trim(),
      });
      setBillFormOpen(false);
      setNotice("Utility bill recorded. This does not record payment or add a rent charge.");
      await load();
    } catch (saveError) {
      setError(message(saveError, "The utility bill could not be saved."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="ops-panel" id="utilities" aria-labelledby="utilities-heading">
      <div className="ops-heading">
        <div>
          <span className="ops-kicker">PROPERTY COSTS</span>
          <h2 id="utilities-heading">Utilities</h2>
          <p className="ops-note">Manual service accounts, bills and readings. Utility records stay separate from rent payments.</p>
        </div>
        {canWrite && <div className="ops-form-actions">
          <button type="button" className="ops-button" onClick={() => setAccountFormOpen(open => !open)}>Add account</button>
          <button type="button" className="ops-button ops-button--primary" disabled={!accounts.some(account => account.is_active)} onClick={() => setBillFormOpen(open => !open)}>Record bill</button>
        </div>}
      </div>

      {error && <p className="ops-alert" role="alert">{error}</p>}
      {notice && <p className="ops-success" role="status">{notice}</p>}

      {accountFormOpen && canWrite && <form className="ops-form" onSubmit={event => void createAccount(event)}>
        <h3>Register a utility service</h3>
        <div className="ops-grid">
          <label>Property<select name="property" required defaultValue=""><option value="" disabled>Select a property</option>{properties.map(property => <option key={property.id} value={property.id}>{property.name}</option>)}</select></label>
          <label>Unit, optional<select name="unit" defaultValue=""><option value="">Property level</option>{units.map(unit => { const building = buildings.find(item => String(item.id) === String(unit.building)); const property = properties.find(item => String(item.id) === String(building?.property)); return <option key={unit.id} value={unit.id}>{property?.name ?? "Property"} · {building?.name ?? "Building"} · {unit.name}</option>; })}</select></label>
          <label>Service<select name="service_type" defaultValue="ELECTRICITY"><option value="ELECTRICITY">Electricity</option><option value="WATER">Water</option><option value="GAS">Gas</option><option value="INTERNET">Internet</option><option value="OTHER">Other</option></select></label>
          <label>Provider<input name="provider_name" maxLength={160} required /></label>
          <label>Service reference<input name="service_reference" maxLength={120} /></label>
          <label>Meter reference<input name="meter_reference" maxLength={120} /></label>
          <label>Responsible party<select name="responsible_party" defaultValue="LANDLORD"><option value="LANDLORD">Landlord</option><option value="TENANT">Tenant</option></select></label>
        </div>
        <p className="ops-note">Tenant responsibility does not create a rent charge.</p>
        <div className="ops-form-actions"><button type="button" className="ops-button" onClick={() => setAccountFormOpen(false)}>Cancel</button><button className="ops-button ops-button--primary" disabled={saving}>{saving ? "Saving…" : "Save account"}</button></div>
      </form>}

      {billFormOpen && canWrite && <form className="ops-form" onSubmit={event => void createBill(event)}>
        <h3>Record a utility bill</h3>
        <div className="ops-grid">
          <label>Service account<select name="account" required defaultValue=""><option value="" disabled>Select an account</option>{accounts.filter(account => account.is_active).map(account => <option key={account.id} value={account.id}>{account.property_name}{account.unit_name ? ` · ${account.unit_name}` : ""} · {serviceName(account.service_type)} · {account.provider_name}</option>)}</select></label>
          <label>Period start<input name="period_start" type="date" required /></label>
          <label>Period end<input name="period_end" type="date" required /></label>
          <label>Due date, optional<input name="due_date" type="date" /></label>
          <label>Bill amount (KES)<input name="amount" type="number" min="0.01" step="0.01" required /></label>
          <label>Reading start, optional<input name="reading_start" type="number" min="0" step="0.001" /></label>
          <label>Reading end, optional<input name="reading_end" type="number" min="0" step="0.001" /></label>
          <label>Reading unit<input name="reading_unit" maxLength={24} placeholder="kWh, m³" /></label>
          <label>Document reference<input name="document_reference" maxLength={255} /></label>
          <label>Notes<input name="notes" maxLength={2000} /></label>
        </div>
        <div className="ops-form-actions"><button type="button" className="ops-button" onClick={() => setBillFormOpen(false)}>Cancel</button><button className="ops-button ops-button--primary" disabled={saving}>{saving ? "Saving…" : "Record bill"}</button></div>
      </form>}

      {loading ? <p className="ops-status" role="status">Loading utility records…</p> : bills.length ? (
        <div className="ops-table-wrap"><table className="ops-table"><thead><tr><th>Service</th><th>Property / unit</th><th>Period</th><th>Responsible</th><th>Bill amount</th><th>Reading</th><th>Due</th></tr></thead><tbody>
          {bills.map(bill => <tr key={bill.id}><td>{serviceName(bill.service_type)}<br /><span className="ops-note">{bill.account_name}</span></td><td>{bill.property_name}{bill.unit_name ? ` · ${bill.unit_name}` : ""}</td><td>{bill.period_start} – {bill.period_end}</td><td>{bill.responsible_party === "LANDLORD" ? "Landlord" : "Tenant"}</td><td>{money(bill.amount_minor, bill.currency)}</td><td>{bill.reading_start != null && bill.reading_end != null ? `${bill.reading_start} → ${bill.reading_end} ${bill.reading_unit}` : "Not recorded"}</td><td>{bill.due_date ?? "—"}</td></tr>)}
        </tbody></table></div>
      ) : <div className="ops-empty"><strong>No utility bills recorded</strong><p>Record provider bills and readings as they arrive. No usage or payment is assumed.</p></div>}
      {!!accounts.length && <details className="ops-disclosure"><summary>Service accounts ({accounts.length})</summary><ul>{accounts.map(account => <li key={account.id}>{account.property_name}{account.unit_name ? ` · ${account.unit_name}` : ""} — {serviceName(account.service_type)} · {account.provider_name} · {account.responsible_party === "LANDLORD" ? "Landlord" : "Tenant"} responsible</li>)}</ul></details>}
      {!canWrite && <p className="ops-note">Accountant access is read only. Contact an organisation owner or property manager to record changes.</p>}
    </section>
  );
}
