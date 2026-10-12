"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Logo } from "@/components/layout/Logo";
import { PropertyBanner } from "@/components/ui/PropertyBanner";
import MaintenanceRequestsPanel from "@/components/ops/MaintenanceRequestsPanel";
import ThemeToggle from "@/components/theme/ThemeToggle";

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
    <main className="min-h-screen bg-bg px-5 py-8 text-text sm:px-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-border pb-4">
          <div className="flex flex-wrap items-center gap-5">
            <Logo size={34} />
            <nav aria-label="Technician workspace" className="flex flex-wrap gap-2 text-sm font-semibold">
              <a className="rounded-md px-3 py-2 text-text-secondary hover:bg-surface hover:text-text" href="#overview">Overview</a>
              <a className="rounded-md px-3 py-2 text-text-secondary hover:bg-surface hover:text-text" href="#maintenance-requests">Assigned work</a>
              <Link className="rounded-md px-3 py-2 text-text-secondary hover:bg-surface hover:text-text" href="/marketplace">Marketplace</Link>
            </nav>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {memberships.length > 1 && (
              <label className="grid gap-1 text-xs font-semibold text-text-secondary">
                Organization
                <select className="rounded-md border border-border bg-surface px-3 py-2 text-sm" value={organizationId} onChange={event => setOrganizationId(event.target.value)}>
                  {memberships.map(item => <option key={item.organization_id} value={item.organization_id}>{item.organization_name}</option>)}
                </select>
              </label>
            )}
            <ThemeToggle />
          </div>
        </header>
        <div id="overview" className="scroll-mt-6">
        <PropertyBanner
          eyebrow="Technician workspace"
          title="Your assigned repair work, in focus."
          description="Review approved work, material requirements and the next step for each job assigned to you."
          imageSrc="/images/hodi/apartment-building.jpg"
          imageSizes="(max-width: 900px) 100vw, 75vw"
          className="technician-overview-banner"
          headingLevel="h1"
        />
        </div>
        {organizationId && <MaintenanceRequestsPanel organizationId={organizationId} canWrite={false} />}
      </div>
    </main>
  );
}
