"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { clientApi } from "@/lib/clientApi";
import { apiErrorMessage, asList, formatWhen, getList, humanize, type ListPayload } from "@/lib/opsApi";
import "./ops.css";

type UnitRow = { id: number | string; building: number | string; name: string };
type BuildingRow = { id: number | string; property: number | string; name: string };
type PropertyRow = { id: number | string; organization: number | string; name: string };
type TenantRow = { id: number | string; organization: number | string; full_name?: string; first_name: string; last_name: string };
type StaffRow = { user: number | string; first_name?: string; last_name?: string; username?: string; role: string; organization: number | string };
type MembershipRow = { user: number | string; role: string; organization: number | string; is_active: boolean };

type WorkOrder = {
  id: number | string;
  assignee: number | null;
  assignee_name?: string | null;
  assigned_to_me?: boolean;
  status: string;
  assignment_status?: "NOT_REQUIRED" | "PENDING" | "ACCEPTED" | "DECLINED" | null;
  assignment_responded_at?: string | null;
  assignment_decline_reason?: string;
  assigned_at?: string | null;
  completed_at?: string | null;
  notes?: string;
};

type RepairQuotation = {
  id: number | string;
  labour_estimate_cents: number;
  materials_estimate_cents: number;
  other_estimate_cents: number;
  total_estimate_cents: number;
  explanation: string;
  status: string;
  decision_notes?: string;
};

type RepairCompletion = {
  id: number | string;
  diagnosis: string;
  failure_category: string;
  resolution_summary: string;
  outcome: string;
  actual_total_cents: number | null;
  status: string;
  follow_up_required: boolean;
  follow_up_reason?: string;
};

type MaintenanceRequestRow = {
  id: number | string;
  organization: number | string;
  unit: number | string;
  tenant: number | string | null;
  title: string;
  description: string;
  status: string;
  category: string;
  hazard: number;
  vulnerability: number;
  priority_class: number;
  emergency_override: boolean;
  safety_override: boolean;
  safety_override_reason?: string;
  triage_notes?: string;
  requires_approval: boolean;
  follow_up_at?: string | null;
  follow_up_reason?: string;
  follow_up_assignee_name?: string | null;
  created_at: string;
  updated_at?: string;
  completed_at?: string | null;
  closed_at?: string | null;
  work_order?: WorkOrder | null;
  quotations?: RepairQuotation[];
  completion?: RepairCompletion | null;
};

type Assignee = { id: string; label: string };

export default function MaintenanceRequestsPanel({
  organizationId,
  canWrite,
}: {
  organizationId: string;
  canWrite: boolean;
}) {
  const [requests, setRequests] = useState<MaintenanceRequestRow[]>([]);
  const [units, setUnits] = useState<UnitRow[]>([]);
  const [buildings, setBuildings] = useState<BuildingRow[]>([]);
  const [properties, setProperties] = useState<PropertyRow[]>([]);
  const [tenants, setTenants] = useState<TenantRow[]>([]);
  const [assignees, setAssignees] = useState<Assignee[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [declineReason, setDeclineReason] = useState("");

  const load = useCallback(async () => {
    if (!organizationId) return;
    setLoading(true);
    setError("");
    try {
      const requestRows = await getList<MaintenanceRequestRow>("/api/v1/maintenance/requests/");
      setRequests(requestRows.filter(row => String(row.organization) === organizationId));
      if (!canWrite) return;
      const [unitRows, buildingRows, propertyRows, tenantRows] = await Promise.all([
        getList<UnitRow>("/api/v1/properties/units/"),
        getList<BuildingRow>("/api/v1/properties/buildings/"),
        getList<PropertyRow>("/api/v1/properties/"),
        getList<TenantRow>("/api/v1/tenants/"),
      ]);
      const orgProperties = propertyRows.filter(row => String(row.organization) === organizationId);
      const propertyIds = new Set(orgProperties.map(row => String(row.id)));
      const orgBuildings = buildingRows.filter(row => propertyIds.has(String(row.property)));
      const buildingIds = new Set(orgBuildings.map(row => String(row.id)));
      setProperties(orgProperties);
      setBuildings(orgBuildings);
      setUnits(unitRows.filter(row => buildingIds.has(String(row.building))));
      setTenants(tenantRows.filter(row => String(row.organization) === organizationId));

      let people: Assignee[] = [];
      try {
        const staff = await clientApi.get<ListPayload<StaffRow>>("/api/v1/organizations/staff/", {
          params: { organization: organizationId },
        });
        people = asList(staff.data).map(row => ({
          id: String(row.user),
          label: [row.first_name, row.last_name].filter(Boolean).join(" ") || row.username || `User ${row.user}`,
        }));
      } catch {
        const memberships = await getList<MembershipRow>("/api/v1/organizations/memberships/");
        people = memberships
          .filter(row => String(row.organization) === organizationId && row.is_active)
          .map(row => ({ id: String(row.user), label: `User ${row.user} · ${humanize(row.role)}` }));
      }
      setAssignees(people);
    } catch (loadError) {
      setError(apiErrorMessage(loadError, "Maintenance requests couldn’t be loaded."));
    } finally {
      setLoading(false);
    }
  }, [canWrite, organizationId]);

  useEffect(() => {
    void load();
  }, [load]);

  const selected = requests.find(row => String(row.id) === selectedId) ?? null;
  const unitLabel = useMemo(() => {
    const map = new Map<string, string>();
    units.forEach(unit => {
      const building = buildings.find(item => String(item.id) === String(unit.building));
      const property = properties.find(item => String(item.id) === String(building?.property));
      map.set(String(unit.id), `${property?.name ?? "Property"} · ${unit.name}`);
    });
    return map;
  }, [buildings, properties, units]);
  const tenantLabel = useMemo(() => {
    const map = new Map<string, string>();
    tenants.forEach(tenant => {
      map.set(String(tenant.id), tenant.full_name || `${tenant.first_name} ${tenant.last_name}`.trim());
    });
    return map;
  }, [tenants]);

  function assigneeName(id: number | null | undefined) {
    if (id == null) return "Unassigned";
    return assignees.find(person => person.id === String(id))?.label ?? `User ${id}`;
  }

  async function createRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const tenant = String(form.get("tenant") ?? "");
      await clientApi.post("/api/v1/maintenance/requests/", {
        unit: Number(form.get("unit")),
        tenant: tenant ? Number(tenant) : null,
        title: String(form.get("title") ?? "").trim(),
        description: String(form.get("description") ?? "").trim(),
        hazard: Number(form.get("hazard")),
        vulnerability: Number(form.get("vulnerability")),
      });
      setShowCreate(false);
      setNotice("Maintenance request opened. Priority was scored by the server.");
      await load();
    } catch (createError) {
      setError(apiErrorMessage(createError, "The request couldn’t be opened."));
    } finally {
      setBusy(false);
    }
  }

  async function assign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await clientApi.post(`/api/v1/maintenance/requests/${selected.id}/assign/`, {
        user_id: Number(form.get("user_id")),
        notes: String(form.get("notes") ?? ""),
      });
      setNotice("Request assigned.");
      await load();
    } catch (assignError) {
      setError(apiErrorMessage(assignError, "The request couldn’t be assigned."));
    } finally {
      setBusy(false);
    }
  }

  async function triage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await clientApi.post(`/api/v1/maintenance/requests/${selected.id}/triage/`, {
        category: String(form.get("category") ?? "OTHER").trim().toUpperCase(),
        hazard: Number(form.get("hazard")),
        vulnerability: Number(form.get("vulnerability")),
        notes: String(form.get("notes") ?? ""),
        safety_override: form.get("safety_override") === "on",
        safety_override_reason: String(form.get("safety_override_reason") ?? ""),
        requires_approval: form.get("requires_approval") === "on",
      });
      setNotice("Triage details saved.");
      await load();
    } catch (triageError) {
      setError(apiErrorMessage(triageError, "Triage details couldn’t be saved."));
    } finally {
      setBusy(false);
    }
  }

  async function submitQuotation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = new FormData(event.currentTarget);
    setBusy(true); setError(""); setNotice("");
    try {
      await clientApi.post(`/api/v1/maintenance/requests/${selected.id}/quotations/`, {
        labour_estimate_cents: Number(form.get("labour_estimate_cents")),
        materials_estimate_cents: Number(form.get("materials_estimate_cents")),
        other_estimate_cents: Number(form.get("other_estimate_cents") || 0),
        explanation: String(form.get("explanation") ?? "").trim(),
      });
      setNotice("Quotation submitted for review.");
      await load();
    } catch (quoteError) {
      setError(apiErrorMessage(quoteError, "The quotation couldn’t be submitted."));
    } finally { setBusy(false); }
  }

  async function startWork() {
    if (!selected) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await clientApi.post(`/api/v1/maintenance/requests/${selected.id}/start/`, {});
      setNotice("Work started."); await load();
    } catch (startError) { setError(apiErrorMessage(startError, "Work couldn’t be started.")); }
    finally { setBusy(false); }
  }

  async function respondToAssignment(accept: boolean, reason = "") {
    if (!selected) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await clientApi.post(`/api/v1/maintenance/requests/${selected.id}/${accept ? "accept" : "decline"}/`,
        accept ? {} : { reason });
      setNotice(accept ? "Assignment accepted." : "Assignment declined and returned to the property team.");
      await load();
    } catch (responseError) {
      setError(apiErrorMessage(responseError, "Your assignment response couldn’t be saved."));
    } finally { setBusy(false); }
  }

  async function scheduleFollowUp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected?.work_order?.assignee) return;
    const form = new FormData(event.currentTarget);
    const localTime = String(form.get("follow_up_at") ?? "");
    setBusy(true); setError(""); setNotice("");
    try {
      await clientApi.post(`/api/v1/maintenance/requests/${selected.id}/follow-up/`, {
        follow_up_at: new Date(localTime).toISOString(),
        reason: String(form.get("reason") ?? "").trim(),
        assignee_id: selected.work_order.assignee,
      });
      setNotice("Repair follow-up scheduled."); await load();
    } catch (scheduleError) {
      setError(apiErrorMessage(scheduleError, "Follow-up couldn’t be scheduled."));
    } finally { setBusy(false); }
  }

  async function submitCompletion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = new FormData(event.currentTarget);
    const materialDescription = String(form.get("material_description") ?? "").trim();
    setBusy(true); setError(""); setNotice("");
    try {
      await clientApi.post(`/api/v1/maintenance/requests/${selected.id}/complete/`, {
        diagnosis: String(form.get("diagnosis") ?? "").trim(),
        failure_category: String(form.get("failure_category") ?? "OTHER").trim().toUpperCase(),
        resolution_summary: String(form.get("resolution_summary") ?? "").trim(),
        outcome: String(form.get("outcome") ?? "FIXED"),
        labour_cost_cents: Number(form.get("labour_cost_cents")),
        materials_cost_cents: Number(form.get("materials_cost_cents")),
        other_cost_cents: Number(form.get("other_cost_cents") || 0),
        follow_up_reason: String(form.get("follow_up_reason") ?? "").trim(),
        materials: materialDescription ? [{
          description: materialDescription,
          quantity: String(form.get("quantity") || "1"),
          unit: String(form.get("unit") || "piece"),
          unit_cost_cents: Number(form.get("unit_cost_cents") || 0),
        }] : [],
      });
      setNotice("Repair submitted for verification."); await load();
    } catch (completionError) { setError(apiErrorMessage(completionError, "Completion couldn’t be submitted.")); }
    finally { setBusy(false); }
  }

  async function decideQuote(quote: RepairQuotation, approved: boolean) {
    if (!selected) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await clientApi.post(`/api/v1/maintenance/requests/${selected.id}/quotations/${quote.id}/decision/`, {
        approved,
        notes: approved ? "Approved for the submitted scope." : "Please revise and resubmit this estimate.",
      });
      setNotice(approved ? "Quotation approved." : "Quotation rejected."); await load();
    } catch (decisionError) { setError(apiErrorMessage(decisionError, "The quotation decision couldn’t be saved.")); }
    finally { setBusy(false); }
  }

  async function verifyCompletion(approved: boolean) {
    if (!selected?.completion) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await clientApi.post(`/api/v1/maintenance/requests/${selected.id}/verify/`, {
        completion_id: selected.completion.id,
        approved,
        notes: approved ? "Repair checked and accepted." : "Please complete the follow-up work described by the property team.",
      });
      setNotice(approved ? "Repair verified and closed." : "Further repair work requested."); await load();
    } catch (verificationError) { setError(apiErrorMessage(verificationError, "The verification decision couldn’t be saved.")); }
    finally { setBusy(false); }
  }

  const finished = selected && ["COMPLETED", "CLOSED", "CANCELLED"].includes(selected.status);

  return (
    <section className="ops-panel" id="maintenance-requests">
      <div className="ops-heading">
        <div>
          <span className="ops-kicker">MAINTENANCE</span>
          <h2>Requests & work orders</h2>
          <p>Open a request, assign it, complete the work order, then close it. Priority comes from the server.</p>
        </div>
        <div className="ops-actions">
          <button type="button" className="ops-button" onClick={() => void load()} disabled={loading}>{loading ? "Loading…" : "Refresh"}</button>
          {canWrite && (
            <button type="button" className="ops-button ops-button--primary" onClick={() => setShowCreate(open => !open)}>
              {showCreate ? "Cancel" : "New request"}
            </button>
          )}
        </div>
      </div>
      {error && <p className="ops-alert" role="alert">{error}</p>}
      {notice && <p className="ops-success" role="status">{notice}</p>}
      {showCreate && canWrite && (
        <form className="ops-form" onSubmit={event => void createRequest(event)}>
          <div className="ops-grid">
            <label>Unit
              <select name="unit" required defaultValue="">
                <option value="" disabled>Select a unit</option>
                {units.map(unit => <option key={unit.id} value={unit.id}>{unitLabel.get(String(unit.id)) ?? unit.name}</option>)}
              </select>
            </label>
            <label>Tenant <span>(optional)</span>
              <select name="tenant" defaultValue="">
                <option value="">No tenant</option>
                {tenants.map(tenant => (
                  <option key={tenant.id} value={tenant.id}>{tenantLabel.get(String(tenant.id))}</option>
                ))}
              </select>
            </label>
            <label>Hazard 1–5
              <input name="hazard" type="number" min={1} max={5} defaultValue={3} required />
            </label>
            <label>Vulnerability 1–5
              <input name="vulnerability" type="number" min={1} max={5} defaultValue={1} required />
            </label>
          </div>
          <label>Title<input name="title" required maxLength={200} /></label>
          <label>Description<textarea name="description" required /></label>
          <div className="ops-form-actions">
            <button className="ops-button ops-button--primary" disabled={busy}>{busy ? "Saving…" : "Open request"}</button>
          </div>
        </form>
      )}
      {loading && !requests.length && <p className="ops-status">Loading maintenance requests…</p>}
      {!loading && !error && requests.length === 0 && (
        <div className="ops-empty">
          <strong>No maintenance requests</strong>
          <p>Reported work for this organization will show priority, status, and the assigned person.</p>
        </div>
      )}
      {requests.length > 0 && (
        <div className="ops-table-wrap">
          <table className="ops-table">
            <thead>
              <tr><th>Request</th><th>Where</th><th>Tenant</th><th>Priority</th><th>Status</th><th>Assignee</th></tr>
            </thead>
            <tbody>
              {requests.map(row => (
                <tr key={row.id}>
                  <td>
                    <button type="button" className="ops-button" onClick={() => setSelectedId(String(row.id))}>{row.title}</button>
                    <div className="ops-note">{formatWhen(row.created_at)}</div>
                  </td>
                  <td>{unitLabel.get(String(row.unit)) ?? `Unit ${row.unit}`}</td>
                  <td>{row.tenant ? tenantLabel.get(String(row.tenant)) ?? `Tenant ${row.tenant}` : "—"}</td>
                  <td><span className={`ops-pill ${row.emergency_override ? "is-hot" : ""}`}>{row.emergency_override ? "Emergency · " : ""}Class {row.priority_class}</span></td>
                  <td>{humanize(row.status)}</td>
                  <td>{assigneeName(row.work_order?.assignee)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {selected && (
        <div className="ops-detail">
          <div className="ops-heading">
            <div>
              <span className="ops-kicker">REQUEST {selected.id}</span>
              <h2>{selected.title}</h2>
              <p>{selected.description}</p>
            </div>
            <button type="button" className="ops-button" onClick={() => setSelectedId("")}>Close details</button>
          </div>
          <dl className="ops-meta">
            <div><dt>Property / unit</dt><dd>{unitLabel.get(String(selected.unit)) ?? `Unit ${selected.unit}`}</dd></div>
            <div><dt>Tenant</dt><dd>{selected.tenant ? tenantLabel.get(String(selected.tenant)) ?? `Tenant ${selected.tenant}` : "—"}</dd></div>
            <div><dt>Status</dt><dd>{humanize(selected.status)}</dd></div>
            <div><dt>Priority</dt><dd>Class {selected.priority_class}{selected.emergency_override ? " · emergency override" : ""}</dd></div>
            <div><dt>Work order</dt><dd>{selected.work_order ? `${humanize(selected.work_order.status)} · ${assigneeName(selected.work_order.assignee)}` : "—"}</dd></div>
            <div><dt>Assignment response</dt><dd>{humanize(selected.work_order?.assignment_status ?? "Not recorded")}</dd></div>
            <div><dt>Opened</dt><dd>{formatWhen(selected.created_at)}</dd></div>
            <div><dt>Assigned</dt><dd>{formatWhen(selected.work_order?.assigned_at)}</dd></div>
            <div><dt>Completed</dt><dd>{formatWhen(selected.completed_at || selected.work_order?.completed_at)}</dd></div>
            <div><dt>Closed</dt><dd>{formatWhen(selected.closed_at)}</dd></div>
          </dl>
          {selected.work_order?.assignment_decline_reason && (
            <p className="ops-alert"><strong>Technician declined:</strong> {selected.work_order.assignment_decline_reason} Reassign this request to continue.</p>
          )}
          {selected.follow_up_at && (
            <article className="ops-note">
              <strong>Follow-up scheduled · {formatWhen(selected.follow_up_at)}</strong>
              <p>{selected.follow_up_reason}</p>
              <p>Responsible: {selected.follow_up_assignee_name ?? "Assigned repair team"}</p>
            </article>
          )}
          {canWrite && !finished && (
            <form className="ops-form" onSubmit={event => void triage(event)}>
              <h3>Triage and safety</h3>
              <div className="ops-grid">
                <label>Repair category
                  <select name="category" defaultValue={selected.category || "OTHER"}>
                    {["OTHER", "PLUMBING", "ELECTRICAL", "CARPENTRY", "HVAC", "MASONRY"].map(category => <option key={category}>{category}</option>)}
                  </select>
                </label>
                <label>Hazard 1–5<input name="hazard" type="number" min={1} max={5} defaultValue={selected.hazard} required /></label>
                <label>Vulnerability 1–5<input name="vulnerability" type="number" min={1} max={5} defaultValue={selected.vulnerability} required /></label>
              </div>
              <label>Internal triage notes<textarea name="notes" defaultValue={selected.triage_notes ?? ""} /></label>
              <label className="ops-check"><input name="safety_override" type="checkbox" defaultChecked={selected.safety_override} /> Safety exception to quotation approval</label>
              <label>Safety exception reason<input name="safety_override_reason" defaultValue={selected.safety_override_reason ?? ""} maxLength={500} /></label>
              <label className="ops-check"><input name="requires_approval" type="checkbox" defaultChecked={selected.requires_approval} /> Require an approved quotation before work starts</label>
              <div className="ops-form-actions"><button className="ops-button ops-button--primary" disabled={busy}>{busy ? "Saving…" : "Save triage"}</button></div>
            </form>
          )}
          {canWrite && !finished && (
            <form className="ops-form" onSubmit={event => void assign(event)}>
              <div className="ops-grid">
                <label>Assign to
                  <select name="user_id" required defaultValue="">
                    <option value="" disabled>Select a person</option>
                    {assignees.map(person => <option key={person.id} value={person.id}>{person.label}</option>)}
                  </select>
                </label>
                <label>Notes<input name="notes" maxLength={500} /></label>
              </div>
              <div className="ops-form-actions">
                <button className="ops-button ops-button--primary" disabled={busy || assignees.length === 0}>
                  {busy ? "Saving…" : "Assign"}
                </button>
              </div>
              {assignees.length === 0 && <p className="ops-note">No staff membership was returned, so assignment isn’t available.</p>}
            </form>
          )}
          {selected.quotations?.map(quote => (
            <article className="ops-note" key={quote.id}>
              <strong>Quotation · {humanize(quote.status)} · KES {(quote.total_estimate_cents / 100).toFixed(2)}</strong>
              <p>{quote.explanation}</p>
              {canWrite && quote.status === "PENDING" && (
                <div className="ops-form-actions">
                  <button type="button" className="ops-button ops-button--primary" disabled={busy} onClick={() => void decideQuote(quote, true)}>Approve scope</button>
                  <button type="button" className="ops-button" disabled={busy} onClick={() => void decideQuote(quote, false)}>Reject / revise</button>
                </div>
              )}
            </article>
          ))}
          {selected.work_order?.assigned_to_me && selected.work_order.status === "ASSIGNED" && selected.work_order.assignment_status === "PENDING" && (
            <form className="ops-form" onSubmit={event => {
              event.preventDefault();
              void respondToAssignment(false, declineReason);
            }}>
              <h3>Respond to assignment</h3>
              <p>Accept this repair or decline with a reason so the property team can reassign it.</p>
              <div className="ops-form-actions">
                <button type="button" className="ops-button ops-button--primary" disabled={busy} onClick={() => void respondToAssignment(true)}>Accept assignment</button>
                <label>Reason for declining<input value={declineReason} onChange={event => setDeclineReason(event.target.value)} maxLength={500} required /></label>
                <button type="submit" className="ops-button" disabled={busy || !declineReason.trim()}>Decline assignment</button>
              </div>
            </form>
          )}
          {selected.work_order?.assigned_to_me && selected.work_order.status === "ASSIGNED" && (selected.work_order.assignment_status === "ACCEPTED" || selected.work_order.assignment_status === "NOT_REQUIRED" || !selected.work_order.assignment_status) && (
            <div className="ops-form-actions">
              <button type="button" className="ops-button ops-button--primary" disabled={busy} onClick={() => void startWork()}>
                {busy ? "Saving…" : "Start assigned work"}
              </button>
            </div>
          )}
          {selected.work_order?.assigned_to_me && selected.work_order.status === "IN_PROGRESS" && (
            <form className="ops-form" onSubmit={event => void submitCompletion(event)}>
              <h3>Submit repair for verification</h3>
              <label>Diagnosis<input name="diagnosis" required /></label>
              <div className="ops-grid">
                <label>Failure category<input name="failure_category" required maxLength={50} /></label>
                <label>Outcome
                  <select name="outcome" defaultValue="FIXED">
                    <option value="FIXED">Fixed</option><option value="PARTIALLY_FIXED">Partially fixed</option>
                    <option value="REPLACED">Replaced</option><option value="NO_FAULT_FOUND">No fault found</option>
                    <option value="NEEDS_FOLLOW_UP">Needs follow-up</option>
                  </select>
                </label>
                <label>Labour cost (KES cents)<input name="labour_cost_cents" type="number" min={0} step={1} required /></label>
                <label>Materials cost (KES cents)<input name="materials_cost_cents" type="number" min={0} step={1} required /></label>
                <label>Other cost (KES cents)<input name="other_cost_cents" type="number" min={0} step={1} defaultValue={0} /></label>
              </div>
              <label>Resolution summary<textarea name="resolution_summary" required /></label>
              <label>Follow-up reason<input name="follow_up_reason" maxLength={500} /></label>
              <div className="ops-grid">
                <label>Material used (optional)<input name="material_description" maxLength={200} /></label>
                <label>Quantity<input name="quantity" type="number" min="0.001" step="0.001" defaultValue="1" /></label>
                <label>Unit<input name="unit" defaultValue="piece" maxLength={30} /></label>
                <label>Unit cost (KES cents)<input name="unit_cost_cents" type="number" min={0} step={1} defaultValue={0} /></label>
              </div>
              <div className="ops-form-actions"><button className="ops-button ops-button--primary" disabled={busy}>{busy ? "Saving…" : "Submit completion"}</button></div>
            </form>
          )}
          {selected.work_order?.assigned_to_me && !finished && selected.work_order.assignment_status !== "PENDING" && !selected.quotations?.some(quote => quote.status === "PENDING") && (
            <form className="ops-form" onSubmit={event => void submitQuotation(event)}>
              <h3>Submit quotation</h3>
              <div className="ops-grid">
                <label>Labour estimate (KES cents)<input name="labour_estimate_cents" type="number" min={0} step={1} required /></label>
                <label>Materials estimate (KES cents)<input name="materials_estimate_cents" type="number" min={0} step={1} required /></label>
                <label>Other estimate (KES cents)<input name="other_estimate_cents" type="number" min={0} step={1} defaultValue={0} /></label>
              </div>
              <label>Scope and assumptions<textarea name="explanation" required /></label>
              <div className="ops-form-actions"><button className="ops-button ops-button--primary" disabled={busy}>{busy ? "Saving…" : "Submit quotation"}</button></div>
            </form>
          )}
          {selected.completion && (
            <article className="ops-note">
              <strong>Repair outcome: {humanize(selected.completion.outcome)} · {humanize(selected.completion.status)}</strong>
              <p>{selected.completion.diagnosis}</p>
              <p>{selected.completion.resolution_summary}</p>
              {selected.completion.follow_up_required && <p>Follow-up: {selected.completion.follow_up_reason}</p>}
              {selected.completion.actual_total_cents != null && <p>Actual cost: KES {(selected.completion.actual_total_cents / 100).toFixed(2)}</p>}
              {canWrite && selected.completion.status === "SUBMITTED" && selected.completion.outcome !== "NEEDS_FOLLOW_UP" && (
                <div className="ops-form-actions">
                  <button type="button" className="ops-button ops-button--primary" disabled={busy} onClick={() => void verifyCompletion(true)}>Verify and close</button>
                  <button type="button" className="ops-button" disabled={busy} onClick={() => void verifyCompletion(false)}>Request further work</button>
                </div>
              )}
              {canWrite && selected.completion.status === "SUBMITTED" && selected.completion.outcome === "NEEDS_FOLLOW_UP" && (
                <p className="ops-note">This repair cannot be verified as resolved. Reject it for further work, then schedule the follow-up.</p>
              )}
            </article>
          )}
          {canWrite && selected.completion &&
            (selected.completion.outcome === "NEEDS_FOLLOW_UP" || selected.completion.status === "REJECTED") &&
            (selected.status === "COMPLETED" || selected.status === "IN_PROGRESS") && (
              <form className="ops-form" onSubmit={event => void scheduleFollowUp(event)}>
                <h3>Schedule repair follow-up</h3>
                <p>Responsible party: {selected.work_order?.assignee_name ?? "No assigned technician"}</p>
                <label>Date and time<input name="follow_up_at" type="datetime-local" required /></label>
                <label>Reason<input name="reason" maxLength={500} required defaultValue={selected.completion.follow_up_reason ?? ""} /></label>
                <div className="ops-form-actions"><button className="ops-button ops-button--primary" disabled={busy || !selected.work_order?.assignee}>{busy ? "Saving…" : "Schedule follow-up"}</button></div>
              </form>
            )}
          {selected.work_order?.notes && <p className="ops-note">Work order notes: {selected.work_order.notes}</p>}
        </div>
      )}
    </section>
  );
}
