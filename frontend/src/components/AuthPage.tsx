"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import Image from "next/image";
import { Logo } from "@/components/layout/Logo";
import {
  AUTH_TOKEN_KEY,
  ClientApiError,
  clientApi,
  login as apiLogin,
  register as apiRegister,
  setStoredAuthToken,
  type AuthResponse,
} from "@/lib/clientApi";
import TenantLinkGate from "@/components/ops/TenantLinkGate";
import ThemeToggle from "@/components/theme/ThemeToggle";

type UserKind = "tenant" | "landlord";
type AuthMode = "signin" | "signup";
type OrganizationMembership = {
  organization_id: number | string;
  organization_name: string;
  role: string;
};
type WorkspaceOption = {
  path: string;
  label: string;
  description: string;
};

const ACCOUNT_TYPE: Record<UserKind, "TENANT" | "OWNER"> = {
  tenant: "TENANT",
  landlord: "OWNER",
};

function userKindFromAccountType(accountType?: string): UserKind | null {
  const type = (accountType || "").toUpperCase();
  if (type === "TENANT") return "tenant";
  if (type === "OWNER") return "landlord";
  return null;
}

function workspacesForAuth(
  auth: AuthResponse,
  memberships: OrganizationMembership[],
): WorkspaceOption[] {
  const workspaces = new Map<string, WorkspaceOption>();
  const addWorkspace = (path: string, label: string, description: string) => {
    workspaces.set(path, { path, label, description });
  };

  const accountKind = userKindFromAccountType(auth.account_type);
  if (accountKind === "tenant") {
    addWorkspace("/clients", "Tenant workspace", "View your tenancy, rent, and maintenance.");
  }

  for (const membership of memberships) {
    switch (membership.role) {
      case "OWNER":
      case "PROPERTY_MANAGER":
        addWorkspace("/landlords", "Property management", "Manage properties and organization operations.");
        break;
      case "ACCOUNTANT":
        addWorkspace("/accountants", "Accountant workspace", "Review invoices and recorded rent transactions.");
        break;
      case "CARETAKER":
        addWorkspace("/caretakers", "Caretaker workspace", "Manage maintenance requests and day-to-day operations.");
        break;
      case "TECHNICIAN":
        addWorkspace("/technicians", "Technician workspace", "Review and update your assigned repair work.");
        break;
    }
  }

  return Array.from(workspaces.values());
}

function dashboardFor(kind: UserKind) {
  return kind === "tenant" ? "/clients" : "/landlords";
}

function dashboardWithPlan(kind: UserKind) {
  const destination = dashboardFor(kind);
  const requestedPlan = new URLSearchParams(window.location.search).get("plan");
  if (kind !== "landlord" || !requestedPlan || !/^[a-z0-9-]{1,32}$/.test(requestedPlan)) {
    return destination;
  }
  return `/landlords?plan=${encodeURIComponent(requestedPlan)}#subscription`;
}

function errorText(error: unknown) {
  if (error instanceof ClientApiError) {
    const fields = error.fieldErrors();
    const fieldMessages = Object.values(fields).filter(Boolean);
    if (fieldMessages.length) return fieldMessages.join(" ");
    return error.message;
  }
  return error instanceof Error ? error.message : "Something went wrong. Please try again.";
}

/** Persist token + role from flat Django auth response; profile fields from the form when present. */
function rememberSession(
  auth: AuthResponse,
  profile: {
    first_name?: string;
    last_name?: string;
    email?: string;
    phone_number?: string;
  } = {},
  memberships: OrganizationMembership[] = [],
) {
  sessionStorage.setItem(AUTH_TOKEN_KEY, auth.token);
  sessionStorage.setItem("hodi_account_type", auth.account_type ?? "");
  sessionStorage.setItem("hodi_memberships", JSON.stringify(memberships));
  sessionStorage.setItem("hodi_first_name", profile.first_name ?? "");
  sessionStorage.setItem("hodi_last_name", profile.last_name ?? "");
  sessionStorage.setItem("hodi_email", profile.email ?? "");
  sessionStorage.setItem("hodi_phone_number", profile.phone_number ?? "");
}

function clearSession() {
  setStoredAuthToken(null);
  for (const key of [
    "hodi_account_type",
    "hodi_memberships",
    "hodi_first_name",
    "hodi_last_name",
    "hodi_email",
    "hodi_phone_number",
  ]) {
    sessionStorage.removeItem(key);
  }
}

function membershipsFromAuth(auth: AuthResponse): OrganizationMembership[] {
  const memberships = auth.memberships;
  if (!Array.isArray(memberships)) return [];
  return memberships.filter((membership): membership is OrganizationMembership => {
    if (!membership || typeof membership !== "object") return false;
    const item = membership as Record<string, unknown>;
    return (
      (typeof item.organization_id === "number" || typeof item.organization_id === "string") &&
      typeof item.organization_name === "string" &&
      typeof item.role === "string"
    );
  });
}

export default function AuthPage({ mode }: { mode: AuthMode }) {
  const [userKind, setUserKind] = useState<UserKind>("landlord");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [needsOrganizationLink, setNeedsOrganizationLink] = useState(false);
  const [tenantNeedsOrganizationLink, setTenantNeedsOrganizationLink] = useState(false);
  const [requestedPlan, setRequestedPlan] = useState("");
  const [workspaceOptions, setWorkspaceOptions] = useState<WorkspaceOption[]>([]);

  useEffect(() => {
    const type = new URLSearchParams(window.location.search).get("type");
    const plan = new URLSearchParams(window.location.search).get("plan");
    if (plan && /^[a-z0-9-]{1,32}$/.test(plan)) setRequestedPlan(plan);
    if (mode === "signup") {
      if (type === "tenant" || type === "client") setUserKind("tenant");
      if (type === "landlord" || type === "owner") setUserKind("landlord");
    }
  }, [mode]);

  function goToWorkspace(path: string) {
    if (path === "/clients" && tenantNeedsOrganizationLink) {
      setWorkspaceOptions([]);
      setNeedsOrganizationLink(true);
      return;
    }
    if (path === "/landlords") {
      window.location.assign(dashboardWithPlan("landlord"));
      return;
    }
    window.location.assign(path);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    const form = new FormData(event.currentTarget);
    const username = String(form.get("username") ?? "").trim();
    const password = String(form.get("password") ?? "");

    try {
      if (mode === "signup") {
        const profile = {
          first_name: String(form.get("first_name") ?? "").trim(),
          last_name: String(form.get("last_name") ?? "").trim(),
          email: String(form.get("email") ?? "").trim(),
          phone_number: String(form.get("phone_number") ?? "").trim(),
        };
        const password_confirm = String(form.get("password_confirm") ?? "");
        if (password !== password_confirm) {
          setError("Passwords do not match.");
          setIsSubmitting(false);
          return;
        }

        const organization_name = String(form.get("organization_name") ?? "").trim();
        if (userKind === "landlord" && !organization_name) {
          setError("Organization / company name is required for landlord accounts.");
          setIsSubmitting(false);
          return;
        }
        if (!username) {
          setError("Username is required.");
          setIsSubmitting(false);
          return;
        }

        const auth = await apiRegister({
          account_type: ACCOUNT_TYPE[userKind],
          username,
          ...profile,
          password,
          password_confirm,
          ...(userKind === "landlord" ? { organization_name } : {}),
        });

        const accountType = auth.account_type;
        const actualKind = userKindFromAccountType(accountType);
        if (!auth.token || !actualKind || actualKind !== userKind) {
          throw new Error(
            "Your account was created, but the API returned an unsupported account type.",
          );
        }
        rememberSession(auth, profile);
        if (actualKind === "tenant" && (auth.organization_id === null || auth.organization_id === undefined)) {
          setNeedsOrganizationLink(true);
          return;
        }
        window.location.assign(dashboardWithPlan(actualKind));
        return;
      }

      const auth = await apiLogin({ username, password });
      if (!auth.token) throw new Error("This account could not be signed in.");
      const memberships = membershipsFromAuth(auth);
      rememberSession(auth, {
        first_name: auth.first_name?.trim() || username,
        last_name: auth.last_name,
        email: auth.email || username,
        phone_number: auth.phone_number,
      }, memberships);

      const tenantNeedsOrganizationLink =
        auth.account_type?.toUpperCase() === "TENANT" &&
        (auth.organization_id === null || auth.organization_id === undefined);
      setTenantNeedsOrganizationLink(tenantNeedsOrganizationLink);
      const workspaces = workspacesForAuth(auth, memberships);
      let invitationLookupFailed = false;
      let invitations: Array<{ status: string; can_accept: boolean; expires_at: string }> = [];
      try {
        const response = await clientApi.get<Array<{ status: string; can_accept: boolean; expires_at: string }>>(
          "/api/v1/organizations/accountant-invitations/",
        );
        invitations = response.data;
      } catch {
        invitationLookupFailed = true;
      }
      if (invitations.some(invitation =>
        invitation.status === "PENDING" &&
        invitation.can_accept &&
        Date.parse(invitation.expires_at) > Date.now()
      )) {
        if (!workspaces.some(workspace => workspace.path === "/accountants")) {
          workspaces.push({
            path: "/accountants",
            label: "Accountant workspace",
            description: "Review and accept your organization invitation.",
          });
        }
      }

      if (workspaces.length > 1) {
        setWorkspaceOptions(workspaces);
        return;
      }
      if (workspaces.length === 1) {
        const workspace = workspaces[0];
        if (workspace.path === "/clients" && tenantNeedsOrganizationLink) {
          setNeedsOrganizationLink(true);
          return;
        }
        goToWorkspace(workspace.path);
        return;
      }

      if (invitationLookupFailed) {
        setError("Your sign-in succeeded, but Hodi could not load your workspace options. Please try again.");
        return;
      }

      clearSession();
      throw new Error(
        "Your sign-in succeeded, but this account has no active Hodi workspace yet. Ask an organization owner to invite you, or contact support.",
      );
    } catch (submitError) {
      setError(errorText(submitError));
    } finally {
      setIsSubmitting(false);
    }
  }

  const isSignup = mode === "signup";
  const authInputClass = isSignup ? "h-10 w-full min-w-0" : "h-11 w-full min-w-0";

  if (needsOrganizationLink) {
    return <TenantLinkGate onLinked={() => window.location.assign("/clients")} />;
  }

  if (workspaceOptions.length > 1) {
    return (
      <main className="min-h-screen bg-bg px-5 py-12 text-text sm:px-8">
        <div className="mx-auto w-full max-w-2xl">
          <div className="mb-8 flex items-center justify-between gap-3">
            <Logo size={40} className="w-fit" />
            <ThemeToggle />
          </div>
          <section className="rounded-2xl border border-border bg-surface p-7 shadow-soft sm:p-10">
            <p className="text-[10px] font-bold tracking-[0.16em] text-text-secondary">SIGNED IN</p>
            <h1 className="mt-3 font-display text-3xl font-semibold tracking-tight">Choose a workspace</h1>
            <p className="mt-2 text-sm leading-6 text-text-secondary">
              This account has access to more than one Hodi workspace. Choose where you want to go.
            </p>
            <div className="mt-6 grid gap-3">
              {workspaceOptions.map(workspace => (
                <button
                  key={workspace.path}
                  type="button"
                  onClick={() => goToWorkspace(workspace.path)}
                  className="rounded-xl border border-border bg-surface-raised p-4 text-left transition-colors hover:border-brand"
                >
                  <span className="block font-semibold">{workspace.label}</span>
                  <span className="mt-1 block text-sm text-text-secondary">{workspace.description}</span>
                </button>
              ))}
            </div>
          </section>
        </div>
      </main>
    );
  }

  return (
    <main
      className={`relative ${isSignup
        ? "min-h-screen bg-bg px-5 pt-5 pb-6 text-text sm:px-8 sm:pt-6"
        : "min-h-screen bg-bg px-5 py-12 text-text sm:px-8"
      }`}
    >
      <div className="mx-auto flex w-full max-w-5xl flex-col">
        <div className="flex items-center justify-between gap-3">
          <Logo size={40} className="w-fit" />
          <ThemeToggle />
        </div>
        <div className={`grid flex-1 items-center ${isSignup
          ? "gap-5 py-4 lg:grid-cols-[minmax(0,1fr)_440px] lg:gap-12 lg:py-5"
          : "gap-12 py-12 lg:grid-cols-[1fr_440px]"
        }`}>
          <section key={userKind} className="auth-story hidden self-stretch lg:flex auth-role-enter">
            <Image
              src="/images/living.jpg"
              alt=""
              fill
              sizes="(max-width: 1024px) 100vw, 52vw"
              className="auth-story-image"
            />
            <div className="auth-story-shade" aria-hidden="true" />
            <div className="auth-story-copy">
            <p className="auth-story-eyebrow">
              PROPERTY OPERATIONS, CONNECTED
            </p>
            <h1>
              {!isSignup
                ? "One sign-in for every Hodi workspace."
                : userKind === "landlord"
                  ? "Run your portfolio with clarity."
                  : "Feel at home with Hodi."}
            </h1>
            <p>
              {!isSignup
                ? "Sign in with your account. Hodi will take you to the workspaces your organization has granted you."
                : userKind === "landlord"
                  ? "Bring properties, tenants, leases, and everyday operations together in one workspace."
                  : "Keep your home, rent, and maintenance updates connected in one dependable place."}
            </p>
            </div>
          </section>

          <section className={`auth-form-panel w-full rounded-2xl border border-border bg-surface shadow-soft ${isSignup ? "p-4 sm:p-5" : "p-7 sm:p-10"}`}>
            <p key={userKind} className="text-[10px] font-bold tracking-[0.16em] text-text-secondary auth-role-enter">
              {!isSignup ? "HODI ACCOUNT" : userKind === "landlord" ? "LANDLORD PORTAL" : "CLIENT PORTAL"}
            </p>
            <h2 className={`${isSignup ? "mt-2 text-2xl" : "mt-3 text-3xl"} font-display font-semibold tracking-tight`}>
              {isSignup ? "Create your account" : "Welcome back"}
            </h2>
            <p className={`${isSignup ? "mt-1.5 text-xs leading-5 sm:text-sm" : "mt-2 text-sm leading-6"} text-text-secondary`}>
              {isSignup
                ? "Choose how you use Hodi to get started."
                : "Enter your account details. We’ll use your active access to choose the right workspace."}
            </p>

            {isSignup && <>
              <div className="mt-4 grid grid-cols-2 gap-2 rounded-lg bg-surface-raised p-1">
              {(["landlord", "tenant"] as const).map(kind => (
                <button
                  key={kind}
                  type="button"
                  aria-pressed={userKind === kind}
                  onClick={() => {
                    setUserKind(kind);
                    setError("");
                  }}
                  className={`min-h-9 rounded-md px-3 text-sm font-semibold transition-colors duration-300 ease-in-out ${
                    userKind === kind
                      ? "bg-brand text-brand-contrast shadow-sm"
                      : "text-text-secondary hover:text-text"
                  }`}
                >
                  {kind === "landlord" ? "Property owner" : "Tenant"}
                </button>
              ))}
              </div>
              <p className="mt-2 text-xs leading-5 text-text-secondary">
                Property managers, accountants, caretakers, and technicians get access through an organization invitation.
              </p>
            </>}

            <form className={`grid ${isSignup ? "mt-3 gap-2.5" : "mt-6 gap-4"}`} onSubmit={submit}>
              {isSignup && (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <label className="grid gap-1.5 text-xs font-semibold text-text-secondary">
                      First name
                      <input className={`${authInputClass} rounded-md border border-border px-3 text-sm`} name="first_name" autoComplete="given-name" required maxLength={150} />
                    </label>
                    <label className="grid gap-1.5 text-xs font-semibold text-text-secondary">
                      Last name
                      <input className={`${authInputClass} rounded-md border border-border px-3 text-sm`} name="last_name" autoComplete="family-name" required maxLength={150} />
                    </label>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="grid gap-1.5 text-xs font-semibold text-text-secondary">
                      Email
                      <input className={`${authInputClass} rounded-md border border-border px-3 text-sm`} name="email" type="email" autoComplete="email" required />
                    </label>
                    <label className="grid gap-1.5 text-xs font-semibold text-text-secondary">
                      Phone number
                      <input className={`${authInputClass} rounded-md border border-border px-3 text-sm`} name="phone_number" type="tel" autoComplete="tel" maxLength={30} />
                    </label>
                  </div>
                  {userKind === "landlord" && (
                    <label key={userKind} className="grid gap-1.5 text-xs font-semibold text-text-secondary auth-role-enter">
                      Organization name
                      <input className={`${authInputClass} rounded-md border border-border px-3 text-sm`} name="organization_name" required maxLength={200} placeholder="e.g. Acacia Property Group" />
                    </label>
                  )}
                </>
              )}
              <label className="grid gap-1.5 text-xs font-semibold text-text-secondary">
                Username
                <input className={`${authInputClass} rounded-md border border-border px-3 text-sm`} name="username" autoComplete="username" required maxLength={150} />
              </label>
              {isSignup && (
                <div className="grid grid-cols-2 gap-3">
                  <label className="grid gap-1.5 text-xs font-semibold text-text-secondary">
                    Password
                    <input className={`${authInputClass} rounded-md border border-border px-3 text-sm`} name="password" type="password" autoComplete="new-password" required minLength={8} />
                  </label>
                  <label className="grid gap-1.5 text-xs font-semibold text-text-secondary">
                    Confirm password
                    <input className={`${authInputClass} rounded-md border border-border px-3 text-sm`} name="password_confirm" type="password" autoComplete="new-password" required minLength={8} />
                  </label>
                </div>
              )}
              {!isSignup && (
                <label className="grid gap-1.5 text-xs font-semibold text-text-secondary">
                  Password
                  <input className={`${authInputClass} rounded-md border border-border px-3 text-sm`} name="password" type="password" autoComplete="current-password" required minLength={8} />
                </label>
              )}
              {error && <p className="m-0 text-sm text-error" role="alert">{error}</p>}
              <button
                type="submit"
                disabled={isSubmitting}
                className={`mt-1 inline-flex ${isSignup ? "min-h-10" : "min-h-11"} items-center justify-center rounded-md bg-brand px-5 text-sm font-semibold text-brand-contrast transition-colors hover:bg-brand-hover disabled:cursor-wait disabled:opacity-60`}
              >
                {isSubmitting
                  ? isSignup ? "Creating account…" : "Signing in…"
                  : isSignup ? "Create account" : "Sign in"}
              </button>
            </form>

            <p className={`${isSignup ? "mt-4" : "mt-6"} text-center text-sm text-text-secondary`}>
              {isSignup ? "Already have an account?" : "New to Hodi?"}{" "}
              <Link
                href={isSignup
                  ? `/signin${requestedPlan ? `?plan=${encodeURIComponent(requestedPlan)}` : ""}`
                  : `/signup?type=${userKind}${userKind === "landlord" && requestedPlan ? `&plan=${encodeURIComponent(requestedPlan)}` : ""}`}
                className="font-semibold text-brand hover:underline"
              >
                {isSignup ? "Sign in" : "Create an account"}
              </Link>
            </p>
          </section>
        </div>
      </div>
    </main>
  );
}
