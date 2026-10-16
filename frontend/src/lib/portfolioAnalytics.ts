/** Honest portfolio figures from records the dashboard has already loaded. */

export type PeriodId = "month" | "30" | "90" | "year";

export type AnalyticsInvoice = {
  organization: string;
  lease: string | null;
  due_date: string;
  status: string;
  total_cents: number;
  paid_cents: number;
  balance_cents: number;
  updated_at?: string | null;
  charges: { id: string }[];
};

export type AnalyticsPayment = {
  organization: string;
  amount_cents: number;
  received_date: string;
  status: string;
  updated_at?: string | null;
  allocations: { charge: string; amount_cents: number }[];
};

export type AnalyticsUnit = { id: string; building: string; status: string };
export type AnalyticsBuilding = { id: string; property: string };
export type AnalyticsLease = {
  id: string;
  unit: string;
  status: string;
  end_date: string | null;
  monthly_rent_minor: number;
};
export type AnalyticsProperty = { id: string; name: string };
export type AnalyticsRequest = {
  id: string;
  organization: string;
  unit: string;
  title: string;
  status: string;
  category: string;
  priority_class: number;
  emergency_override: boolean;
  requires_approval: boolean;
  updated_at?: string | null;
};

export type PortfolioGraph = {
  properties: AnalyticsProperty[];
  buildings: AnalyticsBuilding[];
  units: AnalyticsUnit[];
  leases: AnalyticsLease[];
};

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
export const SETTLED_LEDGER_STATUS = "ALLOCATED";
const OPEN_MAINTENANCE = new Set(["OPEN", "IN_PROGRESS"]);

export function shiftIsoDate(iso: string, days: number): string | null {
  const match = ISO_DATE.exec(iso);
  if (!match || !Number.isInteger(days)) return null;
  const utc = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  if (Number.isNaN(utc.getTime()) || utc.getUTCDate() !== Number(match[3])) return null;
  utc.setUTCDate(utc.getUTCDate() + days);
  const year = utc.getUTCFullYear();
  const month = String(utc.getUTCMonth() + 1).padStart(2, "0");
  const day = String(utc.getUTCDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function periodRange(today: string, period: PeriodId): { start: string; end: string } | null {
  if (!ISO_DATE.test(today)) return null;
  if (period === "month") return { start: `${today.slice(0, 8)}01`, end: today };
  if (period === "year") return { start: `${today.slice(0, 4)}-01-01`, end: today };
  const start = shiftIsoDate(today, period === "30" ? -29 : -89);
  return start ? { start, end: today } : null;
}

export function inDateRange(value: string, start: string, end: string): boolean {
  return ISO_DATE.test(value) && value >= start && value <= end;
}

function safeNonNegative(value: number): number | null {
  return Number.isSafeInteger(value) && value >= 0 ? value : null;
}

export function propertyIdForUnit(unitId: string, graph: PortfolioGraph): string | null {
  const unit = graph.units.find(item => item.id === unitId);
  if (!unit) return null;
  const building = graph.buildings.find(item => item.id === unit.building);
  return building ? building.property : null;
}

export function propertyIdForLease(leaseId: string, graph: PortfolioGraph): string | null {
  const lease = graph.leases.find(item => item.id === leaseId);
  if (!lease) return null;
  return propertyIdForUnit(lease.unit, graph);
}

function propertyIdForCharge(chargeId: string, invoices: AnalyticsInvoice[], graph: PortfolioGraph): string | null {
  const invoice = invoices.find(item => item.charges.some(charge => charge.id === chargeId));
  if (!invoice?.lease) return null;
  return propertyIdForLease(invoice.lease, graph);
}

export function settledInPeriod(payments: AnalyticsPayment[], start: string, end: string): AnalyticsPayment[] {
  return payments.filter(payment =>
    payment.status === SETTLED_LEDGER_STATUS && inDateRange(payment.received_date, start, end),
  );
}

export type CollectionResult = {
  cents: number | null;
  unattributedPayments: number;
};

/** Settled ledger receipts only. Pending, failed, voided, and reversed payments are excluded. */
export function collectedCents(
  payments: AnalyticsPayment[],
  invoices: AnalyticsInvoice[],
  graph: PortfolioGraph,
  start: string,
  end: string,
  propertyId: string,
): CollectionResult {
  const settled = settledInPeriod(payments, start, end);
  if (!propertyId) {
    let total = 0;
    for (const payment of settled) {
      const amount = safeNonNegative(payment.amount_cents);
      if (amount == null || total > Number.MAX_SAFE_INTEGER - amount) return { cents: null, unattributedPayments: 0 };
      total += amount;
    }
    return { cents: total, unattributedPayments: 0 };
  }

  let total = 0;
  let unattributedPayments = 0;
  for (const payment of settled) {
    if (payment.allocations.length === 0) {
      unattributedPayments += 1;
      continue;
    }
    for (const allocation of payment.allocations) {
      if (propertyIdForCharge(allocation.charge, invoices, graph) !== propertyId) continue;
      const amount = safeNonNegative(allocation.amount_cents);
      if (amount == null || total > Number.MAX_SAFE_INTEGER - amount) return { cents: null, unattributedPayments };
      total += amount;
    }
  }
  return { cents: total, unattributedPayments };
}

function invoiceOnProperty(invoice: AnalyticsInvoice, graph: PortfolioGraph, propertyId: string): boolean | null {
  if (!propertyId) return true;
  if (!invoice.lease) return null;
  const property = propertyIdForLease(invoice.lease, graph);
  if (!property) return null;
  return property === propertyId;
}

export function postedOpenInvoices(
  invoices: AnalyticsInvoice[],
  graph: PortfolioGraph,
  propertyId: string,
): { invoices: AnalyticsInvoice[]; unattributed: number } {
  const open = invoices.filter(invoice => invoice.status === "POSTED" && invoice.balance_cents > 0);
  if (!propertyId) return { invoices: open, unattributed: 0 };
  const matched: AnalyticsInvoice[] = [];
  let unattributed = 0;
  for (const invoice of open) {
    const onProperty = invoiceOnProperty(invoice, graph, propertyId);
    if (onProperty === true) matched.push(invoice);
    else if (onProperty === null) unattributed += 1;
  }
  return { invoices: matched, unattributed };
}

export function sumCents(values: number[]): number | null {
  let total = 0;
  for (const value of values) {
    const amount = safeNonNegative(value);
    if (amount == null || total > Number.MAX_SAFE_INTEGER - amount) return null;
    total += amount;
  }
  return total;
}

export type RateResult = { paidCents: number; issuedCents: number; percent: number } | null;

/** Posted invoices due in the period. Drafts and voided invoices are excluded. */
export function collectionRate(
  invoices: AnalyticsInvoice[],
  graph: PortfolioGraph,
  start: string,
  end: string,
  propertyId: string,
): RateResult {
  const due = invoices.filter(invoice =>
    invoice.status === "POSTED" && inDateRange(invoice.due_date, start, end) && invoiceOnProperty(invoice, graph, propertyId) === true,
  );
  const issuedCents = sumCents(due.map(invoice => invoice.total_cents));
  const paidCents = sumCents(due.map(invoice => invoice.paid_cents));
  if (issuedCents == null || paidCents == null || issuedCents <= 0) return null;
  if (paidCents > Number.MAX_SAFE_INTEGER / 10000) return null;
  const percent = Math.round((paidCents * 1000) / issuedCents) / 10;
  return { paidCents, issuedCents, percent };
}

export type OccupancyResult = {
  occupied: number;
  vacant: number;
  maintenance: number;
  inactive: number;
  active: number;
  rate: number | null;
};

export function occupancy(units: AnalyticsUnit[], graph: PortfolioGraph, propertyId: string): OccupancyResult {
  const scoped = propertyId
    ? units.filter(unit => propertyIdForUnit(unit.id, graph) === propertyId)
    : units;
  const occupied = scoped.filter(unit => unit.status === "OCCUPIED").length;
  const vacant = scoped.filter(unit => unit.status === "AVAILABLE").length;
  const maintenance = scoped.filter(unit => unit.status === "MAINTENANCE").length;
  const inactive = scoped.filter(unit => unit.status === "INACTIVE").length;
  const active = occupied + vacant + maintenance;
  const rate = active === 0 ? null : Math.round((occupied * 1000) / active) / 10;
  return { occupied, vacant, maintenance, inactive, active, rate };
}

export type TrendPoint = { key: string; label: string; cents: number };

function monthLabel(key: string): string {
  const [year, month] = key.split("-");
  const date = new Date(Date.UTC(Number(year), Number(month) - 1, 1));
  return new Intl.DateTimeFormat("en-KE", { month: "short", year: "numeric", timeZone: "UTC" }).format(date);
}

function dayLabel(key: string): string {
  const match = ISO_DATE.exec(key);
  if (!match) return key;
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  return new Intl.DateTimeFormat("en-KE", { day: "numeric", month: "short", timeZone: "UTC" }).format(date);
}

export function collectionTrend(
  payments: AnalyticsPayment[],
  invoices: AnalyticsInvoice[],
  graph: PortfolioGraph,
  start: string,
  end: string,
  propertyId: string,
): { points: TrendPoint[]; empty: boolean } {
  const spanStart = shiftIsoDate(end, -45);
  const byDay = spanStart != null && start >= spanStart;
  const keys: string[] = [];
  if (byDay) {
    let cursor = start;
    while (cursor && cursor <= end && keys.length < 120) {
      keys.push(cursor);
      const next = shiftIsoDate(cursor, 1);
      if (!next) break;
      cursor = next;
    }
  } else {
    let cursor = `${start.slice(0, 7)}-01`;
    const last = `${end.slice(0, 7)}-01`;
    while (cursor <= last && keys.length < 36) {
      keys.push(cursor.slice(0, 7));
      const next = shiftIsoDate(cursor, 32);
      if (!next) break;
      cursor = `${next.slice(0, 7)}-01`;
    }
  }

  const totals = new Map(keys.map(key => [key, 0]));
  const add = (key: string, amount: number) => {
    if (!totals.has(key)) return;
    totals.set(key, (totals.get(key) ?? 0) + amount);
  };

  for (const payment of settledInPeriod(payments, start, end)) {
    const key = byDay ? payment.received_date : payment.received_date.slice(0, 7);
    if (!propertyId) {
      const amount = safeNonNegative(payment.amount_cents);
      if (amount != null) add(key, amount);
      continue;
    }
    for (const allocation of payment.allocations) {
      if (propertyIdForCharge(allocation.charge, invoices, graph) !== propertyId) continue;
      const amount = safeNonNegative(allocation.amount_cents);
      if (amount != null) add(key, amount);
    }
  }

  const points = keys.map(key => ({
    key,
    label: byDay ? dayLabel(key) : monthLabel(key),
    cents: totals.get(key) ?? 0,
  }));
  return { points, empty: points.every(point => point.cents === 0) };
}

export type CountSlice = { key: string; label: string; count: number };

export function maintenanceByStatus(requests: AnalyticsRequest[]): CountSlice[] {
  const order = ["OPEN", "IN_PROGRESS", "COMPLETED", "CLOSED", "CANCELLED"];
  const counts = new Map<string, number>();
  for (const request of requests) {
    counts.set(request.status, (counts.get(request.status) ?? 0) + 1);
  }
  const keys = [...order.filter(key => counts.has(key)), ...[...counts.keys()].filter(key => !order.includes(key))];
  return keys.map(key => ({
    key,
    label: key.toLowerCase().replace(/[_-]+/g, " ").replace(/\b\w/g, letter => letter.toUpperCase()),
    count: counts.get(key) ?? 0,
  }));
}

export function maintenanceByPriority(requests: AnalyticsRequest[]): CountSlice[] {
  const buckets = [
    { key: "1", label: "Class 1", test: (request: AnalyticsRequest) => request.priority_class === 1 || request.emergency_override },
    { key: "2", label: "Class 2", test: (request: AnalyticsRequest) => request.priority_class === 2 && !request.emergency_override },
    { key: "later", label: "Class 3 and later", test: (request: AnalyticsRequest) => request.priority_class >= 3 && !request.emergency_override },
  ];
  return buckets
    .map(bucket => ({ key: bucket.key, label: bucket.label, count: requests.filter(bucket.test).length }))
    .filter(bucket => bucket.count > 0);
}

export type PropertyPerformance = {
  id: string;
  name: string;
  occupied: number;
  vacant: number;
  maintenance: number;
  activeLeaseRentMinor: number | null;
};

export function portfolioPerformance(graph: PortfolioGraph): PropertyPerformance[] {
  return graph.properties.map(property => {
    const units = graph.units.filter(unit => propertyIdForUnit(unit.id, graph) === property.id);
    const rentValues = graph.leases
      .filter(lease => lease.status === "ACTIVE" && propertyIdForLease(lease.id, graph) === property.id)
      .map(lease => lease.monthly_rent_minor);
    return {
      id: property.id,
      name: property.name,
      occupied: units.filter(unit => unit.status === "OCCUPIED").length,
      vacant: units.filter(unit => unit.status === "AVAILABLE").length,
      maintenance: units.filter(unit => unit.status === "MAINTENANCE").length,
      activeLeaseRentMinor: sumCents(rentValues),
    };
  });
}

export function needsAttention(request: AnalyticsRequest): boolean {
  return OPEN_MAINTENANCE.has(request.status) && (request.priority_class === 1 || request.emergency_override);
}

export function pendingApproval(request: AnalyticsRequest): boolean {
  return request.requires_approval && OPEN_MAINTENANCE.has(request.status);
}

export function latestTimestamp(values: Array<string | null | undefined>): string | null {
  const stamps = values.filter((value): value is string => Boolean(value));
  if (stamps.length === 0) return null;
  return stamps.reduce((latest, value) => value > latest ? value : latest);
}

export function readPage<T>(payload: T[] | { results?: T[]; next?: string | null } | null | undefined): { rows: T[]; partial: boolean } {
  if (!payload) return { rows: [], partial: false };
  if (Array.isArray(payload)) return { rows: payload, partial: false };
  return { rows: payload.results ?? [], partial: Boolean(payload.next) };
}

export function scopeRequests(
  requests: AnalyticsRequest[],
  organizationId: string,
  graph: PortfolioGraph,
  propertyId: string,
): AnalyticsRequest[] {
  return requests.filter(request => {
    if (request.organization !== organizationId) return false;
    if (!propertyId) return true;
    return propertyIdForUnit(request.unit, graph) === propertyId;
  });
}
