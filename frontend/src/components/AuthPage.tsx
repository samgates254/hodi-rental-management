"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { Logo } from "@/components/layout/Logo";
import {
  AUTH_TOKEN_KEY,
  ClientApiError,
  dashboardPathForAccountType,
  login as apiLogin,
  register as apiRegister,
  type AuthResponse,
} from "@/lib/clientApi";
import TenantLinkGate from "@/components/ops/TenantLinkGate";
import ThemeToggle from "@/components/theme/ThemeToggle";
import { staffLoginKindForRole } from "@/lib/organizationRoles";

type UserKind = "tenant" | "landlord" | "caretaker" | "technician";
type AuthMode = "signin" | "signup";
type OrganizationMembership = {
  organization_id: number | string;
  organization_name: string;
  role: string;
};

const ACCOUNT_TYPE: Record<Exclude<UserKind, "caretaker" | "technician">, "TENANT" | "OWNER"> = {
  tenant: "TENANT",
  landlord: "OWNER",
};

function userKindFromAccountType(accountType?: string): UserKind | null {
  const type = (accountType || "").toUpperCase();
  if (type === "TENANT") return "tenant";
  // OWNER + service pros use the landlord app area today.
  if (type === "OWNER" || type === "SERVICE_PROFESSIONAL") {
    return "landlord";
  }
  return null;
}

function dashboardFor(kind: UserKind, accountType?: string) {
  if (kind === "caretaker") return "/caretakers";
  if (kind === "technician") return "/technicians";
  return dashboardPathForAccountType(accountType);
}

function dashboardWithPlan(kind: UserKind, accountType?: string) {
  const destination = dashboardFor(kind, accountType);
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

function membershipsFromAuth(auth: AuthResponse): OrganizationMembership[] {
  const memberships = (auth as AuthResponse & { memberships?: unknown }).memberships;
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
  const [requestedPlan, setRequestedPlan] = useState("");

  useEffect(() => {
    const type = new URLSearchParams(window.location.search).get("type");
    const plan = new URLSearchParams(window.location.search).get("plan");
    if (plan && /^[a-z0-9-]{1,32}$/.test(plan)) setRequestedPlan(plan);
    if (type === "tenant" || type === "client") setUserKind("tenant");
    if (type === "landlord" || type === "owner") setUserKind("landlord");
    if (type === "caretaker") setUserKind("caretaker");
    if (type === "technician") setUserKind("technician");
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    const form = new FormData(event.currentTarget);
    const username = String(form.get("username") ?? "").trim();
    const password = String(form.get("password") ?? "");

    try {
      if (mode === "signup") {
        if (userKind === "caretaker" || userKind === "technician") {
          throw new Error("Caretaker access is assigned by your property organization.");
        }
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
        window.location.assign(dashboardWithPlan(actualKind, accountType));
        return;
      }

      const auth = await apiLogin({ username, password });
      const memberships = membershipsFromAuth(auth);
      const hasCaretakerMembership = memberships.some(
        membership => staffLoginKindForRole(membership.role) === "caretaker",
      );
      const hasTechnicianMembership = memberships.some(
        membership => staffLoginKindForRole(membership.role) === "technician",
      );
      const hasLandlordMembership = memberships.some(membership =>
        membership.role === "OWNER" || staffLoginKindForRole(membership.role) === "landlord",
      );
      const actualKind = userKind === "caretaker"
        ? hasCaretakerMembership ? "caretaker" : null
        : userKind === "technician"
          ? hasTechnicianMembership ? "technician" : null
        : userKindFromAccountType(auth.account_type) ?? (hasLandlordMembership ? "landlord" : null);
      if (!auth.token || !actualKind) {
        throw new Error(userKind === "caretaker"
          ? "This account does not have an active caretaker membership."
          : userKind === "technician"
            ? "This account does not have an active technician membership."
          : "This account type does not have a Hodi dashboard yet.");
      }
      if (actualKind !== userKind) {
        const accessType = actualKind === "tenant" ? "client" : actualKind === "technician" ? "technician" : "landlord";
        throw new Error(`This account is set up for ${accessType} access.`);
      }
      rememberSession(auth, {
        first_name: auth.first_name?.trim() || username,
        last_name: auth.last_name,
        email: auth.email || username,
        phone_number: auth.phone_number,
      }, memberships);
      if (actualKind === "tenant" && (auth.organization_id === null || auth.organization_id === undefined)) {
        setNeedsOrganizationLink(true);
        return;
      }
      window.location.assign(dashboardWithPlan(actualKind, auth.account_type));
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
          <section key={userKind} className="hidden max-w-lg self-start pt-16 lg:block auth-role-enter">
            <p className="text-xs font-bold tracking-[0.18em] text-brand">
              PROPERTY OPERATIONS, CONNECTED
            </p>
            <h1 className={`${isSignup ? "mt-3 text-4xl" : "mt-5 text-5xl"} font-display font-semibold leading-tight tracking-tight`}>
              {userKind === "landlord"
                ? "Run your portfolio with clarity."
                : userKind === "caretaker"
                  ? "Keep property operations moving."
                  : userKind === "technician"
                    ? "Keep your assigned repair work moving."
                  : "Feel at home with Hodi."}
            </h1>
            <p className={`${isSignup ? "mt-3" : "mt-5"} text-base leading-7 text-text-secondary`}>
              {userKind === "landlord"
                ? "Bring properties, tenants, leases, and everyday operations together in one workspace."
                : userKind === "caretaker"
                  ? "Review maintenance requests, track their progress, and check residents’ rent status."
                  : userKind === "technician"
                    ? "Review only the work orders assigned to you and submit repair outcomes for verification."
                  : "Keep your home, rent, and maintenance updates connected in one dependable place."}
            </p>
            <div className={`${isSignup ? "mt-5" : "mt-8"} flex gap-3 text-sm`}>
              <Link className="font-semibold text-brand underline-offset-4 hover:underline" href="/signin?type=landlord">
                Landlord access
              </Link>
              <span className="text-text-secondary">·</span>
              <Link className="font-semibold text-brand underline-offset-4 hover:underline" href="/signin?type=tenant">
                Client access
              </Link>
            </div>
          </section>

          <section className={`w-full rounded-2xl border border-border bg-surface shadow-soft ${isSignup ? "p-4 sm:p-5" : "p-7 sm:p-10"}`}>
            <p key={userKind} className="text-[10px] font-bold tracking-[0.16em] text-text-secondary auth-role-enter">
              {userKind === "landlord" ? "LANDLORD PORTAL" : userKind === "caretaker" ? "CARETAKER PORTAL" : userKind === "technician" ? "TECHNICIAN PORTAL" : "CLIENT PORTAL"}
            </p>
            <h2 className={`${isSignup ? "mt-2 text-2xl" : "mt-3 text-3xl"} font-display font-semibold tracking-tight`}>
              {isSignup ? "Create your account" : "Welcome back"}
            </h2>
            <p className={`${isSignup ? "mt-1.5 text-xs leading-5 sm:text-sm" : "mt-2 text-sm leading-6"} text-text-secondary`}>
              {isSignup
                ? "Choose how you use Hodi to get started."
                : "Sign in to continue to your Hodi dashboard."}
            </p>

            <div className={`${isSignup ? "mt-4 grid-cols-2" : "mt-6 grid-cols-4"} grid gap-2 rounded-lg bg-surface-raised p-1`}>
              {(isSignup ? ["landlord", "tenant"] as const : ["landlord", "tenant", "caretaker", "technician"] as const).map(kind => (
                <button
                  key={kind}
                  type="button"
                  aria-pressed={userKind === kind}
                  onClick={() => {
                    setUserKind(kind);
                    setError("");
                  }}
                  className={`${isSignup ? "min-h-9 px-3 text-sm" : "min-h-10 min-w-0 whitespace-nowrap px-1 text-xs sm:px-2 sm:text-sm"} rounded-md font-semibold transition-colors duration-300 ease-in-out ${
                    userKind === kind
                      ? "bg-brand text-brand-contrast shadow-sm"
                      : "text-text-secondary hover:text-text"
                  }`}
                >
                  {kind === "landlord" ? "Landlord" : kind === "caretaker" ? "Caretaker" : kind === "technician" ? "Technician" : isSignup ? "Client / tenant" : "Tenant"}
                </button>
              ))}
            </div>

            {!isSignup && userKind === "caretaker" && (
              <p key="caretaker-access-hint" className="mt-2 text-xs leading-5 text-text-secondary auth-role-enter">
                Caretaker access is assigned by your property organization.
              </p>
            )}
            {!isSignup && userKind === "technician" && (
              <p key="technician-access-hint" className="mt-2 text-xs leading-5 text-text-secondary auth-role-enter">
                Technician access is assigned by your property organization.
              </p>
            )}
            {!isSignup && userKind === "landlord" && (
              <p key="landlord-access-hint" className="mt-2 text-xs leading-5 text-text-secondary auth-role-enter">
                Owners, property managers, and accountants use Landlord access.
              </p>
            )}

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

            {!isSignup && (userKind === "caretaker" || userKind === "technician") ? (
              <p className="mt-6 text-center text-sm text-text-secondary auth-role-enter">
                Need access? Contact your property organization.
              </p>
            ) : (
              <p className={`${isSignup ? "mt-4" : "mt-6"} text-center text-sm text-text-secondary`}>
                {isSignup ? "Already have an account?" : "New to Hodi?"}{" "}
                <Link
                  href={`${isSignup ? "/signin" : "/signup"}?type=${userKind}${userKind === "landlord" && requestedPlan ? `&plan=${encodeURIComponent(requestedPlan)}` : ""}`}
                  className="font-semibold text-brand hover:underline"
                >
                  {isSignup ? "Sign in" : "Create an account"}
                </Link>
              </p>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
