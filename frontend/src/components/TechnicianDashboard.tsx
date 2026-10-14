"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Logo } from "@/components/layout/Logo";
import { clientApi } from "@/lib/clientApi";
import MaintenanceRequestsPanel from "@/components/ops/MaintenanceRequestsPanel";
import ThemeToggle from "@/components/theme/ThemeToggle";
import "./technician-dashboard.css";

type Membership = { organization_id: string | number; organization_name: string; role: string };

export default function TechnicianDashboard() {
  const [memberships, setMemberships] = useState<Membership[]>([]);
  const [organizationId, setOrganizationId] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!sessionStorage.getItem("hodi_api_token")) {
      window.location.replace("/signin?type=technician");
      return;
    }
    try {
      const saved = JSON.parse(sessionStorage.getItem("hodi_memberships") ?? "[]") as unknown;
      const technicianMemberships = Array.isArray(saved)
        ? saved.filter((item): item is Membership => Boolean(item) && typeof item === "object" &&
          (item as Membership).role === "TECHNICIAN" && (item as Membership).organization_id !== undefined)
        : [];
      if (technicianMemberships.length === 0) {
        window.location.replace("/signin?type=technician");
        return;
      }
      setMemberships(technicianMemberships);
      setOrganizationId(String(technicianMemberships[0].organization_id));
      setReady(true);
    } catch {
      window.location.replace("/signin?type=technician");
    }
  }, []);

  async function signOut() {
    try {
      await clientApi.post("/api/v1/accounts/logout/");
    } catch {
      // Local session is cleared even if the server sign-out cannot be reached.
    }
    for (const key of [
      "hodi_api_token",
      "hodi_account_type",
      "hodi_memberships",
      "hodi_first_name",
      "hodi_last_name",
      "hodi_email",
      "hodi_phone_number",
    ]) {
      sessionStorage.removeItem(key);
    }
    window.location.assign("/signin?type=technician");
  }

  const organizationName = memberships.find(item => String(item.organization_id) === organizationId)?.organization_name ?? "Technician workspace";

  if (!ready) {
    return (
      <main className="technician-loading">
        <p>Checking your Hodi account…</p>
      </main>
    );
  }

  return (
    <div className="technician-app">
      <aside className="technician-sidebar">
        <Logo size={36} className="technician-sidebar-logo" wordmarkClassName="text-white" />
        <p className="technician-sidebar-label">TECHNICIAN WORKSPACE</p>
        <nav aria-label="Technician workspace">
          <a href="#overview">Overview</a>
          <a href="#maintenance-requests">Assigned work</a>
          <Link href="/marketplace">Marketplace</Link>
        </nav>
        <div className="technician-sidebar-bottom">
          <span>{organizationName}</span>
          <button type="button" onClick={() => void signOut()}>Sign out</button>
        </div>
      </aside>
      <main className="technician-main">
        <header className="technician-header">
          <div>
            <p className="ops-mast-kicker"><span />Technician</p>
            <h1>{organizationName}</h1>
          </div>
          <div className="technician-header-actions">
            {memberships.length > 1 && (
              <label>
                Organization
                <select value={organizationId} onChange={event => setOrganizationId(event.target.value)}>
                  {memberships.map(item => <option key={item.organization_id} value={item.organization_id}>{item.organization_name}</option>)}
                </select>
              </label>
            )}
            <ThemeToggle />
          </div>
        </header>
        <section id="overview" className="ops-mast">
          <h2>Assigned repair work.</h2>
          <p>Jobs appear only after they are assigned to you. Quotations, material receipts, and completion stay on the work order — nothing on this page is a sample record.</p>
        </section>
        {organizationId ? (
          <MaintenanceRequestsPanel organizationId={organizationId} canWrite={false} />
        ) : (
          <p className="technician-empty" role="status">No organization is selected.</p>
        )}
      </main>
    </div>
  );
}
