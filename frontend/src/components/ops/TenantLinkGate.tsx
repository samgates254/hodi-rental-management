"use client";

import { useEffect, useState, type FormEvent } from "react";
import {
  ClientApiError,
  linkTenantOrganization,
  listOrganizations,
  logout,
  type OrganizationOption,
} from "@/lib/clientApi";
import "./ops.css";

export default function TenantLinkGate({ onLinked }: { onLinked: () => void }) {
  const [organizations, setOrganizations] = useState<OrganizationOption[]>([]);
  const [organizationId, setOrganizationId] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    let cancelled = false;
    void listOrganizations()
      .then(rows => {
        if (cancelled) return;
        setOrganizations(rows);
        if (rows[0]) setOrganizationId(String(rows[0].id));
      })
      .catch(loadError => {
        if (!cancelled) {
          setError(loadError instanceof ClientApiError
            ? loadError.message
            : "Property organizations couldn’t be loaded.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!organizationId) {
      setError("Choose the organization that manages your home.");
      return;
    }
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      await linkTenantOrganization(Number(organizationId));
      setSuccess("Your tenant account is linked. Opening your home…");
      onLinked();
    } catch (submitError) {
      const message = submitError instanceof ClientApiError
        ? submitError.message
        : "That organization couldn’t be linked.";
      if (/already assigned/i.test(message)) {
        setSuccess("This account is already linked to an organization.");
        onLinked();
        return;
      }
      setError(message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="ops-link-screen">
      <section className="ops-panel ops-link-card" aria-labelledby="tenant-link-title">
        <span className="ops-kicker">TENANT SETUP</span>
        <h2 id="tenant-link-title">Link your property organization</h2>
        <p className="ops-note">
          Signup only creates your login. Choose the organization that manages your home before the tenant dashboard opens. Hodi will not invent a tenancy without this link.
        </p>
        {loading && <p className="ops-status">Loading organizations…</p>}
        {!loading && error && <p className="ops-alert" role="alert">{error}</p>}
        {!loading && success && <p className="ops-success" role="status">{success}</p>}
        {!loading && !organizations.length && !error && (
          <div className="ops-empty">
            <strong>No organizations are available</strong>
            <p>Ask your landlord to create a Hodi organization, then return here to link your account. You can sign out and come back.</p>
          </div>
        )}
        {!loading && organizations.length > 0 && (
          <form className="ops-form" onSubmit={event => void submit(event)}>
            <label>
              Organization
              <select value={organizationId} onChange={event => setOrganizationId(event.target.value)} required>
                {organizations.map(organization => (
                  <option key={organization.id} value={organization.id}>{organization.name}</option>
                ))}
              </select>
            </label>
            <div className="ops-form-actions">
              <button className="ops-button ops-button--primary" type="submit" disabled={saving}>
                {saving ? "Linking…" : "Link organization"}
              </button>
            </div>
          </form>
        )}
        <div className="ops-form-actions">
          <button className="ops-button" type="button" onClick={() => void logout().finally(() => {
            window.location.assign("/signin?type=tenant");
          })}>
            Sign out
          </button>
        </div>
      </section>
    </main>
  );
}
