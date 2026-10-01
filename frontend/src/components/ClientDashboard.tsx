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
import { Button } from "../components/ui/Button";
import Card from "../components/ui/Card";
import { Container } from "../components/ui/Container";
import SectionHead from "../components/ui/SectionHead";
import { ClientApiError, clientApi } from "../lib/clientApi";
import { compressImage } from "../lib/compressImage";
import ReportIssueModal from "./ReportIssueModal";
import "./client-portal.css";

const PROPERTY_API = "/api/properties/available/";
const ACTIVE_TENANCY_API = "/api/tenancies/my-current/";
const ISSUES_API = "/api/maintenance/issues/my-issues/";
const CREATE_ISSUE_API = "/api/maintenance/issues/";
const INVOICES_API = "/api/invoices/my-invoices/";
const PAYMENTS_API = "/api/payments/my-payments/";
const STATEMENT_API = "/api/ledger/my-statement/";
const MAX_IMAGES = 5;

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
  deposit?: number | string;
  deposit_balance?: number | string;
  agreement_url?: string;
  lease_url?: string;
  phone?: string;
  landlord_phone?: string;
  user?: { name?: string; full_name?: string; email?: string; phone?: string };
  rent_status?: string;
  rent_paid?: boolean;
  status?: string;
  assigned_agent?: { name?: string; full_name?: string; phone?: string };
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
  image?: string | null;
  images?: Array<string | { image?: string; url?: string }>;
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
type Invoice = {
  id: number | string;
  month?: string;
  description?: string;
  amount?: number | string;
  balance?: number | string;
  status?: string;
  due_date?: string;
  paid_amount?: number | string;
};
type Payment = {
  id: number | string;
  reference?: string;
  transaction_id?: string;
  date?: string;
  created_at?: string;
  amount?: number | string;
  description?: string;
  invoice?: Invoice | number | string;
  method?: string;
  status?: string;
  receipt_url?: string;
};
type Statement = {
  tenant_receivable?: number | string;
  balance?: number | string;
  cleared?: boolean;
};
type PaymentRequest = {
  id: number | string;
  status?: string;
  message?: string;
  reference?: string;
  amount?: number | string;
  credit_amount?: number | string;
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
  { key: "confirmed", label: "Client confirmation" },
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

function amount(value: number | string | undefined) {
  const numeric = Number(value ?? 0);
  return Number.isFinite(numeric) ? numeric : 0;
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

function isRecent(date?: string) {
  if (!date) return false;
  const timestamp = new Date(date).getTime();
  return Number.isFinite(timestamp) && Date.now() - timestamp <= 7 * 86_400_000;
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
        Everything looking good? If something needs attention in your flat, you
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
  const images = propertyImages(property);
  const image = images[imageIndex % Math.max(images.length, 1)] ?? propertyImage(property);
  const location = displayLocation(property);
  const title = property.title ?? property.name ?? `${property.room_type ?? property.house_type ?? "Room"} in ${location}`;
  const rent = property.rent ?? property.rent_amount;

  return (
    <article
      className="dashboard-property-card"
      onClick={() => onOpen(property)}
    >
      <div className="dashboard-property-image-wrap">
        {image ? (
          <img className="dashboard-property-image" src={image} alt={title} loading="lazy" />
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
          <strong>KES {money(rent)}</strong>
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
  onRate,
  onAddPhotos,
}: {
  issue: MaintenanceIssue;
  onComment: (issueId: number | string, comment: string) => Promise<void>;
  onResolve: (issueId: number | string) => Promise<void>;
  onRate: (issueId: number | string, rating: number) => Promise<void>;
  onAddPhotos: (issueId: number | string, files: FileList) => Promise<void>;
}) {
  const [comment, setComment] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [actionError, setActionError] = useState("");
  const [isUploading, setIsUploading] = useState(false);
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
              {humanizeStatus(issue.status)}
            </span>
          </div>
          <p>{issue.category ?? "Other"} · {humanizeStatus(issue.priority ?? "medium")} priority</p>
        </div>
      </div>

      {issue.description && <p className="dashboard-issue-description">{issue.description}</p>}
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
        <label className="portal-add-photos">
          <Icon name="camera" size={16} />
          <span>{isUploading ? "Uploading…" : "Add photos"}</span>
          <input
            type="file"
            accept="image/*"
            multiple
            disabled={isUploading}
            onChange={async event => {
              const files = event.currentTarget.files;
              if (!files?.length) return;
              setIsUploading(true);
              setActionError("");
              try {
                await onAddPhotos(issue.id, files);
              } catch {
                setActionError("Photos could not be uploaded. Please try again.");
              } finally {
                setIsUploading(false);
                event.currentTarget.value = "";
              }
            }}
          />
        </label>
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
            Mark resolved
          </Button>
        )}
      </div>
      {step >= 4 && (
        <div className="portal-rating">
          <span>Rate the service</span>
          {[1, 2, 3, 4, 5].map(value => (
            <button
              key={value}
              type="button"
              aria-label={`Rate ${value} out of 5`}
              aria-pressed={issue.rating === value}
              onClick={() => {
                void onRate(issue.id, value).catch(() => setActionError("Your rating could not be saved."));
              }}
            >
              <Icon name="star" size={18} />
            </button>
          ))}
        </div>
      )}
    </article>
  );
}

export default function ClientDashboard() {
  const [clientName, setClientName] = useState("Client");
  const [clientEmail, setClientEmail] = useState("");
  const [properties, setProperties] = useState<Property[]>([]);
  const [tenancy, setTenancy] = useState<Tenancy | null>(null);
  const [issues, setIssues] = useState<MaintenanceIssue[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [statement, setStatement] = useState<Statement | null>(null);
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
  const [sessionError, setSessionError] = useState("");
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
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [selectedInvoiceId, setSelectedInvoiceId] = useState("");
  const [paymentAmount, setPaymentAmount] = useState("");
  const [paymentMethod, setPaymentMethod] = useState<"mpesa" | "bank_transfer">("mpesa");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [paymentRequest, setPaymentRequest] = useState<PaymentRequest | null>(null);
  const [paymentStage, setPaymentStage] = useState<"idle" | "pending" | "reconciling" | "success" | "failed">("idle");
  const [paymentError, setPaymentError] = useState("");
  const [isInitiatingPayment, setIsInitiatingPayment] = useState(false);
  const [receiptError, setReceiptError] = useState("");
  const [isDownloadingStatement, setIsDownloadingStatement] = useState(false);
  const propertyRequestId = useRef(0);
  const paymentStartedAt = useRef<number | null>(null);
  const headerSearchInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let active = true;
    clientApi
      .get<{ user: { role?: string } | null }>("/api/auth/session", {
      })
      .then(response => {
        if (!active) return;
        const user = response.data.user;
        if (!user || user.role?.toLowerCase() !== "client") {
          window.location.replace("/signin");
          return;
        }
        const identity = user as typeof user & {
          name?: string;
          full_name?: string;
          email?: string;
          phone?: string;
        };
        setClientName(identity.name ?? identity.full_name ?? "Client");
        setClientEmail(identity.email ?? "");
        if (identity.phone) setPhoneNumber(identity.phone);
        setIsCheckingSession(false);
      })
      .catch(() => {
        if (!active) return;
        setSessionError("We couldn’t verify your Hodi session. Please sign in again.");
        setIsCheckingSession(false);
      });

    return () => {
      active = false;
    };
  }, []);

  const loadProperties = useCallback(async () => {
    const requestId = ++propertyRequestId.current;
    setIsLoadingProperties(true);
    setPropertyLoadError("");
    try {
      const response = await clientApi.get<ApiPage<Property>>(PROPERTY_API, {
        params: {
          location: location === "all" ? "" : location,
          price: maxPrice,
          bedrooms: bedrooms === "all" ? "" : bedrooms === "bedsitter" ? "bedsitter" : bedrooms.replace("br", ""),
          house_type: bedrooms === "all" ? "" : bedrooms,
          amenities: amenities.join(","),
          search: propertySearch.trim(),
          page: propertyPage,
          page_size: 12,
          available: availableNow ? "true" : "",
        },
      });
      if (requestId !== propertyRequestId.current) return;
      const responseProperties = listFromResponse(response.data);
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
      const response = await clientApi.get<
        Tenancy | Tenancy[] | { results?: Tenancy[]; data?: Tenancy | Tenancy[] } | null
      >(ACTIVE_TENANCY_API);
      const payload = response.data;
      let currentTenancy: Tenancy | null = null;
      if (Array.isArray(payload)) {
        currentTenancy = payload.find(isTenancy) ?? null;
      } else if (payload && typeof payload === "object" && "results" in payload) {
        currentTenancy = payload.results?.find(isTenancy) ?? null;
      } else if (payload && typeof payload === "object" && "data" in payload) {
        const tenancyData = payload.data;
        currentTenancy = Array.isArray(tenancyData)
          ? tenancyData.find(isTenancy) ?? null
          : isTenancy(tenancyData) ? tenancyData : null;
      } else if (isTenancy(payload)) {
        currentTenancy = payload;
      }
      setTenancy(currentTenancy);
      const contactPhone = currentTenancy?.user?.phone ?? currentTenancy?.phone;
      if (contactPhone) setPhoneNumber(current => current || contactPhone);
    } catch (error) {
      if (error instanceof ClientApiError && error.status === 404) {
        setTenancy(null);
      } else {
        setTenancyError("Your tenancy details couldn’t be loaded.");
      }
    } finally {
      setIsLoadingTenancy(false);
    }
  }, []);

  const loadIssues = useCallback(async () => {
    setIsLoadingIssues(true);
    setIssueError("");
    try {
      const response = await clientApi.get<ApiList<MaintenanceIssue>>(ISSUES_API);
      setIssues(listFromResponse(response.data));
    } catch {
      setIssueError("Your reported issues couldn’t be loaded. Please try again.");
    } finally {
      setIsLoadingIssues(false);
    }
  }, []);

  const loadInvoices = useCallback(async () => {
    setIsLoadingInvoices(true);
    setBillingError("");
    try {
      const response = await clientApi.get<ApiList<Invoice>>(INVOICES_API);
      setInvoices(listFromResponse(response.data));
    } catch {
      setBillingError("Your rent invoices couldn’t be loaded. Please try again.");
    } finally {
      setIsLoadingInvoices(false);
    }
  }, []);

  const loadPayments = useCallback(async () => {
    setIsLoadingPayments(true);
    try {
      const [paymentResult, statementResult] = await Promise.allSettled([
        clientApi.get<ApiList<Payment>>(PAYMENTS_API),
        clientApi.get<Statement>(STATEMENT_API),
      ]);
      if (paymentResult.status === "fulfilled") {
        setPayments(listFromResponse(paymentResult.value.data));
      }
      if (statementResult.status === "fulfilled") {
        setStatement(statementResult.value.data);
      }
      setReceiptError(paymentResult.status === "rejected" && statementResult.status === "rejected"
        ? "Your payment history and statement couldn’t be loaded."
        : paymentResult.status === "rejected"
          ? "Your payment history couldn’t be loaded."
          : statementResult.status === "rejected"
            ? "Your account statement couldn’t be loaded."
            : "");
    } catch {
      setReceiptError("Your payment history or statement couldn’t be loaded.");
    } finally {
      setIsLoadingPayments(false);
    }
  }, []);

  useEffect(() => {
    if (isCheckingSession || sessionError) return;
    void loadProperties();
    void loadTenancy();
    void loadIssues();
    void loadInvoices();
    void loadPayments();
  }, [isCheckingSession, loadIssues, loadInvoices, loadPayments, loadProperties, loadTenancy, sessionError]);

  const locations = useMemo(
    () => [...new Set(properties.map(displayLocation).filter(item => item !== "Location not listed"))].sort(),
    [properties],
  );

  const filteredProperties = useMemo(
    () =>
      properties.filter(property => {
        const rent = Number(property.rent ?? property.rent_amount ?? 0);
        const propertyLocation = displayLocation(property);
        const matchesLocation = location === "all" || propertyLocation.toLowerCase().includes(location.toLowerCase());
        const matchesRent = !rent || rent <= maxPrice;
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
    if (tenancy?.id !== undefined) formData.set("tenancy", String(tenancy.id));
    await clientApi.post(CREATE_ISSUE_API, formData);
    setIsReportOpen(false);
    await loadIssues();
    setPageNotice("Your maintenance request has been submitted.");
  }

  async function addIssuePhotos(issueId: number | string, files: FileList) {
    if (files.length > MAX_IMAGES) throw new Error(`Choose no more than ${MAX_IMAGES} images.`);
    const formData = new FormData();
    for (const original of Array.from(files)) {
      if (!original.type.startsWith("image/")) throw new Error("Only image files can be attached.");
      formData.append("images", await compressImage(original));
    }
    await clientApi.patch(`/api/maintenance/issues/${issueId}/`, formData);
    await loadIssues();
    setPageNotice("Photos added to your maintenance request.");
  }

  async function rateIssue(issueId: number | string, rating: number) {
    await clientApi.patch(`/api/maintenance/issues/${issueId}/`, { rating });
    await loadIssues();
    setPageNotice("Thank you for rating the maintenance service.");
  }

  async function addIssueComment(issueId: number | string, comment: string) {
    setIssueActionError("");
    try {
      await clientApi.patch(
        `/api/maintenance/issues/${issueId}/`,
        { client_comment: comment },
      );
      await loadIssues();
    } catch {
      setIssueActionError("Your comment couldn’t be saved. Please try again.");
      throw new Error("Comment save failed");
    }
  }

  async function markResolved(issueId: number | string) {
    setIssueActionError("");
    try {
      await clientApi.patch(
        `/api/maintenance/issues/${issueId}/`,
        { status: "resolved" },
      );
      await loadIssues();
    } catch {
      setIssueActionError("This issue couldn’t be marked as resolved. Please try again.");
    }
  }

  function openProperty(property: Property) {
    window.location.assign(`/properties/${property.id}`);
  }

  function contactAgent(property: Property) {
    const phone = property.agent?.phone_number ?? property.agent?.phone ?? property.agent_phone;
    const email = property.agent?.email ?? property.agent_email;
    if (phone) {
      const whatsappNumber = phone.replace(/\D/g, "").replace(/^0/, "254");
      window.open(`https://wa.me/${whatsappNumber}`, "_blank", "noopener,noreferrer");
    } else if (email) {
      window.location.assign(
        `mailto:${email}?subject=${encodeURIComponent(`Room enquiry: ${property.title ?? property.name ?? "Hodi listing"}`)}`,
      );
    } else {
      setPropertyError(`Contact details for ${agentName(property)} are not available.`);
    }
  }

  function bookViewing(property: Property) {
    const phone = property.agent?.phone_number ?? property.agent?.phone ?? property.agent_phone;
    const whatsappNumber = phone?.replace(/\D/g, "").replace(/^0/, "254");
    if (!whatsappNumber) {
      setPropertyError(`Viewing contact for ${agentName(property)} is not available.`);
      return;
    }
    const title = property.title ?? property.name ?? "this room";
    const message = encodeURIComponent(`Hello, I’d like to book a viewing for ${title} on Hodi.`);
    window.open(`https://wa.me/${whatsappNumber}?text=${message}`, "_blank", "noopener,noreferrer");
  }

  function setRentAmount(value: number) {
    setPaymentAmount(String(Math.max(0, value)));
  }

  function selectInvoice(invoice: Invoice) {
    setSelectedInvoiceId(String(invoice.id));
    setPaymentAmount(String(invoice.balance !== undefined
      ? amount(invoice.balance)
      : Math.max(0, amount(invoice.amount) - amount(invoice.paid_amount))));
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
    return !["paid", "successful", "completed"].includes(status) &&
      (invoice.balance !== undefined
        ? amount(invoice.balance) > 0
        : amount(invoice.amount) > amount(invoice.paid_amount));
  });
  const outstandingTotal = outstandingInvoices.reduce(
    (total, invoice) => total + (invoice.balance !== undefined
      ? amount(invoice.balance)
      : Math.max(0, amount(invoice.amount) - amount(invoice.paid_amount))),
    0,
  );
  const selectedInvoice = invoices.find(invoice => String(invoice.id) === selectedInvoiceId) ??
    outstandingInvoices[0] ?? null;
  const selectedBalance = selectedInvoice
    ? selectedInvoice.balance !== undefined
      ? amount(selectedInvoice.balance)
      : Math.max(0, amount(selectedInvoice.amount) - amount(selectedInvoice.paid_amount))
    : 0;
  const allRentInvoicesPaid = invoices.length > 0 &&
    invoices.every(invoice => isPaymentSuccessful(invoice.status));
  const rentOverviewStatus = outstandingTotal > 0 ||
    invoices.some(invoice => normalizedStatus(invoice.status) === "overdue")
    ? "Payment due"
    : isLoadingInvoices
      ? "Loading…"
      : allRentInvoicesPaid || /paid|clear/i.test(rentStatus)
        ? "Paid"
        : invoices.length ? "Check status" : "No invoice";
  const nextInvoice = [...outstandingInvoices]
    .filter(invoice => invoice.due_date)
    .sort((first, second) => new Date(first.due_date!).getTime() - new Date(second.due_date!).getTime())[0];
  const dueInDays = daysUntil(nextInvoice?.due_date);
  const monthlyRent = tenancy?.monthly_rent ?? tenancyProperty?.rent ?? tenancyProperty?.rent_amount;
  const depositBalance = tenancy?.deposit_balance ?? tenancy?.deposit;
  const activeIssuesCount = issues.filter(issue => issueStep(issue.status) < 4).length;
  const ledgerValue = statement?.tenant_receivable ?? statement?.balance;
  const ledgerCleared = statement?.cleared === true ||
    ledgerValue !== undefined && amount(ledgerValue) <= 0;
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
  const notifications = [
    ...(dueInDays !== null && dueInDays <= 5
      ? [{ title: dueInDays < 0 ? "Rent overdue" : "Rent due soon", description: `Your next rent is ${dueInDays < 0 ? `overdue by ${Math.abs(dueInDays)} days` : dueInDays === 0 ? "due today" : `due in ${dueInDays} days`}.`, icon: "calendar" as const }]
      : []),
    ...issues.filter(issue => isRecent(issue.updated_at ?? issue.last_update)).slice(0, 3).map(issue => ({
      title: "Maintenance update",
      description: `${issue.title ?? "Your reported issue"} was updated ${formatDate(issue.updated_at ?? issue.last_update)}.`,
      icon: "wrench" as const,
    })),
    ...payments.filter(payment => isPaymentSuccessful(payment.status) && isRecent(payment.date ?? payment.created_at)).slice(0, 2).map(payment => ({
      title: "Payment confirmed",
      description: `KES ${money(payment.amount)} payment received.`,
      icon: "check" as const,
    })),
  ];
  const dueLabel = dueInDays !== null && dueInDays < 0
    ? `overdue by ${Math.abs(dueInDays)} day${Math.abs(dueInDays) === 1 ? "" : "s"}`
    : dueInDays === 0
      ? "today"
      : `in ${dueInDays} day${dueInDays === 1 ? "" : "s"}`;
  const issueCounts = {
    all: issues.length,
    open: issues.filter(issue => statusMatchesFilter(issue, "open")).length,
    "in-progress": issues.filter(issue => statusMatchesFilter(issue, "in-progress")).length,
    resolved: issues.filter(issue => statusMatchesFilter(issue, "resolved")).length,
  };

  function contactCurrentAgent() {
    const phone = tenancy?.landlord_phone ??
      tenancy?.landlord?.phone ??
      tenancy?.phone ??
      tenancyProperty?.agent?.phone_number ??
      tenancyProperty?.agent?.phone;
    const email = tenancy?.landlord?.email ?? tenancyProperty?.agent?.email;
    if (phone) {
      const whatsappNumber = phone.replace(/\D/g, "").replace(/^0/, "254");
      window.open(`https://wa.me/${whatsappNumber}`, "_blank", "noopener,noreferrer");
    } else if (email) {
      window.location.assign(`mailto:${email}`);
    } else {
      setPageNotice("Your agent’s contact details are not available yet.");
    }
  }

  const selectedInvoiceIdFromData = selectedInvoice?.id;
  useEffect(() => {
    if (selectedInvoiceIdFromData === undefined) return;
    setSelectedInvoiceId(String(selectedInvoiceIdFromData));
    setPaymentAmount(String(selectedBalance));
  }, [selectedInvoiceIdFromData, selectedBalance]);

  useEffect(() => {
    if (!pageNotice) return;
    const timeout = window.setTimeout(() => setPageNotice(""), 4500);
    return () => window.clearTimeout(timeout);
  }, [pageNotice]);

  useEffect(() => {
    const sections = ["overview", "my-flat", "pay-rent", "maintenance", "browse-rooms", "receipts", "profile"]
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
  }, [isCheckingSession, sessionError]);

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
        setPaymentError("We haven’t received a final M-Pesa confirmation yet. Your payment is being reconciled; check your receipts shortly.");
        return;
      }
      if (elapsed >= 120_000 && paymentStage !== "reconciling") {
        setPaymentStage("reconciling");
        setPaymentError("This payment is taking longer than usual. We’re safely checking its status with M-Pesa.");
      }
      try {
        const response = await clientApi.get<PaymentRequest | { payment?: PaymentRequest }>(
          `/api/payments/${paymentRequest.id}/status/`,
        );
        const current = "payment" in response.data && response.data.payment
          ? response.data.payment
          : response.data as PaymentRequest;
        if (cancelled) return;
        setPaymentRequest(current);
        if (isPaymentSuccessful(current.status)) {
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
        if (isPaymentFailed(current.status)) {
          setPaymentStage("failed");
          setPaymentError(current.message ?? "The payment was not completed. Please try again.");
          return;
        }
        if (["unknown", "reconciling", "timeout", "timedout"].includes(normalizedStatus(current.status))) {
          setPaymentStage("reconciling");
          setPaymentError(current.message ?? "M-Pesa hasn’t returned a final result yet. We’re checking your payment safely.");
        }
      } catch {
        if (cancelled) return;
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
    const parsedAmount = Number(paymentAmount);
    const normalizedPhone = phoneNumber.replace(/[^\d+]/g, "");
    if (!selectedInvoice) {
      setPaymentError("There are no outstanding invoices to pay.");
      return;
    }
    if (!Number.isFinite(parsedAmount) || parsedAmount <= 0) {
      setPaymentError("Enter a valid payment amount.");
      return;
    }
    if (paymentMethod === "mpesa" && !/^(?:\+?254|0)?[17]\d{8}$/.test(normalizedPhone)) {
      setPaymentError("Enter a valid Kenyan M-Pesa phone number.");
      return;
    }
    setIsInitiatingPayment(true);
    try {
      const response = await clientApi.post<PaymentRequest | { payment?: PaymentRequest }>(
        "/api/payments/initiate/",
        {
          invoice_id: selectedInvoice.id,
          amount: parsedAmount,
          phone: normalizedPhone,
          method: paymentMethod,
        },
      );
      const request = "payment" in response.data && response.data.payment
        ? response.data.payment
        : response.data as PaymentRequest;
      if (request.id === undefined || request.id === null) {
        throw new Error("The payment service did not return a payment reference.");
      }
      setPaymentRequest(request);
      paymentStartedAt.current = Date.now();
      setPaymentStage(
        isPaymentSuccessful(request.status)
          ? "success"
          : ["unknown", "reconciling", "timeout", "timedout"].includes(normalizedStatus(request.status))
            ? "reconciling"
            : "pending",
      );
      if (isPaymentSuccessful(request.status)) {
        void loadInvoices();
        void loadPayments();
      }
      if (parsedAmount > outstandingTotal) {
        setPageNotice(`KES ${money(parsedAmount - outstandingTotal)} will be credited to your next rent.`);
      }
    } catch (error) {
      setPaymentError(
        error instanceof ClientApiError
          ? error.message
          : error instanceof Error ? error.message : "We couldn’t start your payment. Please try again.",
      );
    } finally {
      setIsInitiatingPayment(false);
    }
  }

  async function downloadAnnualStatement() {
    setIsDownloadingStatement(true);
    setReceiptError("");
    try {
      const response = await clientApi.get<Blob>(STATEMENT_API, {
        params: { format: "pdf", period: "annual" },
        responseType: "blob",
      });
      const url = URL.createObjectURL(response.data);
      downloadFromUrl(url, "hodi-annual-statement.pdf");
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      setReceiptError("The annual statement PDF isn’t available right now.");
    } finally {
      setIsDownloadingStatement(false);
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
      await clientApi.post("/api/auth/signout");
    } catch {
      setPageNotice("We couldn’t confirm sign out with the server. Redirecting you to sign in.");
    } finally {
      window.location.assign("/signin");
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

  if (sessionError) {
    return (
      <main className="client-dashboard dashboard-auth-check">
        <p className="dashboard-inline-error" role="alert">{sessionError}</p>
        <Button type="button" onClick={() => window.location.assign("/signin")}>
          Go to sign in
        </Button>
      </main>
    );
  }

  return (
    <div className={`client-dashboard portal-layout ${sidebarCollapsed ? "sidebar-collapsed" : ""} ${mobileMenuOpen ? "mobile-menu-open" : ""} ${mobileSearchOpen ? "mobile-search-open" : ""}`}>
      <aside className="portal-sidebar" aria-label="Client navigation">
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
            ["my-flat", "My Flat", "home"],
            ["pay-rent", "Pay Rent", "wallet"],
            ["maintenance", "Maintenance", "wrench"],
            ["browse-rooms", "Browse Rooms", "building"],
            ["receipts", "Receipts", "receipt"],
            ["profile", "Profile", "user"],
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
        </nav>
        <div className="portal-sidebar-bottom">
          {!sidebarCollapsed && (
            <div className="portal-sidebar-help">
              <span><Icon name="shield" size={18} /></span>
              <strong>Talk to your agent</strong>
              <small>Get help with your current home.</small>
              <button type="button" onClick={contactCurrentAgent}>Contact agent <Icon name="arrow" size={14} /></button>
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
              <p>CLIENT PORTAL</p>
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
                      setPropertySearch(headerSearch);
                      setPropertyPage(1);
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
            <div className="portal-notification-wrap">
              <button
                type="button"
                className="portal-notification-button"
                aria-label={`Notifications, ${notifications.length} updates`}
                aria-expanded={notificationsOpen}
                onClick={() => setNotificationsOpen(value => !value)}
              >
                <Icon name="bell" />
                {notifications.length > 0 && <span className="portal-notification-count">{notifications.length}</span>}
              </button>
              {notificationsOpen && (
                <div className="portal-notification-popover">
                  <div className="portal-notification-heading">
                    <strong>Notifications</strong><span>{notifications.length} new</span>
                  </div>
                  {notifications.length ? notifications.map((notification, index) => (
                    <button
                      type="button"
                      key={`${notification.title}-${index}`}
                      onClick={() => {
                        setNotificationsOpen(false);
                        scrollToSection(notification.icon === "calendar" || notification.icon === "check" ? "pay-rent" : "maintenance");
                      }}
                    >
                      <span><Icon name={notification.icon} size={17} /></span>
                      <span><strong>{notification.title}</strong><small>{notification.description}</small></span>
                    </button>
                  )) : <p>You’re all caught up. New rent and maintenance updates will appear here.</p>}
                </div>
              )}
            </div>
            <span className="portal-current-flat"><Icon name="home" size={15} /> Flat {flatNumber}</span>
            <button className="portal-profile-chip" type="button" onClick={() => scrollToSection("profile")}>
              <span className="dashboard-account-avatar">{clientName.slice(0, 1).toUpperCase()}</span>
              <span>{clientName}</span>
              <Icon name="chevron" size={15} />
            </button>
          </div>
        </header>

      <Container className="dashboard-content portal-content">
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
            <SummaryCard
              label="Rent status"
              value={rentOverviewStatus === "Paid" ? "All clear" : rentOverviewStatus}
              caption={outstandingTotal > 0 ? `KES ${money(outstandingTotal)} outstanding` : rentOverviewStatus === "Paid" ? "Your account is up to date" : "Check your latest rent balance"}
              icon="wallet"
              tone={outstandingTotal > 0 || rentOverviewStatus === "Payment due" ? "amber" : rentOverviewStatus === "Paid" ? "green" : "slate"}
            />
            <SummaryCard
              label="Next due date"
              value={nextInvoice?.due_date ? formatDate(nextInvoice.due_date) : "Not scheduled"}
              caption={dueInDays !== null ? dueInDays < 0 ? `Overdue by ${Math.abs(dueInDays)} days` : dueInDays === 0 ? "Due today" : `Due in ${dueInDays} days` : "No upcoming payment"}
              icon="calendar"
              tone={dueInDays !== null && dueInDays <= 5 ? "red" : "blue"}
            />
            <SummaryCard
              label="Active issues"
              value={String(activeIssuesCount)}
              caption={activeIssuesCount === 1 ? "Request being looked after" : "Requests being looked after"}
              icon="wrench"
              tone="slate"
            />
            <SummaryCard
              label="Deposit balance"
              value={depositBalance !== undefined ? `KES ${money(depositBalance)}` : "Not available"}
              caption="Held against your tenancy"
              icon="shield"
              tone="green"
            />
          </div>
          {dueInDays !== null && dueInDays <= 5 && outstandingTotal > 0 && (
            <div className="portal-due-alert">
              <span className="portal-due-icon"><Icon name="clock" size={20} /></span>
              <div><strong>Your rent of KES {money(outstandingTotal)} is {dueLabel}.</strong><small>Pay securely with M-Pesa and keep your tenancy in good standing.</small></div>
              <Button type="button" onClick={() => scrollToSection("pay-rent")}>Pay now <Icon name="arrow" size={16} /></Button>
            </div>
          )}
          <div className="portal-quick-actions">
            <span>Quick actions</span>
            <button type="button" onClick={() => scrollToSection("pay-rent")}><Icon name="wallet" size={17} />Pay rent</button>
            <button type="button" onClick={() => tenancy && setIsReportOpen(true)} disabled={!tenancy}><Icon name="wrench" size={17} />Report an issue</button>
            <button type="button" onClick={contactCurrentAgent}><Icon name="message" size={17} />Contact agent</button>
            <button type="button" onClick={() => scrollToSection("my-flat")}><Icon name="receipt" size={17} />View lease</button>
          </div>
        </section>

        <section className="dashboard-section portal-section" id="my-flat" aria-labelledby="my-flat-title">
          <SectionHead
            eyebrow="Your tenancy"
            title="My Flat"
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
                <div className={`dashboard-rent-status ${/paid|clear/i.test(rentStatus) && outstandingTotal <= 0 ? "is-paid" : ""}`}><span className="dashboard-rent-status-dot" /><span>Rent status</span><strong>{outstandingTotal > 0 ? "Due" : rentStatus}</strong></div>
              </div>
              <div className="portal-tenancy-facts">
                <div><small>MONTHLY RENT</small><strong>KES {money(monthlyRent)}</strong></div>
                <div><small>SECURITY DEPOSIT</small><strong>KES {money(depositBalance)}</strong></div>
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
            <SectionHead eyebrow="Secure rent payments" title="Pay Rent" titleId="pay-rent-title" description="Make a payment in a few taps. M-Pesa STK Push is the fastest way." />
            <span className="portal-mpesa-tag"><Icon name="shield" size={14} /> SECURE CHECKOUT</span>
          </div>
          {billingError && <div className="dashboard-alert" role="alert">{billingError}<Button type="button" variant="ghost" onClick={() => void loadInvoices()}>Try again</Button></div>}
          <div className="portal-rent-layout">
            <div className="portal-invoice-panel">
              <div className="portal-panel-heading"><div><small>YOUR RENT LEDGER</small><h3>Outstanding balance</h3></div><span className={outstandingTotal > 0 ? "portal-amount-due" : "portal-amount-clear"}>KES {money(outstandingTotal)}</span></div>
              {isLoadingInvoices ? <div className="portal-inline-loading"><span className="dashboard-loading-spinner" />Loading your invoices…</div> : invoices.length ? (
                <div className="portal-invoice-list">{invoices.map(invoice => {
                  const balance = invoice.balance !== undefined ? amount(invoice.balance) : Math.max(0, amount(invoice.amount) - amount(invoice.paid_amount));
                  const active = String(invoice.id) === (selectedInvoice?.id === undefined ? "" : String(selectedInvoice.id));
                  return <button type="button" key={invoice.id} className={`portal-invoice-row ${active ? "is-selected" : ""}`} onClick={() => selectInvoice(invoice)}>
                    <span className="portal-invoice-select">{active && <span />}</span>
                    <span className="portal-invoice-name"><strong>{invoice.month ?? invoice.description ?? "Rent invoice"}</strong><small>Due {formatDate(invoice.due_date)}</small></span>
                    <span className={`portal-invoice-status status-${normalizedStatus(invoice.status) || "pending"}`}>{humanizeStatus(invoice.status ?? "pending")}</span>
                    <span className="portal-invoice-balance"><strong>KES {money(balance)}</strong><small>of {money(invoice.amount)}</small></span>
                  </button>;
                })}</div>
              ) : <div className="portal-empty-inline"><Icon name="check" size={20} /><strong>{tenancy ? "No rent invoices yet" : "Add a tenancy to view rent"}</strong><span>When your next invoice is issued, it will show here.</span></div>}
              {outstandingInvoices.length > 0 && <p className="portal-ledger-note"><Icon name="shield" size={14} />Your rent balance is kept against your tenant ledger.</p>}
            </div>
            <form className="portal-payment-card" onSubmit={initiatePayment}>
              <div className="portal-payment-card-heading"><span className="portal-payment-icon"><Icon name="wallet" size={19} /></span><div><small>MAKE A PAYMENT</small><strong>{selectedInvoice?.month ?? selectedInvoice?.description ?? "Select an invoice"}</strong></div></div>
              <label className="portal-payment-amount">Amount to pay (KES)<span className="portal-currency-input"><span>KES</span><input inputMode="numeric" type="number" min="1" step="1" max="99999999" value={paymentAmount} onChange={event => setPaymentAmount(event.target.value)} disabled={!selectedInvoice} required /></span></label>
              <div className="portal-amount-chips">
                <button type="button" disabled={!selectedInvoice} onClick={() => setRentAmount(selectedBalance)}>Full balance <strong>KES {money(selectedBalance)}</strong></button>
                <button type="button" disabled={!selectedInvoice} onClick={() => setRentAmount(Math.max(1, Math.round(selectedBalance / 2)))}>Pay half <strong>KES {money(Math.round(selectedBalance / 2))}</strong></button>
              </div>
              {Number(paymentAmount) > outstandingTotal && outstandingTotal > 0 && <p className="portal-credit-note"><Icon name="check" size={15} />KES {money(Number(paymentAmount) - outstandingTotal)} will be credited to next month.</p>}
              <div className="portal-method-select">
                <span>Payment method</span>
                <label className={paymentMethod === "mpesa" ? "is-selected" : ""}><input type="radio" name="method" value="mpesa" checked={paymentMethod === "mpesa"} onChange={() => setPaymentMethod("mpesa")} /><span className="portal-method-logo">M</span><span><strong>M-Pesa</strong><small>Instant · STK push</small></span><i /></label>
                <label className={paymentMethod === "bank_transfer" ? "is-selected" : ""}><input type="radio" name="method" value="bank_transfer" checked={paymentMethod === "bank_transfer"} onChange={() => setPaymentMethod("bank_transfer")} /><Icon name="building" size={20} /><span><strong>Bank transfer</strong><small>Use your payment reference</small></span><i /></label>
              </div>
              {paymentMethod === "mpesa" && <label className="portal-phone-field">M-Pesa phone number<input type="tel" inputMode="tel" autoComplete="tel" placeholder="07XX XXX XXX" value={phoneNumber} onChange={event => setPhoneNumber(event.target.value)} required /><small>We’ll send a secure payment request to this phone.</small></label>}
              {paymentMethod === "bank_transfer" && <p className="portal-bank-note">Your invoice reference will be attached to this payment. Transfer instructions will be shown after you continue.</p>}
              {paymentError && <p className="dashboard-form-error" role="alert">{paymentError}</p>}
              <Button type="submit" disabled={!selectedInvoice || !Number(paymentAmount) || isInitiatingPayment} className="portal-pay-button">{isInitiatingPayment ? "Starting secure payment…" : `Pay KES ${money(paymentAmount)}`}<Icon name="arrow" size={17} /></Button>
              <p className="portal-secure-note"><Icon name="shield" size={13} />Encrypted payment · Your details stay protected</p>
            </form>
          </div>
        </section>

        <section className="dashboard-section dashboard-rooms portal-section" id="browse-rooms" aria-labelledby="available-rooms-title">
          <SectionHead
            eyebrow="Find your next place"
            title="Available Rooms Near You"
            titleId="available-rooms-title"
            description={`${propertyCount || filteredProperties.length} ${propertyCount === 1 ? "room" : "rooms"} to explore across Kenya`}
          />

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
        </section>

        <section className="dashboard-section dashboard-maintenance portal-section" id="maintenance" aria-labelledby="maintenance-title">
          <SectionHead
            eyebrow="Your home, cared for"
            title="My Current Flat - Maintenance & Issues"
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
                <h3>No active flat linked to your account</h3>
                <p>Once a tenancy is linked, you’ll be able to report and track maintenance requests here.</p>
              </div>
              {tenancyError && <span className="dashboard-inline-error">{tenancyError}</span>}
            </div>
          )}

          {tenancyError && tenancy && <p className="dashboard-inline-error">{tenancyError}</p>}
          {issueActionError && <p className="dashboard-inline-error" role="alert">{issueActionError}</p>}

          <div className="dashboard-issue-section">
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

            {issueError && (
              <div className="dashboard-alert" role="alert">
                {issueError}
                <Button type="button" variant="ghost" onClick={() => void loadIssues()}>Try again</Button>
              </div>
            )}

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
            ) : filteredIssues.length ? (
              <div className="dashboard-issue-list">
                {filteredIssues.map(issue => (
                  <IssueCard
                    key={issue.id}
                    issue={issue}
                    onComment={addIssueComment}
                    onResolve={markResolved}
                    onRate={rateIssue}
                    onAddPhotos={addIssuePhotos}
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
          </div>
        </section>

        <section className="dashboard-section portal-section" id="receipts" aria-labelledby="receipts-title">
          <div className="portal-receipts-heading">
            <SectionHead eyebrow="Your payment history" title="Receipts & statement" titleId="receipts-title" description="Every rent payment, in one secure place." />
            <Button type="button" variant="secondary" onClick={() => void downloadAnnualStatement()} disabled={isDownloadingStatement}>
              <Icon name="download" size={16} />{isDownloadingStatement ? "Preparing…" : "Annual statement"}
            </Button>
          </div>
          <div className={`portal-balance-banner ${ledgerCleared ? "is-clear" : ""}`}>
            <span><Icon name="shield" size={20} /></span>
            <div><small>DOUBLE-ENTRY TENANT LEDGER</small><strong>Your account: Tenant Receivable KES {ledgerValue === undefined ? isLoadingPayments ? "Checking…" : "Not available" : money(ledgerValue)}</strong></div>
            <b>{ledgerCleared ? "You are cleared" : ledgerValue === undefined ? "Ledger unavailable" : "Balance outstanding"}</b>
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
                      <td><strong>KES {money(payment.amount)}</strong></td>
                      <td><span className={`portal-payment-status ${isPaymentSuccessful(payment.status) ? "is-success" : isPaymentFailed(payment.status) ? "is-failed" : "is-pending"}`}>{humanizeStatus(payment.status ?? "pending")}</span></td>
                      <td><button className="portal-receipt-button" type="button" onClick={() => void downloadReceipt(payment)} aria-label={`Download receipt ${payment.reference ?? payment.id}`}><Icon name="download" size={16} /></button></td>
                    </tr>;
                  }) : <tr><td colSpan={7}><div className="portal-table-empty"><Icon name="receipt" size={22} /><strong>No payments yet</strong><span>Your completed rent receipts will appear here.</span></div></td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        <section className="dashboard-section portal-section portal-profile-section" id="profile" aria-labelledby="profile-title">
          <SectionHead eyebrow="Your account" title="Profile & support" titleId="profile-title" description="Manage your contact details and find help when you need it." />
          <div className="portal-profile-card">
            <span className="portal-profile-large">{clientName.slice(0, 1).toUpperCase()}</span>
            <div><small>CLIENT ACCOUNT</small><strong>{clientName}</strong><span>{clientEmail || "Email not available"}</span></div>
            <button type="button" className="portal-contact-button" onClick={contactCurrentAgent}><Icon name="message" size={17} />Contact agent</button>
            <Button type="button" variant="ghost" onClick={() => void signOut()}><Icon name="logout" size={16} />Log out</Button>
          </div>
        </section>
      </Container>
      </div>

      <nav className="portal-bottom-nav" aria-label="Mobile navigation">
        {([
          ["overview", "Home", "grid"],
          ["pay-rent", "Pay", "wallet"],
          ["maintenance", "Issues", "wrench"],
          ["browse-rooms", "Rooms", "building"],
          ["receipts", "Receipts", "receipt"],
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
                setPaymentRequest(null);
                setPaymentError("");
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
                <h2 id="payment-status-title">We’re confirming your payment</h2>
                <p>{paymentError || "Your request is still being reconciled. You will not be charged again while we check with M-Pesa."}</p>
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
                <p>Your payment of <strong>KES {money(paymentRequest.amount ?? paymentAmount)}</strong> has been received.</p>
                <div className="portal-success-receipt"><span>Receipt reference</span><strong>{paymentRequest.reference ?? paymentRequest.id}</strong></div>
                <Button type="button" onClick={() => {
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
