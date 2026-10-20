"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { ClientApiError, clientApi } from "@/lib/clientApi";
import { isPanoramaCaption, visibleCaption } from "@/lib/listingMedia";
import { formatMinor } from "@/lib/money";
import { apiErrorMessage, formatWhen, humanize } from "@/lib/opsApi";
import {
  collectedCents,
  needsAttention,
  occupancy,
  pendingApproval,
  periodRange,
  portfolioPerformance,
  postedOpenInvoices,
  propertyIdForLease,
  readPage,
  scopeRequests,
  sumCents,
  type AnalyticsInvoice,
  type AnalyticsPayment,
  type AnalyticsRequest,
  type PeriodId,
  type PortfolioGraph,
} from "@/lib/portfolioAnalytics";
import { daysUntilRentalDate, rentalBusinessDate } from "@/lib/rentalDate";
import type { ManagedListing } from "@/components/marketplace/shared";
import "./property-command.css";

type Identifier = number | string;
type SourceState = "ready" | "loading" | "error" | "hidden" | "preview";
type TabId = "overview" | "units" | "financials" | "maintenance" | "activity";
type UnitSort = "name" | "status" | "rent" | "outstanding";

type PropertyRecord = {
  id: Identifier;
  name: string;
  address: string;
  city: string;
  country: string;
  is_active: boolean;
};

type BuildingRecord = { id: Identifier; property: Identifier; name: string };
type UnitRecord = { id: Identifier; building: Identifier; name: string; status: string; bedrooms: number };
type TenantRecord = { id: Identifier; full_name: string; first_name: string; last_name: string };
type LeaseRecord = {
  id: Identifier;
  tenant: Identifier;
  unit: Identifier;
  reference: string;
  start_date: string;
  end_date: string | null;
  monthly_rent_minor: number;
  status: string;
};

type PhotoFrame = {
  key: string;
  url: string;
  caption: string;
  unitName: string;
  panorama: boolean;
};

type AuditRow = {
  id: number | string;
  action: string;
  object_type: string;
  object_id: string;
  created_at: string;
};

const TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "units", label: "Units & tenancy" },
  { id: "financials", label: "Financials" },
  { id: "maintenance", label: "Maintenance" },
  { id: "activity", label: "Activity" },
];

const PERIODS: { id: PeriodId; label: string }[] = [
  { id: "month", label: "This month" },
  { id: "30", label: "Last 30 days" },
  { id: "90", label: "Last 90 days" },
  { id: "year", label: "This year" },
];

const UNIT_STATUSES = ["OCCUPIED", "AVAILABLE", "MAINTENANCE", "INACTIVE"] as const;

function textId(value: Identifier | null | undefined): string {
  return value == null ? "" : String(value);
}

function money(cents: number | null | undefined): string {
  return cents == null ? "—" : formatMinor(cents);
}

function civilDate(value: string | null | undefined): string {
  if (!value) return "No end date";
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return value;
  return new Intl.DateTimeFormat("en-KE", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]))));
}

function initials(name: string): string {
  const letters = name.trim().split(/\s+/).slice(0, 2).map(part => part[0]?.toUpperCase() ?? "").join("");
  return letters || "H";
}

function AuthPhoto({ url, alt, fill = false, quiet = false }: { url: string; alt: string; fill?: boolean; quiet?: boolean }) {
  const [src, setSrc] = useState("");
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let objectUrl = "";
    let cancelled = false;
    setFailed(false);
    setSrc("");
    clientApi.get<Blob>(url, { responseType: "blob" }).then(response => {
      if (cancelled) return;
      objectUrl = URL.createObjectURL(response.data);
      setSrc(objectUrl);
    }).catch(() => {
      if (!cancelled) setFailed(true);
    });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [url]);

  if (failed) return quiet ? null : <p className="command-photo-state">This photograph could not be loaded.</p>;
  if (!src) return quiet ? null : <p className="command-photo-state">Loading photograph…</p>;
  if (fill) {
    return <Image src={src} alt={alt} fill unoptimized sizes={quiet ? "96px" : "(max-width: 900px) 100vw, 42vw"} className="object-cover" />;
  }
  return (
    <Image
      src={src}
      alt={alt}
      width={1600}
      height={1000}
      unoptimized
      sizes="92vw"
      style={{ width: "auto", height: "auto", maxWidth: "min(68rem, 92vw)", maxHeight: "78vh", objectFit: "contain" }}
    />
  );
}

export function PropertyCommandCenter({
  property,
  buildings,
  units,
  tenants,
  leases,
  invoices,
  payments,
  requests,
  financeState,
  maintenanceState,
  financePartial,
  maintenancePartial,
  financeError,
  maintenanceError,
  organizationId,
  canReadListings,
  canReadBilling,
  canMaintenance,
  canAudit,
  canWritePortfolio,
  previewMode,
  onBack,
  onNavigate,
  onAddUnit,
}: {
  property: PropertyRecord;
  buildings: BuildingRecord[];
  units: UnitRecord[];
  tenants: TenantRecord[];
  leases: LeaseRecord[];
  invoices: AnalyticsInvoice[];
  payments: AnalyticsPayment[];
  requests: AnalyticsRequest[];
  financeState: SourceState;
  maintenanceState: SourceState;
  financePartial: boolean;
  maintenancePartial: boolean;
  financeError: string;
  maintenanceError: string;
  organizationId: string;
  canReadListings: boolean;
  canReadBilling: boolean;
  canMaintenance: boolean;
  canAudit: boolean;
  canWritePortfolio: boolean;
  previewMode: boolean;
  onBack: () => void;
  onNavigate: (section: string, options?: { unitStatus?: string; query?: string }) => void;
  onAddUnit: () => void;
}) {
  const propertyId = textId(property.id);
  const [tab, setTab] = useState<TabId>("overview");
  const [period, setPeriod] = useState<PeriodId>("month");
  const [unitQuery, setUnitQuery] = useState("");
  const [unitStatus, setUnitStatus] = useState("");
  const [unitSort, setUnitSort] = useState<UnitSort>("name");
  const [photos, setPhotos] = useState<PhotoFrame[]>([]);
  const [photoState, setPhotoState] = useState<"loading" | "ready" | "empty" | "error" | "hidden">(
    previewMode || !canReadListings ? "hidden" : "loading",
  );
  const [photoNote, setPhotoNote] = useState("");
  const [activePhoto, setActivePhoto] = useState(0);
  const [lightbox, setLightbox] = useState(false);
  const [auditRows, setAuditRows] = useState<AuditRow[]>([]);
  const [auditState, setAuditState] = useState<"loading" | "ready" | "error" | "hidden" | "preview">(
    previewMode ? "preview" : canAudit ? "loading" : "hidden",
  );
  const [auditError, setAuditError] = useState("");
  const [auditPartial, setAuditPartial] = useState(false);

  const propertyBuildings = buildings.filter(building => textId(building.property) === propertyId);
  const buildingIds = new Set(propertyBuildings.map(building => textId(building.id)));
  const propertyUnits = units.filter(unit => buildingIds.has(textId(unit.building)));
  const unitIds = new Set(propertyUnits.map(unit => textId(unit.id)));
  const unitIdKey = propertyUnits.map(unit => textId(unit.id)).sort().join(",");

  const graph: PortfolioGraph = {
    properties: [{
      id: propertyId,
      name: property.name,
      address: property.address,
      city: property.city,
      country: property.country,
      is_active: property.is_active,
    }],
    buildings: propertyBuildings.map(building => ({ id: textId(building.id), property: propertyId })),
    units: propertyUnits.map(unit => ({ id: textId(unit.id), building: textId(unit.building), status: unit.status })),
    leases: leases
      .filter(lease => unitIds.has(textId(lease.unit)))
      .map(lease => ({
        id: textId(lease.id),
        unit: textId(lease.unit),
        status: lease.status,
        end_date: lease.end_date,
        monthly_rent_minor: Number.isSafeInteger(lease.monthly_rent_minor) ? lease.monthly_rent_minor : 0,
      })),
  };

  const financeReady = financeState === "ready";
  const maintenanceReady = maintenanceState === "ready";
  const today = rentalBusinessDate();
  const range = periodRange(today, period);
  const performance = portfolioPerformance(
    graph,
    financeReady ? invoices : [],
    maintenanceReady ? requests.filter(request => request.organization === organizationId) : [],
  )[0];
  const stay = occupancy(graph.units, graph, propertyId);
  const propertyRequests = maintenanceReady
    ? scopeRequests(requests, organizationId, graph, propertyId)
    : [];
  const openRequests = propertyRequests.filter(request => request.status === "OPEN" || request.status === "IN_PROGRESS");
  const urgentRequests = propertyRequests.filter(needsAttention);
  const approvalRequests = propertyRequests.filter(pendingApproval);
  const collected = range && financeReady
    ? collectedCents(payments, invoices, graph, range.start, range.end, propertyId)
    : null;
  const openInvoices = financeReady ? postedOpenInvoices(invoices, graph, propertyId) : null;

  useEffect(() => {
    if (previewMode || !canReadListings) return;
    let cancelled = false;
    setPhotoState("loading");
    setPhotoNote("");
    void (async () => {
      try {
        const response = await clientApi.get<ManagedListing[] | { results?: ManagedListing[]; next?: string | null }>(
          "/api/v1/marketplace/manage/listings/",
        );
        if (cancelled) return;
        const page = readPage(response.data);
        const knownUnits = new Set(unitIdKey.split(",").filter(Boolean));
        const frames = page.rows
          .filter(listing => knownUnits.has(textId(listing.unit)))
          .flatMap(listing => (listing.photos ?? []).map(photo => ({
            key: `${listing.id}-${photo.id}`,
            url: photo.url,
            caption: photo.caption ?? "",
            unitName: listing.unit_label || "Unit",
            panorama: isPanoramaCaption(photo.caption),
            position: photo.position ?? 0,
            primary: Boolean(photo.is_primary),
          })))
          .sort((left, right) => Number(right.primary) - Number(left.primary) || left.position - right.position);
        setPhotos(frames.map(frame => ({
          key: frame.key,
          url: frame.url,
          caption: frame.caption,
          unitName: frame.unitName,
          panorama: frame.panorama,
        })));
        setActivePhoto(0);
        setPhotoNote(page.partial ? "Listing photographs are the first loaded page." : "");
        setPhotoState(frames.length ? "ready" : "empty");
      } catch (error) {
        if (cancelled) return;
        if (error instanceof ClientApiError && (error.status === 401 || error.status === 403)) {
          setPhotoState("hidden");
          return;
        }
        setPhotos([]);
        setPhotoNote(apiErrorMessage(error, "Photographs could not be loaded."));
        setPhotoState("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [canReadListings, previewMode, unitIdKey]);

  useEffect(() => {
    if (previewMode || !canAudit || !organizationId) return;
    let cancelled = false;
    setAuditState("loading");
    setAuditError("");
    void (async () => {
      try {
        const response = await clientApi.get<AuditRow[] | { results?: AuditRow[]; next?: string | null }>(
          "/api/v1/audit/logs/",
          { params: { organization: organizationId } },
        );
        if (cancelled) return;
        const page = readPage(response.data);
        setAuditRows(page.rows);
        setAuditPartial(page.partial);
        setAuditState("ready");
      } catch (error) {
        if (cancelled) return;
        setAuditRows([]);
        setAuditError(apiErrorMessage(error, "Property history could not be loaded."));
        setAuditState("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [canAudit, organizationId, previewMode]);

  useEffect(() => {
    if (!lightbox) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setLightbox(false);
      if (event.key === "ArrowRight" && photos.length > 1) setActivePhoto(index => (index + 1) % photos.length);
      if (event.key === "ArrowLeft" && photos.length > 1) setActivePhoto(index => (index - 1 + photos.length) % photos.length);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [lightbox, photos.length]);

  const location = [property.address, property.city, property.country].filter(Boolean).join(", ");
  const activeLeaseByUnit = new Map<string, LeaseRecord>();
  for (const lease of leases) {
    if (lease.status === "ACTIVE" && unitIds.has(textId(lease.unit))) activeLeaseByUnit.set(textId(lease.unit), lease);
  }

  function tenantName(tenantId: Identifier): string {
    const tenant = tenants.find(item => textId(item.id) === textId(tenantId));
    if (!tenant) return "Tenant unavailable";
    return tenant.full_name || `${tenant.first_name} ${tenant.last_name}`.trim() || "Tenant unavailable";
  }

  function onPropertyInvoice(invoice: AnalyticsInvoice): boolean {
    return Boolean(invoice.lease) && propertyIdForLease(invoice.lease ?? "", graph) === propertyId;
  }

  function unitOutstanding(unitId: string): number | null {
    const balances: number[] = [];
    for (const invoice of invoices) {
      if (invoice.status !== "POSTED" || !(invoice.balance_cents > 0) || !invoice.lease) continue;
      const lease = graph.leases.find(item => item.id === invoice.lease);
      if (!lease || lease.unit !== unitId) continue;
      balances.push(invoice.balance_cents);
    }
    if (balances.length === 0) return 0;
    return sumCents(balances);
  }

  function attributedAmount(payment: AnalyticsPayment): number | null {
    const parts: number[] = [];
    for (const allocation of payment.allocations) {
      const invoice = invoices.find(item => item.charges.some(charge => charge.id === allocation.charge));
      if (!invoice?.lease || propertyIdForLease(invoice.lease, graph) !== propertyId) continue;
      parts.push(allocation.amount_cents);
    }
    if (parts.length === 0) return null;
    return sumCents(parts);
  }

  const postedInvoices = financeReady ? invoices.filter(invoice => invoice.status === "POSTED" && onPropertyInvoice(invoice)) : [];
  const attributedPayments = financeReady
    ? payments.flatMap(payment => {
        const amount = attributedAmount(payment);
        return amount == null ? [] : [{ payment, amount }];
      })
    : [];

  const leaseIds = new Set(graph.leases.map(lease => lease.id));
  const invoiceIds = new Set(postedInvoices.flatMap(invoice => invoice.id ? [invoice.id] : []));
  const paymentIds = new Set(attributedPayments.flatMap(row => row.payment.id ? [row.payment.id] : []));
  const requestIds = new Set(propertyRequests.map(request => request.id));
  const activity = auditRows.filter(row => {
    const objectId = String(row.object_id);
    if (row.object_type === "Property") return objectId === propertyId;
    if (row.object_type === "Unit") return unitIds.has(objectId);
    if (row.object_type === "Lease") return leaseIds.has(objectId);
    if (row.object_type === "Invoice") return invoiceIds.has(objectId);
    if (row.object_type === "Payment") return paymentIds.has(objectId);
    if (row.object_type === "MaintenanceRequest") return requestIds.has(objectId);
    return false;
  });

  const unitRows = propertyUnits.map(unit => {
    const id = textId(unit.id);
    const building = propertyBuildings.find(item => textId(item.id) === textId(unit.building));
    const lease = activeLeaseByUnit.get(id) ?? null;
    return {
      unit,
      id,
      buildingName: building?.name ?? "Building unavailable",
      lease,
      tenant: lease ? tenantName(lease.tenant) : "",
      rent: lease && Number.isSafeInteger(lease.monthly_rent_minor) ? lease.monthly_rent_minor : null,
      outstanding: financeReady ? unitOutstanding(id) : null,
    };
  }).filter(row => {
    if (unitStatus && row.unit.status !== unitStatus) return false;
    const needle = unitQuery.trim().toLowerCase();
    if (!needle) return true;
    return [row.unit.name, row.buildingName, row.unit.status, row.tenant, row.lease?.reference]
      .some(value => String(value ?? "").toLowerCase().includes(needle));
  }).sort((left, right) => {
    const byName = left.unit.name.localeCompare(right.unit.name, "en");
    if (unitSort === "name") return byName;
    if (unitSort === "status") return left.unit.status.localeCompare(right.unit.status) || byName;
    const ranked = unitSort === "rent"
      ? nullsLast(left.rent, right.rent)
      : nullsLast(left.outstanding, right.outstanding);
    return ranked || byName;
  });

  const expiring = graph.leases.filter(lease => {
    if (lease.status !== "ACTIVE") return false;
    const days = daysUntilRentalDate(lease.end_date);
    return days != null && days >= 0 && days <= 30;
  });
  const photo = photos[activePhoto];
  const photoAlt = photo
    ? `${visibleCaption(photo.caption) || property.name}. Listing photograph for ${photo.unitName}${photo.panorama ? ". 360 degree photograph shown as a still" : ""}.`
    : "";

  const plateCopy = photoState === "ready" && photo
    ? `${photo.panorama ? "360° listing photograph, shown as a still. " : ""}${visibleCaption(photo.caption) || photo.unitName}${photos.length > 1 ? ` · ${activePhoto + 1} of ${photos.length}` : ""}`
    : photoState === "loading"
      ? "Loading photographs…"
      : photoState === "error"
        ? photoNote
        : photoState === "hidden"
          ? (previewMode
            ? "Preview does not include listing photographs. This plate is not a photograph."
            : "Listing photographs are not loaded in this view.")
          : "Saved listing photos for this property’s units appear here. This plate is not a photograph.";

  return (
    <article className="command" aria-labelledby="command-title">
      <header className="command-hero">
        <div className="command-frame">
          {photoState === "ready" && photo ? (
            <button type="button" className="command-stage" onClick={() => setLightbox(true)} aria-label={`View photograph: ${photoAlt}`}>
              <AuthPhoto url={photo.url} alt={photoAlt} fill />
            </button>
          ) : (
            <div className="command-fallback" role="img" aria-label={photoState === "error" ? photoNote : `No listing photographs are saved for ${property.name}`}>
              <span aria-hidden="true">{initials(property.name)}</span>
            </div>
          )}
          <div className="command-hero-copy">
            <div className="command-identity">
              <button type="button" className="command-back" onClick={onBack}>Back to properties</button>
              <p className="command-kicker">Property workspace</p>
              <h2 id="command-title">{property.name}</h2>
              <p className="command-location">{location || "Address not provided"}</p>
              <p className="command-identity-meta">
                <span className={`command-status ${property.is_active ? "is-active" : ""}`}>{property.is_active ? "Active" : "Inactive"}</span>
                <span>Record {propertyId}</span>
                <span>{propertyBuildings.length} building{propertyBuildings.length === 1 ? "" : "s"}</span>
              </p>
              <p className="command-caption">{plateCopy}{photoNote && photoState === "ready" ? ` ${photoNote}` : ""}</p>
            </div>
            {photoState === "ready" && photos.length > 1 && (
              <div className="command-thumbs" role="tablist" aria-label="Property photographs">
                {photos.map((frame, index) => (
                  <button
                    key={frame.key}
                    type="button"
                    role="tab"
                    aria-selected={index === activePhoto}
                    aria-label={`${frame.unitName}, photograph ${index + 1} of ${photos.length}`}
                    className={index === activePhoto ? "is-selected" : undefined}
                    onClick={() => setActivePhoto(index)}
                  >
                    <AuthPhoto url={frame.url} alt="" fill quiet />
                    <span>{frame.unitName}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        <div className="command-plate">
          <dl className="command-hero-facts">
            <div><dt>Active units</dt><dd>{stay.active} of {propertyUnits.length}</dd></div>
            <div><dt>Occupancy</dt><dd>{stay.rate == null ? "—" : `${stay.rate}%`}</dd></div>
            <div><dt>Occupied</dt><dd>{stay.occupied}</dd></div>
            <div><dt>Vacant</dt><dd>{stay.vacant}</dd></div>
          </dl>
          <div className="command-actions">
            {canWritePortfolio && !previewMode && (
              <button type="button" className="landlord-button landlord-button--primary" onClick={onAddUnit} disabled={!propertyBuildings.length}>Add unit</button>
            )}
            <button type="button" className="landlord-button landlord-button--quiet" onClick={() => onNavigate("units")}>Unit register</button>
            {canReadBilling && !previewMode && (
              <button type="button" className="landlord-button landlord-button--quiet" onClick={() => onNavigate("billing")}>Billing</button>
            )}
            {canMaintenance && !previewMode && (
              <button type="button" className="landlord-button landlord-button--quiet" onClick={() => onNavigate("maintenance-requests")}>Maintenance</button>
            )}
            {canReadListings && !previewMode && (
              <button type="button" className="landlord-button landlord-button--quiet" onClick={() => onNavigate("marketplace")}>Listings</button>
            )}
          </div>
        </div>
      </header>

      <div className="command-tabs" role="tablist" aria-label="Property sections">
        {TABS.map(item => (
          <button
            key={item.id}
            type="button"
            role="tab"
            id={`command-tab-${item.id}`}
            aria-selected={tab === item.id}
            aria-controls={`command-panel-${item.id}`}
            className={tab === item.id ? "is-selected" : undefined}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <section className="command-panel" role="tabpanel" id="command-panel-overview" aria-labelledby="command-tab-overview">
          <div className="command-period">
            <label>
              Collected period
              <select value={period} onChange={event => setPeriod(event.target.value as PeriodId)}>
                {PERIODS.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
              </select>
            </label>
            {range && <p>Nairobi dates {civilDate(range.start)} to {civilDate(range.end)}. Lease rent is the monthly amount on active leases, not cash collected.</p>}
          </div>
          <dl className="command-metrics">
            <div><dt>Active units</dt><dd>{stay.active} <small>of {propertyUnits.length}</small></dd></div>
            <div><dt>Occupancy</dt><dd>{stay.rate == null ? "—" : `${stay.rate}%`}</dd><small>{stay.active === 0 ? "No active units" : `${stay.occupied} occupied`}</small></div>
            <div><dt>Lease rent / month</dt><dd>{performance?.activeLeaseRentMinor == null ? "—" : money(performance.activeLeaseRentMinor)}</dd><small>Active leases</small></div>
            <div>
              <dt>Outstanding</dt>
              <dd>{financeReady ? money(performance?.outstandingCents ?? null) : "—"}</dd>
              <small>{financeReady ? `${openInvoices?.invoices.length ?? 0} posted with a balance` : sourceLabel(financeState, "Billing")}</small>
            </div>
            <div>
              <dt>Collected rent</dt>
              <dd>{financeReady ? money(collected?.cents ?? null) : "—"}</dd>
              <small>Allocated payments in this period</small>
            </div>
            <div>
              <dt>Maintenance</dt>
              <dd>{maintenanceReady ? openRequests.length : "—"}</dd>
              <small>{maintenanceReady ? `${approvalRequests.length} waiting for approval` : sourceLabel(maintenanceState, "Maintenance")}</small>
            </div>
          </dl>
          {(financeError || maintenanceError) && <p className="command-alert" role="alert">{financeError || maintenanceError}</p>}
          {financePartial && <p className="command-note">Billing figures use the first loaded page.</p>}
          {collected && collected.unattributedPayments > 0 && (
            <p className="command-note">{collected.unattributedPayments} settled payment{collected.unattributedPayments === 1 ? "" : "s"} in this period {collected.unattributedPayments === 1 ? "has" : "have"} no allocation and {collected.unattributedPayments === 1 ? "is" : "are"} not included.</p>
          )}
          <div className="command-split-layout">
            <div>
              <h3>Occupancy</h3>
              {propertyUnits.length === 0 ? (
                <p className="command-empty">No units are saved for this property.</p>
              ) : stay.active === 0 ? (
                <p className="command-empty">No active units. Occupancy is not shown as zero. {stay.inactive} inactive.</p>
              ) : (
                <>
                  <div className="command-split" role="group" aria-label="Active unit mix">
                    {stay.occupied > 0 && <button type="button" style={{ flexGrow: stay.occupied }} onClick={() => onNavigate("units", { unitStatus: "OCCUPIED" })} aria-label={`Occupied, ${stay.occupied}. Open the unit register.`}>Occupied</button>}
                    {stay.vacant > 0 && <button type="button" style={{ flexGrow: stay.vacant }} onClick={() => onNavigate("units", { unitStatus: "AVAILABLE" })} aria-label={`Vacant, ${stay.vacant}. Open the unit register.`}>Vacant</button>}
                    {stay.maintenance > 0 && <button type="button" style={{ flexGrow: stay.maintenance }} onClick={() => onNavigate("units", { unitStatus: "MAINTENANCE" })} aria-label={`Maintenance, ${stay.maintenance}. Open the unit register.`}>Maintenance</button>}
                  </div>
                  <ul className="command-legend">
                    <li><button type="button" onClick={() => onNavigate("units", { unitStatus: "OCCUPIED" })}>Occupied {stay.occupied}</button></li>
                    <li><button type="button" onClick={() => onNavigate("units", { unitStatus: "AVAILABLE" })}>Vacant {stay.vacant}</button></li>
                    <li><button type="button" onClick={() => onNavigate("units", { unitStatus: "MAINTENANCE" })}>Maintenance {stay.maintenance}</button></li>
                    <li><button type="button" onClick={() => onNavigate("units", { unitStatus: "INACTIVE" })}>Inactive {stay.inactive}</button></li>
                  </ul>
                </>
              )}
            </div>
            <div>
              <h3>Needs attention</h3>
              <ul className="command-attention">
                {urgentRequests.map(request => (
                  <li key={request.id}>
                    <span><strong>{request.title}</strong><small>{humanize(request.status)} · class {request.priority_class || "—"}{request.emergency_override ? " · emergency" : ""}</small></span>
                    <button type="button" onClick={() => onNavigate("maintenance-requests")}>Open maintenance</button>
                  </li>
                ))}
                {approvalRequests.filter(request => !needsAttention(request)).map(request => (
                  <li key={`approval-${request.id}`}>
                    <span><strong>{request.title}</strong><small>Waiting for approval</small></span>
                    <button type="button" onClick={() => onNavigate("maintenance-requests")}>Review approvals</button>
                  </li>
                ))}
                {expiring.map(lease => (
                  <li key={lease.id}>
                    <span><strong>Lease {leases.find(item => textId(item.id) === lease.id)?.reference || lease.id}</strong><small>Ends {civilDate(lease.end_date)}</small></span>
                    <button type="button" onClick={() => onNavigate("leases", { query: leases.find(item => textId(item.id) === lease.id)?.reference })}>Open leases</button>
                  </li>
                ))}
                {stay.vacant > 0 && (
                  <li>
                    <span><strong>{stay.vacant} unit{stay.vacant === 1 ? "" : "s"} marked available</strong><small>Status available</small></span>
                    <button type="button" onClick={() => onNavigate("units", { unitStatus: "AVAILABLE" })}>Open available units</button>
                  </li>
                )}
                {urgentRequests.length === 0 && approvalRequests.length === 0 && expiring.length === 0 && stay.vacant === 0 && (
                  <li className="command-quiet">Nothing in the loaded records needs attention for this property.</li>
                )}
              </ul>
            </div>
          </div>
        </section>
      )}

      {tab === "units" && (
        <section className="command-panel" role="tabpanel" id="command-panel-units" aria-labelledby="command-tab-units">
          <div className="command-tools">
            <label>Find a unit
              <input type="search" value={unitQuery} onChange={event => setUnitQuery(event.target.value)} placeholder="Name, tenant, or lease" />
            </label>
            <label>Status
              <select value={unitStatus} onChange={event => setUnitStatus(event.target.value)}>
                <option value="">All statuses</option>
                {UNIT_STATUSES.map(status => <option key={status} value={status}>{humanize(status === "AVAILABLE" ? "Vacant" : status)}</option>)}
              </select>
            </label>
            <label>Sort
              <select value={!financeReady && unitSort === "outstanding" ? "name" : unitSort} onChange={event => setUnitSort(event.target.value as UnitSort)}>
                <option value="name">Unit name</option>
                <option value="status">Status</option>
                <option value="rent">Active lease rent</option>
                <option value="outstanding" disabled={!financeReady}>Outstanding</option>
              </select>
            </label>
          </div>
          <p className="command-note" role="status">{unitRows.length} of {propertyUnits.length} units. Monthly rent is the active lease amount, not cash collected.</p>
          {propertyUnits.length === 0 ? (
            <p className="command-empty">This property has no units yet.{canWritePortfolio && !previewMode ? " Add a unit once a building exists." : ""}</p>
          ) : unitRows.length === 0 ? (
            <p className="command-empty">No unit matches that search or status.</p>
          ) : (
            <>
              <div className="command-table-wrap command-desktop-only">
                <table className="command-table">
                  <caption>Units at {property.name}</caption>
                  <thead>
                    <tr>
                      <th>Unit</th><th>Status</th><th>Tenant</th><th>Lease</th><th>Dates</th><th className="num">Lease rent / month</th><th className="num">Outstanding</th><th>Records</th>
                    </tr>
                  </thead>
                  <tbody>
                    {unitRows.map(row => (
                      <tr key={row.id}>
                        <td><strong>{row.unit.name}</strong><small>{row.buildingName}{row.unit.bedrooms ? ` · ${row.unit.bedrooms} bed` : ""}</small></td>
                        <td><span className={`command-pill is-${row.unit.status.toLowerCase()}`}>{humanize(row.unit.status === "AVAILABLE" ? "Vacant" : row.unit.status)}</span></td>
                        <td>{row.lease ? row.tenant : "No active lease"}</td>
                        <td>{row.lease ? row.lease.reference : "—"}</td>
                        <td className="command-nowrap">{row.lease ? `${civilDate(row.lease.start_date)} – ${civilDate(row.lease.end_date)}` : "—"}</td>
                        <td className="num">{row.rent == null ? "—" : money(row.rent)}</td>
                        <td className="num">{financeReady ? money(row.outstanding) : "—"}</td>
                        <td className="command-links">
                          <button type="button" onClick={() => onNavigate("units", { query: row.unit.name })}>Unit register</button>
                          {row.lease && <button type="button" onClick={() => onNavigate("leases", { query: row.lease?.reference })}>Lease</button>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <ul className="command-cards">
                {unitRows.map(row => (
                  <li key={row.id}>
                    <strong>{row.unit.name}</strong>
                    <small>{row.buildingName} · {humanize(row.unit.status === "AVAILABLE" ? "Vacant" : row.unit.status)}</small>
                    <dl>
                      <div><dt>Tenant</dt><dd>{row.lease ? row.tenant : "No active lease"}</dd></div>
                      <div><dt>Lease</dt><dd>{row.lease ? row.lease.reference : "—"}</dd></div>
                      <div className="command-span"><dt>Dates</dt><dd>{row.lease ? `${civilDate(row.lease.start_date)} – ${civilDate(row.lease.end_date)}` : "—"}</dd></div>
                      <div><dt>Lease rent / month</dt><dd>{row.rent == null ? "—" : money(row.rent)}</dd></div>
                      <div><dt>Outstanding</dt><dd>{financeReady ? money(row.outstanding) : "—"}</dd></div>
                    </dl>
                    <div className="command-links">
                      <button type="button" onClick={() => onNavigate("units", { query: row.unit.name })}>Unit register</button>
                      {row.lease && <button type="button" onClick={() => onNavigate("leases", { query: row.lease?.reference })}>Lease</button>}
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      )}

      {tab === "financials" && (
        <section className="command-panel" role="tabpanel" id="command-panel-financials" aria-labelledby="command-tab-financials">
          {!canReadBilling || financeState === "hidden" ? (
            <p className="command-empty">Billing records are not available for this role.</p>
          ) : financeState === "preview" ? (
            <p className="command-empty">Preview does not include ledger records. Outstanding and collected rent are unavailable, not zero.</p>
          ) : financeState === "loading" ? (
            <p className="command-empty">Loading billing…</p>
          ) : financeState === "error" ? (
            <p className="command-alert" role="alert">{financeError || "Billing records could not be loaded."}</p>
          ) : (
            <>
              <div className="command-period">
                <label>
                  Collected period
                  <select value={period} onChange={event => setPeriod(event.target.value as PeriodId)}>
                    {PERIODS.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
                  </select>
                </label>
              </div>
              <dl className="command-metrics command-metrics--three">
                <div><dt>Collected rent</dt><dd>{money(collected?.cents ?? null)}</dd><small>Allocated payments, {range ? `${civilDate(range.start)} – ${civilDate(range.end)}` : "selected period"}</small></div>
                <div><dt>Outstanding</dt><dd>{money(performance?.outstandingCents ?? null)}</dd><small>Current posted balances on this property</small></div>
                <div><dt>Lease rent / month</dt><dd>{performance?.activeLeaseRentMinor == null ? "—" : money(performance.activeLeaseRentMinor)}</dd><small>Not cash collected</small></div>
              </dl>
              {financePartial && <p className="command-note">These records are the first loaded page.</p>}
              {openInvoices && openInvoices.unattributed > 0 && (
                <p className="command-note">{openInvoices.unattributed} open invoice{openInvoices.unattributed === 1 ? "" : "s"} have no reliable property link and are excluded.</p>
              )}
              <div className="command-section-head">
                <h3>Posted invoices</h3>
                <button type="button" className="landlord-button landlord-button--quiet" onClick={() => onNavigate("billing")}>Open billing</button>
              </div>
              {postedInvoices.length === 0 ? (
                <p className="command-empty">No posted invoice is linked to a lease at this property.</p>
              ) : (
                <div className="command-table-wrap command-desktop-only">
                  <table className="command-table">
                    <caption>Posted invoices for {property.name}</caption>
                    <thead><tr><th>Invoice</th><th>Status</th><th>Due</th><th className="num">Total</th><th className="num">Balance</th></tr></thead>
                    <tbody>
                      {postedInvoices.map(invoice => {
                        const lease = graph.leases.find(item => item.id === invoice.lease);
                        const unit = propertyUnits.find(item => textId(item.id) === lease?.unit);
                        return (
                          <tr key={invoice.id || `${invoice.lease}-${invoice.due_date}-${invoice.total_cents}`}>
                            <td><strong>{invoice.id ? `Invoice ${invoice.id}` : "Posted invoice"}</strong><small>{unit ? unit.name : "Unit link unavailable"}</small></td>
                            <td>{humanize(invoice.status)}</td>
                            <td>{civilDate(invoice.due_date)}</td>
                            <td className="num">{money(invoice.total_cents)}</td>
                            <td className="num">{money(invoice.balance_cents)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
              {postedInvoices.length > 0 && (
                <ul className="command-cards">
                  {postedInvoices.map(invoice => {
                    const lease = graph.leases.find(item => item.id === invoice.lease);
                    const unit = propertyUnits.find(item => textId(item.id) === lease?.unit);
                    return (
                      <li key={invoice.id || `${invoice.lease}-${invoice.due_date}-${invoice.total_cents}`}>
                        <strong>{invoice.id ? `Invoice ${invoice.id}` : "Posted invoice"}</strong>
                        <small>{unit ? unit.name : "Unit link unavailable"} · {humanize(invoice.status)}</small>
                        <dl>
                          <div><dt>Due</dt><dd>{civilDate(invoice.due_date)}</dd></div>
                          <div><dt>Total</dt><dd>{money(invoice.total_cents)}</dd></div>
                          <div className="command-span"><dt>Balance</dt><dd>{money(invoice.balance_cents)}</dd></div>
                        </dl>
                        <div className="command-links">
                          <button type="button" onClick={() => onNavigate("billing")}>Open billing</button>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
              <div className="command-section-head">
                <h3>Ledger payments</h3>
              </div>
              <p className="command-note">A payment appears here only when an allocation maps through a charge, invoice, and lease to this property. Unallocated payments stay out. Pending, failed, voided, and reversed payments are not collected rent.</p>
              {attributedPayments.length === 0 ? (
                <p className="command-empty">No ledger payment is allocated to this property.</p>
              ) : (
                <div className="command-table-wrap command-desktop-only">
                  <table className="command-table">
                    <caption>Payments allocated to {property.name}</caption>
                    <thead><tr><th>Payment</th><th>Status</th><th>Received</th><th className="num">Attributed</th></tr></thead>
                    <tbody>
                      {attributedPayments.map(({ payment, amount }) => (
                        <tr key={payment.id || `${payment.received_date}-${payment.amount_cents}-${amount}`}>
                          <td>
                            <strong>{payment.id ? `Payment ${payment.id}` : "Ledger payment"}</strong>
                            <small>{[payment.method ? humanize(payment.method) : "", payment.reference].filter(Boolean).join(" · ") || "No method recorded"}</small>
                          </td>
                          <td>{humanize(payment.status)}</td>
                          <td>{civilDate(payment.received_date)}</td>
                          <td className="num">{money(amount)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {attributedPayments.length > 0 && (
                <ul className="command-cards">
                  {attributedPayments.map(({ payment, amount }) => (
                    <li key={payment.id || `${payment.received_date}-${payment.amount_cents}-${amount}`}>
                      <strong>{payment.id ? `Payment ${payment.id}` : "Ledger payment"}</strong>
                      <small>{[payment.method ? humanize(payment.method) : "", payment.reference].filter(Boolean).join(" · ") || "No method recorded"}</small>
                      <dl>
                        <div><dt>Status</dt><dd>{humanize(payment.status)}</dd></div>
                        <div><dt>Received</dt><dd>{civilDate(payment.received_date)}</dd></div>
                        <div className="command-span"><dt>Attributed</dt><dd>{money(amount)}</dd></div>
                      </dl>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </section>
      )}

      {tab === "maintenance" && (
        <section className="command-panel" role="tabpanel" id="command-panel-maintenance" aria-labelledby="command-tab-maintenance">
          {!canMaintenance || maintenanceState === "hidden" ? (
            <p className="command-empty">Maintenance records are not available for this role.</p>
          ) : maintenanceState === "preview" ? (
            <p className="command-empty">Preview does not include maintenance requests.</p>
          ) : maintenanceState === "loading" ? (
            <p className="command-empty">Loading maintenance…</p>
          ) : maintenanceState === "error" ? (
            <p className="command-alert" role="alert">{maintenanceError || "Maintenance requests could not be loaded."}</p>
          ) : (
            <>
              <div className="command-section-head">
                <h3>Requests for this property</h3>
                <button type="button" className="landlord-button landlord-button--quiet" onClick={() => onNavigate("maintenance-requests")}>Open maintenance</button>
              </div>
              {maintenancePartial && <p className="command-note">Showing the first loaded page of requests.</p>}
              <dl className="command-metrics command-metrics--three">
                <div><dt>Open</dt><dd>{openRequests.length}</dd><small>Open or in progress</small></div>
                <div><dt>Needs attention</dt><dd>{urgentRequests.length}</dd><small>Class 1 or emergency</small></div>
                <div><dt>Approvals</dt><dd>{approvalRequests.length}</dd><small>Waiting for approval</small></div>
              </dl>
              {propertyRequests.length === 0 ? (
                <p className="command-empty">No maintenance request is linked to a unit at this property.</p>
              ) : (
                <ul className="command-feed">
                  {[...propertyRequests].sort((left, right) => String(right.updated_at ?? "").localeCompare(String(left.updated_at ?? ""))).map(request => {
                    const unit = propertyUnits.find(item => textId(item.id) === request.unit);
                    return (
                      <li key={request.id}>
                        <div>
                          <strong>{request.title}</strong>
                          <small>
                            {humanize(request.status)}
                            {unit ? ` · ${unit.name}` : ""}
                            {request.priority_class ? ` · class ${request.priority_class}` : ""}
                            {request.emergency_override ? " · emergency" : ""}
                            {request.requires_approval && (request.status === "OPEN" || request.status === "IN_PROGRESS") ? " · approval required" : ""}
                          </small>
                          <small>{request.updated_at ? `Updated ${formatWhen(request.updated_at)}` : "No update time"}</small>
                        </div>
                        <button type="button" onClick={() => onNavigate("maintenance-requests")}>Open maintenance</button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </>
          )}
        </section>
      )}

      {tab === "activity" && (
        <section className="command-panel" role="tabpanel" id="command-panel-activity" aria-labelledby="command-tab-activity">
          <h3>Saved history</h3>
          <p className="command-note">Only audit entries stored against this property, its units, leases, posted invoices, attributed payments, or maintenance requests are shown. Work orders and quotations are not listed unless the log names one of those records.</p>
          {auditState === "preview" ? (
            <p className="command-empty">Preview does not include organization history.</p>
          ) : auditState === "hidden" ? (
            <p className="command-empty">History is not available for this role.</p>
          ) : auditState === "loading" ? (
            <p className="command-empty">Loading history…</p>
          ) : auditState === "error" ? (
            <p className="command-alert" role="alert">{auditError}</p>
          ) : activity.length === 0 ? (
            <p className="command-empty">No saved history is tied to this property yet.</p>
          ) : (
            <>
              {auditPartial && <p className="command-note">Showing the first loaded page of history.</p>}
              <ol className="command-feed">
                {activity.map(row => (
                  <li key={row.id}>
                    <div>
                      <strong>{humanize(row.action)}</strong>
                      <small>{row.object_type} {row.object_id}</small>
                      <small>{formatWhen(row.created_at)}</small>
                    </div>
                  </li>
                ))}
              </ol>
            </>
          )}
        </section>
      )}

      {lightbox && photo && (
        <div className="command-lightbox" role="dialog" aria-modal="true" aria-label={`Photograph of ${property.name}`}>
          <button type="button" className="command-lightbox-close" onClick={() => setLightbox(false)}>Close</button>
          <AuthPhoto url={photo.url} alt={photoAlt} />
          <p>{visibleCaption(photo.caption) || photo.unitName}{photo.panorama ? " · 360° photograph shown as a still" : ""}</p>
          {photos.length > 1 && (
            <div className="command-lightbox-nav">
              <button type="button" onClick={() => setActivePhoto(index => (index - 1 + photos.length) % photos.length)}>Previous</button>
              <button type="button" onClick={() => setActivePhoto(index => (index + 1) % photos.length)}>Next</button>
            </div>
          )}
        </div>
      )}
    </article>
  );
}

function sourceLabel(state: SourceState, name: string): string {
  if (state === "loading") return `Loading ${name.toLowerCase()}…`;
  if (state === "error") return `${name} unavailable`;
  if (state === "preview") return "Unavailable in preview";
  return "Unavailable";
}

function nullsLast(left: number | null, right: number | null): number {
  if (left == null && right == null) return 0;
  if (left == null) return 1;
  if (right == null) return -1;
  return right - left;
}
