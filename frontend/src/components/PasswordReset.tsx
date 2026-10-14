"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { Logo } from "@/components/layout/Logo";
import ThemeToggle from "@/components/theme/ThemeToggle";
import { clientApi } from "@/lib/clientApi";

function ResetShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <main className="min-h-[70vh] bg-bg px-5 py-12 text-text sm:px-8">
      <div className="mx-auto w-full max-w-xl">
        <div className="mb-8 flex items-center justify-between gap-3">
          <Logo size={40} className="w-fit" />
          <ThemeToggle />
        </div>
        <section className="rounded-2xl border border-border bg-surface p-6 shadow-soft sm:p-9">
          <p className="text-[10px] font-bold tracking-[0.16em] text-text-secondary">ACCOUNT ACCESS</p>
          <h1 className="mt-3 font-[family-name:var(--hodi-editorial)] text-3xl font-normal tracking-tight">{title}</h1>
          {children}
        </section>
        <p className="mt-6 text-center text-sm text-text-secondary">
          <Link href="/signin" className="font-semibold text-brand hover:underline">Return to sign in</Link>
        </p>
      </div>
    </main>
  );
}

export function PasswordResetRequest() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await clientApi.post("/api/v1/accounts/password-reset/", { email: email.trim() }, { skipAuth: true });
      setSent(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The request could not be sent. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <ResetShell title="Reset your password">
      <p className="mt-3 text-sm leading-6 text-text-secondary">
        Enter the email address on your account. If it is active, Hodi will send instructions to reset your password.
      </p>
      {sent ? (
        <p className="mt-6 rounded-lg border border-border bg-bg p-4 text-sm leading-6" role="status">
          If an active account uses that email, reset instructions will be sent. Check your inbox for a secure link.
        </p>
      ) : (
        <form className="mt-6 grid gap-4" onSubmit={event => void submit(event)}>
          <label className="grid gap-1.5 text-sm font-medium text-text-secondary">
            Email address
            <input
              className="auth-input h-11"
              type="email"
              autoComplete="email"
              required
              maxLength={254}
              value={email}
              onChange={event => setEmail(event.target.value)}
            />
          </label>
          {error && <p className="text-sm text-error" role="alert">{error}</p>}
          <button type="submit" disabled={busy} className="inline-flex min-h-11 items-center justify-center rounded-md bg-brand px-5 text-sm font-semibold text-brand-contrast hover:bg-brand-hover disabled:cursor-wait disabled:opacity-60">
            {busy ? "Sending…" : "Send reset instructions"}
          </button>
        </form>
      )}
    </ResetShell>
  );
}

export function PasswordResetConfirm() {
  const [uid, setUid] = useState("");
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [complete, setComplete] = useState(false);

  useEffect(() => {
    const values = new URLSearchParams(window.location.hash.slice(1));
    setUid(values.get("uid") ?? "");
    setToken(values.get("token") ?? "");
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (password !== confirmPassword) {
      setError("The passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      await clientApi.post(
        "/api/v1/accounts/password-reset/confirm/",
        { uid: uid.trim(), token: token.trim(), password, password_confirm: confirmPassword },
        { skipAuth: true },
      );
      setComplete(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "This reset link could not be used. Request a new one.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <ResetShell title="Choose a new password">
      {complete ? (
        <div className="mt-5 grid gap-4">
          <p className="text-sm leading-6" role="status">Your password has been reset. Sign in with your new password.</p>
          <Link href="/signin" className="inline-flex min-h-11 items-center justify-center rounded-md bg-brand px-5 text-sm font-semibold text-brand-contrast hover:bg-brand-hover">
            Go to sign in
          </Link>
        </div>
      ) : (
        <>
          <p className="mt-3 text-sm leading-6 text-text-secondary">
            Use the secure link from your email. If it did not fill these fields, copy the reset values from the email.
          </p>
          <form className="mt-6 grid gap-4" onSubmit={event => void submit(event)}>
            <label className="grid gap-1.5 text-sm font-medium text-text-secondary">
              Reset user code
              <input className="auth-input h-11" autoComplete="off" required value={uid} onChange={event => setUid(event.target.value)} />
            </label>
            <label className="grid gap-1.5 text-sm font-medium text-text-secondary">
              Reset token
              <input className="auth-input h-11" autoComplete="off" required value={token} onChange={event => setToken(event.target.value)} />
            </label>
            <label className="grid gap-1.5 text-sm font-medium text-text-secondary">
              New password
              <input className="auth-input h-11" type="password" autoComplete="new-password" required minLength={8} value={password} onChange={event => setPassword(event.target.value)} />
            </label>
            <label className="grid gap-1.5 text-sm font-medium text-text-secondary">
              Confirm new password
              <input className="auth-input h-11" type="password" autoComplete="new-password" required minLength={8} value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} />
            </label>
            {error && <p className="text-sm text-error" role="alert">{error}</p>}
            <button type="submit" disabled={busy} className="inline-flex min-h-11 items-center justify-center rounded-md bg-brand px-5 text-sm font-semibold text-brand-contrast hover:bg-brand-hover disabled:cursor-wait disabled:opacity-60">
              {busy ? "Updating password…" : "Update password"}
            </button>
          </form>
        </>
      )}
    </ResetShell>
  );
}
