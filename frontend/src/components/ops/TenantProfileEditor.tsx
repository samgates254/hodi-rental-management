"use client";

import { useEffect, useState, type FormEvent } from "react";
import { clientApi } from "@/lib/clientApi";
import { apiErrorMessage, asList, type ListPayload } from "@/lib/opsApi";
import "./ops.css";

type TenantRow = {
  id: number | string;
  user: number | null;
  first_name: string;
  last_name: string;
  phone_number: string;
  email: string;
  national_id?: string;
};

type Me = { id: number };

export default function TenantProfileEditor() {
  const [tenant, setTenant] = useState<TenantRow | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [form, setForm] = useState({ first_name: "", last_name: "", phone_number: "", email: "" });

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const [meResponse, tenantResponse] = await Promise.all([
          clientApi.get<Me>("/api/v1/accounts/me/"),
          clientApi.get<ListPayload<TenantRow>>("/api/v1/tenants/"),
        ]);
        const mine = asList(tenantResponse.data).find(row => row.user === meResponse.data.id) ?? null;
        if (cancelled) return;
        setTenant(mine);
        if (mine) {
          setForm({
            first_name: mine.first_name ?? "",
            last_name: mine.last_name ?? "",
            phone_number: mine.phone_number ?? "",
            email: mine.email ?? "",
          });
        }
      } catch (loadError) {
        if (!cancelled) setError(apiErrorMessage(loadError, "Your profile couldn’t be loaded."));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!tenant) return;
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const response = await clientApi.patch<TenantRow>(`/api/v1/tenants/${tenant.id}/`, {
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        phone_number: form.phone_number.trim(),
        email: form.email.trim(),
      });
      setTenant(response.data);
      setForm({
        first_name: response.data.first_name ?? "",
        last_name: response.data.last_name ?? "",
        phone_number: response.data.phone_number ?? "",
        email: response.data.email ?? "",
      });
      sessionStorage.setItem("hodi_first_name", response.data.first_name ?? "");
      sessionStorage.setItem("hodi_last_name", response.data.last_name ?? "");
      sessionStorage.setItem("hodi_email", response.data.email ?? "");
      sessionStorage.setItem("hodi_phone_number", response.data.phone_number ?? "");
      setSuccess("Contact details saved.");
    } catch (saveError) {
      setError(apiErrorMessage(saveError, "Your profile couldn’t be saved."));
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <p className="ops-status">Loading your profile…</p>;
  if (error && !tenant) return <p className="ops-alert" role="alert">{error}</p>;
  if (!tenant) {
    return (
      <div className="ops-empty">
        <strong>No tenant profile yet</strong>
        <p>Link your organization first. Contact details can be edited after your tenant record exists.</p>
      </div>
    );
  }

  return (
    <form className="ops-form ops-profile-card" onSubmit={event => void save(event)}>
      <p className="ops-note">You can update your name, phone, and email. National ID and tenancy status stay with your property manager.</p>
      {error && <p className="ops-alert" role="alert">{error}</p>}
      {success && <p className="ops-success" role="status">{success}</p>}
      <div className="ops-grid">
        <label>First name
          <input value={form.first_name} required maxLength={100} onChange={event => setForm(current => ({ ...current, first_name: event.target.value }))} />
        </label>
        <label>Last name
          <input value={form.last_name} required maxLength={100} onChange={event => setForm(current => ({ ...current, last_name: event.target.value }))} />
        </label>
        <label>Phone
          <input value={form.phone_number} required maxLength={30} onChange={event => setForm(current => ({ ...current, phone_number: event.target.value }))} />
        </label>
        <label>Email
          <input type="email" value={form.email} maxLength={254} onChange={event => setForm(current => ({ ...current, email: event.target.value }))} />
        </label>
      </div>
      <p className="ops-note">National ID: {tenant.national_id?.trim() || "Not on file"} · not editable here</p>
      <div className="ops-form-actions">
        <button className="ops-button ops-button--primary" type="submit" disabled={saving}>
          {saving ? "Saving…" : "Save contact details"}
        </button>
      </div>
    </form>
  );
}
