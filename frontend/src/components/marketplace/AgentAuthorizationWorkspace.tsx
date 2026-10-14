"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";
import { clientApi } from "@/lib/clientApi";

type Identifier = number | string;
type Property = { id: Identifier; name: string };
type Building = { id: Identifier; property: Identifier; name: string };
type Unit = { id: Identifier; building: Identifier; name: string; status: string };
type Authorization = {
  id: number;
  agent: number;
  agent_name: string;
  agent_email: string;
  unit: number;
  unit_name: string;
  building_name: string;
  property_name: string;
  status: "ACTIVE" | "REVOKED" | string;
  authority_reference: string;
  granted_at: string;
  revoked_at: string | null;
};

export default function AgentAuthorizationWorkspace({
  organizationId,
  units,
  buildings,
  properties,
}: {
  organizationId: string;
  units: Unit[];
  buildings: Building[];
  properties: Property[];
}) {
  const [authorizations, setAuthorizations] = useState<Authorization[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    if (!organizationId) return;
    setLoading(true);
    setError("");
    try {
      const { data } = await clientApi.get<Authorization[]>("/api/v1/marketplace/agent-authorizations/", {
        params: { organization: organizationId },
      });
      setAuthorizations(data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Agent authorizations could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [organizationId]);

  useEffect(() => { void load(); }, [load]);

  async function grant(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setNotice("");
    const form = event.currentTarget;
    const values = new FormData(form);
    try {
      await clientApi.post<Authorization>("/api/v1/marketplace/agent-authorizations/", {
        organization: Number(organizationId),
        unit: Number(values.get("unit")),
        agent_email: String(values.get("agent_email") ?? "").trim(),
        attest_authority: values.get("attest_authority") === "on",
        authority_reference: String(values.get("authority_reference") ?? "").trim(),
      });
      form.reset();
      setNotice("Advertising authority recorded. The agent can now prepare a draft for this unit.");
      await load();
    } catch (grantError) {
      setError(grantError instanceof Error ? grantError.message : "Agent authorization could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  async function revoke(authorization: Authorization) {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await clientApi.delete(`/api/v1/marketplace/agent-authorizations/${authorization.id}/`);
      setNotice("Authorization revoked. A published listing for this unit is paused automatically.");
      await load();
    } catch (revokeError) {
      setError(revokeError instanceof Error ? revokeError.message : "Authorization could not be revoked.");
    } finally {
      setSaving(false);
    }
  }

  const activeUnitIds = new Set(authorizations.filter(item => item.status === "ACTIVE").map(item => String(item.unit)));
  const assignableUnits = units.filter(unit => unit.status !== "INACTIVE" && !activeUnitIds.has(String(unit.id)));

  return (
    <section id="agent-authorizations" className="landlord-section" aria-labelledby="agent-authorizations-title">
      <div className="landlord-section-heading">
        <div><p className="landlord-eyebrow">Marketplace access</p><h2 id="agent-authorizations-title">Property-agent authorizations</h2><p className="text-sm text-text-secondary">Grant or revoke an agent’s permission to advertise a unit. Only organization owners can change these records.</p></div>
        <span className="landlord-section-count">{authorizations.filter(item => item.status === "ACTIVE").length} active</span>
      </div>
      {error && <p className="agent-auth-message agent-auth-message--error" role="alert">{error}</p>}
      {notice && <p className="agent-auth-message agent-auth-message--success" role="status">{notice}</p>}
      <form className="landlord-inline-form" onSubmit={grant}>
        <div className="landlord-form-grid">
          <label>Authorized unit
            <select name="unit" required defaultValue="" disabled={!assignableUnits.length || saving}>
              <option value="" disabled>{assignableUnits.length ? "Select a unit" : "No unassigned units available"}</option>
              {assignableUnits.map(unit => {
                const building = buildings.find(item => String(item.id) === String(unit.building));
                const property = properties.find(item => String(item.id) === String(building?.property));
                return <option key={unit.id} value={unit.id}>{property?.name ?? "Property"} · {building?.name ?? "Building"} · {unit.name}</option>;
              })}
            </select>
          </label>
          <label>Registered agent email<input name="agent_email" type="email" required placeholder="agent@example.com" maxLength={254} /></label>
          <label className="landlord-form-wide">Agreement reference (optional)<input name="authority_reference" maxLength={120} placeholder="Management agreement reference" /></label>
          <label className="agent-authority-attestation"><input name="attest_authority" type="checkbox" required />I confirm I have authority to allow this agent to advertise this unit.</label>
        </div>
        <div className="landlord-form-actions">
          <button className="landlord-button landlord-button--primary" type="submit" disabled={saving || !assignableUnits.length}>{saving ? "Saving…" : "Authorize agent"}</button>
        </div>
      </form>
      {loading ? <p className="text-sm text-text-secondary" role="status">Loading authorizations…</p> : authorizations.length ? (
        <div className="landlord-table-wrap" role="region" aria-label="Property-agent authorizations" tabIndex={0}>
          <table className="landlord-table">
            <thead><tr><th>Agent</th><th>Unit</th><th>Agreement</th><th>Status</th><th>Action</th></tr></thead>
            <tbody>{authorizations.map(item => <tr key={item.id}>
              <td><strong>{item.agent_name}</strong><small>{item.agent_email}</small></td>
              <td>{item.property_name} · {item.building_name} · {item.unit_name}</td>
              <td>{item.authority_reference || "Owner attestation"}</td>
              <td><span className={`landlord-status ${item.status === "ACTIVE" ? "is-active" : ""}`}>{item.status.toLowerCase()}</span></td>
              <td>{item.status === "ACTIVE" ? <button className="landlord-button landlord-button--quiet" type="button" disabled={saving} onClick={() => void revoke(item)}>Revoke</button> : "—"}</td>
            </tr>)}</tbody>
          </table>
        </div>
      ) : <div className="landlord-empty-state"><h3>No agent authorizations</h3><p>When an agent is granted access, Hodi will record who approved it and which unit they may advertise.</p></div>}
    </section>
  );
}
