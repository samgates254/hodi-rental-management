"use client";

import {
  type ChangeEvent,
  type FormEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import Link from "next/link";
import Image from "next/image";
import { Button } from "../components/ui/Button";
import Card from "../components/ui/Card";
import { Container } from "../components/ui/Container";
import SectionHead from "../components/ui/SectionHead";
import { ClientApiError, clientApi, fetchMe } from "../lib/clientApi";
import ReportIssueModal from "./ReportIssueModal";
import MaintenanceAttachments, { type MaintenanceAttachment } from "./MaintenanceAttachments";
import NotificationBell from "./ops/NotificationBell";
import TenantLinkGate from "./ops/TenantLinkGate";
import TenantProfileEditor from "./ops/TenantProfileEditor";
import TenantWorkStatus from "./ops/TenantWorkStatus";
import StatementPanel from "./tenant/StatementPanel";
import ThemeToggle from "@/components/theme/ThemeToggle";
import { formatMinor, payableHalfShillings, payableWholeShillings, wholeShillingsToCents } from "@/lib/money";
import "./client-portal.css";

const MARKETPLACE_AVAILABLE = true;
const ACTIVE_TENANCY_API = "/api/v1/leases/";
const ISSUES_API = "/api/v1/maintenance/issues/";
const CREATE_ISSUE_API = "/api/v1/maintenance/issues/";
const INVOICES_API = "/api/v1/billing/invoices/";
const PAYMENTS_API = "/api/v1/billing/ledger-payments/";
const PAYMENT_FLOW_AVAILABLE = true;
const MPESA_ATTEMPT_STORAGE_KEY = "hodi_mpesa_attempt_id";
const MPESA_IDEMPOTENCY_STORAGE_KEY = "hodi_mpesa_idempotency_key";

type Property = {
  id: number | string;
  title?: string;
  name?: string;
  image?: string | null;
  image_url?: string | null;
  photos?: Array<string | { image?: string; url?: string }>;
  location?: string | { name?: string; city?: string; area?: string };
  estate?: string | { name?: string };
  rent?: number | string;
  rent_amount?: number | string;
  rent_cents?: number;
  bedrooms?: number | string;
  room_type?: string;
  house_type?: string;
  amenities?: string[];
  agent?: {
    name?: string;
    full_name?: string;
    phone?: string;
    phone_number?: string;
    email?: string;
    is_verified?: boolean;
    verified?: boolean;
  };
  agent_name?: string;
  agent_phone?: string;
  agent_email?: string;
  agent_verified?: boolean;
  is_available?: boolean;
  available_now?: boolean;
  whatsapp?: string;
};

type Tenancy = {
  id?: number | string;
  flat_number?: string;
  unit_number?: string;
  property?: Property;
  estate?: string | { name?: string };
  landlord?: { name?: string; full_name?: string; email?: string; phone?: string };
  landlord_name?: string;
  lease_start?: string;
  lease_end?: string;
  start_date?: string;
  end_date?: string;
  monthly_rent?: number | string;
  monthly_rent_cents?: number;
  deposit?: number | string;
  deposit_cents?: number;
  deposit_balance?: number | string;
  agreement_url?: string;
  lease_url?: string;
  phone?: string;
  landlord_phone?: string;
  user?: { name?: string; full_name?: string; email?: string; phone?: string };
  rent_status?: string;
  rent_paid?: boolean;
  status?: string;
  assigned_agent?: { name?: string; full_name?: string; phone?: string; email?: string };
  fundi?: { name?: string; full_name?: string; phone?: string };
  timeline?: Array<{
    status?: string;
    timestamp?: string;
    comment?: string;
    actor_name?: string;
    actor_phone?: string;
    photos?: string[];
  }>;
  rating?: number;
};

type MaintenanceIssue = {
  id: number | string;
  title?: string;
  description?: string;
  category?: string;
  priority?: string;
  status?: string;
  operational_status?: string | null;
  repair_outcome?: string | null;
  repair_resolution?: string;
  follow_up_at?: string | null;
  follow_up_reason?: string;
  image?: string | null;
  images?: Array<string | { image?: string; url?: string }>;
  attachments?: MaintenanceAttachment[];
  created_at?: string;
  date_reported?: string;
  updated_at?: string;
  last_update?: string;
  agent_comment?: string;
  comment?: string;
  assigned_agent?: { name?: string; full_name?: string };
  fundi?: { name?: string; full_name?: string; phone?: string };
  timeline?: Array<{
    status?: string;
    timestamp?: string;
    comment?: string;
    actor_name?: string;
    actor_phone?: string;
    photos?: string[];
  }>;
  rating?: number;
};

type ApiList<T> = T[] | { results?: T[]; data?: T[] };
type IssueFilter = "all" | "open" | "in-progress" | "resolved";
type SharedMaintenanceIssue = {
  id: number | string;
  title: string;
  description: string;
  category: string;
  priority: string;
  status: string;
  operational_status?: string | null;
  repair_outcome?: string | null;
  repair_resolution?: string;
  follow_up_at?: string | null;
  follow_up_reason?: string;
  created_at: string;
  updated_at: string;
  attachments?: MaintenanceAttachment[];
  updates?: Array<{
    id: number | string;
    note?: string;
    status?: string;
    author_name?: string;
    created_at: string;
  }>;
};
type SharedRentPayment = {
  id: number | string;
  reference?: string;
  external_id?: string;
  amount_cents: number;
  received_date: string;
  execution_timestamp?: string | null;
  status: string;
  method?: string;
  created_at: string;
  reversal?: { status: string; reason: string; amount_cents: number } | null;
};
type LedgerInvoice = {
  id: number | string;
  period_start?: string;
  period_end?: string;
  due_date?: string;
  status?: string;
  notes?: string;
  total_cents?: number;
  paid_cents?: number;
  balance_cents?: number;
};
type Invoice = {
  id: number | string;
  month?: string;
  description?: string;
  amount?: number | string;
  balance?: number | string;
  status?: string;
  due_date?: string;
  paid_amount?: number | string;
  amount_cents?: number;
  balance_cents?: number;
  paid_cents?: number;
};
type Payment = {
  id: number | string;
  reference?: string;
  transaction_id?: string;
  date?: string;
  created_at?: string;
  amount?: number | string;
  amount_cents?: number;
  description?: string;
  invoice?: Invoice | number | string;
  method?: string;
  status?: string;
  receipt_url?: string;
  due_date?: string;
  reversal?: { status: string; reason: string; amount_cents: number } | null;
};

function fromSharedIssue(issue: SharedMaintenanceIssue): MaintenanceIssue {
  return {
    id: issue.id,
    title: issue.title,
    description: issue.description,
    category: issue.category,
    priority: issue.priority,
    status: issue.status,
    operational_status: issue.operational_status,
    repair_outcome: issue.repair_outcome,
    repair_resolution: issue.repair_resolution,
    follow_up_at: issue.follow_up_at,
    follow_up_reason: issue.follow_up_reason,
    created_at: issue.created_at,
    updated_at: issue.updated_at,
    attachments: issue.attachments,
    timeline: issue.updates?.map(update => ({
      status: update.status ?? issue.status,
      timestamp: update.created_at,
      comment: update.note,
      actor_name: update.author_name,
    })),
  };
}

function fromSharedPayment(payment: SharedRentPayment): Payment {
  return {
    id: payment.id,
    reference: payment.reference || payment.external_id,
    transaction_id: payment.external_id,
    date: payment.execution_timestamp ?? payment.received_date,
    created_at: payment.created_at,
    amount_cents: payment.amount_cents,
    description: "Rent payment",
    method: payment.method,
    status: payment.status === "ALLOCATED" ? "SUCCESSFUL" : payment.status,
    reversal: payment.reversal,
  };
}

type LeaseRecord = {
  id: number | string;
  reference?: string;
  start_date?: string;
  end_date?: string | null;
  monthly_rent_minor?: number;
  security_deposit_minor?: number;
  status?: string;
  unit_name?: string;
  property_name?: string;
  property_city?: string;
  organization_name?: string;
};

function fromLease(lease: LeaseRecord): Tenancy {
  return {
    id: lease.id,
    flat_number: lease.unit_name,
    unit_number: lease.unit_name,
    start_date: lease.start_date,
    end_date: lease.end_date ?? undefined,
    monthly_rent_cents: lease.monthly_rent_minor,
    deposit_cents: lease.security_deposit_minor,
    status: lease.status,
    property: {
      id: lease.id,
      name: lease.property_name,
      title: lease.reference ? `${lease.property_name ?? "Home"} · ${lease.reference}` : lease.property_name,
      location: lease.property_city,
    },
    estate: lease.property_name,
    landlord_name: lease.organization_name,
  };
}

function fromLedgerInvoice(invoice: LedgerInvoice): Invoice {
  const total = Math.trunc(Number(invoice.total_cents ?? 0));
  const paid = Math.trunc(Number(invoice.paid_cents ?? 0));
  const balance = Math.trunc(Number(invoice.balance_cents ?? 0));
  const period = [invoice.period_start, invoice.period_end].filter(Boolean).join(" – ");
  return {
    id: invoice.id,
    month: invoice.period_start,
    description: invoice.notes?.trim() || (period ? `Rent ${period}` : "Rent invoice"),
    amount_cents: Number.isSafeInteger(total) ? total : 0,
    balance_cents: Number.isSafeInteger(balance) ? balance : 0,
    paid_cents: Number.isSafeInteger(paid) ? paid : 0,
    status: invoice.status,
    due_date: invoice.due_date,
  };
}
type PaymentRequest = {
  id: number | string;
  status?: string;
  message?: string;
  reference?: string;
  amount?: number | string;
  amount_cents?: number;
  receipt?: string | null;
  credit_amount?: number | string;
  payment_settled?: boolean;
  accepted?: boolean;
  reconciliation_state?: string;
};
type ApiPage<T> = ApiList<T> & {
  count?: number;
  next?: string | null;
  previous?: string | null;
};

const ISSUE_STEPS = [
  { key: "submitted", label: "Submitted" },
  { key: "viewed", label: "Viewed by agent" },
  { key: "assigned", label: "Assigned to fundi" },
  { key: "in-progress", label: "In progress" },
  { key: "resolved", label: "Resolved" },
  { key: "confirmed", label: "Tenant confirmation" },
] as const;

function listFromResponse<T>(data: ApiList<T> | null | undefined): T[] {
  if (Array.isArray(data)) return data;
  return data?.results ?? data?.data ?? [];
}

function displayLocation(property: Property) {
  if (typeof property.location === "string") return property.location;
  if (property.location) {
    return (
      property.location.area ??
      property.location.city ??
      property.location.name ??
      "Location not listed"
    );
  }
  if (typeof property.estate === "string") return property.estate;
  return property.estate?.name ?? "Location not listed";
}

function propertyImage(property: Property) {
  const firstPhoto = property.photos?.[0];
  if (typeof firstPhoto === "string") return firstPhoto;
  return (
    property.image_url ??
    property.image ??
    firstPhoto?.image ??
    firstPhoto?.url ??
    ""
  );
}

function propertyImages(property: Property) {
  const photos = (property.photos ?? [])
    .map(photo => typeof photo === "string" ? photo : photo.image ?? photo.url ?? "")
    .filter(Boolean);
  const firstImage = property.image_url ?? property.image ?? "";
  return [...new Set([firstImage, ...photos].filter(Boolean))];
}

function agentName(property: Property) {
  return (
    property.agent?.full_name ??
    property.agent?.name ??
    property.agent_name ??
    "Hodi agent"
  );
}

function agentVerified(property: Property) {
  return property.agent?.is_verified === true ||
    property.agent?.verified === true ||
    property.agent_verified === true;
}

function money(value: number | string | undefined) {
  const numeric = Number(value);
  return Number.isFinite(numeric)
    ? new Intl.NumberFormat("en-KE").format(numeric)
    : "Ask agent";
}

function centsOf(value: number | null | undefined): number {
  const numeric = Math.trunc(Number(value ?? 0));
  return Number.isSafeInteger(numeric) ? numeric : 0;
}

function invoiceBalanceCents(invoice: Invoice): number {
  if (invoice.balance_cents != null) return centsOf(invoice.balance_cents);
  return Math.max(0, centsOf(invoice.amount_cents) - centsOf(invoice.paid_cents));
}

function formatDateTime(date?: string) {
  if (!date) return "Not available";
  const parsed = new Date(date);
  return Number.isNaN(parsed.getTime())
    ? date
    : new Intl.DateTimeFormat("en-KE", {
        day: "numeric",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(parsed);
}

function humanizeStatus(status?: string) {
  return (status || "submitted")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, letter => letter.toUpperCase());
}

function normalizedStatus(status?: string) {
  return (status ?? "").toLowerCase().replace(/[\s_-]+/g, "");
}

function isPaymentSuccessful(status?: string) {
  return ["success", "successful", "paid", "completed"].includes(normalizedStatus(status));
}

function isPaymentFailed(status?: string) {
  return ["failed", "cancelled", "canceled", "rejected", "expired"].includes(normalizedStatus(status));
}

function issueStep(status?: string) {
  const normalized = (status || "submitted").toLowerCase().replace(/[\s-]+/g, "_");
  if (["client_confirmed", "confirmed_by_client", "rated"].includes(normalized)) return 5;
  if (["resolved", "complete", "completed", "closed"].includes(normalized)) return 4;
  if (["in_progress", "inprogress", "being_repaired"].includes(normalized)) return 3;
  if (["assigned", "assigned_to_fundi", "fundi_assigned"].includes(normalized)) return 2;
  if (["viewed", "viewed_by_agent", "acknowledged", "accepted"].includes(normalized)) return 1;
  return 0;
}

function formatDate(date?: string) {
  if (!date) return "Not available";
  const parsed = new Date(date);
  return Number.isNaN(parsed.getTime())
    ? date
    : new Intl.DateTimeFormat("en-KE", {
        day: "numeric",
        month: "short",
        year: "numeric",
      }).format(parsed);
}

function statusMatchesFilter(issue: MaintenanceIssue, filter: IssueFilter) {
  const step = issueStep(issue.status);
  if (filter === "resolved") return step >= 4;
  if (filter === "in-progress") return step >= 2 && step <= 3;
  if (filter === "open") return step < 2;
  return true;
}

function getTenancyProperty(tenancy: Tenancy) {
  return tenancy.property ?? null;
}

function isTenancy(value: unknown): value is Tenancy {
  return Boolean(
    value &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    ("id" in value || "property" in value || "flat_number" in value),
  );
}

function daysUntil(date?: string) {
  if (!date) return null;
  const time = new Date(date).getTime();
  if (!Number.isFinite(time)) return null;
  return Math.ceil((time - new Date().setHours(0, 0, 0, 0)) / 86_400_000);
}

function scrollToSection(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function downloadFromUrl(url?: string, filename = "hodi-document.pdf") {
  if (!url) return false;
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.target = "_blank";
  link.rel = "noreferrer";
  document.body.append(link);
  link.click();
  link.remove();
  return true;
}

function SummaryCard({
  label,
  value,
  caption,
  icon,
  tone = "slate",
}: {
  label: string;
  value: string;
  caption: string;
  icon: Parameters<typeof Icon>[0]["name"];
  tone?: "slate" | "green" | "amber" | "red" | "blue";
}) {
  return (
    <Card className={`portal-kpi portal-kpi--${tone}`}>
      <div className="portal-kpi-top">
        <span>{label}</span>
        <span className="portal-kpi-icon"><Icon name={icon} size={19} /></span>
      </div>
      <strong>{value}</strong>
      <small>{caption}</small>
    </Card>
  );
}

function Icon({
  name,
  size = 20,
}: {
  name:
    | "pin" | "bed" | "arrow" | "close" | "upload" | "camera" | "check" | "home" | "sparkle"
    | "grid" | "wallet" | "wrench" | "search" | "bell" | "receipt" | "user" | "logout"
    | "chevron" | "menu" | "download" | "calendar" | "message" | "external" | "shield"
    | "clock" | "building" | "filter" | "phone" | "star" | "credit";
  size?: number;
}) {
  const shared = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true as const,
  };
  const shapes: Record<typeof name, ReactNode> = {
    pin: <><path d="M20 10c0 5-8 12-8 12S4 15 4 10a8 8 0 1 1 16 0Z" /><circle cx="12" cy="10" r="2.5" /></>,
    bed: <><path d="M3 18v-8a2 2 0 0 1 2-2h4a3 3 0 0 1 3 3v7" /><path d="M12 13h6a3 3 0 0 1 3 3v2M3 14h18M5 18v2m14-2v2" /></>,
    arrow: <><path d="M5 12h14M13 6l6 6-6 6" /></>,
    close: <><path d="m18 6-12 12M6 6l12 12" /></>,
    upload: <><path d="M12 16V4m-4 4 4-4 4 4" /><path d="M4 16v4h16v-4" /></>,
    camera: <><path d="M4 7h3l2-3h6l2 3h3a2 2 0 0 1 2 2v10H2V9a2 2 0 0 1 2-2Z" /><circle cx="12" cy="12" r="3" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    home: <><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7h-6v7H4a1 1 0 0 1-1-1Z" /></>,
    sparkle: <><path d="m12 3 1.7 5.3L19 10l-5.3 1.7L12 17l-1.7-5.3L5 10l5.3-1.7L12 3Z" /><path d="m19 16 .8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8L19 16Z" /></>,
    grid: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
    wallet: <><rect x="3" y="5" width="18" height="15" rx="2" /><path d="M3 9h18M16 14h2" /><path d="M6 5V4a2 2 0 0 1 2-2h10" /></>,
    wrench: <><path d="M14.7 6.3a5 5 0 0 0-6.6 6.6L3 18l3 3 5.1-5.1a5 5 0 0 0 6.6-6.6L14 12l-3-3Z" /></>,
    search: <><circle cx="10.8" cy="10.8" r="6.8" /><path d="m16 16 4.5 4.5" /></>,
    bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></>,
    receipt: <><path d="M5 3h14v18l-3-2-4 2-4-2-3 2Z" /><path d="M8 8h8M8 12h8M8 16h4" /></>,
    user: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
    logout: <><path d="M10 17l5-5-5-5M15 12H3" /><path d="M12 3h6a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-6" /></>,
    chevron: <path d="m9 18 6-6-6-6" />,
    menu: <><path d="M4 6h16M4 12h16M4 18h16" /></>,
    download: <><path d="M12 3v12m-5-5 5 5 5-5" /><path d="M4 17v4h16v-4" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18" /></>,
    message: <><path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8A8.5 8.5 0 0 1 8.7 4a8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8z" /></>,
    external: <><path d="M14 3h7v7M10 14 21 3" /><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /></>,
    shield: <><path d="M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11Z" /><path d="m9 12 2 2 4-4" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    building: <><rect x="4" y="3" width="16" height="18" rx="1" /><path d="M9 21v-4h6v4M8 7h1m6 0h1M8 11h1m6 0h1" /></>,
    filter: <><path d="M4 6h16M7 12h10m-7 6h4" /></>,
    phone: <><path d="M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" /><path d="M11 17h2" /></>,
    star: <path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9Z" />,
    credit: <><rect x="2" y="5" width="20" height="14" rx="2" /><path d="M2 10h20m-15 5h4" /></>,
  };
  return <svg {...shared}>{shapes[name]}</svg>;
}

function LoadingCards() {
  return (
    <div className="dashboard-property-grid" aria-label="Loading rooms">
      {Array.from({ length: 3 }, (_, index) => (
        <div className="dashboard-skeleton-card" key={index}>
          <div className="dashboard-skeleton dashboard-skeleton-image" />
          <div className="dashboard-skeleton dashboard-skeleton-line" />
          <div className="dashboard-skeleton dashboard-skeleton-line short" />
          <div className="dashboard-skeleton dashboard-skeleton-line" />
        </div>
      ))}
    </div>
  );
}

function EmptyIssues() {
  return (
    <div className="dashboard-empty-state">
      <div className="dashboard-empty-illustration" aria-hidden="true">
        <Icon name="sparkle" size={34} />
      </div>
      <h3>No issues reported yet</h3>
      <p>
        Everything looking good? If something needs attention in your home, you
        can report it here and follow progress in one place.
      </p>
    </div>
  );
}

function PropertyCard({
  property,
  onOpen,
  onContact,
  onBookViewing,
  imageIndex,
  onImageChange,
}: {
  property: Property;
  onOpen: (property: Property) => void;
  onContact: (property: Property) => void;
  onBookViewing: (property: Property) => void;
  imageIndex: number;
  onImageChange: (index: number) => void;
}) {
  const [failedImage, setFailedImage] = useState("");
  const images = propertyImages(property);
  const image = images[imageIndex % Math.max(images.length, 1)] ?? propertyImage(property);
  const location = displayLocation(property);
  const title = property.title ?? property.name ?? `${property.room_type ?? property.house_type ?? "Room"} in ${location}`;
  const rentLabel = property.rent_cents != null
    ? formatMinor(property.rent_cents, "KES", { trailingZeros: false })
    : property.rent != null || property.rent_amount != null
      ? `KES ${money(property.rent ?? property.rent_amount)}`
      : "Ask agent";

  return (
    <article
      className="dashboard-property-card"
      onClick={() => onOpen(property)}
    >
      <div className="dashboard-property-image-wrap">
        {image && failedImage !== image ? (
          <Image
            className="dashboard-property-image"
            src={image}
            alt={`Property photo for ${title}`}
            fill
            sizes="(max-width: 760px) 100vw, (max-width: 1100px) 50vw, 33vw"
            unoptimized
            onError={() => setFailedImage(image)}
          />
        ) : (
          <div className="dashboard-property-image dashboard-property-placeholder">
            <Icon name="home" size={34} />
          </div>
        )}
        {images.length > 1 && (
          <div className="portal-carousel">
            <button
              type="button"
              aria-label="Previous property photo"
              onClick={event => {
                event.stopPropagation();
                onImageChange((imageIndex + images.length - 1) % images.length);
              }}
            >‹</button>
            <span>{imageIndex + 1} / {images.length}</span>
            <button
              type="button"
              aria-label="Next property photo"
              onClick={event => {
                event.stopPropagation();
                onImageChange((imageIndex + 1) % images.length);
              }}
            >›</button>
          </div>
        )}
        <span className="dashboard-available-pill">
          <span /> Available now
        </span>
      </div>
      <div className="dashboard-property-body">
        <div className="dashboard-property-title-row">
          <h3>{title}</h3>
          <span className="dashboard-bedroom-count">
            <Icon name="bed" size={16} />
            {property.bedrooms ?? property.room_type ?? "—"}
          </span>
        </div>
        <p className="dashboard-location">
          <Icon name="pin" size={16} />
          {location}
        </p>
        <p className="dashboard-rent">
          <strong>{rentLabel}</strong>
          <span>/ month</span>
        </p>
        <div className="dashboard-agent-row">
          <div className="dashboard-agent-avatar" aria-hidden="true">
            {agentName(property).slice(0, 1).toUpperCase()}
          </div>
          <div className="dashboard-agent-details">
            <span>Listed by</span>
            <strong>{agentName(property)}</strong>
          </div>
          {agentVerified(property) && (
            <span className="dashboard-verified" title="Verified agent" aria-label="Verified agent">
              <Icon name="check" size={13} />
            </span>
          )}
        </div>
        <Button
          type="button"
          variant="secondary"
          className="dashboard-contact-button"
          onClick={event => {
            event.stopPropagation();
            onContact(property);
          }}
        >
          <span>WhatsApp agent</span>
          <Icon name="message" size={17} />
        </Button>
        <div className="portal-property-actions">
          <Button
            type="button"
            variant="ghost"
            onClick={event => {
              event.stopPropagation();
              onOpen(property);
            }}
          >
            View details
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={event => {
              event.stopPropagation();
              onBookViewing(property);
            }}
          >
            Book viewing
          <Icon name="arrow" size={17} />
          </Button>
        </div>
      </div>
    </article>
  );
}

function IssueTimeline({ issue }: { issue: MaintenanceIssue }) {
  const activeStep = issueStep(issue.status);
  return (
    <div className="dashboard-timeline" aria-label={`Issue status: ${humanizeStatus(issue.status)}`}>
      <div className="dashboard-timeline-track">
        <span style={{ width: `${(activeStep / (ISSUE_STEPS.length - 1)) * 100}%` }} />
      </div>
      <ol className="dashboard-timeline-steps">
        {ISSUE_STEPS.map((step, index) => (
          <li
            key={step.key}
            className={[
              index < activeStep ? "is-complete" : "",
              index === activeStep ? "is-current" : "",
            ].filter(Boolean).join(" ")}
          >
            <span className="dashboard-step-dot">
              {index < activeStep ? <Icon name="check" size={12} /> : index + 1}
            </span>
            <span>{step.label}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function IssueCard({
  issue,
  onComment,
  onResolve,
}: {
  issue: MaintenanceIssue;
  onComment: (issueId: number | string, comment: string) => Promise<void>;
  onResolve: (issueId: number | string) => Promise<void>;
}) {
  const [comment, setComment] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [actionError, setActionError] = useState("");
  const step = issueStep(issue.status);
  const thumbnail =
    issue.image ??
    (typeof issue.images?.[0] === "string"
      ? issue.images[0]
      : issue.images?.[0]?.image ?? issue.images?.[0]?.url);

  async function submitComment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!comment.trim()) return;
    setIsSaving(true);
    try {
      await onComment(issue.id, comment.trim());
      setComment("");
    } catch {
      // The parent displays the API error and the comment stays available for retry.
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <article className="dashboard-issue-card">
      <div className="dashboard-issue-heading">
        {thumbnail ? (
          <img className="dashboard-issue-thumbnail" src={thumbnail} alt="" loading="lazy" />
        ) : (
          <div className="dashboard-issue-thumbnail dashboard-issue-thumbnail-empty">
            <Icon name="home" size={21} />
          </div>
        )}
        <div className="dashboard-issue-title">
          <div className="dashboard-issue-title-line">
            <h3>{issue.title ?? "Maintenance request"}</h3>
            <span className={`dashboard-status-badge status-${(issue.status ?? "submitted").toLowerCase().replace(/[^a-z]+/g, "-")}`}>
              {issue.operational_status === "COMPLETED" ? "Awaiting verification" : issue.operational_status === "CANCELLED" ? "Cancelled" : issue.operational_status === "CLOSED" ? "Verified and closed" : humanizeStatus(issue.status)}
            </span>
          </div>
          <p>{issue.category ?? "Other"} · {humanizeStatus(issue.priority ?? "medium")} priority</p>
        </div>
      </div>

      {issue.description && <p className="dashboard-issue-description">{issue.description}</p>}
      {issue.repair_outcome && (
        <div className="dashboard-agent-comment">
          <strong>Repair outcome · {humanizeStatus(issue.repair_outcome)}</strong>
          <p>{issue.repair_resolution}</p>
        </div>
      )}
      {issue.follow_up_at && (
        <div className="dashboard-agent-comment">
          <strong>Follow-up scheduled</strong>
          <p>{new Date(issue.follow_up_at).toLocaleString("en-KE", { dateStyle: "medium", timeStyle: "short" })}</p>
          {issue.follow_up_reason && <p>{issue.follow_up_reason}</p>}
        </div>
      )}
      {(issue.assigned_agent || issue.fundi) && (
        <div className="portal-issue-assignees">
          {issue.assigned_agent && <span><Icon name="user" size={15} /><strong>Agent:</strong> {issue.assigned_agent.full_name ?? issue.assigned_agent.name ?? "Assigned"}</span>}
          {issue.fundi && <span><Icon name="wrench" size={15} /><strong>Fundi:</strong> {issue.fundi.full_name ?? issue.fundi.name ?? "Assigned"}{issue.fundi.phone && <a href={`tel:${issue.fundi.phone}`} aria-label="Call assigned fundi"><Icon name="phone" size={13} /></a>}</span>}
        </div>
      )}
      {issue.images && issue.images.length > 1 && (
        <div className="portal-issue-gallery">
          {issue.images.map((image, index) => {
            const url = typeof image === "string" ? image : image.image ?? image.url;
            return url ? <img key={`${url}-${index}`} src={url} alt={`${issue.title ?? "Issue"} photo ${index + 1}`} loading="lazy" /> : null;
          })}
        </div>
      )}
      <MaintenanceAttachments attachments={issue.attachments} />
      <IssueTimeline issue={issue} />

      <div className="dashboard-issue-meta">
        <span>Reported {formatDate(issue.date_reported ?? issue.created_at)}</span>
        <span>Updated {formatDate(issue.last_update ?? issue.updated_at)}</span>
      </div>
      {(issue.agent_comment ?? issue.comment) && (
        <div className="dashboard-agent-comment">
          <strong>Agent update</strong>
          <p>{issue.agent_comment ?? issue.comment}</p>
        </div>
      )}

      {issue.timeline && issue.timeline.length > 0 && (
        <ol className="portal-issue-events">
          {issue.timeline.map((event, index) => (
            <li key={`${event.timestamp ?? event.status}-${index}`}>
              <span className="portal-event-dot" />
              <div>
                <strong>{humanizeStatus(event.status)}</strong>
                <small>{formatDateTime(event.timestamp)}{event.actor_name ? ` · ${event.actor_name}` : ""}{event.actor_phone ? ` · ${event.actor_phone}` : ""}</small>
                {event.comment && <p>{event.comment}</p>}
                {event.photos && event.photos.length > 0 && (
                  <span className="portal-event-photos">
                    {event.photos.map((photo, photoIndex) => (
                      <img key={`${photo}-${photoIndex}`} src={photo} alt={`Update photo ${photoIndex + 1}`} loading="lazy" />
                    ))}
                  </span>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}

      {actionError && <p className="dashboard-form-error" role="alert">{actionError}</p>}
      <div className="dashboard-issue-actions">
        <form className="dashboard-comment-form" onSubmit={submitComment}>
          <label className="sr-only" htmlFor={`comment-${issue.id}`}>Add a comment</label>
          <input
            id={`comment-${issue.id}`}
            value={comment}
            onChange={event => setComment(event.target.value)}
            placeholder="Add a comment for your agent"
            maxLength={1000}
          />
          <Button type="submit" variant="ghost" disabled={!comment.trim() || isSaving}>
            {isSaving ? "Sending…" : "Comment"}
          </Button>
        </form>
        {step < 4 && (
          <Button
            type="button"
            variant="secondary"
            className="dashboard-resolve-button"
            onClick={async () => {
              setActionError("");
              try {
                await onResolve(issue.id);
              } catch {
                setActionError("This issue could not be marked as resolved.");
              }
            }}
          >
            Ask caretaker to close
          </Button>
        )}
      </div>
    </article>
  );
}

export default function ClientDashboard() {
  const [clientName, setClientName] = useState("Tenant");
  const [clientEmail, setClientEmail] = useState("");
  const [properties, setProperties] = useState<Property[]>([]);
  const [tenancy, setTenancy] = useState<Tenancy | null>(null);
  const [issues, setIssues] = useState<MaintenanceIssue[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [propertyCount, setPropertyCount] = useState(0);
  const [propertyHasNext, setPropertyHasNext] = useState(false);
  const [propertyHasPrevious, setPropertyHasPrevious] = useState(false);
  const [propertiesServerPaginated, setPropertiesServerPaginated] = useState(false);
  const [isLoadingProperties, setIsLoadingProperties] = useState(true);
  const [isLoadingTenancy, setIsLoadingTenancy] = useState(true);
  const [isLoadingIssues, setIsLoadingIssues] = useState(true);
  const [isLoadingInvoices, setIsLoadingInvoices] = useState(true);
  const [isLoadingPayments, setIsLoadingPayments] = useState(true);
  const [isCheckingSession, setIsCheckingSession] = useState(true);
  const [needsOrganizationLink, setNeedsOrganizationLink] = useState(false);
  const [propertyError, setPropertyError] = useState("");
  const [propertyLoadError, setPropertyLoadError] = useState("");
  const [tenancyError, setTenancyError] = useState("");
  const [issueError, setIssueError] = useState("");
  const [billingError, setBillingError] = useState("");
  const [pageNotice, setPageNotice] = useState("");
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [location, setLocation] = useState("all");
  const [maxPrice, setMaxPrice] = useState(100000);
  const [bedrooms, setBedrooms] = useState("all");
  const [amenities, setAmenities] = useState<string[]>([]);
  const [propertySearch, setPropertySearch] = useState("");
  const [propertyPage, setPropertyPage] = useState(1);
  const [activeImage, setActiveImage] = useState<Record<string, number>>({});
  const [availableNow, setAvailableNow] = useState(false);
  const [issueFilter, setIssueFilter] = useState<IssueFilter>("all");
  const [isReportOpen, setIsReportOpen] = useState(false);
  const [issueActionError, setIssueActionError] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [activeSection, setActiveSection] = useState("overview");
  const [headerSearch, setHeaderSearch] = useState("");
  const [mobileSearchOpen, setMobileSearchOpen] = useState(false);
  const [selectedInvoiceId, setSelectedInvoiceId] = useState("");
  const [paymentAmount, setPaymentAmount] = useState("");
  const paymentMethod = "mpesa" as const;
  const [phoneNumber, setPhoneNumber] = useState("");
  const [paymentRequest, setPaymentRequest] = useState<PaymentRequest | null>(null);
  const [paymentStage, setPaymentStage] = useState<"idle" | "pending" | "reconciling" | "success" | "failed">("idle");
  const [paymentError, setPaymentError] = useState("");
  const [isInitiatingPayment, setIsInitiatingPayment] = useState(false);
  const [receiptError, setReceiptError] = useState("");
  const propertyRequestId = useRef(0);
  const paymentStartedAt = useRef<number | null>(null);
  const headerSearchInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const token = window.sessionStorage.getItem("hodi_api_token");
    const accountType = window.sessionStorage.getItem("hodi_account_type");
    if (!token || accountType !== "TENANT") {
      window.location.replace("/signin?type=tenant");
      return;
    }
    const firstName = window.sessionStorage.getItem("hodi_first_name") ?? "";
    const lastName = window.sessionStorage.getItem("hodi_last_name") ?? "";
    setClientName([firstName, lastName].filter(Boolean).join(" ") || "Tenant");
    setClientEmail(window.sessionStorage.getItem("hodi_email") ?? "");
    setPhoneNumber(window.sessionStorage.getItem("hodi_phone_number") ?? "");
    void fetchMe()
      .then(me => {
        if (!me.organization_id) setNeedsOrganizationLink(true);
        const name = [me.first_name, me.last_name].filter(Boolean).join(" ");
        if (name) setClientName(name);
        if (me.email) setClientEmail(me.email);
        if (me.phone_number) setPhoneNumber(me.phone_number);
      })
      .catch(() => {
        window.location.replace("/signin?type=tenant");
      })
      .finally(() => setIsCheckingSession(false));
  }, []);

  useEffect(() => {
    const savedAttemptId = window.sessionStorage.getItem(MPESA_ATTEMPT_STORAGE_KEY);
    if (!savedAttemptId || !/^[0-9a-f-]{36}$/i.test(savedAttemptId)) return;
    setPaymentRequest({ id: savedAttemptId, status: "UNRESOLVED" });
    setPaymentStage("reconciling");
    setPaymentError("This payment has no final status yet. You can check its status again without starting another payment.");
    paymentStartedAt.current = Date.now() - 240_000;
  }, []);

  const loadProperties = useCallback(async () => {
    if (!MARKETPLACE_AVAILABLE) {
      setIsLoadingProperties(false);
      setProperties([]);
      setPropertyCount(0);
      setPropertyHasNext(false);
      setPropertyHasPrevious(false);
      setPropertiesServerPaginated(false);
      setPropertyLoadError("");
      return;
    }
    const requestId = ++propertyRequestId.current;
    setIsLoadingProperties(true);
    setPropertyLoadError("");
    try {
      const response = await clientApi.get<ApiPage<Property & { monthly_rent_minor?: number; area?: string; city?: string; property_name?: string; unit_label?: string; available?: boolean }>>("/api/v1/marketplace/listings/", {
        params: {
          location: location === "all" ? propertySearch.trim() : location,
          max_rent: maxPrice * 100,
          bedrooms: bedrooms === "all" ? "" : bedrooms === "bedsitter" ? 0 : bedrooms.replace("br", ""),
          amenity: amenities,
          page: propertyPage,
        },
      });
      if (requestId !== propertyRequestId.current) return;
      const responseProperties = listFromResponse(response.data).map(item => ({
        ...item,
        rent_cents: item.monthly_rent_minor,
        location: [item.area, item.city].filter(Boolean).join(", "),
        name: item.title,
        image_url: item.photos?.[0] && typeof item.photos[0] === "object" ? item.photos[0].url : undefined,
        is_available: item.available,
      }));
      const hasPaginationMetadata = !Array.isArray(response.data) &&
        ("count" in response.data || "next" in response.data || "previous" in response.data);
      setPropertiesServerPaginated(hasPaginationMetadata);
      setProperties(responseProperties);
      setPropertyCount(
        !Array.isArray(response.data) && typeof response.data.count === "number"
          ? response.data.count
          : listFromResponse(response.data).length,
      );
      setPropertyHasNext(hasPaginationMetadata
        ? Boolean(!Array.isArray(response.data) && response.data.next)
        : propertyPage * 12 < responseProperties.length);
      setPropertyHasPrevious(hasPaginationMetadata
        ? Boolean(!Array.isArray(response.data) && response.data.previous)
        : propertyPage > 1);
    } catch {
      if (requestId !== propertyRequestId.current) return;
      setPropertyLoadError("Available rooms couldn’t be loaded. Please try again.");
    } finally {
      if (requestId === propertyRequestId.current) setIsLoadingProperties(false);
    }
  }, [amenities, availableNow, bedrooms, location, maxPrice, propertyPage, propertySearch]);

  const loadTenancy = useCallback(async () => {
    setIsLoadingTenancy(true);
    setTenancyError("");
    try {
      const response = await clientApi.get<ApiList<LeaseRecord>>(ACTIVE_TENANCY_API);
      const leases = listFromResponse(response.data);
      const current = leases.find(lease => lease.status === "ACTIVE") ?? leases[0] ?? null;
      setTenancy(current ? fromLease(current) : null);
    } catch (error) {
      if (error instanceof ClientApiError && error.status === 404) {
        setTenancy(null);
      } else {
        setTenancyError(error instanceof ClientApiError
          ? error.message
          : "Your tenancy details couldn’t be loaded.");
      }
    } finally {
      setIsLoadingTenancy(false);
    }
  }, []);

  const loadIssues = useCallback(async () => {
    setIsLoadingIssues(true);
    setIssueError("");
    try {
      const response = await clientApi.get<ApiList<SharedMaintenanceIssue>>(ISSUES_API);
      setIssues(listFromResponse(response.data).map(fromSharedIssue));
    } catch (error) {
      setIssueError(error instanceof ClientApiError
        ? error.message
        : "Your reported issues couldn’t be loaded. Please try again.");
    } finally {
      setIsLoadingIssues(false);
    }
  }, []);

  const loadInvoices = useCallback(async () => {
    setIsLoadingInvoices(true);
    setBillingError("");
    try {
      const response = await clientApi.get<ApiList<LedgerInvoice>>(INVOICES_API);
      setInvoices(listFromResponse(response.data).map(fromLedgerInvoice));
    } catch (error) {
      setBillingError(error instanceof ClientApiError
        ? error.message
        : "Your rent invoices couldn’t be loaded. Please try again.");
    } finally {
      setIsLoadingInvoices(false);
    }
  }, []);

  const loadPayments = useCallback(async () => {
    setIsLoadingPayments(true);
    try {
      const [paymentResult] = await Promise.allSettled([clientApi.get<ApiList<SharedRentPayment>>(PAYMENTS_API)]);
      if (paymentResult.status === "fulfilled") {
        setPayments(listFromResponse(paymentResult.value.data).map(fromSharedPayment));
      }
      setReceiptError(paymentResult.status === "rejected"
        ? "Your payment history couldn’t be loaded."
        : "");
    } catch {
      setReceiptError("Your payment history couldn’t be loaded.");
    } finally {
      setIsLoadingPayments(false);
    }
  }, []);

  useEffect(() => {
    if (isCheckingSession || needsOrganizationLink) return;
    void loadProperties();
    void loadTenancy();
    void loadIssues();
    void loadInvoices();
    void loadPayments();
  }, [isCheckingSession, loadIssues, loadInvoices, loadPayments, loadProperties, loadTenancy, needsOrganizationLink]);

  const locations = useMemo(
    () => [...new Set(properties.map(displayLocation).filter(item => item !== "Location not listed"))].sort(),
    [properties],
  );

  const filteredProperties = useMemo(
    () =>
      properties.filter(property => {
        const rentCents = property.rent_cents;
        const propertyLocation = displayLocation(property);
        const matchesLocation = location === "all" || propertyLocation.toLowerCase().includes(location.toLowerCase());
        const matchesRent = rentCents == null || rentCents <= maxPrice * 100;
        const matchesBedrooms =
          bedrooms === "all" ||
          (bedrooms === "bedsitter"
            ? /bedsitter|studio/i.test(`${property.room_type ?? ""} ${property.house_type ?? ""} ${property.title ?? property.name ?? ""}`)
            : Number(property.bedrooms ?? property.house_type?.replace(/\D/g, "")) === Number(bedrooms.replace("br", "")));
        const matchesAvailability =
          !availableNow || property.available_now !== false && property.is_available !== false;
        const matchesAmenities = amenities.every(amenity =>
          (property.amenities ?? []).some(value => value.toLowerCase() === amenity.toLowerCase()),
        );
        const search = propertySearch.trim().toLowerCase();
        const matchesSearch = !search || [
          property.title,
          property.name,
          propertyLocation,
          property.room_type,
        ].some(value => value?.toLowerCase().includes(search));
        return matchesLocation && matchesRent && matchesBedrooms && matchesAvailability && matchesAmenities && matchesSearch;
      }),
    [amenities, availableNow, bedrooms, location, maxPrice, properties, propertySearch],
  );
  const visibleProperties = propertiesServerPaginated
    ? filteredProperties
    : filteredProperties.slice((propertyPage - 1) * 12, propertyPage * 12);

  const filteredIssues = useMemo(
    () => issues.filter(issue => statusMatchesFilter(issue, issueFilter)),
    [issueFilter, issues],
  );

  async function submitIssue(formData: FormData) {
    const issueData = new FormData();
    issueData.set("title", String(formData.get("title") ?? "").trim());
    issueData.set("category", String(formData.get("category") ?? "general").toUpperCase());
    issueData.set("priority", String(formData.get("priority") ?? "normal").toUpperCase());
    issueData.set("description", String(formData.get("description") ?? "").trim());
    formData.getAll("attachments").forEach(file => issueData.append("attachments", file));
    await clientApi.post(CREATE_ISSUE_API, issueData);
    setIsReportOpen(false);
    await loadIssues();
    setPageNotice("Your maintenance request has been submitted.");
  }

  async function addIssueComment(issueId: number | string, comment: string) {
    setIssueActionError("");
    try {
      await clientApi.post(`/api/v1/maintenance/issues/${issueId}/updates/`, { note: comment });
      await loadIssues();
    } catch {
      setIssueActionError("Your comment couldn’t be saved. Please try again.");
      throw new Error("Comment save failed");
    }
  }

  async function markResolved(issueId: number | string) {
    setIssueActionError("");
    try {
      await clientApi.post(`/api/v1/maintenance/issues/${issueId}/updates/`, {
        note: "The resident reports that this issue is resolved and requests caretaker confirmation.",
      });
      await loadIssues();
      setPageNotice("Your closure request was shared with the caretaker.");
    } catch {
      setIssueActionError("Your closure request couldn’t be sent. Please try again.");
    }
  }

  function openProperty(property: Property) {
    window.location.assign(`/marketplace/${property.id}`);
  }

  function contactAgent(property: Property) {
    window.location.assign(`/marketplace/${property.id}`);
  }

  function bookViewing(property: Property) {
    window.location.assign(`/marketplace/${property.id}`);
  }

  function setRentAmount(value: number) {
    setPaymentAmount(String(Math.max(0, value)));
  }

  function selectInvoice(invoice: Invoice) {
    setSelectedInvoiceId(String(invoice.id));
    const whole = payableWholeShillings(invoiceBalanceCents(invoice));
    setPaymentAmount(whole == null ? "" : String(whole));
    scrollToSection("pay-rent");
  }

  const tenancyProperty = tenancy ? getTenancyProperty(tenancy) : null;
  const propertyTitle = tenancyProperty
    ? tenancyProperty.title ?? tenancyProperty.name ?? tenancyProperty.room_type ?? "Your Hodi home"
    : "No current flat";
  const flatNumber = tenancy?.flat_number ?? tenancy?.unit_number ?? "Not listed";
  const estate =
    typeof tenancy?.estate === "string"
      ? tenancy.estate
      : tenancy?.estate?.name ?? (tenancyProperty ? displayLocation(tenancyProperty) : "Not listed");
  const landlord =
    tenancy?.landlord?.full_name ?? tenancy?.landlord?.name ?? tenancy?.landlord_name ?? "Not listed";
  const rentStatus =
    tenancy?.rent_status ?? (tenancy?.rent_paid ? "Paid" : "Check with landlord");
  const outstandingInvoices = invoices.filter(invoice => {
    const status = normalizedStatus(invoice.status);
    return !["paid", "successful", "completed"].includes(status) && invoiceBalanceCents(invoice) > 0;
  });
  const outstandingCents = outstandingInvoices.reduce(
    (total, invoice) => total + invoiceBalanceCents(invoice),
    0,
  );
  const selectedInvoice = invoices.find(invoice => String(invoice.id) === selectedInvoiceId) ??
    outstandingInvoices[0] ?? null;
  const selectedBalanceCents = selectedInvoice ? invoiceBalanceCents(selectedInvoice) : 0;
  const payableFull = payableWholeShillings(selectedBalanceCents);
  const payableHalf = payableHalfShillings(selectedBalanceCents);
  const sharedUnpaidPayments = payments.filter(payment =>
    ["pending", "overdue"].includes(normalizedStatus(payment.status)),
  );
  const sharedOverduePayments = payments.filter(
    payment => normalizedStatus(payment.status) === "overdue",
  );
  const sharedUnpaidCents = sharedUnpaidPayments.reduce(
    (total, payment) => total + centsOf(payment.amount_cents),
    0,
  );
  const allRentInvoicesPaid = invoices.length > 0 &&
    invoices.every(invoice => isPaymentSuccessful(invoice.status));
  const hasSharedRentStatus = payments.length > 0;
  const rentOverviewStatus = outstandingCents > 0 ||
    invoices.some(invoice => normalizedStatus(invoice.status) === "overdue") ||
    sharedOverduePayments.length > 0
    ? "Payment due"
    : hasSharedRentStatus && sharedUnpaidPayments.length > 0
      ? "Payment pending"
    : isLoadingInvoices
      ? "Loading…"
      : allRentInvoicesPaid || hasSharedRentStatus && sharedUnpaidPayments.length === 0 || /paid|clear/i.test(rentStatus)
        ? "Paid"
        : invoices.length || hasSharedRentStatus ? "Check status" : "No invoice";
  const nextInvoice = [...outstandingInvoices]
    .filter(invoice => invoice.due_date)
    .sort((first, second) => new Date(first.due_date!).getTime() - new Date(second.due_date!).getTime())[0];
  const nextSharedPayment = sharedUnpaidPayments
    .filter(payment => payment.due_date)
    .sort((first, second) => new Date(first.due_date!).getTime() - new Date(second.due_date!).getTime())[0];
  const dueDate = [nextInvoice?.due_date, nextSharedPayment?.due_date]
    .filter((value): value is string => Boolean(value))
    .sort((first, second) => new Date(first).getTime() - new Date(second).getTime())[0];
  const dueInDays = daysUntil(dueDate);
  const rentDueCents = outstandingCents > 0 ? outstandingCents : sharedUnpaidCents;
  const monthlyRentCents = tenancy?.monthly_rent_cents ?? tenancyProperty?.rent_cents;
  const depositCents = tenancy?.deposit_cents;
  const activeIssuesCount = issues.filter(issue => issueStep(issue.status) < 4).length;
  const leaseStart = tenancy?.lease_start ?? tenancy?.start_date;
  const leaseEnd = tenancy?.lease_end ?? tenancy?.end_date;
  const leaseStartTimestamp = leaseStart ? new Date(leaseStart).getTime() : NaN;
  const leaseEndTimestamp = leaseEnd ? new Date(leaseEnd).getTime() : NaN;
  const leaseDurationMonths = Number.isFinite(leaseStartTimestamp) && Number.isFinite(leaseEndTimestamp)
    ? Math.max(1, Math.round((leaseEndTimestamp - leaseStartTimestamp) / (30.4375 * 86_400_000)))
    : 12;
  const leaseMonthsUsed = Number.isFinite(leaseStartTimestamp)
    ? Math.max(0, Math.min(leaseDurationMonths, Math.floor((Date.now() - leaseStartTimestamp) / (30.4375 * 86_400_000))))
    : 0;
  const dueLabel = dueInDays !== null && dueInDays < 0
    ? `overdue by ${Math.abs(dueInDays)} day${Math.abs(dueInDays) === 1 ? "" : "s"}`
    : dueInDays === 0
      ? "today"
      : `in ${dueInDays} day${dueInDays === 1 ? "" : "s"}`;
  const latestIssue = [...issues].sort((first, second) =>
    (Date.parse(second.updated_at ?? second.last_update ?? second.created_at ?? "") || 0) -
    (Date.parse(first.updated_at ?? first.last_update ?? first.created_at ?? "") || 0),
  )[0];
  const latestPayment = [...payments].sort((first, second) =>
    (Date.parse(second.date ?? second.created_at ?? "") || 0) -
    (Date.parse(first.date ?? first.created_at ?? "") || 0),
  )[0];
  const issueCounts = {
    all: issues.length,
    open: issues.filter(issue => statusMatchesFilter(issue, "open")).length,
    "in-progress": issues.filter(issue => statusMatchesFilter(issue, "in-progress")).length,
    resolved: issues.filter(issue => statusMatchesFilter(issue, "resolved")).length,
  };

  function contactMaintenanceManager() {
    const manager = tenancy?.assigned_agent;
    const phone = manager?.phone;
    const email = manager?.email;
    if (phone) {
      const whatsappNumber = phone.replace(/\D/g, "").replace(/^0/, "254");
      window.open(`https://wa.me/${whatsappNumber}`, "_blank", "noopener,noreferrer");
    } else if (email) {
      window.location.assign(`mailto:${email}`);
    } else {
      const managerName = manager?.full_name ?? manager?.name;
      setPageNotice(managerName
        ? `Contact details for ${managerName} are not available yet.`
        : "Your caretaker or property manager’s contact details are not available yet.");
    }
  }

  const selectedInvoiceIdFromData = selectedInvoice?.id;
  useEffect(() => {
    if (selectedInvoiceIdFromData === undefined) return;
    setSelectedInvoiceId(String(selectedInvoiceIdFromData));
    setPaymentAmount(payableFull == null ? "" : String(payableFull));
  }, [selectedInvoiceIdFromData, payableFull]);

  useEffect(() => {
    if (!pageNotice) return;
    const timeout = window.setTimeout(() => setPageNotice(""), 4500);
    return () => window.clearTimeout(timeout);
  }, [pageNotice]);

  useEffect(() => {
    const sections = ["overview", "my-flat", "pay-rent", "statement", "maintenance", "browse-rooms", "receipts", "profile"]
      .map(id => document.getElementById(id))
      .filter((section): section is HTMLElement => section !== null);
    if (!sections.length) return;
    const observer = new IntersectionObserver(entries => {
      const visible = entries
        .filter(entry => entry.isIntersecting)
        .sort((first, second) => second.intersectionRatio - first.intersectionRatio)[0];
      if (visible) setActiveSection(visible.target.id);
    }, { rootMargin: "-110px 0px -58% 0px", threshold: [0.05, 0.25, 0.5] });
    sections.forEach(section => observer.observe(section));
    return () => observer.disconnect();
  }, [isCheckingSession]);

  useEffect(() => {
    if (!paymentRequest?.id || !["pending", "reconciling"].includes(paymentStage)) return;
    let cancelled = false;
    let timeoutId = 0;
    const startedAt = paymentStartedAt.current ?? Date.now();
    const poll = async () => {
      if (cancelled) return;
      const elapsed = Date.now() - startedAt;
      if (elapsed >= 240_000) {
        setPaymentStage("reconciling");
        setPaymentError("We haven’t received a final M-Pesa confirmation. You can check this attempt again without starting another payment.");
        return;
      }
      if (elapsed >= 120_000 && paymentStage !== "reconciling") {
        setPaymentStage("reconciling");
        setPaymentError("This payment is taking longer than usual. No final confirmation has arrived; it will not be marked successful until verified.");
      }
      try {
        const response = await clientApi.get<PaymentRequest>(
          `/api/v1/billing/mpesa/attempts/${paymentRequest.id}/`,
        );
        const current = response.data;
        if (cancelled) return;
        setPaymentRequest({
          ...current,
          amount_cents: current.amount_cents,
          reference: current.receipt ?? undefined,
        });
        if (current.status === "SUCCESSFUL") {
          window.sessionStorage.removeItem(MPESA_ATTEMPT_STORAGE_KEY);
          setPaymentStage("success");
          setPageNotice("Payment confirmed. Your rent ledger is being refreshed.");
          try {
            const AudioContextConstructor = window.AudioContext;
            if (AudioContextConstructor) {
              const audio = new AudioContextConstructor();
              const oscillator = audio.createOscillator();
              const gain = audio.createGain();
              oscillator.frequency.value = 880;
              gain.gain.setValueAtTime(0.08, audio.currentTime);
              gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + 0.25);
              oscillator.connect(gain);
              gain.connect(audio.destination);
              oscillator.start();
              oscillator.stop(audio.currentTime + 0.25);
              void audio.close();
            }
          } catch {
            // Audio is an optional enhancement; payment confirmation remains authoritative.
          }
          void loadInvoices();
          void loadPayments();
          return;
        }
        if (["FAILED", "CANCELLED", "EXPIRED"].includes(current.status ?? "")) {
          window.sessionStorage.removeItem(MPESA_ATTEMPT_STORAGE_KEY);
          setPaymentStage("failed");
          setPaymentError(current.message ?? "The payment was not completed. Please try again.");
          return;
        }
        if (current.status === "UNRESOLVED") {
          setPaymentStage("reconciling");
          setPaymentError(current.message ?? "M-Pesa hasn’t returned a final result yet. You can check this attempt again without starting another payment.");
        }
      } catch (error) {
        if (cancelled) return;
        // A restored attempt may belong to a tenant account that is no longer
        // active. The endpoint returns 404 without revealing another tenant's data.
        if (error instanceof ClientApiError && error.status === 404) {
          window.sessionStorage.removeItem(MPESA_ATTEMPT_STORAGE_KEY);
          setPaymentStage("failed");
          setPaymentError("This payment attempt is no longer available to this account. Contact your property manager before paying again.");
          return;
        }
      }
      timeoutId = window.setTimeout(poll, elapsed > 120_000 ? 10000 : 3000);
    };
    timeoutId = window.setTimeout(poll, 3000);
    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [loadInvoices, loadPayments, paymentRequest?.id, paymentStage]);

  async function initiatePayment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPaymentError("");
    const parsedCents = wholeShillingsToCents(paymentAmount);
    const normalizedPhone = phoneNumber.replace(/[^\d+]/g, "");
    if (!selectedInvoice) {
      setPaymentError("There are no outstanding invoices to pay.");
      return;
    }
    if (parsedCents == null || parsedCents <= 0) {
      setPaymentError("Enter a positive whole number of Kenyan shillings. M-Pesa does not accept cents, and extra decimal places are not rounded.");
      return;
    }
    if (paymentMethod === "mpesa" && !/^(?:\+?254|0)?[17]\d{8}$/.test(normalizedPhone)) {
      setPaymentError("Enter a valid Kenyan M-Pesa phone number.");
      return;
    }
    setIsInitiatingPayment(true);
    try {
      const idempotencyKey = window.sessionStorage.getItem(MPESA_IDEMPOTENCY_STORAGE_KEY) || window.crypto.randomUUID();
      window.sessionStorage.setItem(MPESA_IDEMPOTENCY_STORAGE_KEY, idempotencyKey);
      const response = await clientApi.post<PaymentRequest>(
        "/api/v1/billing/mpesa/initiate/",
        {
          invoice: selectedInvoice.id,
          amount_cents: parsedCents,
          phone_number: normalizedPhone,
          idempotency_key: idempotencyKey,
        },
      );
      const request = response.data;
      if (request.id === undefined || request.id === null) {
        throw new Error("The payment service did not return a payment reference.");
      }
      setPaymentRequest(request);
      window.sessionStorage.setItem(MPESA_ATTEMPT_STORAGE_KEY, String(request.id));
      window.sessionStorage.removeItem(MPESA_IDEMPOTENCY_STORAGE_KEY);
      paymentStartedAt.current = Date.now();
      setPaymentStage(
        request.payment_settled === true
          ? "success"
          : request.accepted !== true || request.status === "UNRESOLVED"
            ? "reconciling"
            : "pending",
      );
      if (request.accepted !== true && request.payment_settled !== true) {
        setPaymentError("The request outcome is uncertain. Check this attempt before starting another payment.");
      }
      if (request.payment_settled === true) {
        void loadInvoices();
        void loadPayments();
      }
      if (parsedCents > outstandingCents) {
        setPageNotice(`${formatMinor(parsedCents - outstandingCents)} will be credited to your next rent.`);
      }
    } catch (error) {
      if (error instanceof ClientApiError && error.status >= 400 && error.status < 500 && error.status !== 429) {
        window.sessionStorage.removeItem(MPESA_IDEMPOTENCY_STORAGE_KEY);
      }
      setPaymentError(
        error instanceof ClientApiError
          ? error.message
          : error instanceof Error ? error.message : "We couldn’t start your payment. Please try again.",
      );
    } finally {
      setIsInitiatingPayment(false);
    }
  }

  async function downloadReceipt(payment: Payment) {
    setReceiptError("");
    if (!payment.receipt_url) {
      setReceiptError("A receipt isn’t available for this payment yet.");
      return;
    }
    if (!downloadFromUrl(payment.receipt_url, `hodi-receipt-${payment.reference ?? payment.id}.pdf`)) {
      setReceiptError("The receipt link is invalid.");
    }
  }

  async function signOut() {
    setIsSigningOut(true);
    try {
      await clientApi.post("/api/v1/accounts/logout/");
    } catch {
      setPageNotice("We couldn’t confirm sign out with the server. Redirecting you to sign in.");
    } finally {
      window.sessionStorage.removeItem("hodi_api_token");
      window.sessionStorage.removeItem("hodi_account_type");
      window.sessionStorage.removeItem("hodi_memberships");
      window.sessionStorage.removeItem("hodi_first_name");
      window.sessionStorage.removeItem("hodi_last_name");
      window.sessionStorage.removeItem("hodi_email");
      window.sessionStorage.removeItem("hodi_phone_number");
      window.location.assign("/signin?type=tenant");
    }
  }

  if (isCheckingSession) {
    return (
      <main className="client-dashboard dashboard-auth-check" aria-live="polite">
        <span className="dashboard-loading-spinner" aria-hidden="true" />
        <p>Checking your Hodi account…</p>
      </main>
    );
  }

  if (needsOrganizationLink) {
    return <TenantLinkGate onLinked={() => setNeedsOrganizationLink(false)} />;
  }

  return (
    <div className={`client-dashboard portal-layout ${sidebarCollapsed ? "sidebar-collapsed" : ""} ${mobileMenuOpen ? "mobile-menu-open" : ""} ${mobileSearchOpen ? "mobile-search-open" : ""}`}>
      <aside className="portal-sidebar" aria-label="Tenant navigation">
        <Link className="dashboard-brand" href="/" aria-label="Hodi home">
          <img src="/apple-touch-icon.png" alt="" />
          {!sidebarCollapsed && <span>hodi</span>}
        </Link>
        <button
          type="button"
          className="portal-collapse-button"
          aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          onClick={() => setSidebarCollapsed(value => !value)}
        >
          <Icon name="chevron" size={16} />
        </button>
        <nav className="portal-nav">
          {([
            ["overview", "Dashboard", "grid"],
            ["my-flat", "My home", "home"],
            ["pay-rent", "Rent", "wallet"],
            ["statement", "Statement", "receipt"],
            ["maintenance", "Maintenance", "wrench"],
          ] as const).map(([id, label, icon]) => (
            <button
              type="button"
              className={`portal-nav-item ${activeSection === id ? "is-active" : ""}`}
              key={id}
              title={sidebarCollapsed ? label : undefined}
              onClick={() => {
                setMobileMenuOpen(false);
                scrollToSection(id);
              }}
            >
              <Icon name={icon} size={19} />
              {!sidebarCollapsed && <span>{label}</span>}
            </button>
          ))}
          <details className="portal-nav-more">
            <summary
              className={`portal-nav-item ${["browse-rooms", "receipts", "profile"].includes(activeSection) ? "is-active" : ""}`}
              title={sidebarCollapsed ? "More sections" : undefined}
            >
              <Icon name="chevron" size={19} />
              {!sidebarCollapsed && <span>More</span>}
            </summary>
            <div className="portal-nav-more-items">
              {([
                ["browse-rooms", "Browse rooms", "building"],
                ["receipts", "Receipts", "receipt"],
                ["profile", "Profile & support", "user"],
              ] as const).map(([id, label, icon]) => (
                <button
                  type="button"
                  className={`portal-nav-item ${activeSection === id ? "is-active" : ""}`}
                  key={id}
                  title={sidebarCollapsed ? label : undefined}
                  onClick={() => {
                    setMobileMenuOpen(false);
                    scrollToSection(id);
                  }}
                >
                  <Icon name={icon} size={19} />
                  {!sidebarCollapsed && <span>{label}</span>}
                </button>
              ))}
              <Link href="/utilities" className="portal-nav-item" onClick={() => setMobileMenuOpen(false)}>
                <Icon name="building" size={19} />
                {!sidebarCollapsed && <span>Utilities</span>}
              </Link>
              <Link href="/living" className="portal-nav-item" onClick={() => setMobileMenuOpen(false)}>
                <Icon name="home" size={19} />
                {!sidebarCollapsed && <span>HODI Living</span>}
              </Link>
              <Link href="/marketplace" className="portal-nav-item" onClick={() => setMobileMenuOpen(false)}>
                <Icon name="building" size={19} />
                {!sidebarCollapsed && <span>Marketplace</span>}
              </Link>
            </div>
          </details>
        </nav>
        <div className="portal-sidebar-bottom">
          {!sidebarCollapsed && (
            <div className="portal-sidebar-help">
              <span><Icon name="message" size={18} /></span>
              <div>
                <strong>Need help at home?</strong>
                <small>Your caretaker or property manager can help.</small>
              </div>
              <button type="button" onClick={contactMaintenanceManager}>Message manager <Icon name="arrow" size={14} /></button>
            </div>
          )}
          <button className="portal-nav-item portal-signout" type="button" onClick={() => void signOut()}>
            <Icon name="logout" size={19} />
            {!sidebarCollapsed && <span>{isSigningOut ? "Signing out…" : "Log out"}</span>}
          </button>
        </div>
      </aside>
      <button
        type="button"
        className="portal-sidebar-scrim"
        aria-label="Close menu"
        onClick={() => setMobileMenuOpen(false)}
      />
      <div className="portal-workspace">
        <header className="portal-header">
          <div className="portal-header-leading">
            <button
              type="button"
              className="portal-mobile-menu-button"
              aria-label="Open navigation menu"
              onClick={() => setMobileMenuOpen(true)}
            ><Icon name="menu" /></button>
            <div>
              <p>TENANT PORTAL</p>
              <strong>Good to see you, {clientName.split(" ")[0]}.</strong>
            </div>
          </div>
          <div className="portal-header-tools">
            <label className="portal-search">
              <Icon name="search" size={18} />
              <input
                ref={headerSearchInput}
                value={headerSearch}
                onChange={event => setHeaderSearch(event.target.value)}
                onKeyDown={event => {
                  if (event.key === "Enter") {
                    const term = headerSearch.trim().toLowerCase();
                    const paymentMatch = payments.some(payment =>
                      (payment.reference ?? payment.transaction_id ?? "").toLowerCase().includes(term),
                    );
                    const invoiceMatch = invoices.some(invoice =>
                      (invoice.month ?? invoice.description ?? "").toLowerCase().includes(term),
                    );
                    if (term && (paymentMatch || invoiceMatch)) {
                      scrollToSection(paymentMatch ? "receipts" : "pay-rent");
                    } else {
                      setPageNotice("Published homes are listed on the public marketplace.");
                      scrollToSection("browse-rooms");
                    }
                    setMobileSearchOpen(false);
                  }
                }}
                placeholder="Search rooms, payments…"
                aria-label="Search rooms and payments"
              />
            </label>
            <button
              type="button"
              className="portal-mobile-search-button"
              aria-label={mobileSearchOpen ? "Close search" : "Open search"}
              aria-expanded={mobileSearchOpen}
              onClick={() => {
                setMobileSearchOpen(open => !open);
                window.setTimeout(() => headerSearchInput.current?.focus(), 0);
              }}
            ><Icon name={mobileSearchOpen ? "close" : "search"} size={19} /></button>
            <NotificationBell />
            <ThemeToggle className="portal-theme-toggle" />
            <span className="portal-current-flat"><Icon name="home" size={15} /> Flat {flatNumber}</span>
            <button className="portal-profile-chip" type="button" onClick={() => scrollToSection("profile")}>
              <span className="dashboard-account-avatar">{clientName.slice(0, 1).toUpperCase()}</span>
              <span>{clientName}</span>
              <Icon name="chevron" size={15} />
            </button>
          </div>
        </header>

      <Container className="dashboard-content portal-content">
        {paymentRequest && paymentStage === "idle" && (
          <div className="portal-toast" role="status">
            Payment attempt {paymentRequest.id} has no final status.
            <Button type="button" variant="secondary" onClick={() => {
              paymentStartedAt.current = Date.now();
              setPaymentStage("pending");
              setPaymentError("");
            }}>Resume status check</Button>
          </div>
        )}
        {pageNotice && <div className="portal-toast" role="status"><Icon name="check" size={17} />{pageNotice}<button type="button" aria-label="Dismiss notification" onClick={() => setPageNotice("")}>×</button></div>}
        {propertyError && <div className="portal-toast portal-toast--error" role="alert">{propertyError}<button type="button" aria-label="Dismiss notification" onClick={() => setPropertyError("")}>×</button></div>}
        <section className="portal-overview" id="overview">
          <div className="portal-page-heading">
            <div>
              <p className="dashboard-greeting">YOUR HOME, AT A GLANCE</p>
              <h1>Welcome home, {clientName.split(" ")[0]}.</h1>
              <p>Here’s what’s happening with your Hodi home today.</p>
            </div>
            <span className="portal-overview-date"><Icon name="calendar" size={16} />{new Intl.DateTimeFormat("en-KE", { weekday: "long", day: "numeric", month: "long" }).format(new Date())}</span>
          </div>
          <div className="portal-kpi-grid">
            <article className={`portal-rent-summary ${rentDueCents > 0 ? dueInDays !== null && dueInDays < 0 ? "is-overdue" : "is-due" : rentOverviewStatus === "Paid" ? "is-clear" : ""}`}>
              <div className="portal-rent-summary-heading">
                <div><small>RENT AT A GLANCE</small><span>{rentOverviewStatus}</span></div>
                <span className="portal-kpi-icon"><Icon name="wallet" size={19} /></span>
              </div>
              <strong className="portal-rent-summary-value">
                {rentDueCents > 0 ? formatMinor(rentDueCents) : rentOverviewStatus === "Paid" ? "All clear" : rentOverviewStatus}
              </strong>
              <small className="portal-rent-summary-caption">
                {rentDueCents > 0
                  ? dueDate ? `Outstanding · due ${formatDate(dueDate)} (${dueLabel})` : "Outstanding balance · due date not available"
                  : dueDate ? `Next due ${formatDate(dueDate)}${dueInDays !== null ? ` · ${dueLabel}` : ""}` : rentOverviewStatus === "Paid" ? "Your account is up to date" : "Check your latest rent details"}
              </small>
              <Button type="button" onClick={() => scrollToSection("pay-rent")}>
                {rentDueCents > 0 ? "Pay rent" : "View rent"}<Icon name="arrow" size={15} />
              </Button>
            </article>
            <SummaryCard
              label="Active issues"
              value={String(activeIssuesCount)}
              caption={activeIssuesCount === 1 ? "Request being looked after" : "Requests being looked after"}
              icon="wrench"
              tone="slate"
            />
            <SummaryCard
              label="Deposit balance"
              value={depositCents != null ? formatMinor(depositCents) : "Not available"}
              caption="Held against your tenancy"
              icon="shield"
              tone="green"
            />
          </div>
          <div className="portal-quick-actions">
            <span>Quick actions</span>
            <button type="button" onClick={() => setIsReportOpen(true)}><Icon name="wrench" size={17} />Report an issue</button>
            <button type="button" onClick={contactMaintenanceManager}><Icon name="message" size={17} />Contact manager</button>
            <button type="button" onClick={() => scrollToSection("my-flat")}><Icon name="home" size={17} />View home details</button>
          </div>
          <div className="portal-recent-activity" aria-label="Recent account activity">
            <article className="portal-activity-item">
              <span className="portal-activity-icon"><Icon name="wrench" size={18} /></span>
              <div>
                <small>Latest maintenance</small>
                <strong>{isLoadingIssues ? "Loading updates…" : issueError ? "Updates unavailable" : latestIssue?.title ?? "No requests yet"}</strong>
                <span>{issueError ? "Open maintenance to retry." : latestIssue ? `${humanizeStatus(latestIssue.status)} · updated ${formatDate(latestIssue.updated_at ?? latestIssue.last_update ?? latestIssue.created_at)}` : "Your reported issues will appear here."}</span>
              </div>
              <button type="button" onClick={() => latestIssue ? scrollToSection("maintenance") : setIsReportOpen(true)}>
                {latestIssue ? "View" : "Report"}
              </button>
            </article>
            <article className="portal-activity-item">
              <span className="portal-activity-icon"><Icon name="receipt" size={18} /></span>
              <div>
                <small>Latest payment</small>
                <strong>{isLoadingPayments ? "Loading payments…" : receiptError ? "Activity unavailable" : latestPayment?.amount_cents != null ? formatMinor(latestPayment.amount_cents) : "No payment recorded"}</strong>
                <span>{receiptError ? "Open receipts to retry." : latestPayment ? `${humanizeStatus(latestPayment.status)} · ${formatDate(latestPayment.date ?? latestPayment.created_at)}` : "Your recent rent payments will appear here."}</span>
              </div>
              <button type="button" onClick={() => scrollToSection("receipts")}>View</button>
            </article>
          </div>
        </section>

        <section className="dashboard-section portal-section" id="my-flat" aria-labelledby="my-flat-title">
          <SectionHead
            eyebrow="Your tenancy"
            title="My home"
            titleId="my-flat-title"
            description="Your home details and lease at a glance."
          />
          {isLoadingTenancy ? (
            <div className="dashboard-tenancy-skeleton"><div className="dashboard-skeleton dashboard-skeleton-line" /><div className="dashboard-skeleton dashboard-skeleton-line short" /></div>
          ) : tenancy ? (
            <>
              <div className="portal-tenancy-summary">
                <div className="portal-tenancy-art"><Icon name="building" size={30} /></div>
                <div className="portal-tenancy-primary"><small>CURRENT RESIDENCE</small><h3>{propertyTitle}</h3><p><Icon name="pin" size={14} />{estate} <span>·</span> House {flatNumber}</p></div>
                <div className="portal-tenancy-landlord"><small>LANDLORD / AGENT</small><strong>{landlord}</strong><span><Icon name="shield" size={14} /> Verified tenancy</span></div>
                <div className={`dashboard-rent-status ${/paid|clear/i.test(rentStatus) && outstandingCents <= 0 ? "is-paid" : ""}`}><span className="dashboard-rent-status-dot" /><span>Rent status</span><strong>{outstandingCents > 0 ? "Due" : rentStatus}</strong></div>
              </div>
              <div className="portal-tenancy-facts">
                <div><small>MONTHLY RENT</small><strong>{monthlyRentCents != null ? formatMinor(monthlyRentCents) : "Not listed"}</strong></div>
                <div><small>SECURITY DEPOSIT</small><strong>{depositCents != null ? formatMinor(depositCents) : "Not listed"}</strong></div>
                <div><small>LEASE START</small><strong>{formatDate(leaseStart)}</strong></div>
                <div><small>LEASE END</small><strong>{formatDate(leaseEnd)}</strong></div>
              </div>
              <div className="portal-lease-progress">
                <div><span>Lease progress</span><strong>{leaseMonthsUsed} of {leaseDurationMonths} months used</strong></div>
                <div className="portal-progress-track"><span style={{ width: `${Math.min(100, leaseMonthsUsed / leaseDurationMonths * 100)}%` }} /></div>
                <div className="portal-lease-dates"><span>{formatDate(leaseStart)}</span><span>{formatDate(leaseEnd)}</span></div>
              </div>
              <div className="portal-tenancy-actions">
                <Button type="button" variant="secondary" onClick={() => {
                  const url = tenancy.lease_url ?? tenancy.agreement_url;
                  if (!downloadFromUrl(url, "hodi-lease-agreement.pdf")) setPageNotice("Your lease agreement isn’t available for download yet.");
                }}><Icon name="external" size={16} />View lease agreement</Button>
                <Button type="button" variant="ghost" onClick={() => {
                  const url = tenancy.lease_url ?? tenancy.agreement_url;
                  if (!downloadFromUrl(url, "hodi-lease-agreement.pdf")) setPageNotice("Your lease agreement isn’t available for download yet.");
                }}><Icon name="download" size={16} />Download agreement</Button>
              </div>
            </>
          ) : (
            <div className="dashboard-no-tenancy"><span className="dashboard-empty-room-icon"><Icon name="home" /></span><div><h3>No active tenancy is linked to your account</h3><p>Once your tenancy is connected, your home, lease and rent information will appear here.</p>{tenancyError && <p className="dashboard-inline-error">{tenancyError}</p>}</div></div>
          )}
        </section>

        <section className="dashboard-section portal-section" id="pay-rent" aria-labelledby="pay-rent-title">
          <div className="portal-section-heading">
            <SectionHead eyebrow="Rent account" title="Pay Rent" titleId="pay-rent-title" description="Review your rent invoices and current balance." />
          </div>
          {billingError && <div className="dashboard-alert" role="alert">{billingError}<Button type="button" variant="ghost" onClick={() => void loadInvoices()}>Try again</Button></div>}
          <div className="portal-rent-layout">
            <div className="portal-invoice-panel">
              <div className="portal-panel-heading"><div><small>YOUR RENT LEDGER</small><h3>Outstanding balance</h3></div><span className={outstandingCents > 0 ? "portal-amount-due" : "portal-amount-clear"}>{outstandingCents > 0 ? formatMinor(outstandingCents) : formatMinor(0)}</span></div>
              {isLoadingInvoices ? <div className="portal-inline-loading"><span className="dashboard-loading-spinner" />Loading your invoices…</div> : billingError ? (
                <div className="portal-empty-inline"><Icon name="clock" size={20} /><strong>Invoices are unavailable</strong><span>Retry above, or contact your agent to confirm your current balance.</span></div>
              ) : invoices.length ? (
                <div className="portal-invoice-list">{invoices.map(invoice => {
                  const balance = invoiceBalanceCents(invoice);
                  const active = String(invoice.id) === (selectedInvoice?.id === undefined ? "" : String(selectedInvoice.id));
                  return <button type="button" key={invoice.id} className={`portal-invoice-row ${PAYMENT_FLOW_AVAILABLE && active ? "is-selected" : ""}`} onClick={() => selectInvoice(invoice)} disabled={!PAYMENT_FLOW_AVAILABLE}>
                    <span className="portal-invoice-select">{PAYMENT_FLOW_AVAILABLE && active && <span />}</span>
                    <span className="portal-invoice-name"><strong>{invoice.month ?? invoice.description ?? "Rent invoice"}</strong><small>Due {formatDate(invoice.due_date)}</small></span>
                    <span className={`portal-invoice-status status-${normalizedStatus(invoice.status) || "pending"}`}>{humanizeStatus(invoice.status ?? "pending")}</span>
                    <span className="portal-invoice-balance"><strong>Balance due: {formatMinor(balance)}</strong><small>Invoice total: {formatMinor(invoice.amount_cents ?? 0)}</small><small>Amount paid: {formatMinor(invoice.paid_cents ?? 0)}</small></span>
                  </button>;
                })}</div>
              ) : <div className="portal-empty-inline"><Icon name="check" size={20} /><strong>{tenancy ? "No rent invoices yet" : "Add a tenancy to view rent"}</strong><span>When your next invoice is issued, it will show here.</span></div>}
              {outstandingInvoices.length > 0 && <p className="portal-ledger-note"><Icon name="shield" size={14} />Your rent balance is kept against your tenant ledger.</p>}
            </div>
            {PAYMENT_FLOW_AVAILABLE ? <form className="portal-payment-card" onSubmit={initiatePayment}>
              <div className="portal-payment-card-heading"><span className="portal-payment-icon"><Icon name="wallet" size={19} /></span><div><small>MAKE A PAYMENT</small><strong>{selectedInvoice?.month ?? selectedInvoice?.description ?? "Select an invoice"}</strong></div></div>
              <label className="portal-payment-amount">Amount to pay (KES)<span className="portal-currency-input"><span>KES</span><input inputMode="numeric" type="number" min="1" step="1" max="99999999" value={paymentAmount} onChange={event => setPaymentAmount(event.target.value)} disabled={!selectedInvoice} required /></span></label>
              <div className="portal-amount-chips">
                <button type="button" disabled={payableFull == null} onClick={() => payableFull != null && setRentAmount(payableFull)}>Full balance <strong>{payableFull == null ? "Not a whole shilling" : formatMinor(payableFull * 100, "KES", { trailingZeros: false })}</strong></button>
                <button type="button" disabled={payableHalf == null} onClick={() => payableHalf != null && setRentAmount(payableHalf)}>Pay half <strong>{payableHalf == null ? "Not an even split" : formatMinor(payableHalf * 100, "KES", { trailingZeros: false })}</strong></button>
              </div>
              {selectedInvoice && selectedBalanceCents > 0 && payableFull == null && <p className="portal-credit-note">This balance includes cents. M-Pesa accepts whole shillings only, so the exact balance cannot be sent in one prompt. Enter a whole-shilling amount; the remainder stays on the invoice.</p>}
              {wholeShillingsToCents(paymentAmount) != null && (wholeShillingsToCents(paymentAmount) ?? 0) > outstandingCents && outstandingCents > 0 && <p className="portal-credit-note"><Icon name="check" size={15} />{formatMinor((wholeShillingsToCents(paymentAmount) ?? 0) - outstandingCents)} will be credited to next month.</p>}
              <div className="portal-method-select">
                <span>Payment method</span>
                <div className="portal-method-select is-selected"><span className="portal-method-logo">M</span><span><strong>M-Pesa</strong><small>STK push · confirmation shown after provider settlement</small></span><i /></div>
              </div>
              {paymentMethod === "mpesa" && <label className="portal-phone-field">M-Pesa phone number<input type="tel" inputMode="tel" autoComplete="tel" placeholder="07XX XXX XXX" value={phoneNumber} onChange={event => setPhoneNumber(event.target.value)} required /><small>We’ll send a secure payment request to this phone.</small></label>}
              {paymentError && <p className="dashboard-form-error" role="alert">{paymentError}</p>}
              <Button type="submit" disabled={!selectedInvoice || !Number(paymentAmount) || isInitiatingPayment} className="portal-pay-button">{isInitiatingPayment ? "Starting secure payment…" : `Pay KES ${money(paymentAmount)}`}<Icon name="arrow" size={17} /></Button>
              <p className="portal-secure-note"><Icon name="shield" size={13} />Encrypted payment · Your details stay protected</p>
            </form> : (
              <div className="portal-payment-unavailable" role="status">
                <span className="portal-payment-unavailable-icon"><Icon name="wallet" size={20} /></span>
                <div>
                  <strong>Online payments aren’t available yet</strong>
                  <p>Contact your property agent to confirm your balance and current payment instructions.</p>
                </div>
                <Button type="button" variant="secondary" onClick={contactMaintenanceManager}>
                  <Icon name="message" size={16} />Contact manager
                </Button>
              </div>
            )}
          </div>
        </section>

        <StatementPanel />

        <section className="dashboard-section" aria-label="Tenant services">
          <SectionHead eyebrow="Hodi Living" title="Services and utilities" titleId="tenant-services-title" description="Request household services and see utility bills recorded for your current tenancy." />
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <Link className="dashboard-link" href="/living">Open Hodi Living</Link>
            <Link className="dashboard-link" href="/utilities">View tenancy utilities</Link>
          </div>
        </section>

        <section className="dashboard-section dashboard-rooms portal-section" id="browse-rooms" aria-labelledby="available-rooms-title">
          <SectionHead
            eyebrow="Find your next place"
            title="Available rooms"
            titleId="available-rooms-title"
            description="Published homes are listed on the public marketplace. Opening it does not reserve a home."
          />
          {!MARKETPLACE_AVAILABLE && (
            <div className="dashboard-empty-rooms">
              <span className="dashboard-empty-room-icon"><Icon name="home" size={26} /></span>
              <div>
                <h3>Browse published homes</h3>
                <p>Available listings live on the public marketplace. This portal does not book a viewing or mark a home as rented.</p>
                <Link href="/marketplace" className="dashboard-link">Open marketplace</Link>
              </div>
            </div>
          )}
          {MARKETPLACE_AVAILABLE && (
          <>
          <div className="dashboard-filters">
            <label className="dashboard-filter-control">
              <span>Search listings</span>
              <div className="portal-filter-search"><Icon name="search" size={16} /><input value={propertySearch} placeholder="Estate, town or room…" onChange={event => {
                setPropertySearch(event.target.value);
                setPropertyPage(1);
              }} /></div>
            </label>
            <label className="dashboard-filter-control">
              <span>Location</span>
              <select value={location} onChange={(event: ChangeEvent<HTMLSelectElement>) => {
                setLocation(event.target.value);
                setPropertyPage(1);
              }}>
                <option value="all">All locations</option>
                {[...new Set(["Ruiru", "Kahawa", "Eldoret", "Nairobi", ...locations])].map(item => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>

            <label className="dashboard-filter-control dashboard-price-filter">
              <span>Monthly rent <strong>Up to KES {money(maxPrice)}</strong></span>
              <input
                type="range"
                min={3000}
                max={100000}
                step={1000}
                value={maxPrice}
                onChange={(event: ChangeEvent<HTMLInputElement>) => {
                  setMaxPrice(Number(event.target.value));
                  setPropertyPage(1);
                }}
                aria-label="Maximum monthly rent"
              />
              <span className="dashboard-range-labels"><span>KES 3,000</span><span>KES 100,000</span></span>
            </label>

            <label className="dashboard-filter-control">
              <span>Room type</span>
              <select value={bedrooms} onChange={(event: ChangeEvent<HTMLSelectElement>) => {
                setBedrooms(event.target.value);
                setPropertyPage(1);
              }}>
                <option value="all">Any room type</option>
                <option value="bedsitter">Bedsitter</option>
                <option value="1br">1 bedroom</option>
                <option value="2br">2 bedrooms</option>
                <option value="3br">3 bedrooms</option>
              </select>
            </label>

            <div className="portal-amenity-filter">
              <span>Amenities</span>
              {["Water", "WiFi"].map(value => (
                <label key={value}>
                  <input
                    type="checkbox"
                    checked={amenities.includes(value)}
                    onChange={event => {
                      setAmenities(current => event.target.checked
                        ? [...current, value]
                        : current.filter(item => item !== value));
                      setPropertyPage(1);
                    }}
                  />
                  {value}
                </label>
              ))}
            </div>
            <label className="dashboard-available-toggle">
              <input
                type="checkbox"
                checked={availableNow}
                onChange={(event: ChangeEvent<HTMLInputElement>) => {
                  setAvailableNow(event.target.checked);
                  setPropertyPage(1);
                }}
              />
              <span className="dashboard-toggle-track" aria-hidden="true"><span /></span>
              <span>Available now</span>
            </label>
          </div>

          {isLoadingProperties ? (
            <LoadingCards />
          ) : propertyLoadError ? (
            <div className="dashboard-alert" role="alert">
              {propertyLoadError}
              <Button type="button" variant="ghost" onClick={() => void loadProperties()}>Try again</Button>
            </div>
          ) : filteredProperties.length ? (
            <div className="dashboard-property-grid">
              {visibleProperties.map(property => (
                <PropertyCard
                  key={property.id}
                  property={property}
                  onOpen={openProperty}
                  onContact={contactAgent}
                  onBookViewing={bookViewing}
                  imageIndex={activeImage[String(property.id)] ?? 0}
                  onImageChange={index => setActiveImage(current => ({ ...current, [String(property.id)]: index }))}
                />
              ))}
            </div>
          ) : (
            <div className="dashboard-empty-rooms">
              <span className="dashboard-empty-room-icon"><Icon name="home" size={26} /></span>
              <div>
                <h3>No rooms match these filters</h3>
                <p>Try another location or a higher rent range to see more places.</p>
              </div>
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setLocation("all");
                  setBedrooms("all");
                  setMaxPrice(100000);
                  setAvailableNow(false);
                  setAmenities([]);
                  setPropertySearch("");
                  setPropertyPage(1);
                }}
              >
                Clear filters
              </Button>
            </div>
          )}
          {!isLoadingProperties && (propertyCount > 12 || propertyHasNext || propertyPage > 1) && (
            <div className="portal-pagination">
              <span>{propertyCount > 0 ? `Page ${propertyPage} of ${Math.ceil(propertyCount / 12)}` : `Page ${propertyPage}`}</span>
              <div>
                <Button type="button" variant="secondary" disabled={propertyPage <= 1 || propertyCount <= 0 && !propertyHasPrevious} onClick={() => setPropertyPage(page => Math.max(1, page - 1))}>Previous</Button>
                <Button type="button" variant="secondary" disabled={propertyCount > 0 ? propertyPage >= Math.ceil(propertyCount / 12) : !propertyHasNext} onClick={() => setPropertyPage(page => page + 1)}>Next <Icon name="arrow" size={15} /></Button>
              </div>
            </div>
          )}
          </>
          )}
        </section>

        <section className="dashboard-section dashboard-maintenance portal-section" id="maintenance" aria-labelledby="maintenance-title">
          <SectionHead
            eyebrow="Your home, cared for"
            title="Maintenance & issues"
            titleId="maintenance-title"
            description="Report a problem and follow it through to resolution."
            action={
              tenancy ? (
                <Button type="button" className="dashboard-report-button portal-report-cta" onClick={() => setIsReportOpen(true)}>
                  Report New Issue <span aria-hidden="true">+</span>
                </Button>
              ) : undefined
            }
          />

          {isLoadingTenancy ? (
            <div className="dashboard-tenancy-skeleton">
              <div className="dashboard-skeleton dashboard-skeleton-line" />
              <div className="dashboard-skeleton dashboard-skeleton-line short" />
            </div>
          ) : tenancy ? (
            <div className="dashboard-tenancy-card">
              <div className="dashboard-tenancy-icon"><Icon name="home" size={24} /></div>
              <div className="dashboard-tenancy-details">
                <span>Your current home</span>
                <h3>Flat {flatNumber}</h3>
                <p>{estate} <span>·</span> Landlord: {landlord}</p>
              </div>
              <div className={`dashboard-rent-status ${/paid/i.test(rentStatus) ? "is-paid" : ""}`}>
                <span className="dashboard-rent-status-dot" />
                <span>Rent</span>
                <strong>{rentStatus}</strong>
              </div>
              <Button
                type="button"
                className="dashboard-report-mobile"
                onClick={() => setIsReportOpen(true)}
              >
                Report New Issue <span aria-hidden="true">+</span>
              </Button>
            </div>
          ) : (
            <div className="dashboard-no-tenancy">
              <div className="dashboard-empty-room-icon"><Icon name="home" size={25} /></div>
              <div>
                <h3>No active tenancy linked to your account</h3>
                <p>Once a tenancy is linked, you’ll be able to report and track maintenance requests here.</p>
              </div>
              {tenancyError && <span className="dashboard-inline-error">{tenancyError}</span>}
            </div>
          )}

          {tenancyError && tenancy && <p className="dashboard-inline-error">{tenancyError}</p>}
          {tenancy && issueActionError && <p className="dashboard-inline-error" role="alert">{issueActionError}</p>}

          {!isLoadingTenancy && tenancy && <div className="dashboard-issue-section">
            <div className="dashboard-issue-toolbar">
              <div>
                <h3>Your reported issues</h3>
                <p>Keep track of every request you’ve raised.</p>
              </div>
              <div className="dashboard-issue-filters" aria-label="Filter reported issues">
                {([
                  ["all", "All"],
                  ["open", "Open"],
                  ["in-progress", "In progress"],
                  ["resolved", "Resolved"],
                ] as const).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    className={issueFilter === value ? "is-active" : ""}
                    aria-pressed={issueFilter === value}
                    onClick={() => setIssueFilter(value)}
                  >
                    {label}
                    <span>{issueCounts[value]}</span>
                  </button>
                ))}
              </div>
            </div>

            {isLoadingIssues ? (
              <div className="dashboard-issue-list" aria-label="Loading reported issues">
                {[1, 2].map(item => (
                  <div className="dashboard-skeleton-issue" key={item}>
                    <div className="dashboard-skeleton dashboard-skeleton-line" />
                    <div className="dashboard-skeleton dashboard-skeleton-line short" />
                    <div className="dashboard-skeleton dashboard-skeleton-line" />
                  </div>
                ))}
              </div>
            ) : issueError ? (
              <div className="dashboard-alert" role="alert">
                {issueError}
                <Button type="button" variant="ghost" onClick={() => void loadIssues()}>Try again</Button>
              </div>
            ) : filteredIssues.length ? (
              <div className="dashboard-issue-list">
                {filteredIssues.map(issue => (
                  <IssueCard
                    key={issue.id}
                    issue={issue}
                    onComment={addIssueComment}
                    onResolve={markResolved}
                  />
                ))}
              </div>
            ) : issues.length ? (
              <div className="dashboard-filter-empty">
                No issues in this category. Choose another filter to view your requests.
              </div>
            ) : (
              <EmptyIssues />
            )}
          </div>}
          <TenantWorkStatus />
        </section>

        <section className="dashboard-section portal-section" id="receipts" aria-labelledby="receipts-title">
          <div className="portal-receipts-heading">
            <SectionHead eyebrow="Your payment history" title="Receipts" titleId="receipts-title" description="Rent payments recorded for your lease. The statement section builds a PDF from posted charges and payments." />
            <Button type="button" variant="secondary" onClick={() => scrollToSection("statement")}>
              <Icon name="download" size={16} />Open statement
            </Button>
          </div>
          <div className="portal-balance-banner">
            <span><Icon name="shield" size={20} /></span>
            <div><small>RENT RECORD</small><strong>{isLoadingPayments ? "Checking payments…" : payments.length ? `${payments.length} rent payment${payments.length === 1 ? "" : "s"} on file` : "No rent payments on file"}</strong></div>
            <b>Use Statement for the PDF</b>
          </div>
          {receiptError && <p className="dashboard-inline-error" role="alert">{receiptError}<button type="button" className="portal-text-button" onClick={() => void loadPayments()}>Retry</button></p>}
          <div className="portal-table-wrap">
            <table className="portal-payments-table">
              <thead><tr><th>Date</th><th>Reference</th><th>For</th><th>Method</th><th>Amount</th><th>Status</th><th>Receipt</th></tr></thead>
              <tbody>
                {isLoadingPayments ? <tr><td colSpan={7}><div className="portal-inline-loading"><span className="dashboard-loading-spinner" />Loading your payments…</div></td></tr>
                  : payments.length ? payments.map(payment => {
                    const invoice = typeof payment.invoice === "object" ? payment.invoice : undefined;
                    return <tr key={payment.id}>
                      <td>{formatDate(payment.date ?? payment.created_at)}</td>
                      <td><strong className="portal-reference">{payment.reference ?? payment.transaction_id ?? `HOD-${payment.id}`}</strong></td>
                      <td>{invoice?.month ?? invoice?.description ?? payment.description ?? "Rent payment"}</td>
                      <td>{humanizeStatus(payment.method ?? "M-Pesa")}</td>
                      <td><strong>{payment.amount_cents != null ? formatMinor(payment.amount_cents) : "—"}</strong></td>
                      <td>
                        <span className={`portal-payment-status ${normalizedStatus(payment.status) === "reversed" ? "is-reversed" : isPaymentSuccessful(payment.status) ? "is-success" : isPaymentFailed(payment.status) ? "is-failed" : normalizedStatus(payment.status) === "overdue" ? "is-overdue" : "is-pending"}`}>{humanizeStatus(payment.status ?? "pending")}</span>
                        {payment.reversal && <small className="portal-reversal-note">{humanizeStatus(payment.reversal.status)}: {payment.reversal.reason}</small>}
                      </td>
                      <td><button className="portal-receipt-button" type="button" onClick={() => void downloadReceipt(payment)} disabled={!payment.receipt_url} aria-label={`Download receipt ${payment.reference ?? payment.id}`} title={payment.receipt_url ? "Download receipt" : "Receipt not available"}><Icon name="download" size={16} /></button></td>
                    </tr>;
                  }) : <tr><td colSpan={7}><div className="portal-table-empty"><Icon name="receipt" size={22} /><strong>No payments yet</strong><span>Your completed rent receipts will appear here.</span></div></td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        <section className="dashboard-section portal-section portal-profile-section" id="profile" aria-labelledby="profile-title">
          <SectionHead eyebrow="Your account" title="Profile & support" titleId="profile-title" description={`Update the contact details your property team is allowed to change.${clientEmail ? ` Signed in as ${clientEmail}.` : ""}`} />
          <TenantProfileEditor />
          <div className="portal-profile-card">
            <button type="button" className="portal-contact-button" onClick={contactMaintenanceManager}><Icon name="message" size={17} />Contact manager</button>
            <Button type="button" variant="ghost" onClick={() => void signOut()}><Icon name="logout" size={16} />Log out</Button>
          </div>
        </section>
      </Container>
      </div>

      <nav className="portal-bottom-nav" aria-label="Tenant navigation">
        {([
          ["overview", "Home", "grid"],
          ["my-flat", "My home", "home"],
          ["pay-rent", "Rent", "wallet"],
          ["maintenance", "Issues", "wrench"],
        ] as const).map(([id, label, icon]) => (
          <button type="button" className={activeSection === id ? "is-active" : ""} key={id} onClick={() => scrollToSection(id)}><Icon name={icon} size={19} /><span>{label}</span></button>
        ))}
      </nav>

      {isReportOpen && (
        <ReportIssueModal
          onClose={() => setIsReportOpen(false)}
          onSubmit={submitIssue}
          flatLabel={`${propertyTitle} · Flat ${flatNumber} · ${estate}`}
        />
      )}
      {paymentRequest && paymentStage !== "idle" && (
        <div className="dashboard-modal-backdrop portal-payment-backdrop" role="presentation">
          <section className={`portal-payment-modal payment-${paymentStage}`} role="dialog" aria-modal="true" aria-labelledby="payment-status-title">
            <button className="dashboard-icon-button portal-payment-close" type="button" aria-label="Close payment status" onClick={() => {
              if (paymentStage !== "pending") {
                setPaymentStage("idle");
                setPaymentError("");
                if (paymentStage !== "reconciling") {
                  window.sessionStorage.removeItem(MPESA_ATTEMPT_STORAGE_KEY);
                  setPaymentRequest(null);
                }
              }
            }} disabled={paymentStage === "pending"}><Icon name="close" size={18} /></button>
            {paymentStage === "pending" ? (
              <>
                <div className="portal-stk-animation"><span /><Icon name="phone" size={27} /></div>
                <p className="portal-modal-eyebrow">M-PESA SECURE CHECKOUT</p>
                <h2 id="payment-status-title">Check your phone</h2>
                <p>{paymentMethod === "mpesa" ? <>We’ve sent an STK Push to <strong>{phoneNumber}</strong>. Enter your M-Pesa PIN to approve the payment.</> : <>Your bank transfer has been initiated. {paymentRequest.message ?? <>Use reference <strong>{paymentRequest.reference ?? paymentRequest.id}</strong> and keep this page open while we verify it.</>}</>}</p>
                <div className="portal-payment-wait"><span className="dashboard-loading-spinner" />{paymentMethod === "mpesa" ? "Waiting for M-Pesa confirmation…" : "Waiting for transfer confirmation…"}</div>
                <small className="portal-payment-reference">Payment ref: {paymentRequest.reference ?? paymentRequest.id}</small>
              </>
            ) : paymentStage === "reconciling" ? (
              <>
                <div className="portal-reconcile-icon"><Icon name="clock" size={28} /></div>
                <p className="portal-modal-eyebrow">PAYMENT STATUS</p>
                <h2 id="payment-status-title">Payment status is unresolved</h2>
                <p>{paymentError || "No final status is available yet. Check this attempt again before starting another payment."}</p>
                <div className="portal-reconcile-reference">Reference <strong>{paymentRequest.reference ?? paymentRequest.id}</strong></div>
                <Button type="button" variant="secondary" onClick={() => {
                  paymentStartedAt.current = Date.now();
                  setPaymentStage("pending");
                  setPaymentError("");
                }}>Check status again</Button>
              </>
            ) : paymentStage === "success" ? (
              <>
                <div className="portal-payment-success-mark"><Icon name="check" size={31} /></div>
                <div className="portal-success-confetti" aria-hidden="true"><span /><span /><span /><span /><span /><span /></div>
                <p className="portal-modal-eyebrow">PAYMENT CONFIRMED</p>
                <h2 id="payment-status-title">Asante, {clientName.split(" ")[0]}!</h2>
                <p>Your payment of <strong>{paymentRequest.amount_cents != null ? formatMinor(paymentRequest.amount_cents) : formatMinor(wholeShillingsToCents(paymentAmount) ?? 0)}</strong> has been received.</p>
                <div className="portal-success-receipt"><span>M-Pesa receipt</span><strong>{paymentRequest.receipt ?? paymentRequest.reference ?? "Not available"}</strong></div>
                <Button type="button" onClick={() => {
                  window.sessionStorage.removeItem(MPESA_ATTEMPT_STORAGE_KEY);
                  setPaymentStage("idle");
                  setPaymentRequest(null);
                  scrollToSection("receipts");
                }}>View receipt <Icon name="arrow" size={16} /></Button>
              </>
            ) : (
              <>
                <div className="portal-payment-failure-mark"><Icon name="close" size={28} /></div>
                <p className="portal-modal-eyebrow">PAYMENT NOT COMPLETED</p>
                <h2 id="payment-status-title">Let’s try that again</h2>
                <p>{paymentError || "The payment could not be completed. You can retry without losing your invoice."}</p>
                <Button type="button" onClick={() => {
                  window.sessionStorage.removeItem(MPESA_ATTEMPT_STORAGE_KEY);
                  setPaymentStage("idle");
                  setPaymentRequest(null);
                  setPaymentError("");
                }}>Return to payment</Button>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
