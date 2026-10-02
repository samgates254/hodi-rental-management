"use client";

import {
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import Link from "next/link";
import "./landlord-dashboard.css";

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
  if (payload && typeof payload === "object") {
    const details = payload as Record<string, unknown>;
    if (typeof details.detail === "string") return details.detail;
    if (typeof details.error === "string") return details.error;
    const firstError = Object.values(details).find(value => typeof value === "string");
    if (typeof firstError === "string") return firstError;
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
      <a className="landlord-wordmark" href="/">hodi<span>.</span></a>
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
        <p className="landlord-login-note">Your account must belong to at least one Hodi organization.</p>
      </section>
    </main>
  );
}

export default function LandlordDashboard() {
  const [token, setToken] = useState("");
  const [data, setData] = useState<DashboardData>(EMPTY_DATA);
  const [selectedOrganizationId, setSelectedOrganizationId] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSigningIn, setIsSigningIn] = useState(false);
  const [pageError, setPageError] = useState("");
  const [notice, setNotice] = useState("");
  const [organizationFormOpen, setOrganizationFormOpen] = useState(false);
  const [propertyFormOpen, setPropertyFormOpen] = useState(false);
  const [tenantFormOpen, setTenantFormOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [previewMode, setPreviewMode] = useState(false);

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
      setSelectedOrganizationId(String(PREVIEW_DATA.organizations[0].id));
      setToken("preview");
      return;
    }
    const savedToken = sessionStorage.getItem(TOKEN_KEY);
    if (!savedToken) return;
    setToken(savedToken);
    void loadDashboard(savedToken);
  }, [loadDashboard]);

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
      const response = await apiRequest<{ token: string }>("/accounts/login/", undefined, {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      if (!response.token) throw new Error("The API didn’t return an authentication token.");
      sessionStorage.setItem(TOKEN_KEY, response.token);
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
    setToken("");
    setData(EMPTY_DATA);
    setSelectedOrganizationId("");
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
        <a className="landlord-wordmark" href="/">hodi<span>.</span></a>
        <span className="landlord-sidebar-label">WORKSPACE</span>
        <nav className="landlord-nav" aria-label="Landlord dashboard">
          <a className="is-active" href="#overview"><Icon name="overview" />Overview</a>
          <a href="#properties"><Icon name="building" />Properties</a>
          <a href="#tenants"><Icon name="people" />Tenants</a>
          <a href="#leases"><Icon name="lease" />Leases</a>
        </nav>
        <div className="landlord-sidebar-bottom">
          <span className="landlord-sidebar-label">HODI PROPERTY OPERATIONS</span>
          <a href="/" className="landlord-back-link">Back to Hodi website</a>
        </div>
      </aside>

      <main className="landlord-main">
        <header className="landlord-topbar">
          <div>
            <span className="landlord-eyebrow">LANDLORD PORTAL</span>
            <h1>{organization?.name ?? "Your properties"}</h1>
          </div>
          <div className="landlord-topbar-actions">
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
            <section id="overview" className="landlord-welcome">
              <div>
                <p className="landlord-eyebrow">YOUR PORTFOLIO</p>
                <h2>Property overview</h2>
                <p>A clear view of your properties, homes, tenants, and active leases.</p>
              </div>
              {isLoading && <span className="landlord-loading-label">Syncing with Hodi…</span>}
            </section>

            <section className="landlord-metrics" aria-label="Portfolio summary">
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
            </section>

            <section id="properties" className="landlord-section">
              <div className="landlord-section-heading">
                <div>
                  <span className="landlord-eyebrow">PORTFOLIO</span>
                  <h2>Properties &amp; units</h2>
                </div>
                {!previewMode && (
                  <button
                    type="button"
                    className="landlord-button landlord-button--primary"
                    onClick={() => setPropertyFormOpen(open => !open)}
                  >
                    <Icon name="plus" />Add property
                  </button>
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
                <div className="landlord-table-wrap">
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
                <span className="landlord-section-count">{organizationData.leases.length} records</span>
              </div>
              {organizationData.leases.length ? (
                <div className="landlord-table-wrap">
                  <table className="landlord-table">
                    <thead><tr><th>Lease</th><th>Tenant</th><th>Unit</th><th>Monthly rent</th><th>Dates</th><th>Status</th></tr></thead>
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
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="landlord-empty-state">
                  <h3>No leases recorded</h3>
                  <p>Lease records added to this organization will appear here.</p>
                </div>
              )}
            </section>

            <section className="landlord-section landlord-units-section">
              <div className="landlord-section-heading">
                <div>
                  <span className="landlord-eyebrow">UNIT REGISTER</span>
                  <h2>Unit status</h2>
                </div>
              </div>
              {organizationData.units.length ? (
                <div className="landlord-table-wrap">
                  <table className="landlord-table">
                    <thead><tr><th>Unit</th><th>Property</th><th>Bedrooms</th><th>Rent status</th><th>Availability</th></tr></thead>
                    <tbody>
                      {organizationData.units.map(unit => {
                        const building = organizationData.buildings.find(item => String(item.id) === String(unit.building));
                        const property = organizationData.properties.find(item => String(item.id) === String(building?.property));
                        const lease = activeLeaseByUnit.get(String(unit.id));
                        return (
                          <tr key={unit.id}>
                            <td><strong>{unit.name}</strong></td>
                            <td>{property?.name ?? building?.name ?? "Property unavailable"}</td>
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
                  <p>Units are grouped under buildings. Add them to your property structure through Hodi.</p>
                </div>
              )}
            </section>
          </>
        )}
        <footer className="landlord-footer">Hodi property operations <span>·</span> Data synced from your organization</footer>
      </main>
    </div>
  );
}
