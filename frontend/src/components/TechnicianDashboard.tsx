"use client";

import { useEffect, useState } from "react";
import MaintenanceRequestsPanel from "@/components/ops/MaintenanceRequestsPanel";

type Membership = { organization_id: string | number; organization_name: string; role: string };

export default function TechnicianDashboard() {
  const [memberships, setMemberships] = useState<Membership[]>([]);
  const [organizationId, setOrganizationId] = useState("");

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
    } catch {
      window.location.replace("/signin?type=technician");
    }
  }, []);

  return (
    <main className="min-h-screen bg-[#f7f8f7] px-5 py-8 text-[#19202a] sm:px-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-bold tracking-[0.18em] text-[#0a9290]">TECHNICIAN WORKSPACE</p>
            <h1 className="mt-2 text-3xl font-semibold">Assigned repairs</h1>
            <p className="mt-2 text-sm text-[#687381]">Work orders assigned to your active organization membership.</p>
          </div>
          {memberships.length > 1 && (
            <label className="grid gap-1 text-xs font-semibold text-[#46515d]">
              Organization
              <select className="rounded-md border border-[#dce1e5] bg-white px-3 py-2 text-sm" value={organizationId} onChange={event => setOrganizationId(event.target.value)}>
                {memberships.map(item => <option key={item.organization_id} value={item.organization_id}>{item.organization_name}</option>)}
              </select>
            </label>
          )}
        </header>
        {organizationId && <MaintenanceRequestsPanel organizationId={organizationId} canWrite={false} />}
      </div>
    </main>
  );
}
