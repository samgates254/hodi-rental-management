"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { Logo } from "@/components/layout/Logo";
import { clientApi } from "@/lib/clientApi";
import MaintenanceAttachments, { type MaintenanceAttachment } from "./MaintenanceAttachments";
import MaintenanceRequestsPanel from "./ops/MaintenanceRequestsPanel";
import NotificationBell from "./ops/NotificationBell";
import "./caretaker-dashboard.css";

type OrganizationMembership = {
  organization_id: number | string;
  organization_name: string;
  role: string;
};

type IssueUpdate = {
  id: number | string;
  note?: string;
  status?: string;
  author_name?: string;
  created_at: string;
};

type MaintenanceIssue = {
  id: number | string;
  organization: number | string;
  tenant_name?: string;
  unit_name?: string;
  property_name?: string;
  operational_request_id?: number | null;
  operational_status?: string | null;
  title: string;
  category?: string;
  priority?: string;
  description?: string;
  status: string;
  created_at: string;
  updated_at?: string;
  updates?: IssueUpdate[];
  attachments?: MaintenanceAttachment[];
};

type RentPayment = {
  id: number | string;
  organization: number | string;
  tenant_name?: string;
  unit_name?: string;
  lease_reference?: string;
  amount_minor: number;
  due_date: string;
  status: string;
  paid_at?: string | null;
  method?: string;
  reference?: string;
};

type ListResponse<T> = T[] | { results?: T[]; data?: T[] };

function listFromResponse<T>(response: ListResponse<T> | null | undefined) {
  if (!response) return [];
  return Array.isArray(response) ? response : response.results ?? response.data ?? [];
}

function formatMoney(minor: number) {
  return new Intl.NumberFormat("en-KE", {
    style: "currency",
    currency: "KES",
    maximumFractionDigits: 0,
  }).format(minor / 100);
}

function formatDate(value: string | null | undefined) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("en-KE", {
        day: "numeric",
        month: "short",
        year: "numeric",
      }).format(date);
}

function humanize(value: string | null | undefined) {
  if (!value) {
    return "-";
  }
  return value.toLowerCase().replace(/[_-]+/g, " ").replace(/\b\w/g, char => char.toUpperCase());
}

function requestError(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function exportPayments(payments: RentPayment[]) {
  const headers = ["Resident", "Unit", "Lease", "Amount (KES)", "Due date", "Status", "Paid on", "Reference"];
  const rows = payments.map(payment => [
    payment.tenant_name ?? "Resident",
    payment.unit_name ?? "",
    payment.lease_reference ?? "Rent",
    (payment.amount_minor / 100).toFixed(2),
    payment.due_date,
    payment.status,
    payment.paid_at ?? "",
    payment.reference ?? "",
  ]);
  const csv = [headers, ...rows]
    .map(row => row.map(value => {
      const safeValue = /^[=+\-@\t\r]/.test(value) ? `'${value}` : value;
      return `"${safeValue.replaceAll('"', '""')}"`;
    }).join(","))
    .join("\r\n");
  const url = URL.createObjectURL(new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `rent-payments-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function CaretakerDashboard() {
  const [memberships, setMemberships] = useState<OrganizationMembership[]>([]);
  const [organizationId, setOrganizationId] = useState("");
  const [issues, setIssues] = useState<MaintenanceIssue[]>([]);
  const [payments, setPayments] = useState<RentPayment[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [pageError, setPageError] = useState("");
  const [issueFilter, setIssueFilter] = useState("ALL");
  const [paymentFilter, setPaymentFilter] = useState("ALL");
  const [issueSearch, setIssueSearch] = useState("");
  const [paymentSearch, setPaymentSearch] = useState("");
  const [updatingIssueId, setUpdatingIssueId] = useState<string | null>(null);

  useEffect(() => {
    const token = sessionStorage.getItem("hodi_api_token");
    if (!token) {
      window.location.replace("/signin?type=caretaker");
      return;
    }
    let parsedMemberships: OrganizationMembership[] = [];
    try {
      const stored = JSON.parse(sessionStorage.getItem("hodi_memberships") ?? "[]") as unknown;
      if (Array.isArray(stored)) {
        parsedMemberships = stored.filter(
          (item): item is OrganizationMembership =>
            Boolean(item) &&
            typeof item === "object" &&
            (item as OrganizationMembership).role === "CARETAKER" &&
            (item as OrganizationMembership).organization_id !== undefined,
        );
      }
    } catch {
      setPageError("Your saved organization access is invalid. Please sign in again.");
    }
    if (parsedMemberships.length === 0) {
      window.location.replace("/signin?type=caretaker");
      return;
    }
    setMemberships(parsedMemberships);
    setOrganizationId(String(parsedMemberships[0].organization_id));
  }, []);

  const loadDashboard = useCallback(async () => {
    if (!organizationId) return;
    setIsLoading(true);
    setPageError("");
    try {
      const query = { organization: organizationId };
      // Load independently so one failing endpoint cannot blank the whole page.
      const [issueResult, paymentResult] = await Promise.allSettled([
        clientApi.get<ListResponse<MaintenanceIssue>>("/api/v1/maintenance/issues/", { params: query }),
        clientApi.get<ListResponse<RentPayment>>("/api/v1/billing/payments/", { params: query }),
      ]);

      const errors: string[] = [];

      if (issueResult.status === "fulfilled") {
        setIssues(listFromResponse(issueResult.value.data));
      } else {
        setIssues([]);
        errors.push(requestError(issueResult.reason, "Unable to load maintenance issues."));
      }

      if (paymentResult.status === "fulfilled") {
        setPayments(listFromResponse(paymentResult.value.data));
      } else {
        setPayments([]);
        errors.push(requestError(paymentResult.reason, "Unable to load rent payments."));
      }

      if (errors.length > 0) {
        setPageError(errors.join(" "));
      }
    } catch (error) {
      setPageError(requestError(error, "The caretaker workspace could not be loaded."));
    } finally {
      setIsLoading(false);
    }
  }, [organizationId]);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  async function updateIssue(
    issue: MaintenanceIssue,
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const note = String(form.get("note") ?? "").trim();
    const status = String(form.get("status") ?? issue.status);
    if (!note && status === issue.status) return;
    setUpdatingIssueId(String(issue.id));
    setPageError("");
    try {
      await clientApi.post(`/api/v1/maintenance/issues/${issue.id}/updates/`, { status, note });
      await loadDashboard();
    } catch (error) {
      setPageError(requestError(error, "The issue couldn’t be updated."));
    } finally {
      setUpdatingIssueId(null);
    }
  }

  async function signOut() {
    setPageError("");
    try {
      await clientApi.post("/api/v1/accounts/logout/");
    } catch (error) {
      setPageError(requestError(error, "The sign-out request failed."));
    } finally {
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
      window.location.assign("/signin?type=caretaker");
    }
  }

  const activeIssues = useMemo(
    () => issues.filter(issue => issue.status !== "RESOLVED"),
    [issues],
  );
  const overduePayments = payments.filter(payment => payment.status === "OVERDUE");
  const pendingPayments = payments.filter(payment => payment.status === "PENDING");
  const overdueTotal = overduePayments.reduce((total, payment) => total + payment.amount_minor, 0);
  const pendingTotal = pendingPayments.reduce((total, payment) => total + payment.amount_minor, 0);
  const issueQuery = issueSearch.trim().toLocaleLowerCase();
  const visibleIssues = issues.filter(issue => {
    const matchesStatus = issueFilter === "ALL" || issue.status === issueFilter;
    const searchableText = [
      issue.title,
      issue.tenant_name,
      issue.unit_name,
      issue.property_name,
      issue.category,
      issue.description,
    ].filter(Boolean).join(" ").toLocaleLowerCase();
    return matchesStatus && (!issueQuery || searchableText.includes(issueQuery));
  });
  const paymentQuery = paymentSearch.trim().toLocaleLowerCase();
  const visiblePayments = payments.filter(payment => {
    const matchesStatus = paymentFilter === "ALL" || payment.status === paymentFilter;
    const searchableText = [
      payment.tenant_name,
      payment.unit_name,
      payment.lease_reference,
      payment.reference,
      payment.status,
    ].filter(Boolean).join(" ").toLocaleLowerCase();
    return matchesStatus && (!paymentQuery || searchableText.includes(paymentQuery));
  });
  const organizationName = memberships.find(
    membership => String(membership.organization_id) === organizationId,
  )?.organization_name ?? "Caretaker workspace";

  if (!organizationId && !pageError) {
    return (
      <main className="caretaker-loading">
        <span className="caretaker-spinner" aria-hidden="true" />
        <p>Opening your caretaker workspace…</p>
      </main>
    );
  }

  return (
    <div className="caretaker-app">
      <aside className="caretaker-sidebar">
        <Logo size={36} className="caretaker-sidebar-logo" wordmarkClassName="text-white" />
        <p className="caretaker-sidebar-label">CARETAKER WORKSPACE</p>
        <nav aria-label="Caretaker dashboard">
          <a href="#overview">Overview</a>
          <a href="#issues">Maintenance issues</a>
          <a href="#maintenance-requests">Work orders</a>
          <a href="#payments">Rent status</a>
          <Link href="/marketplace">Browse marketplace</Link>
        </nav>
        <div className="caretaker-sidebar-bottom">
          <span>{organizationName}</span>
          <button type="button" onClick={() => void signOut()}>Sign out</button>
        </div>
      </aside>

      <main className="caretaker-main">
        <header className="caretaker-header">
          <div>
            <span className="caretaker-eyebrow">CARETAKER PORTAL</span>
            <h1>{organizationName}</h1>
          </div>
          {memberships.length > 1 && (
            <label className="caretaker-organization-select">
              <span className="sr-only">Organization</span>
              <select value={organizationId} onChange={event => setOrganizationId(event.target.value)}>
                {memberships.map(membership => (
                  <option key={membership.organization_id} value={membership.organization_id}>
                    {membership.organization_name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <button type="button" className="caretaker-refresh" onClick={() => void loadDashboard()} disabled={isLoading}>
            {isLoading ? "Refreshing…" : "Refresh"}
          </button>
          <NotificationBell />
        </header>

        {pageError && <div className="caretaker-alert" role="alert">{pageError}</div>}

        <section className="caretaker-intro" id="overview">
          <div>
            <span className="caretaker-eyebrow">TODAY AT A GLANCE</span>
            <h2>Property operations</h2>
            <p>Handle maintenance requests and keep an eye on residents’ rent status.</p>
          </div>
        </section>

        <section className="caretaker-summary" aria-label="Workspace summary">
          <article><span>Open issues</span><strong>{activeIssues.length}</strong><small>Need follow-up</small></article>
          <article><span>In progress</span><strong>{issues.filter(issue => issue.status === "IN_PROGRESS").length}</strong><small>Being handled</small></article>
          <article className="is-warning"><span>Rent overdue</span><strong>{overduePayments.length}</strong><small>{formatMoney(overdueTotal)} outstanding</small></article>
          <article><span>Awaiting payment</span><strong>{pendingPayments.length}</strong><small>{formatMoney(pendingTotal)} pending</small></article>
        </section>

        <section className="caretaker-panel" id="issues">
          <div className="caretaker-panel-heading">
            <div>
              <span className="caretaker-eyebrow">MAINTENANCE</span>
              <h2>Reported issues</h2>
              <p>Review requests, update progress, and leave a note for the team.</p>
            </div>
            <div className="caretaker-panel-tools">
              <label>
                <span className="sr-only">Search issues</span>
                <input
                  className="caretaker-search"
                  type="search"
                  value={issueSearch}
                  onChange={event => setIssueSearch(event.target.value)}
                  placeholder="Search issues or residents"
                />
              </label>
              <label>
                <span className="sr-only">Filter issues</span>
                <select value={issueFilter} onChange={event => setIssueFilter(event.target.value)}>
                  <option value="ALL">All issues</option>
                  <option value="OPEN">Open</option>
                  <option value="IN_PROGRESS">In progress</option>
                  <option value="RESOLVED">Resolved</option>
                </select>
              </label>
            </div>
          </div>
          {isLoading ? (
            <div className="caretaker-empty"><span className="caretaker-spinner" />Loading issues…</div>
          ) : visibleIssues.length ? (
            <div className="caretaker-issue-list">
              {visibleIssues.map(issue => (
                <article className="caretaker-issue" key={issue.id}>
                  <div className="caretaker-issue-top">
                    <div>
                      <h3>{issue.title}</h3>
                      <p>{issue.tenant_name ?? "Resident"} · {[issue.property_name, issue.unit_name].filter(Boolean).join(" · ") || "Property not listed"}</p>
                    </div>
                    <span className={`caretaker-status status-${(issue.operational_status ?? issue.status).toLowerCase()}`}>
                      {humanize(issue.operational_status ?? issue.status)}
                    </span>
                  </div>
                  <div className="caretaker-issue-meta">
                    <span>{humanize(issue.category ?? "General")}</span>
                    <span>{humanize(issue.priority ?? "Normal")} priority</span>
                    <span>Reported {formatDate(issue.created_at)}</span>
                  </div>
                  {issue.description && <p className="caretaker-issue-description">{issue.description}</p>}
                  <MaintenanceAttachments attachments={issue.attachments} />
                  {issue.updates?.length ? (
                    <ol className="caretaker-updates">
                      {issue.updates.map(update => (
                        <li key={update.id}>
                          <span><strong>{update.author_name ?? "Team update"}</strong> · {formatDate(update.created_at)}</span>
                          {update.status && <b>{humanize(update.status)}</b>}
                          {update.note && <p>{update.note}</p>}
                        </li>
                      ))}
                    </ol>
                  ) : null}
                  {issue.operational_request_id ? (
                    <p className="caretaker-issue-description">This repair uses the unified work order. Triage, assignment and verification are managed in the repair queue below.</p>
                  ) : issue.status !== "RESOLVED" && (
                    <form className="caretaker-update-form" onSubmit={event => void updateIssue(issue, event)}>
                      <label>
                        Update status
                        <select name="status" defaultValue={issue.status}>
                          <option value="OPEN">Open</option>
                          <option value="IN_PROGRESS">In progress</option>
                          <option value="RESOLVED">Resolved</option>
                        </select>
                      </label>
                      <label className="caretaker-note-field">
                        Add a note
                        <input name="note" maxLength={2000} placeholder="Add an update for this issue…" />
                      </label>
                      <button type="submit" disabled={updatingIssueId === String(issue.id)}>
                        {updatingIssueId === String(issue.id) ? "Saving…" : "Save update"}
                      </button>
                    </form>
                  )}
                </article>
              ))}
            </div>
          ) : (
            <div className="caretaker-empty">
              {issues.length ? "No issues match your search and filter." : "No maintenance issues have been reported."}
            </div>
          )}
        </section>

        <section className="caretaker-panel" id="payments">
          <div className="caretaker-panel-heading">
            <div>
              <span className="caretaker-eyebrow">RENT TRACKING</span>
              <h2>Residents’ rent status</h2>
              <p>Payment status is read-only here. Contact your property manager about corrections.</p>
            </div>
            <div className="caretaker-panel-tools">
              <label>
                <span className="sr-only">Search rent payments</span>
                <input
                  className="caretaker-search"
                  type="search"
                  value={paymentSearch}
                  onChange={event => setPaymentSearch(event.target.value)}
                  placeholder="Search residents, units, references"
                />
              </label>
              <label>
                <span className="sr-only">Filter rent payments</span>
                <select value={paymentFilter} onChange={event => setPaymentFilter(event.target.value)}>
                  <option value="ALL">All payments</option>
                  <option value="PENDING">Pending</option>
                  <option value="PAID">Paid</option>
                  <option value="OVERDUE">Overdue</option>
                </select>
              </label>
              <button
                type="button"
                className="caretaker-export"
                onClick={() => exportPayments(visiblePayments)}
                disabled={!visiblePayments.length}
              >
                Export CSV
              </button>
            </div>
          </div>
          {isLoading ? (
            <div className="caretaker-empty"><span className="caretaker-spinner" />Loading rent status…</div>
          ) : visiblePayments.length ? (
            <div className="caretaker-table-wrap">
              <table>
                <thead><tr><th>Resident</th><th>Unit</th><th>Period / lease</th><th>Amount</th><th>Due date</th><th>Status</th><th>Paid on</th></tr></thead>
                <tbody>
                  {visiblePayments.map(payment => (
                    <tr key={payment.id}>
                      <td><strong>{payment.tenant_name ?? "Resident"}</strong></td>
                      <td>{payment.unit_name ?? "—"}</td>
                      <td>{payment.lease_reference ?? "Rent"}</td>
                      <td>{formatMoney(payment.amount_minor)}</td>
                      <td>{formatDate(payment.due_date)}</td>
                      <td><span className={`caretaker-status status-${payment.status.toLowerCase()}`}>{humanize(payment.status)}</span></td>
                      <td>{formatDate(payment.paid_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="caretaker-empty">
              {payments.length ? "No payment records match your search and filter." : "There are no rent-payment records for this organization yet."}
            </div>
          )}
        </section>
        <MaintenanceRequestsPanel organizationId={organizationId} canWrite />
      </main>
    </div>
  );
}
