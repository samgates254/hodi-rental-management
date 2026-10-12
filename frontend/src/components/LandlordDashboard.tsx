"use client";

import {
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import Link from "next/link";
import { Logo } from "@/components/layout/Logo";
import { PropertyBanner } from "@/components/ui/PropertyBanner";
import AuditLogPanel from "@/components/ops/AuditLogPanel";
import BillingWorkspace from "@/components/ops/BillingWorkspace";
import MaintenanceRequestsPanel from "@/components/ops/MaintenanceRequestsPanel";
import MarketplaceManager from "@/components/marketplace/MarketplaceManager";
import CommerceWorkspace from "@/components/marketplace/CommerceWorkspace";
import NotificationBell from "@/components/ops/NotificationBell";
import SubscriptionPanel from "@/components/SubscriptionPanel";
import UtilitiesWorkspace from "@/components/utilities/UtilitiesWorkspace";
import ThemeToggle from "@/components/theme/ThemeToggle";
import { AUTH_API_PATHS } from "@/lib/clientApi";
import { ORGANIZATION_STAFF_ROLES, staffLoginKindForRole } from "@/lib/organizationRoles";
import "./landlord-dashboard.css";
import "@/components/ops/ops.css";

const API_ROOT = "/api/v1";
const TOKEN_KEY = "hodi_api_token";

type Identifier = number | string;
type ApiList<T> = T[] | { results?: T[]; data?: T[] };

type Organization = {
  id: Identifier;
  name: string;
  slug: string;
  is_active: boolean;
};

type Property = {
  id: Identifier;
  organization: Identifier;
  name: string;
  address: string;
  city: string;
  country: string;
  is_active: boolean;
};

type Building = {
  id: Identifier;
  property: Identifier;
  name: string;
};

type Unit = {
  id: Identifier;
  building: Identifier;
  name: string;
  status: "AVAILABLE" | "OCCUPIED" | "MAINTENANCE" | "INACTIVE" | string;
  bedrooms: number;
};

type Tenant = {
  id: Identifier;
  organization: Identifier;
  first_name: string;
  last_name: string;
  full_name: string;
  phone_number: string;
  email: string;
  is_active: boolean;
};

type Lease = {
  id: Identifier;
  tenant: Identifier;
  unit: Identifier;
  reference: string;
  start_date: string;
  end_date: string | null;
  monthly_rent_minor: number;
  security_deposit_minor: number;
  status: "DRAFT" | "ACTIVE" | "TERMINATED" | "EXPIRED" | string;
};

type OrganizationMembership = {
  organization_id: Identifier;
  organization_name: string;
  role: string;
};

type TeamMember = {
  id: Identifier;
  organization: Identifier;
  user: Identifier;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  phone_number: string;
  role: "PROPERTY_MANAGER" | "CARETAKER" | string;
  is_active: boolean;
  created_at: string;
};

type DashboardData = {
  organizations: Organization[];
  properties: Property[];
  buildings: Building[];
  units: Unit[];
  tenants: Tenant[];
  leases: Lease[];
};

const EMPTY_DATA: DashboardData = {
  organizations: [],
  properties: [],
  buildings: [],
  units: [],
  tenants: [],
  leases: [],
};

const PREVIEW_DATA: DashboardData = {
  organizations: [{ id: 1, name: "Hodi Demo Properties", slug: "hodi-demo", is_active: true }],
  properties: [
    {
      id: 1,
      organization: 1,
      name: "Acacia Heights",
      address: "12 Ngong Road",
      city: "Nairobi",
      country: "Kenya",
      is_active: true,
    },
    {
      id: 2,
      organization: 1,
      name: "Riverside Apartments",
      address: "8 Riverside Drive",
      city: "Nairobi",
      country: "Kenya",
      is_active: true,
    },
  ],
  buildings: [
    { id: 1, property: 1, name: "Acacia Heights" },
    { id: 2, property: 2, name: "Riverside Apartments" },
  ],
  units: [
    { id: 1, building: 1, name: "A-204", status: "OCCUPIED", bedrooms: 2 },
    { id: 2, building: 1, name: "A-305", status: "AVAILABLE", bedrooms: 1 },
    { id: 3, building: 2, name: "B-102", status: "OCCUPIED", bedrooms: 3 },
  ],
  tenants: [
    {
      id: 1,
      organization: 1,
      first_name: "Amina",
      last_name: "Njoroge",
      full_name: "Amina Njoroge",
      phone_number: "+254 712 345 678",
      email: "amina@example.com",
      is_active: true,
    },
    {
      id: 2,
      organization: 1,
      first_name: "Brian",
      last_name: "Otieno",
      full_name: "Brian Otieno",
      phone_number: "+254 723 456 789",
      email: "brian@example.com",
      is_active: true,
    },
  ],
  leases: [
    {
      id: 1,
      tenant: 1,
      unit: 1,
      reference: "HOD-2026-014",
      start_date: "2026-01-01",
      end_date: "2026-12-31",
      monthly_rent_minor: 6500000,
      security_deposit_minor: 6500000,
      status: "ACTIVE",
    },
    {
      id: 2,
      tenant: 2,
      unit: 3,
      reference: "HOD-2026-021",
      start_date: "2026-03-01",
      end_date: null,
      monthly_rent_minor: 9200000,
      security_deposit_minor: 9200000,
      status: "ACTIVE",
    },
  ],
};

class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

function listFromResponse<T>(data: ApiList<T>): T[] {
  if (Array.isArray(data)) return data;
  return data.results ?? data.data ?? [];
}

function errorMessage(payload: unknown, fallback: string) {
  if (typeof payload === "string") {
    const text = payload.trim();
    if (text && !/<!DOCTYPE|Internal Server Error/i.test(text)) return text;
    return fallback;
  }
  if (payload && typeof payload === "object") {
    const details = payload as Record<string, unknown>;
    if (typeof details.detail === "string" && details.detail.trim()) return details.detail;
    if (Array.isArray(details.detail) && details.detail.length) {
      return details.detail.map(String).join(" ");
    }
    if (typeof details.error === "string" && details.error.trim()) return details.error;
    if (Array.isArray(details.non_field_errors) && details.non_field_errors.length) {
      return details.non_field_errors.map(String).join(" ");
    }
    const parts: string[] = [];
    for (const [key, value] of Object.entries(details)) {
      if (key === "detail" || key === "non_field_errors") continue;
      if (Array.isArray(value) && value.length) {
        parts.push(`${key}: ${value.map(String).join(" ")}`);
      } else if (typeof value === "string" && value.trim()) {
        parts.push(`${key}: ${value}`);
      }
    }
    if (parts.length) return parts.join(" · ");
  }
  return fallback;
}

async function apiRequest<T>(
  path: string,
  token?: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Token ${token}`);
  if (options.body) headers.set("Content-Type", "application/json");

  const response = await fetch(`${API_ROOT}${path}`, {
    ...options,
    headers,
    cache: "no-store",
  });

  if (!response.ok) {
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    throw new ApiError(
      errorMessage(payload, `The request failed (${response.status}).`),
      response.status,
    );
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function formatMoney(minorUnits: number) {
  const amount = Number(minorUnits);
  return Number.isFinite(amount)
    ? new Intl.NumberFormat("en-KE", {
        style: "currency",
        currency: "KES",
        maximumFractionDigits: 2,
      }).format(amount / 100)
    : "KES 0";
}

function formatDate(value: string | null) {
  if (!value) return "No end date";
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("en-KE", {
        day: "numeric",
        month: "short",
        year: "numeric",
      }).format(date);
}

function displayStatus(value: string) {
  return value.toLowerCase().replace(/[_-]+/g, " ").replace(/\b\w/g, letter => letter.toUpperCase());
}

function Icon({ name }: { name: "overview" | "building" | "people" | "lease" | "plus" | "logout" | "refresh" }) {
  const paths = {
    overview: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
    building: <><rect x="4" y="3" width="16" height="18" rx="1" /><path d="M9 21v-4h6v4M8 7h1m6 0h1M8 11h1m6 0h1" /></>,
    people: <><circle cx="9" cy="8" r="3" /><path d="M3 20a6 6 0 0 1 12 0m2-9a3 3 0 1 0-1-5.8M18 14a5 5 0 0 1 3 4.6" /></>,
    lease: <><path d="M6 3h9l4 4v14H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" /><path d="M14 3v5h5M8 13h8M8 17h8" /></>,
    plus: <><path d="M12 5v14M5 12h14" /></>,
    logout: <><path d="M10 17l5-5-5-5m5 5H3" /><path d="M12 3h6a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-6" /></>,
    refresh: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M5.6 9a7 7 0 0 1 11.6-2L20 12M4 12l2.8 5A7 7 0 0 0 18.4 15" /></>,
  };
  return (
    <svg
      aria-hidden="true"
      width="19"
      height="19"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name]}
    </svg>
  );
}

function LoginForm({
  error,
  isSubmitting,
  onSubmit,
}: {
  error: string;
  isSubmitting: boolean;
  onSubmit: (username: string, password: string) => Promise<void>;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSubmit(username.trim(), password);
  }

  return (
    <main className="landlord-login">
      <Logo size={40} className="landlord-login-logo" wordmarkClassName="text-charcoal" />
      <section className="landlord-login-card">
        <span className="landlord-eyebrow">PROPERTY OPERATIONS</span>
        <h1>Welcome back</h1>
        <p>Sign in with your Hodi account to manage your properties and tenancies.</p>
        <form onSubmit={submit} className="landlord-form">
          <label>
            Username
            <input
              autoComplete="username"
              required
              value={username}
              onChange={event => setUsername(event.target.value)}
            />
          </label>
          <label>
            Password
            <input
              autoComplete="current-password"
              type="password"
              required
              value={password}
              onChange={event => setPassword(event.target.value)}
            />
          </label>
          {error && <p className="landlord-error" role="alert">{error}</p>}
          <button className="landlord-button landlord-button--primary" disabled={isSubmitting}>
            {isSubmitting ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="landlord-login-note">Owners, property managers, and accountants sign in here. Caretakers use caretaker access.</p>
      </section>
    </main>
  );
}

export default function LandlordDashboard() {
  const [token, setToken] = useState("");
  const [data, setData] = useState<DashboardData>(EMPTY_DATA);
  const [hasLoadedDashboard, setHasLoadedDashboard] = useState(false);
  const [memberships, setMemberships] = useState<OrganizationMembership[]>([]);
  const [selectedOrganizationId, setSelectedOrganizationId] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSigningIn, setIsSigningIn] = useState(false);
  const [pageError, setPageError] = useState("");
  const [notice, setNotice] = useState("");
  const [organizationFormOpen, setOrganizationFormOpen] = useState(false);
  const [propertyFormOpen, setPropertyFormOpen] = useState(false);
  const [buildingFormOpen, setBuildingFormOpen] = useState(false);
  const [unitFormOpen, setUnitFormOpen] = useState(false);
  const [tenantFormOpen, setTenantFormOpen] = useState(false);
  const [leaseFormOpen, setLeaseFormOpen] = useState(false);
  const [teamMembers, setTeamMembers] = useState<TeamMember[]>([]);
  const [isLoadingTeam, setIsLoadingTeam] = useState(false);
  const [teamError, setTeamError] = useState("");
  const [teamFormOpen, setTeamFormOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [previewMode, setPreviewMode] = useState(false);
  const [accountType, setAccountType] = useState("");
  const [leaseAction, setLeaseAction] = useState<null | { id: Identifier; reference: string; mode: "terminate" | "expire" }>(null);
  const [leaseEndDate, setLeaseEndDate] = useState("");
  const [leaseReason, setLeaseReason] = useState("");

  const loadDashboard = useCallback(async (authToken: string) => {
    setIsLoading(true);
    setPageError("");
    try {
      const [organizations, properties, buildings, units, tenants, leases] = await Promise.all([
        apiRequest<ApiList<Organization>>("/organizations/", authToken),
        apiRequest<ApiList<Property>>("/properties/", authToken),
        apiRequest<ApiList<Building>>("/properties/buildings/", authToken),
        apiRequest<ApiList<Unit>>("/properties/units/", authToken),
        apiRequest<ApiList<Tenant>>("/tenants/", authToken),
        apiRequest<ApiList<Lease>>("/leases/", authToken),
      ]);
      const nextData = {
        organizations: listFromResponse(organizations),
        properties: listFromResponse(properties),
        buildings: listFromResponse(buildings),
        units: listFromResponse(units),
        tenants: listFromResponse(tenants),
        leases: listFromResponse(leases),
      };
      setData(nextData);
      setHasLoadedDashboard(true);
      setSelectedOrganizationId(current =>
        nextData.organizations.some(org => String(org.id) === current)
          ? current
          : String(nextData.organizations[0]?.id ?? ""),
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : "Your dashboard couldn’t be loaded.";
      setPageError(message);
      if (error instanceof ApiError && error.status === 401) {
        sessionStorage.removeItem(TOKEN_KEY);
        setToken("");
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("preview") === "1") {
      setPreviewMode(true);
      setData(PREVIEW_DATA);
      setHasLoadedDashboard(true);
      setMemberships([{ organization_id: 1, organization_name: "Hodi Demo Properties", role: "OWNER" }]);
      setSelectedOrganizationId(String(PREVIEW_DATA.organizations[0].id));
      setToken("preview");
      return;
    }
    const savedToken = sessionStorage.getItem(TOKEN_KEY);
    if (!savedToken) {
      window.location.replace("/signin?type=landlord");
      return;
    }
    setAccountType(sessionStorage.getItem("hodi_account_type") ?? "");
    try {
      const savedMemberships: unknown = JSON.parse(sessionStorage.getItem("hodi_memberships") ?? "[]");
      setMemberships(Array.isArray(savedMemberships) ? savedMemberships as OrganizationMembership[] : []);
    } catch {
      setMemberships([]);
    }
    setToken(savedToken);
    void loadDashboard(savedToken);
  }, [loadDashboard]);

  const orgRole = memberships.find(
    membership => String(membership.organization_id) === selectedOrganizationId,
  )?.role ?? "";
  const isOwner = previewMode || orgRole === "OWNER" || (!orgRole && accountType === "OWNER");
  const isManager = orgRole === "PROPERTY_MANAGER";
  const isAccountant = !previewMode && orgRole === "ACCOUNTANT";
  const showPortfolio = !isAccountant;
  const canManageTeam = isOwner;
  const canWritePortfolio = isOwner || isManager;
  const canReadBilling = isOwner || isManager || isAccountant;
  const canReadUtilities = isOwner || isManager || isAccountant;
  const canWriteLedger = (isOwner || isAccountant) && !previewMode;
  const canWriteRentLog = (isOwner || isManager || isAccountant) && !previewMode;
  const canMaintenance = isOwner || isManager;
  const canAudit = isOwner || isManager || isAccountant;

  useEffect(() => {
    if (previewMode) {
      setTeamMembers([{
        id: "preview-manager",
        organization: 1,
        user: 3,
        username: "sam.manager",
        first_name: "Sam",
        last_name: "Kamau",
        email: "sam.manager@example.com",
        phone_number: "+254 712 345 678",
        role: "PROPERTY_MANAGER",
        is_active: true,
        created_at: "2026-01-15T00:00:00Z",
      }]);
      setIsLoadingTeam(false);
      return;
    }
    if (!token || !selectedOrganizationId || !canManageTeam) {
      setTeamMembers([]);
      setTeamError("");
      setIsLoadingTeam(false);
      return;
    }

    let cancelled = false;
    setIsLoadingTeam(true);
    setTeamError("");
    void apiRequest<ApiList<TeamMember>>(
      `/organizations/staff/?organization=${encodeURIComponent(selectedOrganizationId)}`,
      token,
    ).then(response => {
      if (!cancelled) setTeamMembers(listFromResponse(response));
    }).catch(error => {
      if (!cancelled) {
        setTeamError(error instanceof Error ? error.message : "Team members couldn’t be loaded.");
      }
    }).finally(() => {
      if (!cancelled) setIsLoadingTeam(false);
    });

    return () => {
      cancelled = true;
    };
  }, [canManageTeam, previewMode, selectedOrganizationId, token]);

  const organization = data.organizations.find(org => String(org.id) === selectedOrganizationId);
  const organizationData = useMemo(() => {
    const properties = data.properties.filter(item => String(item.organization) === selectedOrganizationId);
    const propertyIds = new Set(properties.map(item => String(item.id)));
    const buildings = data.buildings.filter(item => propertyIds.has(String(item.property)));
    const buildingIds = new Set(buildings.map(item => String(item.id)));
    const units = data.units.filter(item => buildingIds.has(String(item.building)));
    const tenants = data.tenants.filter(item => String(item.organization) === selectedOrganizationId);
    const tenantIds = new Set(tenants.map(item => String(item.id)));
    const unitIds = new Set(units.map(item => String(item.id)));
    const leases = data.leases.filter(item =>
      tenantIds.has(String(item.tenant)) && unitIds.has(String(item.unit)),
    );
    return { properties, buildings, units, tenants, leases };
  }, [data, selectedOrganizationId]);

  const activeLeases = organizationData.leases.filter(lease => lease.status === "ACTIVE");
  const activeLeaseByUnit = new Map<string, Lease>();
  activeLeases.forEach(lease => activeLeaseByUnit.set(String(lease.unit), lease));
  const monthlyRentMinor = activeLeases.reduce(
    (total, lease) => total + Number(lease.monthly_rent_minor || 0),
    0,
  );

  async function signIn(username: string, password: string) {
    setIsSigningIn(true);
    setPageError("");
    try {
      const response = await apiRequest<{
        token: string;
        account_type?: string;
        memberships?: OrganizationMembership[];
      }>(AUTH_API_PATHS.login, undefined, {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      if (!response.token) throw new Error("The API didn’t return an authentication token.");
      sessionStorage.setItem(TOKEN_KEY, response.token);
      sessionStorage.setItem("hodi_account_type", response.account_type ?? "");
      sessionStorage.setItem("hodi_memberships", JSON.stringify(response.memberships ?? []));
      setAccountType(response.account_type ?? "");
      setMemberships(response.memberships ?? []);
      setToken(response.token);
      await loadDashboard(response.token);
    } catch (error) {
      setPageError(error instanceof Error ? error.message : "Sign in failed. Please try again.");
    } finally {
      setIsSigningIn(false);
    }
  }

  async function signOut() {
    const activeToken = token;
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem("hodi_account_type");
    sessionStorage.removeItem("hodi_first_name");
    sessionStorage.removeItem("hodi_last_name");
    sessionStorage.removeItem("hodi_email");
    sessionStorage.removeItem("hodi_phone_number");
    sessionStorage.removeItem("hodi_memberships");
    setToken("");
    setData(EMPTY_DATA);
    setSelectedOrganizationId("");
    setMemberships([]);
    setPageError("");
    try {
      await apiRequest<void>("/accounts/logout/", activeToken, { method: "POST" });
    } catch (error) {
      setPageError(error instanceof Error
        ? `You were signed out on this device, but the API token could not be revoked: ${error.message}`
        : "You were signed out on this device, but the API token could not be revoked.");
    }
  }

  async function createProperty(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!organization) return;
    const form = new FormData(event.currentTarget);
    setIsSaving(true);
    setPageError("");
    try {
      await apiRequest<Property>("/properties/", token, {
        method: "POST",
        body: JSON.stringify({
          organization: organization.id,
          name: String(form.get("name") ?? "").trim(),
          address: String(form.get("address") ?? "").trim(),
          city: String(form.get("city") ?? "").trim(),
          country: String(form.get("country") ?? "Kenya").trim(),
          is_active: true,
        }),
      });
      setPropertyFormOpen(false);
      setNotice("Property added.");
      await loadDashboard(token);
    } catch (error) {
      setPageError(error instanceof Error ? error.message : "The property couldn’t be added.");
    } finally {
      setIsSaving(false);
    }
  }

  async function createBuilding(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setIsSaving(true);
    setPageError("");
    try {
      await apiRequest<Building>("/properties/buildings/", token, {
        method: "POST",
        body: JSON.stringify({
          property: Number(form.get("property")),
          name: String(form.get("name") ?? "").trim(),
        }),
      });
      setBuildingFormOpen(false);
      setNotice("Building added.");
      await loadDashboard(token);
    } catch (error) {
      setPageError(error instanceof Error ? error.message : "The building couldn’t be added.");
    } finally {
      setIsSaving(false);
    }
  }

  async function createUnit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setIsSaving(true);
    setPageError("");
    try {
      await apiRequest<Unit>("/properties/units/", token, {
        method: "POST",
        body: JSON.stringify({
          building: Number(form.get("building")),
          name: String(form.get("name") ?? "").trim(),
          bedrooms: Number(form.get("bedrooms") ?? 0),
          status: String(form.get("status") ?? "AVAILABLE"),
        }),
      });
      setUnitFormOpen(false);
      setNotice("Unit added.");
      await loadDashboard(token);
    } catch (error) {
      setPageError(error instanceof Error ? error.message : "The unit couldn’t be added.");
    } finally {
      setIsSaving(false);
    }
  }

  async function createOrganization(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setIsSaving(true);
    setPageError("");
    try {
      await apiRequest<Organization>("/organizations/", token, {
        method: "POST",
        body: JSON.stringify({ name: String(form.get("name") ?? "").trim() }),
      });
      setOrganizationFormOpen(false);
      setNotice("Organization created. You are its owner.");
      await loadDashboard(token);
    } catch (error) {
      setPageError(error instanceof Error ? error.message : "The organization couldn’t be created.");
    } finally {
      setIsSaving(false);
    }
  }

  async function createTenant(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!organization) return;
    const form = new FormData(event.currentTarget);
    setIsSaving(true);
    setPageError("");
    try {
      await apiRequest<Tenant>("/tenants/", token, {
        method: "POST",
        body: JSON.stringify({
          organization: organization.id,
          first_name: String(form.get("first_name") ?? "").trim(),
          last_name: String(form.get("last_name") ?? "").trim(),
          phone_number: String(form.get("phone_number") ?? "").trim(),
          email: String(form.get("email") ?? "").trim(),
          is_active: true,
        }),
      });
      setTenantFormOpen(false);
      setNotice("Tenant added.");
      await loadDashboard(token);
    } catch (error) {
      setPageError(error instanceof Error ? error.message : "The tenant couldn’t be added.");
    } finally {
      setIsSaving(false);
    }
  }

  async function createLease(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setIsSaving(true);
    setPageError("");
    try {
      const requestedStatus = String(form.get("status") ?? "DRAFT");
      const created = await apiRequest<Lease>("/leases/", token, {
        method: "POST",
        body: JSON.stringify({
          tenant: Number(form.get("tenant")),
          unit: Number(form.get("unit")),
          reference: String(form.get("reference") ?? "").trim(),
          start_date: String(form.get("start_date") ?? ""),
          end_date: String(form.get("end_date") ?? "") || null,
          monthly_rent_minor: Math.round(Number(form.get("monthly_rent")) * 100),
          security_deposit_minor: Math.round(Number(form.get("security_deposit") || 0) * 100),
          status: "DRAFT",
        }),
      });
      if (requestedStatus === "ACTIVE") {
        await apiRequest<Lease>(`/leases/${created.id}/activate/`, token, { method: "POST" });
      }
      setLeaseFormOpen(false);
      setNotice(requestedStatus === "ACTIVE" ? "Lease added and activated. The unit is now occupied." : "Lease added.");
      await loadDashboard(token);
    } catch (error) {
      setPageError(error instanceof Error ? error.message : "The lease couldn’t be added.");
    } finally {
      setIsSaving(false);
    }
  }

  async function submitLeaseAction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!leaseAction) return;
    setIsSaving(true);
    setPageError("");
    try {
      if (leaseAction.mode === "terminate") {
        await apiRequest<Lease>(`/leases/${leaseAction.id}/terminate/`, token, {
          method: "POST",
          body: JSON.stringify({ end_date: leaseEndDate, reason: leaseReason }),
        });
        setNotice("Lease terminated. If nothing else occupies the unit, it becomes available.");
      } else {
        await apiRequest<Lease>(`/leases/${leaseAction.id}/expire/`, token, { method: "POST" });
        setNotice("Lease expired. If nothing else occupies the unit, it becomes available.");
      }
      setLeaseAction(null);
      await loadDashboard(token);
    } catch (error) {
      setPageError(error instanceof Error ? error.message : "The lease couldn’t be updated.");
    } finally {
      setIsSaving(false);
    }
  }

  async function createTeamMember(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!organization) return;
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") ?? "");
    const passwordConfirm = String(form.get("password_confirm") ?? "");
    if (password !== passwordConfirm) {
      setTeamError("The passwords do not match.");
      return;
    }

    const role = String(form.get("role") ?? "CARETAKER");
    const roleLabel = ORGANIZATION_STAFF_ROLES.find(item => item.value === role)?.label ?? "Team member";
    const loginKind = staffLoginKindForRole(role);
    const accessLabel = loginKind === "caretaker" ? "Caretaker" : loginKind === "technician" ? "Technician" : "Landlord";
    setIsSaving(true);
    setTeamError("");
    try {
      const staffMember = await apiRequest<TeamMember>("/organizations/staff/", token, {
        method: "POST",
        body: JSON.stringify({
          organization: organization.id,
          username: String(form.get("username") ?? "").trim(),
          email: String(form.get("email") ?? "").trim(),
          first_name: String(form.get("first_name") ?? "").trim(),
          last_name: String(form.get("last_name") ?? "").trim(),
          phone_number: String(form.get("phone_number") ?? "").trim(),
          role,
          password,
          password_confirm: passwordConfirm,
        }),
      });
      setTeamMembers(current => [staffMember, ...current]);
      setTeamFormOpen(false);
      setNotice(
        `${roleLabel} account created. Share the initial password securely; they should sign in using ${accessLabel} access.`,
      );
    } catch (error) {
      setTeamError(error instanceof Error ? error.message : "The team account couldn’t be created.");
    } finally {
      setIsSaving(false);
    }
  }

  async function inviteAccountant(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!organization) return;
    const email = String(new FormData(event.currentTarget).get("accountant_email") ?? "").trim();
    setIsSaving(true); setTeamError("");
    try {
      await apiRequest("/organizations/accountant-invitations/", token, {
        method: "POST", body: JSON.stringify({ organization: organization.id, email }),
      });
      event.currentTarget.reset();
      setNotice(`Accountant invitation sent to ${email}. They can accept it in the Accountant workspace.`);
    } catch (error) {
      setTeamError(error instanceof Error ? error.message : "The accountant invitation could not be sent.");
    } finally { setIsSaving(false); }
  }

  useEffect(() => {
    if (!notice) return;
    const timeout = window.setTimeout(() => setNotice(""), 4000);
    return () => window.clearTimeout(timeout);
  }, [notice]);

  if (!token) {
    return (
      <LoginForm
        error={pageError}
        isSubmitting={isSigningIn}
        onSubmit={signIn}
      />
    );
  }

  return (
    <div className="landlord-app">
      <aside className="landlord-sidebar">
        <Logo size={36} className="landlord-sidebar-logo" wordmarkClassName="text-white" />
        <span className="landlord-sidebar-label">WORKSPACE</span>
        <nav className="landlord-nav" aria-label="Landlord dashboard">
          <a className="is-active" href="#overview"><Icon name="overview" />Overview</a>
          {showPortfolio && <a href="#properties"><Icon name="building" />Properties</a>}
          {showPortfolio && <a href="#units"><Icon name="building" />Units</a>}
          {showPortfolio && <a href="#tenants"><Icon name="people" />Tenants</a>}
          {showPortfolio && <a href="#leases"><Icon name="lease" />Leases</a>}
          {canWritePortfolio && <a href="#marketplace"><Icon name="building" />Listings</a>}
          <Link href="/marketplace">Marketplace</Link>
          {canManageTeam && <Link href="/accountants">Accountants</Link>}
          {canReadBilling && <a href="#billing"><Icon name="lease" />Billing</a>}
          {canReadBilling && <a href="#subscription"><Icon name="lease" />Subscription</a>}
          {canReadUtilities && <a href="#utilities"><Icon name="building" />Utilities</a>}
          {canMaintenance && <a href="#maintenance-requests"><Icon name="building" />Maintenance</a>}
          {canManageTeam && <a href="#team"><Icon name="people" />Team</a>}
          {canAudit && !previewMode && <a href="#audit"><Icon name="overview" />Audit</a>}
        </nav>
        <div className="landlord-sidebar-bottom">
          <span className="landlord-sidebar-label">HODI PROPERTY OPERATIONS</span>
          <Link href="/" className="landlord-back-link">Back to Hodi website</Link>
        </div>
      </aside>

      <main className="landlord-main">
        <header className="landlord-topbar">
          <div>
            <span className="landlord-eyebrow">{isAccountant ? "ACCOUNTING" : isManager ? "PROPERTY MANAGER" : "LANDLORD PORTAL"}</span>
            <h1>{organization?.name ?? "Your properties"}</h1>
          </div>
          <div className="landlord-topbar-actions">
            <ThemeToggle />
            {data.organizations.length > 1 && (
              <label className="landlord-org-select">
                <span className="sr-only">Organization</span>
                <select
                  value={selectedOrganizationId}
                  onChange={event => setSelectedOrganizationId(event.target.value)}
                >
                  {data.organizations.map(item => (
                    <option key={item.id} value={item.id}>{item.name}</option>
                  ))}
                </select>
              </label>
            )}
            {!previewMode && (
              <>
                <button
                  type="button"
                  className="landlord-icon-button"
                  aria-label="Refresh dashboard"
                  disabled={isLoading}
                  onClick={() => void loadDashboard(token)}
                >
                  <Icon name="refresh" />
                </button>
                <button type="button" className="landlord-button landlord-button--quiet" onClick={() => void signOut()}>
                  <Icon name="logout" />Sign out
                </button>
                <NotificationBell />
              </>
            )}
          </div>
        </header>

        {previewMode && (
          <div className="landlord-preview-banner" role="status">
            Preview mode · Sample data only; changes are disabled.
            <Link href="/landlords">Exit preview</Link>
          </div>
        )}
        {pageError && <div className="landlord-alert" role="alert">{pageError}</div>}
        {notice && <div className="landlord-notice" role="status">{notice}</div>}

        {data.organizations.length === 0 && !isLoading ? (
          <section className="landlord-empty-workspace">
            <span className="landlord-empty-icon"><Icon name="building" /></span>
            <h2>No organization is linked to your account</h2>
            <p>Create an organization to start a property portfolio, or ask an existing owner to add you as a member.</p>
            {!organizationFormOpen ? (
              <button
                type="button"
                className="landlord-button landlord-button--primary landlord-create-organization"
                onClick={() => setOrganizationFormOpen(true)}
              >
                <Icon name="plus" />Create organization
              </button>
            ) : (
              <form className="landlord-form landlord-create-organization-form" onSubmit={createOrganization}>
                <label>
                  Organization name
                  <input name="name" required maxLength={200} autoFocus />
                </label>
                {pageError && <p className="landlord-error" role="alert">{pageError}</p>}
                <div className="landlord-form-actions">
                  <button type="button" className="landlord-button landlord-button--quiet" onClick={() => setOrganizationFormOpen(false)}>Cancel</button>
                  <button className="landlord-button landlord-button--primary" disabled={isSaving}>{isSaving ? "Creating…" : "Create organization"}</button>
                </div>
              </form>
            )}
          </section>
        ) : (
          <>
            {isAccountant ? (
              <section id="overview" className="landlord-welcome">
                <div>
                  <p className="landlord-eyebrow">ACCOUNTS</p>
                  <h2>Billing workspace</h2>
                  <p>Invoices, the rent log, ledger allocation, delinquency, and the audit trail for this organization.</p>
                </div>
                {isLoading && <span className="landlord-loading-label">Syncing with Hodi…</span>}
              </section>
            ) : (
              <div id="overview" className="landlord-overview-banner-wrap">
                <PropertyBanner
                  eyebrow="Your portfolio"
                  title="A clear view of the places you manage."
                  description="Properties, homes, tenants and active leases, held together in one operating space."
                  imageSrc="/images/hodi/apartment-building.jpg"
                  imageSizes="(max-width: 900px) 100vw, 75vw"
                  className="landlord-overview-banner"
                />
                {isLoading && <span className="landlord-banner-sync" role="status">Syncing with HODI…</span>}
              </div>
            )}

            {showPortfolio && hasLoadedDashboard && <section className="landlord-metrics" aria-label="Portfolio summary" aria-busy={isLoading}>
              <article className="landlord-metric-card">
                <span>Properties</span>
                <strong>{organizationData.properties.length}</strong>
                <small>In this organization</small>
              </article>
              <article className="landlord-metric-card">
                <span>Total units</span>
                <strong>{organizationData.units.length}</strong>
                <small>{organizationData.units.filter(unit => unit.status === "OCCUPIED").length} marked occupied</small>
              </article>
              <article className="landlord-metric-card">
                <span>Active tenants</span>
                <strong>{organizationData.tenants.filter(tenant => tenant.is_active).length}</strong>
                <small>{organizationData.tenants.length} tenant records</small>
              </article>
              <article className="landlord-metric-card landlord-metric-card--accent">
                <span>Monthly rent on active leases</span>
                <strong>{formatMoney(monthlyRentMinor)}</strong>
                <small>{activeLeases.length} active lease{activeLeases.length === 1 ? "" : "s"}</small>
              </article>
            </section>}
            {showPortfolio && isLoading && !hasLoadedDashboard && (
              <section className="landlord-metrics landlord-metrics--loading" aria-label="Loading portfolio summary" aria-busy="true">
                {Array.from({ length: 4 }, (_, index) => <div className="landlord-metric-skeleton" key={index} aria-hidden="true" />)}
              </section>
            )}

            {showPortfolio && <>
            <section id="properties" className="landlord-section">
              <div className="landlord-section-heading">
                <div>
                  <span className="landlord-eyebrow">PORTFOLIO</span>
                  <h2>Properties &amp; units</h2>
                </div>
                {!previewMode && (
                  <div className="landlord-section-actions">
                    <button
                      type="button"
                      className="landlord-button landlord-button--quiet"
                      disabled={!organizationData.properties.length}
                      title={!organizationData.properties.length ? "Add a property first" : undefined}
                      onClick={() => setBuildingFormOpen(open => !open)}
                    >
                      <Icon name="plus" />Add building
                    </button>
                    <button
                      type="button"
                      className="landlord-button landlord-button--primary"
                      onClick={() => setPropertyFormOpen(open => !open)}
                    >
                      <Icon name="plus" />Add property
                    </button>
                  </div>
                )}
              </div>
              {propertyFormOpen && (
                <form className="landlord-inline-form" onSubmit={createProperty}>
                  <h3>Add a property</h3>
                  <div className="landlord-form-grid">
                    <label>Property name<input name="name" required maxLength={200} /></label>
                    <label>City<input name="city" required defaultValue="Ongata Rongai" maxLength={100} /></label>
                    <label className="landlord-form-wide">Address<input name="address" /></label>
                    <label>Country<input name="country" required defaultValue="Kenya" maxLength={100} /></label>
                  </div>
                  <div className="landlord-form-actions">
                    <button type="button" className="landlord-button landlord-button--quiet" onClick={() => setPropertyFormOpen(false)}>Cancel</button>
                    <button className="landlord-button landlord-button--primary" disabled={isSaving}>{isSaving ? "Saving…" : "Save property"}</button>
                  </div>
                </form>
              )}
              {buildingFormOpen && (
                <form className="landlord-inline-form" onSubmit={createBuilding}>
                  <h3>Add a building</h3>
                  <div className="landlord-form-grid">
                    <label>Property
                      <select name="property" required defaultValue="">
                        <option value="" disabled>Select a property</option>
                        {organizationData.properties.map(property => <option key={property.id} value={property.id}>{property.name}</option>)}
                      </select>
                    </label>
                    <label>Building name<input name="name" required maxLength={200} placeholder="e.g. Block A" /></label>
                  </div>
                  <div className="landlord-form-actions">
                    <button type="button" className="landlord-button landlord-button--quiet" onClick={() => setBuildingFormOpen(false)}>Cancel</button>
                    <button className="landlord-button landlord-button--primary" disabled={isSaving}>{isSaving ? "Saving…" : "Save building"}</button>
                  </div>
                </form>
              )}
              {organizationData.properties.length ? (
                <div className="landlord-property-grid">
                  {organizationData.properties.map(property => {
                    const buildings = organizationData.buildings.filter(
                      building => String(building.property) === String(property.id),
                    );
                    const propertyUnits = organizationData.units.filter(unit =>
                      buildings.some(building => String(building.id) === String(unit.building)),
                    );
                    const occupiedCount = propertyUnits.filter(unit => unit.status === "OCCUPIED").length;
                    return (
                      <article className="landlord-property-card" key={property.id}>
                        <div className="landlord-property-card-top">
                          <span className="landlord-property-icon"><Icon name="building" /></span>
                          <span className={`landlord-status ${property.is_active ? "is-active" : ""}`}>
                            {property.is_active ? "Active" : "Inactive"}
                          </span>
                        </div>
                        <h3>{property.name}</h3>
                        <p>{[property.address, property.city, property.country].filter(Boolean).join(", ") || "Address not provided"}</p>
                        <div className="landlord-property-meta">
                          <span>{buildings.length} building{buildings.length === 1 ? "" : "s"}</span>
                          <span>{propertyUnits.length} unit{propertyUnits.length === 1 ? "" : "s"}</span>
                          <span>{occupiedCount} occupied</span>
                        </div>
                      </article>
                    );
                  })}
                </div>
              ) : (
                <div className="landlord-empty-state">
                  <h3>No properties yet</h3>
                  <p>Add a property to start organizing buildings and units in your portfolio.</p>
                </div>
              )}
            </section>

            {canManageTeam && <section id="team" className="landlord-section">
              <div className="landlord-section-heading">
                <div>
                  <span className="landlord-eyebrow">ORGANIZATION ACCESS</span>
                  <h2>Team</h2>
                </div>
                {!previewMode && (
                  <button
                    type="button"
                    className="landlord-button landlord-button--primary"
                    onClick={() => setTeamFormOpen(open => !open)}
                  >
                    <Icon name="plus" />Add team member
                  </button>
                )}
              </div>
              {teamError && <div className="landlord-alert" role="alert">{teamError}</div>}
              {!previewMode && <form className="landlord-inline-form" onSubmit={inviteAccountant}>
                <h3>Invite an accountant</h3>
                <p className="landlord-form-note">The invited user must sign in to accept access to this organisation.</p>
                <div className="landlord-form-grid"><label>Account email<input name="accountant_email" required type="email" autoComplete="email" /></label></div>
                <div className="landlord-form-actions"><button className="landlord-button landlord-button--primary" disabled={isSaving}>{isSaving ? "Sending…" : "Send invitation"}</button><Link className="landlord-button landlord-button--quiet" href="/accountants">Accountant workspace</Link></div>
              </form>}
              {teamFormOpen && !previewMode && (
                <form className="landlord-inline-form" onSubmit={createTeamMember}>
                  <h3>Add an organization team member</h3>
                  <p className="landlord-form-note">
                    This creates a login for {organization?.name ?? "this organization"}. Share the initial password securely.
                  </p>
                  <div className="landlord-form-grid">
                    <label>First name<input name="first_name" required maxLength={150} autoComplete="given-name" /></label>
                    <label>Last name<input name="last_name" required maxLength={150} autoComplete="family-name" /></label>
                    <label>Username<input name="username" required maxLength={150} autoComplete="username" /></label>
                    <label>Email<input name="email" required type="email" autoComplete="email" /></label>
                    <label>Phone number <span className="landlord-optional">(optional)</span><input name="phone_number" type="tel" maxLength={30} autoComplete="tel" /></label>
                    <label>Role
                      <select name="role" defaultValue="CARETAKER">
                        {ORGANIZATION_STAFF_ROLES.filter(item => item.value !== "ACCOUNTANT").map(item => (
                          <option key={item.value} value={item.value}>{item.label}</option>
                        ))}
                      </select>
                    </label>
                    <label>Initial password<input name="password" type="password" required minLength={8} autoComplete="new-password" /></label>
                    <label>Confirm password<input name="password_confirm" type="password" required minLength={8} autoComplete="new-password" /></label>
                  </div>
                  <div className="landlord-form-actions">
                    <button type="button" className="landlord-button landlord-button--quiet" onClick={() => { setTeamFormOpen(false); setTeamError(""); }}>Cancel</button>
                    <button className="landlord-button landlord-button--primary" disabled={isSaving}>{isSaving ? "Creating account…" : "Create login"}</button>
                  </div>
                </form>
              )}
              {isLoadingTeam ? (
                <div className="landlord-empty-state">Loading team members…</div>
              ) : teamMembers.length ? (
                <div className="landlord-table-wrap" role="region" aria-label="Organization team" tabIndex={0}>
                  <table className="landlord-table">
                    <thead><tr><th>Team member</th><th>Login</th><th>Role</th><th>Status</th></tr></thead>
                    <tbody>
                      {teamMembers.map(member => (
                        <tr key={member.id}>
                          <td>
                            <div className="landlord-person">
                              <span className="landlord-avatar">{member.first_name.slice(0, 1).toUpperCase()}</span>
                              <span><strong>{`${member.first_name} ${member.last_name}`.trim() || member.username}</strong><small>{member.phone_number || "No phone number"}</small></span>
                            </div>
                          </td>
                          <td><strong>{member.username}</strong><br /><small>{member.email}</small></td>
                          <td>{displayStatus(member.role)}</td>
                          <td><span className={`landlord-status ${member.is_active ? "is-active" : ""}`}>{member.is_active ? "Active" : "Inactive"}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="landlord-empty-state">
                  <h3>No team members yet</h3>
                  <p>Add property managers for operations or caretakers for maintenance and resident support.</p>
                </div>
              )}
            </section>}

            <section id="tenants" className="landlord-section">
              <div className="landlord-section-heading">
                <div>
                  <span className="landlord-eyebrow">PEOPLE</span>
                  <h2>Tenants</h2>
                </div>
                {!previewMode && (
                  <button
                    type="button"
                    className="landlord-button landlord-button--primary"
                    onClick={() => setTenantFormOpen(open => !open)}
                  >
                    <Icon name="plus" />Add tenant
                  </button>
                )}
              </div>
              {tenantFormOpen && (
                <form className="landlord-inline-form" onSubmit={createTenant}>
                  <h3>Add a tenant</h3>
                  <div className="landlord-form-grid">
                    <label>First name<input name="first_name" required maxLength={100} /></label>
                    <label>Last name<input name="last_name" required maxLength={100} /></label>
                    <label>Phone number<input name="phone_number" required type="tel" maxLength={30} /></label>
                    <label>Email <span className="landlord-optional">(optional)</span><input name="email" type="email" /></label>
                  </div>
                  <div className="landlord-form-actions">
                    <button type="button" className="landlord-button landlord-button--quiet" onClick={() => setTenantFormOpen(false)}>Cancel</button>
                    <button className="landlord-button landlord-button--primary" disabled={isSaving}>{isSaving ? "Saving…" : "Save tenant"}</button>
                  </div>
                </form>
              )}
              {organizationData.tenants.length ? (
                <div className="landlord-table-wrap" role="region" aria-label="Organization tenants" tabIndex={0}>
                  <table className="landlord-table">
                    <thead><tr><th>Tenant</th><th>Contact</th><th>Lease</th><th>Status</th></tr></thead>
                    <tbody>
                      {organizationData.tenants.map(tenant => {
                        const tenantLeases = organizationData.leases.filter(
                          lease => String(lease.tenant) === String(tenant.id),
                        );
                        const currentLease = tenantLeases.find(lease => lease.status === "ACTIVE");
                        return (
                          <tr key={tenant.id}>
                            <td>
                              <div className="landlord-person">
                                <span className="landlord-avatar">{tenant.first_name.slice(0, 1).toUpperCase()}</span>
                                <span><strong>{tenant.full_name || `${tenant.first_name} ${tenant.last_name}`}</strong><small>{tenant.email || "No email provided"}</small></span>
                              </div>
                            </td>
                            <td>{tenant.phone_number}</td>
                            <td>{currentLease ? currentLease.reference : tenantLeases.length ? "No active lease" : "Not assigned"}</td>
                            <td><span className={`landlord-status ${tenant.is_active ? "is-active" : ""}`}>{tenant.is_active ? "Active" : "Inactive"}</span></td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="landlord-empty-state">
                  <h3>No tenant records yet</h3>
                  <p>Add a tenant here. Lease and unit assignment can be managed through the Hodi API.</p>
                </div>
              )}
            </section>

            <section id="leases" className="landlord-section">
              <div className="landlord-section-heading">
                <div>
                  <span className="landlord-eyebrow">TENANCY</span>
                  <h2>Leases &amp; occupancy</h2>
                </div>
                <div className="landlord-section-actions">
                  <span className="landlord-section-count">{organizationData.leases.length} records</span>
                  {!previewMode && (
                    <button
                      type="button"
                      className="landlord-button landlord-button--primary"
                      disabled={!organizationData.tenants.some(tenant => tenant.is_active) || !organizationData.units.some(unit => unit.status === "AVAILABLE")}
                      title={!organizationData.tenants.some(tenant => tenant.is_active) ? "Add an active tenant first" : !organizationData.units.some(unit => unit.status === "AVAILABLE") ? "Add an available unit first" : undefined}
                      onClick={() => setLeaseFormOpen(open => !open)}
                    >
                      <Icon name="plus" />Add lease
                    </button>
                  )}
                </div>
              </div>
              {leaseFormOpen && !previewMode && (
                <form className="landlord-inline-form" onSubmit={createLease}>
                  <h3>Create a lease</h3>
                  <p className="landlord-form-note">Only active tenants and available units in {organization?.name ?? "this organization"} are listed.</p>
                  <div className="landlord-form-grid">
                    <label>Tenant
                      <select name="tenant" required defaultValue="">
                        <option value="" disabled>Select a tenant</option>
                        {organizationData.tenants.filter(tenant => tenant.is_active).map(tenant => <option key={tenant.id} value={tenant.id}>{tenant.full_name || `${tenant.first_name} ${tenant.last_name}`}</option>)}
                      </select>
                    </label>
                    <label>Available unit
                      <select name="unit" required defaultValue="">
                        <option value="" disabled>Select a unit</option>
                        {organizationData.units.filter(unit => unit.status === "AVAILABLE").map(unit => {
                          const building = organizationData.buildings.find(item => String(item.id) === String(unit.building));
                          const property = organizationData.properties.find(item => String(item.id) === String(building?.property));
                          return <option key={unit.id} value={unit.id}>{property?.name ?? "Property"} · {building?.name ?? "Building"} · {unit.name}</option>;
                        })}
                      </select>
                    </label>
                    <label>Lease reference<input name="reference" required maxLength={100} /></label>
                    <label>Status
                      <select name="status" defaultValue="ACTIVE">
                        <option value="DRAFT">Draft</option>
                        <option value="ACTIVE">Active</option>
                      </select>
                    </label>
                    <label>Start date<input name="start_date" type="date" required /></label>
                    <label>End date <span className="landlord-optional">(optional)</span><input name="end_date" type="date" /></label>
                    <label>Monthly rent (KES)<input name="monthly_rent" type="number" min="0.01" step="0.01" required /></label>
                    <label>Security deposit (KES)<input name="security_deposit" type="number" min="0" step="0.01" defaultValue="0" required /></label>
                  </div>
                  <div className="landlord-form-actions">
                    <button type="button" className="landlord-button landlord-button--quiet" onClick={() => setLeaseFormOpen(false)}>Cancel</button>
                    <button className="landlord-button landlord-button--primary" disabled={isSaving}>{isSaving ? "Saving…" : "Create lease"}</button>
                  </div>
                </form>
              )}
              {organizationData.leases.length ? (
                <div className="landlord-table-wrap" role="region" aria-label="Lease records" tabIndex={0}>
                  <table className="landlord-table">
                    <thead><tr><th>Lease</th><th>Tenant</th><th>Unit</th><th>Monthly rent</th><th>Dates</th><th>Status</th>{canWritePortfolio && !previewMode && <th>Actions</th>}</tr></thead>
                    <tbody>
                      {organizationData.leases.map(lease => {
                        const tenant = organizationData.tenants.find(item => String(item.id) === String(lease.tenant));
                        const unit = organizationData.units.find(item => String(item.id) === String(lease.unit));
                        const building = organizationData.buildings.find(item => String(item.id) === String(unit?.building));
                        const property = organizationData.properties.find(item => String(item.id) === String(building?.property));
                        return (
                          <tr key={lease.id}>
                            <td><strong>{lease.reference}</strong></td>
                            <td>{tenant?.full_name ?? "Tenant unavailable"}</td>
                            <td>{unit ? `${property?.name ?? building?.name ?? "Property"} · ${unit.name}` : "Unit unavailable"}</td>
                            <td>{formatMoney(lease.monthly_rent_minor)}</td>
                            <td>{formatDate(lease.start_date)} – {formatDate(lease.end_date)}</td>
                            <td><span className={`landlord-status ${lease.status === "ACTIVE" ? "is-active" : ""}`}>{displayStatus(lease.status)}</span></td>
                            {canWritePortfolio && !previewMode && (
                              <td>
                                {lease.status === "ACTIVE" ? (
                                  <div className="landlord-section-actions">
                                    <button
                                      type="button"
                                      className="landlord-button landlord-button--quiet"
                                      onClick={() => {
                                        setLeaseEndDate(new Date().toISOString().slice(0, 10));
                                        setLeaseReason("");
                                        setLeaseAction({ id: lease.id, reference: lease.reference, mode: "terminate" });
                                      }}
                                    >
                                      Terminate
                                    </button>
                                    <button
                                      type="button"
                                      className="landlord-button landlord-button--quiet"
                                      onClick={() => setLeaseAction({ id: lease.id, reference: lease.reference, mode: "expire" })}
                                    >
                                      Expire
                                    </button>
                                  </div>
                                ) : "—"}
                              </td>
                            )}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="landlord-empty-state">
                  <h3>No leases recorded</h3>
                  <p>Create a lease when an active tenant and available unit are ready.</p>
                </div>
              )}
            </section>

            <section id="units" className="landlord-section landlord-units-section">
              <div className="landlord-section-heading">
                <div>
                  <span className="landlord-eyebrow">UNIT REGISTER</span>
                  <h2>Unit status</h2>
                </div>
                {!previewMode && (
                  <button
                    type="button"
                    className="landlord-button landlord-button--primary"
                    disabled={!organizationData.buildings.length}
                    title={!organizationData.buildings.length ? "Add a building first" : undefined}
                    onClick={() => setUnitFormOpen(open => !open)}
                  >
                    <Icon name="plus" />Add unit
                  </button>
                )}
              </div>
              {unitFormOpen && !previewMode && (
                <form className="landlord-inline-form" onSubmit={createUnit}>
                  <h3>Add a unit</h3>
                  <div className="landlord-form-grid">
                    <label>Building
                      <select name="building" required defaultValue="">
                        <option value="" disabled>Select a building</option>
                        {organizationData.buildings.map(building => {
                          const property = organizationData.properties.find(item => String(item.id) === String(building.property));
                          return <option key={building.id} value={building.id}>{property?.name ?? "Property"} · {building.name}</option>;
                        })}
                      </select>
                    </label>
                    <label>Unit name<input name="name" required maxLength={100} placeholder="e.g. A-204" /></label>
                    <label>Bedrooms<input name="bedrooms" type="number" min="0" max="255" step="1" defaultValue="1" required /></label>
                    <label>Status
                      <select name="status" defaultValue="AVAILABLE">
                        <option value="AVAILABLE">Available</option>
                        <option value="OCCUPIED">Occupied</option>
                        <option value="MAINTENANCE">Maintenance</option>
                        <option value="INACTIVE">Inactive</option>
                      </select>
                    </label>
                  </div>
                  <div className="landlord-form-actions">
                    <button type="button" className="landlord-button landlord-button--quiet" onClick={() => setUnitFormOpen(false)}>Cancel</button>
                    <button className="landlord-button landlord-button--primary" disabled={isSaving}>{isSaving ? "Saving…" : "Save unit"}</button>
                  </div>
                </form>
              )}
              {organizationData.units.length ? (
                <div className="landlord-table-wrap" role="region" aria-label="Unit records" tabIndex={0}>
                  <table className="landlord-table">
                    <thead><tr><th>Unit</th><th>Property / building</th><th>Bedrooms</th><th>Rent status</th><th>Availability</th></tr></thead>
                    <tbody>
                      {organizationData.units.map(unit => {
                        const building = organizationData.buildings.find(item => String(item.id) === String(unit.building));
                        const property = organizationData.properties.find(item => String(item.id) === String(building?.property));
                        const lease = activeLeaseByUnit.get(String(unit.id));
                        return (
                          <tr key={unit.id}>
                            <td><strong>{unit.name}</strong></td>
                            <td>{property?.name ?? "Property unavailable"} · {building?.name ?? "Building unavailable"}</td>
                            <td>{unit.bedrooms}</td>
                            <td>{lease ? formatMoney(lease.monthly_rent_minor) : "—"}</td>
                            <td><span className={`landlord-status ${unit.status === "AVAILABLE" ? "is-active" : ""}`}>{displayStatus(unit.status)}</span></td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="landlord-empty-state">
                  <h3>No units to show</h3>
                  <p>Add a building first, then add units to track occupancy and assign leases.</p>
                </div>
              )}
            </section>
            </>}

            {canWritePortfolio && !previewMode && (
              <MarketplaceManager
                units={organizationData.units}
                buildings={organizationData.buildings}
                properties={organizationData.properties}
              />
            )}
            {canWritePortfolio && !previewMode && <CommerceWorkspace key={`commerce-${selectedOrganizationId}`} organizationId={selectedOrganizationId} />}

            {canReadBilling && !previewMode && (
              <BillingWorkspace
                key={`billing-${selectedOrganizationId}`}
                organizationId={selectedOrganizationId}
                canWriteLedger={canWriteLedger}
                canWriteRentLog={canWriteRentLog}
              />
            )}
            {canReadUtilities && !previewMode && (
              <UtilitiesWorkspace
                key={`utilities-${selectedOrganizationId}`}
                organizationId={selectedOrganizationId}
                canWrite={canWritePortfolio}
                properties={organizationData.properties}
                buildings={organizationData.buildings}
                units={organizationData.units}
              />
            )}
            {canReadBilling && !previewMode && (
              <SubscriptionPanel organizationId={selectedOrganizationId} canManage={canWritePortfolio} />
            )}
            {canMaintenance && !previewMode && (
              <MaintenanceRequestsPanel
                key={`maintenance-${selectedOrganizationId}`}
                organizationId={selectedOrganizationId}
                canWrite={canWritePortfolio}
              />
            )}
            {canAudit && !previewMode && <AuditLogPanel organizationId={selectedOrganizationId} />}
          </>
        )}
        {leaseAction && (
          <div className="ops-dialog-backdrop">
            <form className="ops-dialog" onSubmit={event => void submitLeaseAction(event)}>
              <span className="ops-kicker">{leaseAction.mode === "terminate" ? "TERMINATE LEASE" : "EXPIRE LEASE"}</span>
              <h3>{leaseAction.reference}</h3>
              <p className="ops-note">
                {leaseAction.mode === "terminate"
                  ? "This ends an active lease. The unit becomes available when no other active lease still occupies it. The server validates the date."
                  : "This marks the active lease expired. The unit becomes available when no other active lease still occupies it."}
              </p>
              {leaseAction.mode === "terminate" && (
                <>
                  <label className="ops-field">End date
                    <input type="date" required value={leaseEndDate} onChange={event => setLeaseEndDate(event.target.value)} />
                  </label>
                  <label className="ops-field">Reason
                    <input value={leaseReason} onChange={event => setLeaseReason(event.target.value)} maxLength={300} />
                  </label>
                </>
              )}
              <div className="ops-form-actions">
                <button type="button" className="ops-button" onClick={() => setLeaseAction(null)}>Keep lease</button>
                <button className="ops-button ops-button--primary" disabled={isSaving}>
                  {isSaving ? "Saving…" : leaseAction.mode === "terminate" ? "Terminate lease" : "Expire lease"}
                </button>
              </div>
            </form>
          </div>
        )}
        <footer className="landlord-footer">Hodi property operations <span>·</span> Data synced from your organization</footer>
      </main>
    </div>
  );
}
