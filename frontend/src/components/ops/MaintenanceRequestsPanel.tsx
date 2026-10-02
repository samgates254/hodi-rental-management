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
  status: string;
  assigned_at?: string | null;
  completed_at?: string | null;
  notes?: string;
};

type MaintenanceRequestRow = {
  id: number | string;
  organization: number | string;
  unit: number | string;
  tenant: number | string | null;
  title: string;
  description: string;
  status: string;
  priority_class: number;
  emergency_override: boolean;
  created_at: string;
  updated_at?: string;
  completed_at?: string | null;
  closed_at?: string | null;
  work_order?: WorkOrder | null;
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

  const load = useCallback(async () => {
    if (!organizationId) return;
    setLoading(true);
    setError("");
    try {
      const [requestRows, unitRows, buildingRows, propertyRows, tenantRows] = await Promise.all([
        getList<MaintenanceRequestRow>("/api/v1/maintenance/requests/"),
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
      setRequests(requestRows.filter(row => String(row.organization) === organizationId));

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
  }, [organizationId]);

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

  async function complete() {
    if (!selected) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await clientApi.post(`/api/v1/maintenance/requests/${selected.id}/complete/`, {});
      setNotice("Work order marked complete.");
      await load();
    } catch (completeError) {
      setError(apiErrorMessage(completeError, "The work order couldn’t be completed."));
    } finally {
      setBusy(false);
    }
  }

  async function closeRequest() {
    if (!selected) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await clientApi.post(`/api/v1/maintenance/requests/${selected.id}/close/`, {});
      setNotice("Request closed.");
      await load();
    } catch (closeError) {
      setError(apiErrorMessage(closeError, "The request couldn’t be closed."));
    } finally {
      setBusy(false);
    }
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
            <div><dt>Opened</dt><dd>{formatWhen(selected.created_at)}</dd></div>
            <div><dt>Assigned</dt><dd>{formatWhen(selected.work_order?.assigned_at)}</dd></div>
            <div><dt>Completed</dt><dd>{formatWhen(selected.completed_at || selected.work_order?.completed_at)}</dd></div>
            <div><dt>Closed</dt><dd>{formatWhen(selected.closed_at)}</dd></div>
          </dl>
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
                <button className="ops-button" type="button" disabled={busy} onClick={() => void complete()}>Complete work</button>
              </div>
              {assignees.length === 0 && <p className="ops-note">No staff membership was returned, so assignment isn’t available.</p>}
            </form>
          )}
          {canWrite && selected.status === "COMPLETED" && (
            <div className="ops-form-actions">
              <button className="ops-button ops-button--primary" type="button" disabled={busy} onClick={() => void closeRequest()}>
                {busy ? "Closing…" : "Close request"}
              </button>
            </div>
          )}
          {selected.work_order?.notes && <p className="ops-note">Work order notes: {selected.work_order.notes}</p>}
        </div>
      )}
    </section>
  );
}
