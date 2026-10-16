import assert from "node:assert/strict";
import test from "node:test";
import {
  collectedCents,
  collectionRate,
  collectionTrend,
  needsAttention,
  occupancy,
  pendingApproval,
  periodRange,
  postedOpenInvoices,
  type AnalyticsInvoice,
  type AnalyticsPayment,
  type PortfolioGraph,
} from "./portfolioAnalytics.ts";

const graph: PortfolioGraph = {
  properties: [
    { id: "p1", name: "Acacia" },
    { id: "p2", name: "Riverside" },
  ],
  buildings: [
    { id: "b1", property: "p1" },
    { id: "b2", property: "p2" },
  ],
  units: [
    { id: "u1", building: "b1", status: "OCCUPIED" },
    { id: "u2", building: "b1", status: "AVAILABLE" },
    { id: "u3", building: "b2", status: "MAINTENANCE" },
    { id: "u4", building: "b2", status: "INACTIVE" },
  ],
  leases: [
    { id: "l1", unit: "u1", status: "ACTIVE", end_date: "2026-12-01", monthly_rent_minor: 10000 },
  ],
};

const invoices: AnalyticsInvoice[] = [
  {
    organization: "1",
    lease: "l1",
    due_date: "2026-10-05",
    status: "POSTED",
    total_cents: 10000,
    paid_cents: 4000,
    balance_cents: 6000,
    charges: [{ id: "c1" }],
  },
  {
    organization: "1",
    lease: "l1",
    due_date: "2026-09-05",
    status: "DRAFT",
    total_cents: 9000,
    paid_cents: 0,
    balance_cents: 9000,
    charges: [{ id: "c-draft" }],
  },
  {
    organization: "1",
    lease: null,
    due_date: "2026-10-01",
    status: "POSTED",
    total_cents: 5000,
    paid_cents: 0,
    balance_cents: 5000,
    charges: [{ id: "c-none" }],
  },
];

const payments: AnalyticsPayment[] = [
  {
    organization: "1",
    amount_cents: 4000,
    received_date: "2026-10-06",
    status: "ALLOCATED",
    allocations: [{ charge: "c1", amount_cents: 4000 }],
  },
  {
    organization: "1",
    amount_cents: 2500,
    received_date: "2026-10-08",
    status: "PENDING",
    allocations: [],
  },
  {
    organization: "1",
    amount_cents: 800,
    received_date: "2026-10-02",
    status: "REVERSED",
    allocations: [],
  },
];

test("period range stays on the Nairobi calendar date it is given", () => {
  assert.deepEqual(periodRange("2026-10-16", "month"), { start: "2026-10-01", end: "2026-10-16" });
  assert.deepEqual(periodRange("2026-10-16", "30"), { start: "2026-09-17", end: "2026-10-16" });
});

test("collected rent counts only allocated ledger payments in the period", () => {
  const result = collectedCents(payments, invoices, graph, "2026-10-01", "2026-10-16", "");
  assert.equal(result.cents, 4000);
  const property = collectedCents(payments, invoices, graph, "2026-10-01", "2026-10-16", "p1");
  assert.equal(property.cents, 4000);
  const other = collectedCents(payments, invoices, graph, "2026-10-01", "2026-10-16", "p2");
  assert.equal(other.cents, 0);
});

test("a settled payment without allocations is not assigned to a property", () => {
  const loose: AnalyticsPayment[] = [{
    organization: "1",
    amount_cents: 1500,
    received_date: "2026-10-04",
    status: "ALLOCATED",
    allocations: [],
  }];
  const result = collectedCents(loose, invoices, graph, "2026-10-01", "2026-10-16", "p1");
  assert.equal(result.cents, 0);
  assert.equal(result.unattributedPayments, 1);
});

test("outstanding balances ignore drafts and collection rate uses posted invoices due in range", () => {
  const open = postedOpenInvoices(invoices, graph, "");
  assert.deepEqual(open.invoices.map(invoice => invoice.balance_cents), [6000, 5000]);
  const rate = collectionRate(invoices, graph, "2026-10-01", "2026-10-31", "p1");
  assert.equal(rate?.issuedCents, 10000);
  assert.equal(rate?.paidCents, 4000);
  assert.equal(rate?.percent, 40);
  assert.equal(collectionRate(invoices, graph, "2026-08-01", "2026-08-31", ""), null);
});

test("occupancy uses unit status and leaves inactive units out of the rate", () => {
  const all = occupancy(graph.units, graph, "");
  assert.equal(all.occupied, 1);
  assert.equal(all.vacant, 1);
  assert.equal(all.maintenance, 1);
  assert.equal(all.inactive, 1);
  assert.equal(all.rate, 33.3);
  assert.equal(occupancy(graph.units, graph, "p1").vacant, 1);
});

test("collection trend is empty when the period has no settled payments", () => {
  const trend = collectionTrend(payments, invoices, graph, "2026-01-01", "2026-01-31", "");
  assert.equal(trend.empty, true);
  const october = collectionTrend(payments, invoices, graph, "2026-10-01", "2026-10-16", "");
  assert.equal(october.empty, false);
  assert.equal(october.points.find(point => point.key === "2026-10-06")?.cents, 4000);
  assert.equal(october.points.find(point => point.key === "2026-10-08")?.cents, 0);
});

test("maintenance attention follows saved status and priority", () => {
  const open = {
    id: "r1",
    organization: "1",
    unit: "u1",
    title: "Leak",
    status: "OPEN",
    category: "PLUMBING",
    priority_class: 1,
    emergency_override: false,
    requires_approval: true,
  };
  const closed = { ...open, id: "r2", status: "CLOSED", requires_approval: true, priority_class: 1 };
  assert.equal(needsAttention(open), true);
  assert.equal(needsAttention({ ...open, priority_class: 3, emergency_override: false }), false);
  assert.equal(pendingApproval(open), true);
  assert.equal(pendingApproval(closed), false);
});
