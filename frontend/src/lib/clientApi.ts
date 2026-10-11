type ApiRequestOptions = {
  params?: Record<string, string | number | boolean | readonly (string | number | boolean)[] | null | undefined>;
  responseType?: "json" | "blob";
  /** Skip attaching Authorization (e.g. public auth endpoints). */
  skipAuth?: boolean;
};

type ApiResponse<T> = { data: T };

/** Must match LandlordDashboard / ClientDashboard session key. */
export const AUTH_TOKEN_KEY = "hodi_api_token";

/**
 * Backend AccountProfile.AccountType values.
 * @see backend apps.accounts.models.AccountProfile
 */
export type AccountType =
  | "UNSPECIFIED"
  | "TENANT"
  | "OWNER"
  | "SERVICE_PROFESSIONAL"
  | string;

/**
 * Auth endpoints return a flat payload (not a nested user object):
 * { token, account_type, organization_id, professional_trade }
 */
export type AuthResponse = {
  token: string;
  first_name?: string;
  last_name?: string;
  email?: string;
  phone_number?: string;
  account_type?: AccountType;
  organization_id?: number | null;
  professional_trade?: string;
};

export type OrganizationOption = {
  id: number;
  name: string;
  slug?: string;
};

export type SignupPayload = {
  first_name: string;
  last_name: string;
  email: string;
  username: string;
  password: string;
  password_confirm: string;
  account_type: "OWNER" | "TENANT" | "SERVICE_PROFESSIONAL" | "UNSPECIFIED";
  organization_id?: number | null;
  organization_name?: string;
  phone_number?: string;
  professional_trade?: string;
};

export type LoginPayload = {
  username: string;
  password: string;
};

function apiBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_BASE_URL?.trim() ?? "";
  // Empty = same-origin (Next.js rewrites /api/v1 → Django).
  return raw.replace(/\/$/, "");
}

function buildUrl(path: string, params?: ApiRequestOptions["params"]): string {
  const base = apiBaseUrl();
  const normalized = path.startsWith("/") ? path : `/${path}`;
  const url =
    base && /^https?:\/\//i.test(base)
      ? new URL(`${base}${normalized}`)
      : new URL(
          `${base}${normalized}`,
          typeof window === "undefined" ? "http://localhost" : window.location.origin,
        );

  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null || value === "") continue;
      if (Array.isArray(value)) {
        for (const item of value) {
          if (item !== "") url.searchParams.append(key, String(item));
        }
      } else {
        url.searchParams.set(key, String(value));
      }
    }
  }

  if (base && /^https?:\/\//i.test(base)) {
    return url.toString();
  }
  return `${url.pathname}${url.search}`;
}

function readStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(AUTH_TOKEN_KEY);
}

export function getStoredAuthToken(): string | null {
  return readStoredToken();
}

export function setStoredAuthToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (!token) {
    window.sessionStorage.removeItem(AUTH_TOKEN_KEY);
    return;
  }
  window.sessionStorage.setItem(AUTH_TOKEN_KEY, token);
}

function formatErrorDetail(payload: unknown, status: number, statusText: string): string {
  if (status === 429) {
    if (payload && typeof payload === "object" && typeof (payload as { detail?: unknown }).detail === "string") {
      return String((payload as { detail: string }).detail);
    }
    return "Too many attempts. Please wait a minute and try again.";
  }

  if (status >= 500) {
    // Next rewrite / Django HTML error pages are not useful to show raw.
    if (typeof payload === "string" && /<!DOCTYPE|Internal Server Error/i.test(payload)) {
      return "Server error during signup. Confirm Django is running on http://127.0.0.1:8000 and check the Django terminal for the traceback.";
    }
  }

  if (!payload || typeof payload !== "object") {
    if (status === 0) {
      return "Could not reach the server. Is the API running?";
    }
    return statusText || `Request failed (${status})`;
  }

  const data = payload as Record<string, unknown>;

  if (typeof data.detail === "string" && data.detail.trim()) {
    return data.detail;
  }

  if (Array.isArray(data.non_field_errors) && data.non_field_errors.length) {
    return data.non_field_errors.map(String).join(" ");
  }

  const fieldMessages: string[] = [];
  for (const [key, value] of Object.entries(data)) {
    if (key === "detail" || key === "non_field_errors") continue;
    if (Array.isArray(value)) {
      fieldMessages.push(`${key}: ${value.map(String).join(" ")}`);
    } else if (typeof value === "string") {
      fieldMessages.push(`${key}: ${value}`);
    } else if (value && typeof value === "object") {
      fieldMessages.push(`${key}: ${JSON.stringify(value)}`);
    }
  }

  if (fieldMessages.length) return fieldMessages.join(" · ");
  if (status >= 500) {
    return "Server error during signup. Check the Django terminal for the traceback.";
  }
  return statusText || `Request failed (${status})`;
}

export class ClientApiError extends Error {
  status: number;
  payload: unknown;

  constructor(status: number, statusText: string, payload: unknown) {
    super(formatErrorDetail(payload, status, statusText));
    this.name = "ClientApiError";
    this.status = status;
    this.payload = payload;
  }

  /** Field-level DRF errors, e.g. { email: ["..."], password: ["..."] } */
  fieldErrors(): Record<string, string> {
    if (!this.payload || typeof this.payload !== "object") return {};
    const out: Record<string, string> = {};
    for (const [key, value] of Object.entries(this.payload as Record<string, unknown>)) {
      if (key === "detail" || key === "non_field_errors") continue;
      if (Array.isArray(value)) out[key] = value.map(String).join(" ");
      else if (typeof value === "string") out[key] = value;
    }
    return out;
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  options: ApiRequestOptions = {},
): Promise<ApiResponse<T>> {
  const headers: Record<string, string> = {
    Accept: "application/json",
  };

  if (!options.skipAuth) {
    const token = readStoredToken();
    if (token) headers.Authorization = `Token ${token}`;
  }

  let payload: BodyInit | undefined;
  if (body !== undefined && body !== null) {
    if (typeof FormData !== "undefined" && body instanceof FormData) {
      payload = body;
    } else {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.params), {
      method,
      headers,
      body: payload,
      credentials: "same-origin",
    });
  } catch {
    throw new ClientApiError(0, "Network Error", {
      detail: "Could not reach the server. Check that the API is running.",
    });
  }

  if (response.status === 204) {
    return { data: undefined as T };
  }

  const contentType = response.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");

  if (!response.ok) {
    let errorPayload: unknown = null;
    try {
      errorPayload = isJson ? await response.json() : await response.text();
    } catch {
      errorPayload = null;
    }
    throw new ClientApiError(response.status, response.statusText, errorPayload);
  }

  if (options.responseType === "blob") {
    const blob = await response.blob();
    return { data: blob as T };
  }

  if (!isJson) {
    const text = await response.text();
    return { data: text as T };
  }

  const data = (await response.json()) as T;
  return { data };
}

export const clientApi = {
  get<T>(path: string, options?: ApiRequestOptions) {
    return request<T>("GET", path, undefined, options);
  },
  post<T>(path: string, body?: unknown, options?: ApiRequestOptions) {
    return request<T>("POST", path, body, options);
  },
  put<T>(path: string, body?: unknown, options?: ApiRequestOptions) {
    return request<T>("PUT", path, body, options);
  },
  patch<T>(path: string, body?: unknown, options?: ApiRequestOptions) {
    return request<T>("PATCH", path, body, options);
  },
  delete<T>(path: string, options?: ApiRequestOptions) {
    return request<T>("DELETE", path, undefined, options);
  },
};

/** Django: POST /api/v1/accounts/login/ { username, password } */
export async function login(payload: LoginPayload): Promise<AuthResponse> {
  const { data } = await clientApi.post<AuthResponse>(
    "/api/v1/accounts/login/",
    payload,
    { skipAuth: true },
  );
  if (!data?.token) {
    throw new ClientApiError(500, "Invalid response", {
      detail: "Login succeeded but no token was returned.",
    });
  }
  setStoredAuthToken(data.token);
  if (typeof window !== "undefined" && data.account_type) {
    window.sessionStorage.setItem("hodi_account_type", data.account_type);
  }
  return data;
}

/** Django: POST /api/v1/accounts/signup/ */
export async function register(payload: SignupPayload): Promise<AuthResponse> {
  const { data } = await clientApi.post<AuthResponse>(
    "/api/v1/accounts/signup/",
    payload,
    { skipAuth: true },
  );
  if (!data?.token) {
    throw new ClientApiError(500, "Invalid response", {
      detail: "Signup succeeded but no token was returned.",
    });
  }
  setStoredAuthToken(data.token);
  if (typeof window !== "undefined" && data.account_type) {
    window.sessionStorage.setItem("hodi_account_type", data.account_type);
  }
  return data;
}

/** Django: POST /api/v1/accounts/logout/ (Token auth) → 204 */
export async function logout(): Promise<void> {
  try {
    await clientApi.post<void>("/api/v1/accounts/logout/", {});
  } catch (error) {
    // Always clear local session even if the token was already invalid.
    if (!(error instanceof ClientApiError) || (error.status !== 401 && error.status !== 403)) {
      setStoredAuthToken(null);
      if (typeof window !== "undefined") {
        window.sessionStorage.removeItem("hodi_account_type");
      }
      throw error;
    }
  }
  setStoredAuthToken(null);
  if (typeof window !== "undefined") {
    window.sessionStorage.removeItem("hodi_account_type");
    window.sessionStorage.removeItem("hodi_first_name");
    window.sessionStorage.removeItem("hodi_last_name");
    window.sessionStorage.removeItem("hodi_email");
    window.sessionStorage.removeItem("hodi_phone_number");
  }
}

/** Public org list for owner signup. */
export async function listOrganizations(): Promise<OrganizationOption[]> {
  const { data } = await clientApi.get<OrganizationOption[]>(
    "/api/v1/accounts/organizations/",
    { skipAuth: true },
  );
  return Array.isArray(data) ? data : [];
}

/** Public org list used when a tenant must link after signup. Linking itself is authenticated POST. */
export async function listTenantOrganizations(): Promise<OrganizationOption[]> {
  return listOrganizations();
}

export type MeResponse = {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  account_type: string;
  organization_id: number | null;
  professional_trade?: string;
  phone_number?: string;
  memberships: Array<{
    organization: number;
    organization_name: string;
    role: string;
    is_active: boolean;
  }>;
};

export async function fetchMe(): Promise<MeResponse> {
  const { data } = await clientApi.get<MeResponse>("/api/v1/accounts/me/");
  return data;
}

/** Django: POST /api/v1/accounts/tenant-organization/ { organization_id } */
export async function linkTenantOrganization(organizationId: number): Promise<{
  account_type: string;
  organization_id: number;
}> {
  const { data } = await clientApi.post<{ account_type: string; organization_id: number }>(
    "/api/v1/accounts/tenant-organization/",
    { organization_id: organizationId },
  );
  return data;
}

/** Route path after auth based on backend account_type. */
export function dashboardPathForAccountType(accountType: string | null | undefined): string {
  const type = (accountType || "").toUpperCase();
  if (type === "TENANT") return "/clients";
  // OWNER and SERVICE_PROFESSIONAL use the landlord/ops area today.
  return "/landlords";
}
