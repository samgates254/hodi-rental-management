"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { clientApi, ClientApiError } from "@/lib/clientApi";
import { Logo } from "@/components/layout/Logo";

type UserKind = "tenant" | "landlord";
type AuthMode = "signin" | "signup";
type AuthResponse = {
  token: string;
  account_type: string;
};

const ACCOUNT_TYPE: Record<UserKind, "TENANT" | "OWNER"> = {
  tenant: "TENANT",
  landlord: "OWNER",
};

function userKindFromAccountType(accountType?: string): UserKind | null {
  if (accountType === "TENANT") return "tenant";
  if (accountType === "OWNER") return "landlord";
  return null;
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
  accountType: string,
  profile: { first_name?: string; last_name?: string; email?: string; phone_number?: string },
) {
  sessionStorage.setItem("hodi_api_token", token);
  sessionStorage.setItem("hodi_account_type", accountType);
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
        rememberSession(response.data.token, response.data.account_type, profile);
        window.location.assign(actualKind === "landlord" ? "/landlords" : "/clients");
        return;
      }

      const response = await clientApi.post<AuthResponse>("/api/v1/accounts/login/", {
        username,
        password,
      });
      const actualKind = userKindFromAccountType(response.data.account_type);
      if (!response.data.token || !actualKind) {
        throw new Error("This account type does not have a Hodi dashboard yet.");
      }
      rememberSession(response.data.token, response.data.account_type, {});
      window.location.assign(actualKind === "landlord" ? "/landlords" : "/clients");
    } catch (submitError) {
      setError(errorText(submitError));
    } finally {
      setIsSubmitting(false);
    }
  }

  const isSignup = mode === "signup";

  const modePath = isSignup ? "signup" : "signin";

  return (
    <main
      className={`bg-[#f7f8f7] px-5 text-[#19202a] sm:px-8 ${
        isSignup
          ? "auth-page-signup flex min-h-dvh flex-col py-5 sm:py-6"
          : "flex min-h-screen flex-col py-12"
      }`}
    >
      <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col">
        <Logo size={isSignup ? 36 : 40} className="w-fit shrink-0" />

        <div
          className={`grid flex-1 gap-10 lg:grid-cols-[1fr_440px] ${
            isSignup
              ? "min-h-0 items-start gap-8 pt-8 lg:items-start lg:pt-16"
              : "items-center gap-12 py-12"
          }`}
        >
          <section
            className={`hidden max-w-lg lg:block ${
              isSignup ? "pt-6 lg:pt-10" : ""
            }`}
          >
            <p className="text-xs font-bold tracking-[0.18em] text-[#0a9290]">
              PROPERTY OPERATIONS, CONNECTED
            </p>
            <h1
              className={`font-display font-semibold leading-tight tracking-tight ${
                isSignup
                  ? "mt-3 text-4xl xl:text-5xl"
                  : "mt-5 text-5xl"
              }`}
            >
              {userKind === "landlord"
                ? "Run your portfolio with clarity."
                : "Feel at home with Hodi."}
            </h1>
            <p
              className={`text-base text-[#687381] ${
                isSignup ? "mt-3 leading-6" : "mt-5 leading-7"
              }`}
            >
              {userKind === "landlord"
                ? "Bring properties, tenants, leases, and everyday operations together in one workspace."
                : "Keep your home, rent, and maintenance updates connected in one dependable place."}
            </p>
            <div className={`flex gap-3 text-sm ${isSignup ? "mt-5" : "mt-8"}`}>
              <Link
                className="font-semibold text-[#168582] underline-offset-4 hover:underline"
                href={`/${modePath}?type=landlord`}
              >
                Landlord access
              </Link>
              <span className="text-[#9ba4ac]">·</span>
              <Link
                className="font-semibold text-[#168582] underline-offset-4 hover:underline"
                href={`/${modePath}?type=tenant`}
              >
                Client access
              </Link>
            </div>
          </section>

          <section
            className={`w-full rounded-2xl border border-[#e6e8ec] bg-white shadow-[0_18px_50px_rgba(25,32,42,0.07)] ${
              isSignup
                ? "-mt-1 p-5 sm:p-6 lg:-mt-4"
                : "p-7 sm:p-10"
            }`}
          >
            <div className="flex items-end justify-between gap-4">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#0a9290]">
                  {isSignup ? "Create account" : "Welcome back"}
                </p>
                <h2
                  className={`text-2xl font-semibold tracking-tight ${
                    isSignup ? "mt-1.5" : "mt-2"
                  }`}
                >
                  {isSignup ? "Sign up" : "Sign in"}
                </h2>
              </div>
              <p className="hidden text-right text-sm text-[#687381] sm:block">
                {userKind === "landlord" ? "Landlord" : "Client / tenant"}
              </p>
            </div>

            <div
              className={`relative grid grid-cols-2 gap-2 rounded-xl bg-[#f3f5f4] p-1 ${
                isSignup ? "mt-4" : "mt-6"
              }`}
            >
              <span
                aria-hidden
                className={`pointer-events-none absolute inset-y-1 left-1 w-[calc(50%-0.375rem)] rounded-lg bg-[#0bacaa] shadow-sm transition-transform duration-300 ease-out ${
                  userKind === "tenant" ? "translate-x-[calc(100%+0.5rem)]" : "translate-x-0"
                }`}
              />
              {(["landlord", "tenant"] as const).map(kind => (
                <button
                  key={kind}
                  type="button"
                  onClick={() => setUserKind(kind)}
                  className={`relative z-10 rounded-lg px-3 text-sm transition-colors duration-300 ${
                    isSignup ? "py-2" : "py-2.5"
                  } ${
                    userKind === kind
                      ? "font-semibold text-white"
                      : "font-medium text-[#687381] hover:text-[#19202a]"
                  }`}
                >
                  {kind === "landlord" ? "Landlord" : "Client / tenant"}
                </button>
              ))}
            </div>

            <form
              className={`grid ${isSignup ? "mt-4 gap-2.5" : "mt-6 gap-4"}`}
              onSubmit={submit}
            >
              {isSignup && (
                <>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="grid gap-1 text-sm font-medium">
                      First name
                      <input
                        name="first_name"
                        className="auth-input"
                        autoComplete="given-name"
                        required
                      />
                    </label>
                    <label className="grid gap-1 text-sm font-medium">
                      Last name
                      <input
                        name="last_name"
                        className="auth-input"
                        autoComplete="family-name"
                        required
                      />
                    </label>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="grid gap-1 text-sm font-medium">
                      Email
                      <input
                        name="email"
                        className="auth-input"
                        type="email"
                        autoComplete="email"
                        required
                      />
                    </label>
                    <label className="grid gap-1 text-sm font-medium">
                      Phone number
                      <input
                        name="phone_number"
                        className="auth-input"
                        type="tel"
                        autoComplete="tel"
                        required
                      />
                    </label>
                  </div>
                  {userKind === "landlord" && (
                    <label className="grid gap-1 text-sm font-medium">
                      Organization name
                      <input name="organization_name" className="auth-input" required />
                    </label>
                  )}
                </>
              )}

              <label className={`grid text-sm font-medium ${isSignup ? "gap-1" : "gap-1.5"}`}>
                Username
                <input name="username" className="auth-input" autoComplete="username" required />
              </label>

              {isSignup ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="grid gap-1 text-sm font-medium">
                    Password
                    <input
                      name="password"
                      className="auth-input"
                      type="password"
                      autoComplete="new-password"
                      required
                    />
                  </label>
                  <label className="grid gap-1 text-sm font-medium">
                    Confirm password
                    <input
                      name="password_confirm"
                      className="auth-input"
                      type="password"
                      autoComplete="new-password"
                      required
                    />
                  </label>
                </div>
              ) : (
                <label className="grid gap-1.5 text-sm font-medium">
                  Password
                  <input
                    name="password"
                    className="auth-input"
                    type="password"
                    autoComplete="current-password"
                    required
                  />
                </label>
              )}

              {error ? (
                <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                  {error}
                </p>
              ) : null}

              <button
                type="submit"
                disabled={isSubmitting}
                className={`mt-1 inline-flex items-center justify-center rounded-xl bg-[#0bacaa] px-4 text-sm font-semibold text-white transition hover:bg-[#099693] disabled:cursor-not-allowed disabled:opacity-60 ${
                  isSignup ? "h-10" : "h-11"
                }`}
              >
                {isSubmitting ? "Please wait…" : isSignup ? "Create account" : "Sign in"}
              </button>
            </form>

            <p className={`text-center text-sm text-[#687381] ${isSignup ? "mt-4" : "mt-6"}`}>
              {isSignup ? "Already have an account?" : "New to Hodi?"}{" "}
              <Link
                href={isSignup ? `/signin?type=${userKind}` : `/signup?type=${userKind}`}
                className="font-semibold text-[#168582] underline-offset-4 hover:underline"
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
