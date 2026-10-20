"use client";

import { useMemo, useState } from "react";
import { formatMinor } from "@/lib/money";
import { daysUntilRentalDate, rentalBusinessDate } from "@/lib/rentalDate";
import { formatWhen } from "@/lib/opsApi";
import {
  collectedCents,
  collectionRate,
  collectionTrend,
  latestTimestamp,
  maintenanceByPriority,
  maintenanceByStatus,
  needsAttention,
  occupancy,
  pendingApproval,
  periodRange,
  portfolioPerformance,
  postedOpenInvoices,
  propertyMatches,
  sortProperties,
  type PropertySort,
  scopeRequests,
  sumCents,
  type AnalyticsInvoice,
  type AnalyticsPayment,
  type AnalyticsRequest,
  type PeriodId,
  type PortfolioGraph,
} from "@/lib/portfolioAnalytics";
import "./portfolio-analytics.css";

type SourceState = "ready" | "loading" | "error" | "hidden" | "preview";

type PortfolioAnalyticsProps = {
  greetingName: string;
  showPortfolio: boolean;
  canReadBilling: boolean;
  canMaintenance: boolean;
  organizationId: string;
  graph: PortfolioGraph;
  invoices: AnalyticsInvoice[];
  payments: AnalyticsPayment[];
  requests: AnalyticsRequest[];
  financeState: SourceState;
  maintenanceState: SourceState;
  financePartial: boolean;
  maintenancePartial: boolean;
  financeError: string;
  maintenanceError: string;
  propertyId: string;
  onPropertyId: (propertyId: string) => void;
  onOpenProperty?: (propertyId: string) => void;
  onOpen: (section: string, unitStatus?: string) => void;
};

const PERIODS: { id: PeriodId; label: string }[] = [
  { id: "month", label: "This month" },
  { id: "30", label: "Last 30 days" },
  { id: "90", label: "Last 90 days" },
  { id: "year", label: "This year" },
];

function money(cents: number | null): string {
  return cents == null ? "—" : formatMinor(cents);
}

function formatCivil(iso: string): string {
  const month = /^(\d{4})-(\d{2})$/.exec(iso);
  if (month) {
    return new Intl.DateTimeFormat("en-KE", { month: "short", year: "numeric", timeZone: "UTC" }).format(
      new Date(Date.UTC(Number(month[1]), Number(month[2]) - 1, 1)),
    );
  }
  const day = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!day) return iso;
  return new Intl.DateTimeFormat("en-KE", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(
    new Date(Date.UTC(Number(day[1]), Number(day[2]) - 1, Number(day[3]))),
  );
}

function compactAxis(cents: number): string {
  const whole = Math.trunc(cents / 100);
  if (whole >= 1_000_000) {
    const millions = Math.trunc(whole / 100_000) / 10;
    return `${millions}m`;
  }
  if (whole >= 10_000) return `${Math.trunc(whole / 1000)}k`;
  return whole.toLocaleString("en-KE");
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function axisTick(key: string, keys: string[], index: number): string {
  if (/^\d{4}-\d{2}-\d{2}$/.test(key)) {
    const day = String(Number(key.slice(8, 10)));
    if (keys.length > 12) return day;
    const month = MONTHS[Number(key.slice(5, 7)) - 1] ?? "";
    return `${day} ${month}`;
  }
  if (/^\d{4}-\d{2}$/.test(key)) {
    const month = MONTHS[Number(key.slice(5, 7)) - 1] ?? key;
    const year = key.slice(0, 4);
    if (keys.length <= 6) return `${month} ${year}`;
    const previousYear = index > 0 ? keys[index - 1].slice(0, 4) : "";
    return index === 0 || year !== previousYear ? `${month} ${year.slice(2)}` : month;
  }
  return key;
}

function openBalanceNote(count: number): string {
  if (count === 0) return "No posted invoice has an open balance";
  return `${count} posted invoice${count === 1 ? "" : "s"} with a balance still open`;
}

export function PortfolioAnalytics({
  greetingName,
  showPortfolio,
  canMaintenance,
  organizationId,
  graph,
  invoices,
  payments,
  requests,
  financeState,
  maintenanceState,
  financePartial,
  maintenancePartial,
  financeError,
  maintenanceError,
  propertyId,
  onPropertyId,
  onOpenProperty,
  onOpen,
}: PortfolioAnalyticsProps) {
  const openPropertyRecord = (id: string) => {
    if (onOpenProperty) onOpenProperty(id);
    else {
      onPropertyId(id);
      onOpen("properties");
    }
  };
  const [period, setPeriod] = useState<PeriodId>("month");
  const [propertyQuery, setPropertyQuery] = useState("");
  const [propertySort, setPropertySort] = useState<PropertySort>("name");
  const [tip, setTip] = useState<{ x: number; y: number; title: string; value: string } | null>(null);
  const today = rentalBusinessDate();
  const range = periodRange(today, period);
  const orgInvoices = invoices.filter(invoice => invoice.organization === organizationId);
  const orgPayments = payments.filter(payment => payment.organization === organizationId);
  const scopedRequests = scopeRequests(requests, organizationId, graph, propertyId);
  const units = occupancy(graph.units, graph, propertyId);
  const collected = range && financeState === "ready"
    ? collectedCents(orgPayments, orgInvoices, graph, range.start, range.end, propertyId)
    : null;
  const openInvoices = financeState === "ready" ? postedOpenInvoices(orgInvoices, graph, propertyId) : null;
  const outstanding = openInvoices ? sumCents(openInvoices.invoices.map(invoice => invoice.balance_cents)) : null;
  const overdueInvoices = openInvoices
    ? openInvoices.invoices.filter(invoice => {
      const days = daysUntilRentalDate(invoice.due_date);
      return days != null && days < 0;
    })
    : [];
  const overdueCents = sumCents(overdueInvoices.map(invoice => invoice.balance_cents));
  const rate = range && financeState === "ready"
    ? collectionRate(orgInvoices, graph, range.start, range.end, propertyId)
    : null;
  const trend = range && financeState === "ready"
    ? collectionTrend(orgPayments, orgInvoices, graph, range.start, range.end, propertyId)
    : null;
  const openRequests = scopedRequests.filter(request => request.status === "OPEN" || request.status === "IN_PROGRESS");
  const urgent = scopedRequests.filter(needsAttention);
  const approvals = scopedRequests.filter(pendingApproval);
  const ending = graph.leases.filter(lease => {
    if (lease.status !== "ACTIVE") return false;
    if (propertyId) {
      const unit = graph.units.find(item => item.id === lease.unit);
      const building = graph.buildings.find(item => item.id === unit?.building);
      if (building?.property !== propertyId) return false;
    }
    const days = daysUntilRentalDate(lease.end_date);
    return days != null && days >= 0 && days <= 30;
  });
  const updated = latestTimestamp([
    ...orgInvoices.map(invoice => invoice.updated_at),
    ...orgPayments.map(payment => payment.updated_at),
    ...scopedRequests.map(request => request.updated_at),
  ]);
  const periodLabel = PERIODS.find(item => item.id === period)?.label ?? "This month";
  const rangeText = range ? `${formatCivil(range.start)} to ${formatCivil(range.end)}` : periodLabel;
  const financeReady = financeState === "ready";
  const maintenanceReady = maintenanceState === "ready";
  const bucket = period === "month" || period === "30" ? "day" : "month";
  const activeSort: PropertySort = !financeReady && propertySort === "outstanding" ? "name" : propertySort;
  const allPropertyRows = useMemo(() => {
    return portfolioPerformance(
      graph,
      financeReady ? orgInvoices : [],
      maintenanceReady ? requests.filter(request => request.organization === organizationId) : [],
    );
  }, [financeReady, graph, maintenanceReady, orgInvoices, organizationId, requests]);
  const propertyRows = useMemo(() => {
    return sortProperties(allPropertyRows, activeSort).filter(property => propertyMatches(property, propertyQuery));
  }, [activeSort, allPropertyRows, propertyQuery]);

  const attention = [
    financeReady && overdueInvoices.length > 0 ? {
      id: "overdue",
      label: `${overdueInvoices.length} posted invoice${overdueInvoices.length === 1 ? "" : "s"} past the due date`,
      detail: money(overdueCents),
      action: "Review billing",
      section: "billing",
    } : null,
    showPortfolio && ending.length > 0 ? {
      id: "leases",
      label: `${ending.length} active lease${ending.length === 1 ? "" : "s"} end within 30 days`,
      detail: "Leases",
      action: "Open leases",
      section: "leases",
    } : null,
    showPortfolio && units.vacant > 0 ? {
      id: "vacant",
      label: `${units.vacant} unit${units.vacant === 1 ? "" : "s"} marked available`,
      detail: "Units",
      action: "Open available units",
      section: "units",
      status: "AVAILABLE",
    } : null,
    maintenanceReady && urgent.length > 0 ? {
      id: "urgent",
      label: `${urgent.length} open request${urgent.length === 1 ? "" : "s"} at class 1 or emergency`,
      detail: urgent[0]?.title ?? "Maintenance",
      action: "Open maintenance",
      section: "maintenance-requests",
    } : null,
    maintenanceReady && approvals.length > 0 ? {
      id: "approval",
      label: `${approvals.length} open request${approvals.length === 1 ? "" : "s"} waiting for approval`,
      detail: "Maintenance",
      action: "Review approvals",
      section: "maintenance-requests",
    } : null,
  ].filter((item): item is { id: string; label: string; detail: string; action: string; section: string; status?: string } => item != null);

  return (
    <section className="analytics" aria-label="Portfolio analytics">
      <div className="analytics-header">
        <div>
          <p className="analytics-kicker">{greetingName ? greetingName : "Portfolio"}</p>
          <h2>Operations</h2>
          <p>
            {rangeText}. Nairobi dates. Collected amounts are allocated ledger payments. Outstanding amounts are current posted balances.
          </p>
          {updated && <p>Last record update {formatWhen(updated)}.</p>}
        </div>
        <div className="analytics-controls">
          <label>
            Period
            <select value={period} onChange={event => setPeriod(event.target.value as PeriodId)}>
              {PERIODS.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
            </select>
          </label>
          {showPortfolio && graph.properties.length > 0 && (
            <label>
              Property
              <select value={propertyId} onChange={event => onPropertyId(event.target.value)}>
                <option value="">All properties</option>
                {graph.properties.map(property => <option key={property.id} value={property.id}>{property.name}</option>)}
              </select>
            </label>
          )}
        </div>
      </div>

      <div className="analytics-pulse" aria-label="Portfolio pulse">
        <div className="analytics-pulse-lead">
          <p className="analytics-kicker">Portfolio pulse</p>
          <p className="analytics-pulse-title">
            {attention.length > 0
              ? `${attention.length} live signal${attention.length === 1 ? "" : "s"} need a look.`
              : "No follow-ups in the loaded records."}
          </p>
          <p className="analytics-note">
            {propertyId ? "This view is scoped to the selected property." : "A quick read across the current organization scope."}
          </p>
        </div>
        <div className="analytics-pulse-stat">
          <span>Occupancy</span>
          <strong>{units.rate == null ? "—" : `${units.rate}%`}</strong>
          <small>{units.active === 0 ? "No active units" : `${units.occupied} of ${units.active} active units`}</small>
        </div>
        <div className="analytics-pulse-stat">
          <span>Attention</span>
          <strong>{attention.length}</strong>
          <small>{attention.length === 1 ? "recorded signal" : "recorded signals"}</small>
        </div>
        <div className="analytics-pulse-stat">
          <span>Ledger</span>
          <strong>{financeReady ? (rate ? `${rate.percent}%` : "—") : "—"}</strong>
          <small>{financeReady ? "collection rate" : financeNote(financeState, "collection rate", financeError)}</small>
        </div>
      </div>

      {showPortfolio && (
        <div className="analytics-kpis" aria-label="Portfolio counts">
          <Kpi label="Properties" value={String(propertyId ? 1 : graph.properties.length)} note="Saved property records" onClick={() => onOpen("properties")} />
          <Kpi label="Units" value={String(units.occupied + units.vacant + units.maintenance + units.inactive)} note={units.inactive > 0 ? `${units.inactive} inactive, excluded from the rate` : "Every saved unit"} onClick={() => onOpen("units")} />
          <Kpi label="Occupancy" value={units.rate == null ? "—" : `${units.rate}%`} note={units.active === 0 ? "No active units" : `${units.occupied} of ${units.active} active units occupied`} onClick={() => onOpen("units", "OCCUPIED")} />
          <Kpi label="Vacant units" value={String(units.vacant)} note="Status available" onClick={() => onOpen("units", "AVAILABLE")} />
        </div>
      )}
      <div className="analytics-ledger">
        <p className="analytics-kicker">Ledger</p>
        <p className="analytics-note">Collected and the collection rate use {rangeText}. Outstanding stays the current posted balance, including invoices due outside that window.</p>
        <div className="analytics-kpis" aria-label="Ledger figures">
          <Kpi label="Rent collected" value={financeReady ? money(collected?.cents ?? null) : "—"} note={financeNote(financeState, "Allocated payments received in this period", financeError)} onClick={() => onOpen("billing")} />
          <Kpi label="Outstanding" value={financeReady ? money(outstanding) : "—"} note={financeReady ? openBalanceNote(openInvoices?.invoices.length ?? 0) : financeNote(financeState, "Posted invoices with a balance still open", financeError)} onClick={() => onOpen("billing")} />
          <Kpi label="Collection rate" value={financeReady && rate ? `${rate.percent}%` : "—"} note={financeReady && rate ? `${money(rate.paidCents)} of ${money(rate.issuedCents)} due in this period` : financeReady ? "No posted invoices are due in this period" : financeNote(financeState, "Paid against posted invoices due in this period", financeError)} onClick={() => onOpen("billing")} />
          <Kpi label="Maintenance" value={maintenanceReady ? String(openRequests.length) : "—"} note={maintenanceNote(maintenanceState, "Open or in progress", maintenanceError, canMaintenance)} onClick={() => onOpen("maintenance-requests")} />
        </div>
      </div>
      {(financePartial || maintenancePartial || (collected?.unattributedPayments ?? 0) > 0 || (openInvoices?.unattributed ?? 0) > 0) && (
        <p className="analytics-note">
          {financePartial && "Invoice and payment totals use the first returned page, not a complete ledger. "}
          {maintenancePartial && "Maintenance counts use the first returned page. "}
          {(collected?.unattributedPayments ?? 0) > 0 && `${collected?.unattributedPayments} settled payment${collected?.unattributedPayments === 1 ? "" : "s"} had no charge allocation, so ${propertyId ? "they are left out of this property" : "they are still included in the organization total"}. `}
          {(openInvoices?.unattributed ?? 0) > 0 && `${openInvoices?.unattributed} open invoice${openInvoices?.unattributed === 1 ? "" : "s"} could not be tied to the selected property.`}
        </p>
      )}

      <div className="analytics-grid">
        <article className="analytics-panel analytics-span">
          <div className="analytics-panel-head">
            <div>
              <h3>Rent collection</h3>
              <p className="analytics-note">Allocated ledger payments by {bucket}, {rangeText}. Pending, failed, voided, and reversed payments stay out.</p>
            </div>
            <p className="analytics-figure">{financeReady ? money(collected?.cents ?? null) : "—"}<small>settled in period</small></p>
          </div>
          {financeState === "loading" && <EmptyPlot title="Loading billing records" detail="Collection history appears when the ledger responds." />}
          {financeState !== "loading" && !financeReady && <EmptyPlot title="Collection history unavailable" detail={financeNote(financeState, "Collection history is unavailable.", financeError)} action="Open billing" onAction={() => onOpen("billing")} />}
          {financeReady && trend?.empty && range && (
            <EmptyCollection start={range.start} end={range.end} onOpen={() => onOpen("billing")} />
          )}
          {financeReady && trend && !trend.empty && (
            <ColumnChart
              points={trend.points.map((point, index) => ({
                key: point.key,
                axis: axisTick(point.key, trend.points.map(item => item.key), index),
                value: point.cents,
                title: formatCivil(point.key),
                valueText: formatMinor(point.cents),
              }))}
              maxLabel={compactAxis(Math.max(...trend.points.map(point => point.cents), 1))}
              midLabel={compactAxis(Math.round(Math.max(...trend.points.map(point => point.cents), 1) / 2))}
              onHover={setTip}
              onSelect={() => onOpen("billing")}
            />
          )}
        </article>

        {showPortfolio && (
          <article className="analytics-panel">
            <div className="analytics-panel-head">
              <div>
                <h3>Occupancy</h3>
                <p className="analytics-note">Inactive units stay out of the rate. A segment or row opens that status in the unit register.</p>
              </div>
              <p className="analytics-figure">{units.rate == null ? "—" : `${units.rate}%`}<small>{units.rate == null ? "no active units" : "of active units"}</small></p>
            </div>
            {units.active + units.inactive === 0 ? (
              <p className="analytics-empty">No units are saved for this scope.</p>
            ) : (
              <>
              {units.active === 0 ? (
                <p className="analytics-empty">No active units. Occupancy is not shown as zero.</p>
              ) : (
                <SplitBar
                  segments={[
                    { key: "OCCUPIED", label: "Occupied", count: units.occupied, color: "var(--hodi-chart-1)" },
                    { key: "AVAILABLE", label: "Vacant", count: units.vacant, color: "var(--hodi-chart-2)" },
                    { key: "MAINTENANCE", label: "Maintenance", count: units.maintenance, color: "var(--hodi-chart-4)" },
                  ]}
                  onSelect={status => onOpen("units", status)}
                />
              )}
              <BarList
                rows={[
                  { key: "OCCUPIED", label: "Occupied", count: units.occupied, color: "var(--hodi-chart-1)" },
                  { key: "AVAILABLE", label: "Vacant", count: units.vacant, color: "var(--hodi-chart-2)" },
                  { key: "MAINTENANCE", label: "Maintenance", count: units.maintenance, color: "var(--hodi-chart-4)" },
                  { key: "INACTIVE", label: "Inactive", count: units.inactive, color: "var(--hodi-chart-3)" },
                ]}
                onSelect={status => onOpen("units", status)}
              />
              </>
            )}
          </article>
        )}

        <article className="analytics-panel">
          <h3>Rent position</h3>
          <p className="analytics-note">These are different measures. Settled receipts belong to {rangeText}. Open balances are the stock of posted invoices today.</p>
          {!financeReady && <EmptyPlot title="Rent position unavailable" detail={financeNote(financeState, "Rent position is unavailable.", financeError)} action="Open billing" onAction={() => onOpen("billing")} />}
          {financeReady && (
            <div className="analytics-position">
              <button type="button" onClick={() => onOpen("billing")}>
                <span>Settled this period</span>
                <strong>{money(collected?.cents ?? null)}</strong>
                <small>Allocated payments received in this period.</small>
              </button>
              <button type="button" onClick={() => onOpen("billing")}>
                <span>Open posted balances</span>
                <strong>{money(outstanding)}</strong>
                <small>Posted invoices that still have a balance. Drafts and voided invoices are excluded.</small>
              </button>
              <button type="button" onClick={() => onOpen("billing")}>
                <span>Collection rate</span>
                <strong>{rate ? `${rate.percent}%` : "—"}</strong>
                <small>{rate ? `${money(rate.paidCents)} paid of ${money(rate.issuedCents)} issued on posted invoices due in this period.` : "No posted invoices are due in this period, so the rate is not shown as zero."}</small>
              </button>
            </div>
          )}
        </article>

        <article className="analytics-panel analytics-span">
          <h3>Maintenance</h3>
          <p className="analytics-note">Request counts by saved status. This is not a count of completed work orders.</p>
          {maintenanceState === "loading" && <p className="analytics-empty">Loading maintenance requests…</p>}
          {!maintenanceReady && maintenanceState !== "loading" && <p className="analytics-empty">{maintenanceNote(maintenanceState, "Maintenance counts are unavailable.", maintenanceError, canMaintenance)}</p>}
          {maintenanceReady && scopedRequests.length === 0 && <p className="analytics-empty">No maintenance requests are saved for this scope.</p>}
          {maintenanceReady && scopedRequests.length > 0 && (
            <>
              <BarList
                rows={maintenanceByStatus(scopedRequests).map((slice, index) => ({
                  key: slice.key,
                  label: slice.label,
                  count: slice.count,
                  color: `var(--hodi-chart-${(index % 4) + 1})`,
                }))}
                onSelect={() => onOpen("maintenance-requests")}
              />
              {maintenanceByPriority(scopedRequests).length > 1 && (
                <ul className="analytics-legend" aria-label="Priority classes">
                  {maintenanceByPriority(scopedRequests).map(slice => <li key={slice.key}>{slice.label}: {slice.count}</li>)}
                </ul>
              )}
            </>
          )}
        </article>

        {showPortfolio && graph.properties.length > 0 && (
          <article className="analytics-panel analytics-span">
            <h3>Portfolio</h3>
            <p className="analytics-note">Lease rent is the monthly amount on active leases, not cash collected. Outstanding is the current posted balance attributed through a lease. A dash means that figure is not available. Property opens the record. Units opens its register.</p>
            <div className="analytics-portfolio-tools">
              <label>
                Find a property
                <input
                  type="search"
                  value={propertyQuery}
                  onChange={event => setPropertyQuery(event.target.value)}
                  placeholder="Name, city, or address"
                />
              </label>
              <label>
                Sort
                <select value={activeSort} onChange={event => setPropertySort(event.target.value as PropertySort)}>
                  <option value="name">Property name</option>
                  <option value="occupancy">Occupancy, lowest first</option>
                  <option value="lease">Active lease rent</option>
                  <option value="outstanding" disabled={!financeReady}>Outstanding balance</option>
                </select>
              </label>
            </div>
            <p className="analytics-note" role="status">{propertyRows.length} of {graph.properties.length} {graph.properties.length === 1 ? "property" : "properties"}</p>
            {propertyRows.length === 0 ? (
              <p className="analytics-empty">No property matches that name or location.</p>
            ) : (
              <>
                <div className="analytics-plot analytics-portfolio-table">
                  <table>
                    <caption className="analytics-sr">Property performance from saved units, leases, posted balances, and open maintenance</caption>
                    <thead>
                      <tr>
                        <th>Property</th>
                        <th className="analytics-num">Active / total</th>
                        <th className="analytics-num">Occupied</th>
                        <th className="analytics-num">Vacant</th>
                        <th className="analytics-num">Rate</th>
                        <th className="analytics-num">Lease rent / month</th>
                        <th className="analytics-num">Outstanding</th>
                        <th className="analytics-num">Attention</th>
                        <th>Records</th>
                      </tr>
                    </thead>
                    <tbody>
                      {propertyRows.map(property => (
                        <tr key={property.id} className={property.id === propertyId ? "is-selected" : undefined} aria-current={property.id === propertyId ? "true" : undefined}>
                          <td>
                            <button type="button" className="analytics-link" onClick={() => openPropertyRecord(property.id)}>{property.name}</button>
                            {locationText(property) && <small className="analytics-location">{locationText(property)}</small>}
                            <span className={`analytics-property-status ${property.isActive === false ? "is-inactive" : property.isActive === true ? "is-active" : "is-unknown"}`}>
                              {property.isActive === false ? "Inactive" : property.isActive === true ? "Active" : "Status unavailable"}
                            </span>
                            <Mix
                              counts={[property.occupied, property.vacant, property.maintenance]}
                              colors={["var(--hodi-chart-1)", "var(--hodi-chart-2)", "var(--hodi-chart-4)"]}
                            />
                          </td>
                          <td className="analytics-num">{property.activeUnits} of {property.totalUnits}</td>
                          <td className="analytics-num">{property.occupied}</td>
                          <td className="analytics-num">{property.vacant}</td>
                          <td className="analytics-num">{property.occupancyRate == null ? "—" : `${property.occupancyRate}%`}</td>
                          <td className="analytics-num analytics-money">{property.activeLeaseRentMinor == null ? "—" : money(property.activeLeaseRentMinor)}</td>
                          <td className="analytics-num analytics-money">{financeReady ? money(property.outstandingCents) : "—"}</td>
                          <td className="analytics-num">{maintenanceReady ? property.attentionCount : "—"}</td>
                          <td className="analytics-record-links">
                            <button type="button" className="analytics-text-button" onClick={() => openPropertyRecord(property.id)}>Property</button>
                            <button type="button" className="analytics-text-button" onClick={() => { onPropertyId(property.id); onOpen("units"); }}>Units</button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <ul className="analytics-property-cards">
                  {propertyRows.map(property => (
                    <li key={property.id} className={property.id === propertyId ? "analytics-property-card is-selected" : "analytics-property-card"}>
                      <div>
                        <button type="button" className="analytics-link" onClick={() => openPropertyRecord(property.id)}>{property.name}</button>
                        {locationText(property) && <small className="analytics-location">{locationText(property)}</small>}
                        <span className={`analytics-property-status ${property.isActive === false ? "is-inactive" : property.isActive === true ? "is-active" : "is-unknown"}`}>
                          {property.isActive === false ? "Inactive" : property.isActive === true ? "Active" : "Status unavailable"}
                        </span>
                      </div>
                      <Mix
                        counts={[property.occupied, property.vacant, property.maintenance]}
                        colors={["var(--hodi-chart-1)", "var(--hodi-chart-2)", "var(--hodi-chart-4)"]}
                      />
                      <dl className="analytics-property-facts">
                        <div><dt>Active units</dt><dd>{property.activeUnits} of {property.totalUnits}</dd></div>
                        <div><dt>Occupancy</dt><dd>{property.occupancyRate == null ? "—" : `${property.occupancyRate}%`}</dd></div>
                        <div><dt>Occupied</dt><dd>{property.occupied}</dd></div>
                        <div><dt>Vacant</dt><dd>{property.vacant}</dd></div>
                        <div><dt>Lease rent / month</dt><dd>{property.activeLeaseRentMinor == null ? "—" : money(property.activeLeaseRentMinor)}</dd></div>
                        <div><dt>Outstanding</dt><dd>{financeReady ? money(property.outstandingCents) : "—"}</dd></div>
                        <div><dt>Attention</dt><dd>{maintenanceReady ? property.attentionCount : "—"}</dd></div>
                        <div><dt>Maintenance units</dt><dd>{property.maintenance}</dd></div>
                      </dl>
                      <div className="analytics-property-actions">
                        <button type="button" className="analytics-text-button" onClick={() => openPropertyRecord(property.id)}>Property</button>
                        <button type="button" className="analytics-text-button" onClick={() => { onPropertyId(property.id); onOpen("units"); }}>Units</button>
                      </div>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </article>
        )}
      </div>

      <div className="analytics-attention">
        <h3>Needs attention</h3>
        {attention.length === 0 ? (
          <p className="analytics-empty">Nothing in the loaded records needs attention.</p>
        ) : (
          <ul>
            {attention.map(item => (
              <li key={item.id}>
                <button type="button" onClick={() => onOpen(item.section, item.status)}>
                  <i className="analytics-attention-mark" aria-hidden="true" />
                  <span>
                    <strong>{item.label}</strong>
                    <small>{item.detail}</small>
                  </span>
                  <span className="analytics-attention-go">{item.action}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {tip && (
        <div className="analytics-tip" style={{ left: tip.x, top: tip.y }} role="tooltip">
          <span>{tip.title}</span>
          <strong>{tip.value}</strong>
          <small>Allocated</small>
        </div>
      )}
    </section>
  );
}

function financeNote(state: SourceState, ready: string, error: string): string {
  if (state === "loading") return "Loading billing records…";
  if (state === "preview") return "Preview mode has no invoices or ledger payments.";
  if (state === "hidden") return "Billing is not available for this role.";
  if (state === "error") return error || "Billing records could not be loaded.";
  return ready;
}

function maintenanceNote(state: SourceState, ready: string, error: string, allowed: boolean): string {
  if (!allowed || state === "hidden") return "Maintenance is not available for this role.";
  if (state === "loading") return "Loading maintenance requests…";
  if (state === "preview") return "Preview mode has no maintenance requests.";
  if (state === "error") return error || "Maintenance requests could not be loaded.";
  return ready;
}

function EmptyPlot({ title, detail, action, onAction }: { title: string; detail: string; action?: string; onAction?: () => void }) {
  return (
    <div className="analytics-empty-plot">
      <p className="analytics-empty-kicker">{title}</p>
      <p>{detail}</p>
      {action && onAction && <button type="button" className="analytics-text-button" onClick={onAction}>{action}</button>}
    </div>
  );
}

function EmptyCollection({ start, end, onOpen }: { start: string; end: string; onOpen: () => void }) {
  return (
    <div className="analytics-plot">
      <div className="analytics-columns">
        <div className="analytics-columns-scale analytics-columns-scale--baseline" aria-hidden="true">
          <span>0</span>
        </div>
        <div className="analytics-columns-scroll">
          <div className="analytics-columns-plot analytics-columns-plot--quiet">
            <div className="analytics-empty-copy">
              <p className="analytics-empty-kicker">No allocated payments</p>
              <p>Nothing settled between these dates. Pending, failed, voided, and reversed payments stay out, and this period is not drawn as a zero line.</p>
              <button type="button" className="analytics-text-button" onClick={onOpen}>Open billing</button>
            </div>
          </div>
        </div>
      </div>
      <div className="analytics-axis-span">
        <span>{formatCivil(start)}</span>
        <span>{formatCivil(end)}</span>
      </div>
      <p className="analytics-axis-note">The axis is the selected Nairobi period. There is no column because no allocated ledger payment falls inside it.</p>
    </div>
  );
}

function locationText(property: { address: string; city: string; country: string }): string {
  return [property.address, property.city, property.country].filter(Boolean).join(", ");
}

function SplitBar({
  segments,
  onSelect,
}: {
  segments: { key: string; label: string; count: number; color: string }[];
  onSelect: (key: string) => void;
}) {
  const total = segments.reduce((sum, segment) => sum + segment.count, 0);
  if (total <= 0) return null;
  return (
    <div className="analytics-split" role="group" aria-label="Active unit mix">
      {segments.map(segment => segment.count > 0 ? (
        <button
          key={segment.key}
          type="button"
          style={{ width: `${(segment.count / total) * 100}%`, background: segment.color }}
          aria-label={`${segment.label}, ${segment.count} of ${total} active units. Open the matching records.`}
          onClick={() => onSelect(segment.key)}
        />
      ) : null)}
    </div>
  );
}

function Mix({ counts, colors }: { counts: number[]; colors: string[] }) {
  const total = counts.reduce((sum, count) => sum + count, 0);
  if (total <= 0) return null;
  return (
    <span className="analytics-stack" aria-hidden="true">
      {counts.map((count, index) => count > 0 ? (
        <span key={colors[index]} style={{ width: `${(count / total) * 100}%`, background: colors[index] }} />
      ) : null)}
    </span>
  );
}

function Kpi({ label, value, note, onClick }: { label: string; value: string; note: string; onClick: () => void }) {
  return (
    <button type="button" className="analytics-kpi" onClick={onClick}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
      <em className="analytics-kpi-go">Open</em>
    </button>
  );
}

function BarList({
  rows,
  onSelect,
}: {
  rows: { key: string; label: string; count: number; color: string; display?: string }[];
  onSelect: (key: string) => void;
}) {
  const max = Math.max(...rows.map(row => row.count), 1);
  return (
    <ul className="analytics-bars">
      {rows.map(row => {
        const width = row.count === 0 ? 0 : (row.count / max) * 100;
        return (
          <li key={row.key}>
            <button type="button" onClick={() => onSelect(row.key)} aria-label={`${row.label}, ${row.display ?? row.count}. Open the matching records.`}>
              <span className="analytics-bar-label"><i style={{ background: row.color }} aria-hidden="true" />{row.label}</span>
              <span className="analytics-bar-track" aria-hidden="true">
                <span style={{ width: `${width}%`, minWidth: row.count > 0 ? "2px" : 0, background: row.color }} />
              </span>
              <strong>{row.display ?? row.count}</strong>
              <em className="analytics-bar-go">Open</em>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function placeTip(x: number, y: number): { x: number; y: number } {
  const width = 220;
  return {
    x: Math.max(8, Math.min(x, window.innerWidth - width)),
    y: Math.max(8, y),
  };
}

function ColumnChart({
  points,
  maxLabel,
  midLabel,
  onHover,
  onSelect,
}: {
  points: { key: string; axis: string; value: number; title: string; valueText: string }[];
  maxLabel: string;
  midLabel: string;
  onHover: (tip: { x: number; y: number; title: string; value: string } | null) => void;
  onSelect: () => void;
}) {
  const max = Math.max(...points.map(point => point.value), 1);
  const showTick = (index: number) => {
    if (points.length <= 16) return true;
    const step = Math.ceil(points.length / 8);
    return index % step === 0 || index === points.length - 1;
  };
  const dayChart = (points[0]?.key.length ?? 0) > 7;
  const firstMonth = points[0]?.key.slice(0, 7) ?? "";
  const lastMonth = points[points.length - 1]?.key.slice(0, 7) ?? "";
  const monthSpan = firstMonth && firstMonth === lastMonth
    ? formatCivil(firstMonth)
    : firstMonth
      ? `${formatCivil(firstMonth)} to ${formatCivil(lastMonth)}`
      : "";
  return (
    <div className="analytics-plot">
      <div className="analytics-columns">
        <div className="analytics-columns-scale" aria-hidden="true">
          <span>{maxLabel}</span>
          <span>{midLabel}</span>
          <span>0</span>
        </div>
        <div className="analytics-columns-scroll">
          <div className="analytics-columns-plot" style={{ minWidth: `${Math.max(points.length * 36, 280)}px` }}>
            {points.map((point, index) => {
              const height = point.value <= 0 ? 0 : (point.value / max) * 100;
              return (
                <button
                  key={point.key}
                  type="button"
                  className="analytics-column"
                  aria-label={`${point.title}, ${point.valueText} allocated. Open billing.`}
                  onClick={onSelect}
                  onMouseEnter={event => onHover({ ...placeTip(event.clientX + 14, event.clientY - 78), title: point.title, value: point.valueText })}
                  onMouseMove={event => onHover({ ...placeTip(event.clientX + 14, event.clientY - 78), title: point.title, value: point.valueText })}
                  onMouseLeave={() => onHover(null)}
                  onFocus={event => {
                    const rect = event.currentTarget.getBoundingClientRect();
                    onHover({ ...placeTip(rect.left, rect.top - 72), title: point.title, value: point.valueText });
                  }}
                  onBlur={() => onHover(null)}
                >
                  <span className="analytics-column-track">
                    <span className="analytics-column-bar" style={{ height: `${height}%`, minHeight: point.value > 0 ? "2px" : 0 }} />
                  </span>
                  <span className="analytics-column-label">{showTick(index) ? point.axis : ""}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>
      <p className="analytics-axis-note">{dayChart && monthSpan ? `${monthSpan}. ` : ""}Scale in Kenyan shillings. A column opens the billing register. The tooltip shows the allocated total for that {dayChart ? "day" : "month"}.</p>
      <table className="analytics-sr">
        <caption>Allocated ledger payments</caption>
        <tbody>
          {points.map(point => <tr key={point.key}><th scope="row">{point.title}</th><td>{point.valueText} allocated</td></tr>)}
        </tbody>
      </table>
    </div>
  );
}
