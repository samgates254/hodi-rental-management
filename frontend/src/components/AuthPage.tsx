"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { clientApi, ClientApiError } from "@/lib/clientApi";

type UserKind = "tenant" | "landlord" | "caretaker";
type AuthMode = "signin" | "signup";
type AuthResponse = {
  token: string;
  account_type?: string;
  memberships?: Array<{
    organization_id: number | string;
    organization_name: string;
    role: string;
  }>;
};

const ACCOUNT_TYPE: Record<Exclude<UserKind, "caretaker">, "TENANT" | "OWNER"> = {
  tenant: "TENANT",
  landlord: "OWNER",
};

function userKindFromAccountType(accountType?: string): UserKind | null {
  if (accountType === "TENANT") return "tenant";
  if (accountType === "OWNER") return "landlord";
  return null;
}

function dashboardFor(kind: UserKind) {
  if (kind === "caretaker") return "/caretakers";
  return kind === "landlord" ? "/landlords" : "/clients";
}

function errorText(error: unknown) {
  if (error instanceof ClientApiError) {
    const payload = error.data;
    if (payload && typeof payload === "object") {
      const messages = Object.values(payload as Record<string, unknown>)
        .flatMap(value => Array.isArray(value) ? value : [value])
        .filter((value): value is string => typeof value === "string");
      if (messages.length) return messages.join(" ");
    }
    return error.message;
  }
  return error instanceof Error ? error.message : "Something went wrong. Please try again.";
}

function rememberSession(
  token: string,
  accountType: string | undefined,
  profile: { first_name?: string; last_name?: string; email?: string; phone_number?: string },
  memberships: AuthResponse["memberships"] = [],
) {
  sessionStorage.setItem("hodi_api_token", token);
  sessionStorage.setItem("hodi_account_type", accountType ?? "");
  sessionStorage.setItem("hodi_memberships", JSON.stringify(memberships));
  sessionStorage.setItem("hodi_first_name", profile.first_name ?? "");
  sessionStorage.setItem("hodi_last_name", profile.last_name ?? "");
  sessionStorage.setItem("hodi_email", profile.email ?? "");
  sessionStorage.setItem("hodi_phone_number", profile.phone_number ?? "");
}

export default function AuthPage({ mode }: { mode: AuthMode }) {
  const [userKind, setUserKind] = useState<UserKind>("landlord");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const type = new URLSearchParams(window.location.search).get("type");
    if (type === "tenant" || type === "client") setUserKind("tenant");
    if (type === "landlord" || type === "owner") setUserKind("landlord");
    if (type === "caretaker") setUserKind("caretaker");
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
        if (userKind === "caretaker") {
          throw new Error("Caretaker access is assigned by your property organization.");
        }
        const profile = {
          first_name: String(form.get("first_name") ?? "").trim(),
          last_name: String(form.get("last_name") ?? "").trim(),
          email: String(form.get("email") ?? "").trim(),
          phone_number: String(form.get("phone_number") ?? "").trim(),
        };
        const response = await clientApi.post<AuthResponse>("/api/v1/accounts/signup/", {
          account_type: ACCOUNT_TYPE[userKind],
          username,
          ...profile,
          ...(userKind === "landlord"
            ? { organization_name: String(form.get("organization_name") ?? "").trim() }
            : {}),
          password,
          password_confirm: String(form.get("password_confirm") ?? ""),
        });
        const actualKind = userKindFromAccountType(response.data.account_type);
        if (!response.data.token || !actualKind) {
          throw new Error("Your account was created, but the API returned an unsupported account type.");
        }
        rememberSession(response.data.token, response.data.account_type, profile, response.data.memberships);
        window.location.assign(dashboardFor(actualKind));
        return;
      }

      const response = await clientApi.post<AuthResponse>("/api/v1/accounts/login/", {
        username,
        password,
      });
      const hasCaretakerMembership = response.data.memberships?.some(
        membership => membership.role === "CARETAKER",
      ) ?? false;
      const actualKind = userKind === "caretaker"
        ? hasCaretakerMembership ? "caretaker" : null
        : userKindFromAccountType(response.data.account_type);
      if (!response.data.token || !actualKind) {
        throw new Error(userKind === "caretaker"
          ? "This account does not have an active caretaker membership."
          : "This account type does not have a Hodi dashboard yet.");
      }
      if (actualKind !== userKind) {
        throw new Error(`This account is set up for ${actualKind === "tenant" ? "client" : "caretaker"} access.`);
      }
      rememberSession(response.data.token, response.data.account_type, {}, response.data.memberships);
      window.location.assign(dashboardFor(actualKind));
    } catch (submitError) {
      setError(errorText(submitError));
    } finally {
      setIsSubmitting(false);
    }
  }

  const isSignup = mode === "signup";

  return (
    <main className="min-h-screen bg-[#f7f8f7] px-5 py-12 text-[#19202a] sm:px-8">
      <div className="mx-auto flex w-full max-w-5xl flex-col">
        <Link href="/" className="w-fit text-3xl font-extrabold tracking-[-0.08em]">
          hodi<span className="text-[#0bacaa]">.</span>
        </Link>
        <div className="grid flex-1 items-center gap-12 py-12 lg:grid-cols-[1fr_440px]">
          <section className="hidden max-w-lg lg:block">
            <p className="text-xs font-bold tracking-[0.18em] text-[#0a9290]">
              PROPERTY OPERATIONS, CONNECTED
            </p>
            <h1 className="mt-5 font-display text-5xl font-semibold leading-tight tracking-tight">
              {userKind === "landlord"
                ? "Run your portfolio with clarity."
                : userKind === "caretaker"
                  ? "Keep property operations moving."
                  : "Feel at home with Hodi."}
            </h1>
            <p className="mt-5 text-base leading-7 text-[#687381]">
              {userKind === "landlord"
                ? "Bring properties, tenants, leases, and everyday operations together in one workspace."
                : userKind === "caretaker"
                  ? "Review maintenance requests, track their progress, and check residents’ rent status."
                  : "Keep your home, rent, and maintenance updates connected in one dependable place."}
            </p>
            <div className="mt-8 flex gap-3 text-sm">
              <Link className="font-semibold text-[#168582] underline-offset-4 hover:underline" href="/signin?type=landlord">
                Landlord access
              </Link>
              <span className="text-[#9ba4ac]">·</span>
              <Link className="font-semibold text-[#168582] underline-offset-4 hover:underline" href="/signin?type=tenant">
                Client access
              </Link>
            </div>
          </section>

          <section className="w-full rounded-2xl border border-[#e6e8ec] bg-white p-7 shadow-[0_18px_50px_rgba(25,32,42,0.07)] sm:p-10">
            <p className="text-[10px] font-bold tracking-[0.16em] text-[#778391]">
              {userKind === "landlord" ? "LANDLORD PORTAL" : userKind === "caretaker" ? "CARETAKER PORTAL" : "CLIENT PORTAL"}
            </p>
            <h2 className="mt-3 font-display text-3xl font-semibold tracking-tight">
              {isSignup ? "Create your account" : "Welcome back"}
            </h2>
            <p className="mt-2 text-sm leading-6 text-[#687381]">
              {isSignup
                ? "Choose how you use Hodi to get started."
                : "Sign in to continue to your Hodi dashboard."}
            </p>

            <div className="mt-6 grid grid-cols-2 gap-2 rounded-lg bg-[#f3f5f5] p-1">
              {(isSignup ? ["landlord", "tenant"] as const : ["landlord", "tenant", "caretaker"] as const).map(kind => (
                <button
                  key={kind}
                  type="button"
                  aria-pressed={userKind === kind}
                  onClick={() => {
                    setUserKind(kind);
                    setError("");
                  }}
                  className={`min-h-10 rounded-md px-3 text-sm font-semibold transition-colors ${
                    userKind === kind
                      ? "bg-white text-[#19202a] shadow-sm"
                      : "text-[#687381] hover:text-[#19202a]"
                  }`}
                >
                  {kind === "landlord" ? "Landlord" : kind === "caretaker" ? "Caretaker" : "Client / tenant"}
                </button>
              ))}
            </div>

            <form className="mt-6 grid gap-4" onSubmit={submit}>
              {isSignup && (
                <>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="grid gap-1.5 text-xs font-semibold text-[#46515d]">
                      First name
                      <input className="h-11 rounded-md border border-[#dce1e5] px-3 text-sm" name="first_name" autoComplete="given-name" required maxLength={150} />
                    </label>
                    <label className="grid gap-1.5 text-xs font-semibold text-[#46515d]">
                      Last name
                      <input className="h-11 rounded-md border border-[#dce1e5] px-3 text-sm" name="last_name" autoComplete="family-name" required maxLength={150} />
                    </label>
                  </div>
                  <label className="grid gap-1.5 text-xs font-semibold text-[#46515d]">
                    Email
                    <input className="h-11 rounded-md border border-[#dce1e5] px-3 text-sm" name="email" type="email" autoComplete="email" required />
                  </label>
                  <label className="grid gap-1.5 text-xs font-semibold text-[#46515d]">
                    Phone number
                    <input className="h-11 rounded-md border border-[#dce1e5] px-3 text-sm" name="phone_number" type="tel" autoComplete="tel" maxLength={30} />
                  </label>
                  {userKind === "landlord" && (
                    <label className="grid gap-1.5 text-xs font-semibold text-[#46515d]">
                      Organization name
                      <input className="h-11 rounded-md border border-[#dce1e5] px-3 text-sm" name="organization_name" required maxLength={200} placeholder="e.g. Acacia Property Group" />
                    </label>
                  )}
                </>
              )}
              <label className="grid gap-1.5 text-xs font-semibold text-[#46515d]">
                Username
                <input className="h-11 rounded-md border border-[#dce1e5] px-3 text-sm" name="username" autoComplete="username" required maxLength={150} />
              </label>
              <label className="grid gap-1.5 text-xs font-semibold text-[#46515d]">
                Password
                <input className="h-11 rounded-md border border-[#dce1e5] px-3 text-sm" name="password" type="password" autoComplete={isSignup ? "new-password" : "current-password"} required minLength={8} />
              </label>
              {isSignup && (
                <label className="grid gap-1.5 text-xs font-semibold text-[#46515d]">
                  Confirm password
                  <input className="h-11 rounded-md border border-[#dce1e5] px-3 text-sm" name="password_confirm" type="password" autoComplete="new-password" required minLength={8} />
                </label>
              )}
              {error && <p className="m-0 text-sm text-[#a52d2d]" role="alert">{error}</p>}
              <button
                type="submit"
                disabled={isSubmitting}
                className="mt-1 inline-flex min-h-11 items-center justify-center rounded-md bg-[#0bacaa] px-5 text-sm font-semibold text-white transition-colors hover:bg-[#099996] disabled:cursor-wait disabled:opacity-60"
              >
                {isSubmitting
                  ? isSignup ? "Creating account…" : "Signing in…"
                  : isSignup ? "Create account" : "Sign in"}
              </button>
            </form>

            <p className="mt-6 text-center text-sm text-[#687381]">
              {isSignup ? "Already have an account?" : "New to Hodi?"}{" "}
              <Link
                href={`${isSignup ? "/signin" : userKind === "caretaker" ? "/signin" : "/signup"}?type=${userKind}`}
                className="font-semibold text-[#087d7a] hover:underline"
              >
                {isSignup ? "Sign in" : userKind === "caretaker" ? "Caretaker access is assigned by your organization" : "Create an account"}
              </Link>
            </p>
          </section>
        </div>
      </div>
    </main>
  );
}
