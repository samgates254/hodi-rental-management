"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { Logo } from "@/components/layout/Logo";
import ThemeToggle from "@/components/theme/ThemeToggle";
import { clientApi, setStoredAuthToken } from "@/lib/clientApi";

type VerificationResponse = {
  detail: string;
  token: string;
  account_type: string;
  first_name?: string;
  last_name?: string;
  email?: string;
  phone_number?: string;
};

export default function AgentEmailVerification() {
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [verified, setVerified] = useState(false);
  const [email, setEmail] = useState("");
  const [resendBusy, setResendBusy] = useState(false);
  const [resendSent, setResendSent] = useState(false);
  const [resendError, setResendError] = useState("");

  useEffect(() => {
    const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
    // Keep the single-use token out of browser history and subsequent navigation.
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
    if (!token) {
      setError("This verification link is missing or has expired. Request a new one below.");
      setBusy(false);
      return;
    }

    void clientApi
      .post<VerificationResponse>(
        "/api/v1/accounts/verify-email/",
        { token },
        { skipAuth: true },
      )
      .then(({ data }) => {
        if (!data.token || data.account_type !== "PROPERTY_AGENT") {
          throw new Error("The verification response was incomplete. Please sign in to continue.");
        }
        for (const key of ["hodi_first_name", "hodi_last_name", "hodi_email", "hodi_phone_number", "hodi_memberships"]) {
          window.sessionStorage.removeItem(key);
        }
        setStoredAuthToken(data.token);
        window.sessionStorage.setItem("hodi_account_type", data.account_type);
        window.sessionStorage.setItem("hodi_first_name", data.first_name ?? "");
        window.sessionStorage.setItem("hodi_last_name", data.last_name ?? "");
        window.sessionStorage.setItem("hodi_email", data.email ?? "");
        window.sessionStorage.setItem("hodi_phone_number", data.phone_number ?? "");
        window.sessionStorage.setItem("hodi_memberships", "[]");
        setVerified(true);
      })
      .catch((cause: unknown) => {
        setError(cause instanceof Error ? cause.message : "This verification link could not be used.");
      })
      .finally(() => setBusy(false));
  }, []);

  async function resend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setResendBusy(true);
    setResendError("");
    try {
      await clientApi.post(
        "/api/v1/accounts/email-verification/request/",
        { email: email.trim() },
        { skipAuth: true },
      );
      setResendSent(true);
    } catch (cause) {
      setResendError(cause instanceof Error ? cause.message : "The request could not be sent. Try again.");
    } finally {
      setResendBusy(false);
    }
  }

  return (
    <main className="min-h-[70vh] bg-bg px-5 py-12 text-text sm:px-8">
      <div className="mx-auto w-full max-w-xl">
        <div className="mb-8 flex items-center justify-between gap-3">
          <Logo size={40} className="w-fit" />
          <ThemeToggle />
        </div>
        <section className="hodi-auth-sheet">
          <p className="text-[10px] font-bold tracking-[0.16em] text-text-secondary">PROPERTY AGENT</p>
          <h1 className="mt-3 font-[family-name:var(--hodi-editorial)] text-3xl font-normal tracking-tight">
            {busy ? "Verifying your email" : verified ? "Email confirmed" : "Verification link unavailable"}
          </h1>
          {busy ? (
            <p className="mt-3 text-sm leading-6 text-text-secondary" role="status">Please wait while Hodi confirms your email address.</p>
          ) : verified ? (
            <div className="mt-4 grid gap-4">
              <p className="text-sm leading-6 text-text-secondary" role="status">
                Your email is confirmed. You can continue to your agent workspace and complete your profile.
              </p>
              <Link href="/agents" className="inline-flex min-h-11 items-center justify-center rounded-md bg-brand px-5 text-sm font-semibold text-brand-contrast hover:bg-brand-hover">
                Continue to agent workspace
              </Link>
            </div>
          ) : (
            <>
              <p className="mt-3 text-sm leading-6 text-text-secondary" role="alert">{error}</p>
              {resendSent ? (
                <p className="mt-5 rounded-lg border border-border bg-bg p-4 text-sm leading-6" role="status">
                  If an eligible account uses that email, new verification instructions will be sent.
                </p>
              ) : (
                <form className="mt-5 grid gap-4" onSubmit={event => void resend(event)}>
                  <label className="grid gap-1.5 text-sm font-medium text-text-secondary">
                    Account email
                    <input className="auth-input h-11" type="email" autoComplete="email" maxLength={254} required value={email} onChange={event => setEmail(event.target.value)} />
                  </label>
                  {resendError && <p className="text-sm text-error" role="alert">{resendError}</p>}
                  <button type="submit" disabled={resendBusy} className="inline-flex min-h-11 items-center justify-center rounded-md border border-border px-5 text-sm font-semibold hover:border-brand disabled:cursor-wait disabled:opacity-60">
                    {resendBusy ? "Sending…" : "Request a new verification link"}
                  </button>
                </form>
              )}
            </>
          )}
        </section>
        <p className="mt-6 text-center text-sm text-text-secondary">
          <Link href="/signin" className="font-semibold text-brand hover:underline">Return to sign in</Link>
        </p>
      </div>
    </main>
  );
}
