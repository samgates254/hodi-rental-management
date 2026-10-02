"use client";

import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { contactEmail } from "@/lib/site";

export const contactReasons = [
  { id: "demo", label: "Book a demo", subject: "Book a demo" },
  { id: "management", label: "Property management", subject: "Property management" },
  { id: "portfolio", label: "Portfolio / ownership", subject: "Portfolio / ownership" },
  { id: "partnership", label: "Partnership", subject: "Partnership" },
  { id: "support", label: "Support", subject: "Support" },
  { id: "other", label: "Something else", subject: "General inquiry" },
] as const;

export type ContactReasonId = (typeof contactReasons)[number]["id"];

const portfolioSizes = [
  { value: "", label: "Select range" },
  { value: "1-5", label: "1–5 units" },
  { value: "6-20", label: "6–20 units" },
  { value: "21-50", label: "21–50 units" },
  { value: "51-200", label: "51–200 units" },
  { value: "200+", label: "200+ units" },
  { value: "na", label: "Not applicable" },
] as const;

type FieldName =
  | "name"
  | "email"
  | "phone"
  | "company"
  | "reason"
  | "portfolio"
  | "subject"
  | "message";

type FormState = Record<FieldName, string>;
type FieldErrors = Partial<Record<FieldName, string>>;
type Status = "idle" | "submitting" | "success" | "error";

const initial: FormState = {
  name: "",
  email: "",
  phone: "",
  company: "",
  reason: "",
  portfolio: "",
  subject: "",
  message: "",
};

function validate(values: FormState): FieldErrors {
  const errors: FieldErrors = {};

  if (!values.name.trim()) {
    errors.name = "Please enter your name.";
  }

  const email = values.email.trim();
  if (!email) {
    errors.email = "Please enter your email.";
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    errors.email = "Enter a valid email address.";
  }

  if (!values.reason) {
    errors.reason = "Choose what this is about.";
  }

  if (!values.subject.trim()) {
    errors.subject = "Please add a subject.";
  }

  if (!values.message.trim()) {
    errors.message = "Please write a short message.";
  } else if (values.message.trim().length < 12) {
    errors.message = "Add a little more detail — at least a sentence.";
  }

  return errors;
}

function reasonLabel(id: string) {
  return contactReasons.find((r) => r.id === id)?.label ?? id;
}

function subjectFor(reason: string) {
  return contactReasons.find((r) => r.id === reason)?.subject ?? "";
}

function buildMailto(values: FormState): string {
  const subject = encodeURIComponent(
    values.subject.trim() || "Message from Hodi website",
  );
  const lines = [
    values.message.trim(),
    "",
    "—",
    `Name: ${values.name.trim()}`,
    `Email: ${values.email.trim()}`,
    values.phone.trim() ? `Phone: ${values.phone.trim()}` : null,
    values.company.trim() ? `Company / property: ${values.company.trim()}` : null,
    values.reason ? `Reason: ${reasonLabel(values.reason)}` : null,
    values.portfolio ? `Portfolio size: ${values.portfolio}` : null,
  ].filter(Boolean);

  const body = encodeURIComponent(lines.join("\n"));
  return `mailto:${contactEmail}?subject=${subject}&body=${body}`;
}

type ContactFormProps = {
  /** Prefill / controlled reason from page chips */
  reasonId?: string;
  onReasonIdChange?: (id: string) => void;
  className?: string;
};

export function ContactForm({
  reasonId,
  onReasonIdChange,
  className,
}: ContactFormProps) {
  const formId = useId();
  const [values, setValues] = useState<FormState>(initial);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [touched, setTouched] = useState<Partial<Record<FieldName, boolean>>>(
    {},
  );
  const [status, setStatus] = useState<Status>("idle");

  // Sync external chip selection into the form
  useEffect(() => {
    if (reasonId === undefined) return;
    const match = contactReasons.find((r) => r.id === reasonId);
    setValues((prev) => {
      const nextReason = reasonId;
      const nextSubject =
        match && (!prev.subject.trim() || prev.subject === subjectFor(prev.reason))
          ? match.subject
          : prev.subject;
      return { ...prev, reason: nextReason, subject: nextSubject };
    });
    if (reasonId) {
      setErrors((prev) => {
        if (!prev.reason && !prev.subject) return prev;
        const copy = { ...prev };
        delete copy.reason;
        if (match) delete copy.subject;
        return copy;
      });
    }
  }, [reasonId]);

  function nextValues(
    prev: FormState,
    name: FieldName,
    value: string,
  ): FormState {
    const next = { ...prev, [name]: value };
    if (name === "reason") {
      const match = contactReasons.find((r) => r.id === value);
      if (
        match &&
        (!prev.subject.trim() || prev.subject === subjectFor(prev.reason))
      ) {
        next.subject = match.subject;
      }
    }
    return next;
  }

  function setField(name: FieldName, value: string) {
    const next = nextValues(values, name, value);
    setValues(next);
    if (name === "reason") {
      onReasonIdChange?.(value);
    }
    if (touched[name] || errors[name]) {
      const nextErrors = validate(next);
      setErrors((e) => {
        const copy = { ...e };
        if (nextErrors[name]) copy[name] = nextErrors[name];
        else delete copy[name];
        if (name === "reason" && !nextErrors.subject) delete copy.subject;
        return copy;
      });
    }
  }

  function onBlur(name: FieldName) {
    setTouched((prev) => ({ ...prev, [name]: true }));
    const nextErrors = validate(values);
    setErrors((prev) => {
      const copy = { ...prev };
      if (nextErrors[name]) copy[name] = nextErrors[name];
      else delete copy[name];
      return copy;
    });
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const nextErrors = validate(values);
    setErrors(nextErrors);
    setTouched({
      name: true,
      email: true,
      phone: true,
      company: true,
      reason: true,
      portfolio: true,
      subject: true,
      message: true,
    });

    if (Object.keys(nextErrors).length > 0) {
      setStatus("idle");
      const first = (
        ["name", "email", "reason", "subject", "message"] as FieldName[]
      ).find((k) => nextErrors[k]);
      if (first) {
        document.getElementById(`${formId}-${first}`)?.focus();
      }
      return;
    }

    setStatus("submitting");

    try {
      // No contact API in this repo yet — open a real mailto with the message.
      // Swap this block for a POST when an endpoint exists.
      const href = buildMailto(values);
      window.location.href = href;
      setStatus("success");
    } catch {
      setStatus("error");
    }
  }

  if (status === "success") {
    return (
      <div
        className={cn(
          "border border-border border-l-[3px] border-l-teal bg-bg px-6 py-10 sm:px-8",
          className,
        )}
        role="status"
      >
        <p className="text-sm font-medium tracking-wide text-teal">Message ready</p>
        <h3 className="mt-3 font-display text-2xl font-semibold tracking-[-0.02em] text-charcoal">
          Your email draft is open.
        </h3>
        <p className="mt-3 max-w-md text-sm leading-relaxed text-text-secondary sm:text-base">
          Send it from your mail app to reach us at{" "}
          <span className="font-medium text-charcoal">{contactEmail}</span>.
          If nothing opened, check your browser’s pop-up or mail settings.
        </p>
        <ul className="mt-6 space-y-2 text-sm leading-relaxed text-text-secondary">
          <li className="flex gap-2">
            <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-teal" aria-hidden />
            We read every message — usually within one business day.
          </li>
          <li className="flex gap-2">
            <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-teal" aria-hidden />
            For demos, include portfolio size and the tools you use today.
          </li>
        </ul>
        <div className="mt-8">
          <Button
            type="button"
            variant="secondary"
            size="md"
            onClick={() => {
              setValues(initial);
              setErrors({});
              setTouched({});
              setStatus("idle");
              onReasonIdChange?.("");
            }}
          >
            Write another message
          </Button>
        </div>
      </div>
    );
  }

  return (
    <form
      id="contact-form"
      onSubmit={onSubmit}
      noValidate
      className={cn("flex flex-col gap-5", className)}
      aria-describedby={status === "error" ? `${formId}-form-error` : undefined}
    >
      <div className="grid gap-5 sm:grid-cols-2">
        <Field
          id={`${formId}-name`}
          label="Name"
          error={errors.name}
        >
          <input
            id={`${formId}-name`}
            name="name"
            type="text"
            autoComplete="name"
            value={values.name}
            onChange={(e) => setField("name", e.target.value)}
            onBlur={() => onBlur("name")}
            aria-invalid={Boolean(errors.name)}
            aria-describedby={errors.name ? `${formId}-name-err` : undefined}
            className={inputClass(Boolean(errors.name))}
          />
        </Field>

        <Field
          id={`${formId}-email`}
          label="Email"
          error={errors.email}
        >
          <input
            id={`${formId}-email`}
            name="email"
            type="email"
            autoComplete="email"
            value={values.email}
            onChange={(e) => setField("email", e.target.value)}
            onBlur={() => onBlur("email")}
            aria-invalid={Boolean(errors.email)}
            aria-describedby={errors.email ? `${formId}-email-err` : undefined}
            className={inputClass(Boolean(errors.email))}
          />
        </Field>
      </div>

      <div className="grid gap-5 sm:grid-cols-2">
        <Field
          id={`${formId}-phone`}
          label="Phone"
          optional
          error={errors.phone}
        >
          <input
            id={`${formId}-phone`}
            name="phone"
            type="tel"
            autoComplete="tel"
            value={values.phone}
            onChange={(e) => setField("phone", e.target.value)}
            onBlur={() => onBlur("phone")}
            className={inputClass(false)}
          />
        </Field>

        <Field
          id={`${formId}-company`}
          label="Company / property"
          optional
          error={errors.company}
        >
          <input
            id={`${formId}-company`}
            name="company"
            type="text"
            autoComplete="organization"
            value={values.company}
            onChange={(e) => setField("company", e.target.value)}
            onBlur={() => onBlur("company")}
            className={inputClass(false)}
          />
        </Field>
      </div>

      <fieldset>
        <legend className="text-sm font-medium text-charcoal">
          What is this about? <span className="text-text-secondary">Required</span>
        </legend>
        <div
          className="mt-3 flex flex-wrap gap-2"
          role="group"
          aria-describedby={errors.reason ? `${formId}-reason-err` : undefined}
        >
          {contactReasons.map((r) => {
            const selected = values.reason === r.id;
            return (
              <button
                key={r.id}
                id={r.id === values.reason ? `${formId}-reason` : undefined}
                type="button"
                onClick={() => setField("reason", r.id)}
                aria-pressed={selected}
                className={cn(
                  "rounded-full border px-3.5 py-1.5 text-sm transition-colors",
                  selected
                    ? "border-teal bg-soft-teal text-charcoal"
                    : "border-border bg-surface text-text-secondary hover:border-charcoal/25 hover:text-charcoal",
                )}
              >
                {r.label}
              </button>
            );
          })}
        </div>
        {errors.reason ? (
          <p id={`${formId}-reason-err`} className="mt-2 text-sm text-charcoal" role="alert">
            {errors.reason}
          </p>
        ) : null}
        {/* Hidden input so native form semantics still carry reason */}
        <input type="hidden" name="reason" value={values.reason} />
      </fieldset>

      <Field
        id={`${formId}-portfolio`}
        label="Portfolio size"
        optional
        error={errors.portfolio}
      >
        <PortfolioSizeSelect
          id={`${formId}-portfolio`}
          name="portfolio"
          value={values.portfolio}
          invalid={Boolean(errors.portfolio)}
          onChange={(next) => setField("portfolio", next)}
          onBlur={() => onBlur("portfolio")}
        />
      </Field>

      <Field
        id={`${formId}-subject`}
        label="Subject"
        error={errors.subject}
      >
        <input
          id={`${formId}-subject`}
          name="subject"
          type="text"
          value={values.subject}
          onChange={(e) => setField("subject", e.target.value)}
          onBlur={() => onBlur("subject")}
          aria-invalid={Boolean(errors.subject)}
          aria-describedby={errors.subject ? `${formId}-subject-err` : undefined}
          className={inputClass(Boolean(errors.subject))}
        />
      </Field>

      <Field
        id={`${formId}-message`}
        label="Message"
        error={errors.message}
      >
        <textarea
          id={`${formId}-message`}
          name="message"
          rows={5}
          value={values.message}
          onChange={(e) => setField("message", e.target.value)}
          onBlur={() => onBlur("message")}
          aria-invalid={Boolean(errors.message)}
          aria-describedby={errors.message ? `${formId}-message-err` : undefined}
          placeholder="Tell us about your property, tools you use today, or what you want to solve."
          className={cn(inputClass(Boolean(errors.message)), "resize-y min-h-[8rem]")}
        />
      </Field>

      {status === "error" ? (
        <p
          id={`${formId}-form-error`}
          className="text-sm text-charcoal"
          role="alert"
        >
          Something went wrong preparing your message. Email us directly at{" "}
          <a className="font-medium text-teal underline-offset-2 hover:underline" href={`mailto:${contactEmail}`}>
            {contactEmail}
          </a>
          .
        </p>
      ) : null}

      <div className="flex flex-col gap-3 border-t border-border pt-5 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs leading-relaxed text-text-secondary sm:max-w-xs">
          Opens your email app with a draft to {contactEmail}. No account required.
        </p>
        <Button
          type="submit"
          size="lg"
          disabled={status === "submitting"}
          className="w-full sm:w-auto"
        >
          {status === "submitting" ? "Preparing…" : "Send message"}
        </Button>
      </div>
    </form>
  );
}

function inputClass(invalid: boolean) {
  return cn(
    "w-full rounded-md border bg-surface px-3.5 py-2.5 text-sm text-charcoal shadow-none",
    "outline-none transition-[border-color,box-shadow]",
    "placeholder:text-text-secondary/70",
    "focus:border-teal focus:ring-1 focus:ring-teal/30",
    invalid ? "border-charcoal/40 ring-1 ring-charcoal/15" : "border-border",
  );
}

const portfolioChoices = portfolioSizes.filter((opt) => opt.value !== "");

function PortfolioSizeSelect({
  id,
  name,
  value,
  invalid,
  onChange,
  onBlur,
}: {
  id: string;
  name: string;
  value: string;
  invalid?: boolean;
  onChange: (value: string) => void;
  onBlur?: () => void;
}) {
  const listId = `${id}-listbox`;
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(() => {
    const idx = portfolioChoices.findIndex((opt) => opt.value === value);
    return idx >= 0 ? idx : 0;
  });

  const selected = portfolioChoices.find((opt) => opt.value === value);
  const label = selected?.label ?? "Select portfolio size";

  useEffect(() => {
    if (!open) return;

    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
        onBlur?.();
      }
    }

    function onKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        buttonRef.current?.focus();
        onBlur?.();
      }
    }

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onBlur]);

  useEffect(() => {
    if (!open) return;
    const idx = portfolioChoices.findIndex((opt) => opt.value === value);
    setActiveIndex(idx >= 0 ? idx : 0);
  }, [open, value]);

  function choose(next: string) {
    onChange(next);
    setOpen(false);
    buttonRef.current?.focus();
    onBlur?.();
  }

  function moveActive(delta: number) {
    setActiveIndex((i) => {
      const next = i + delta;
      if (next < 0) return portfolioChoices.length - 1;
      if (next >= portfolioChoices.length) return 0;
      return next;
    });
  }

  function onMenuKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!open) setOpen(true);
      else moveActive(1);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) setOpen(true);
      else moveActive(-1);
      return;
    }
    if (event.key === "Home") {
      event.preventDefault();
      setOpen(true);
      setActiveIndex(0);
      return;
    }
    if (event.key === "End") {
      event.preventDefault();
      setOpen(true);
      setActiveIndex(portfolioChoices.length - 1);
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      const opt = portfolioChoices[activeIndex];
      if (opt) choose(opt.value);
      return;
    }
    if (event.key === "Escape" && open) {
      event.preventDefault();
      setOpen(false);
      buttonRef.current?.focus();
      onBlur?.();
      return;
    }
    if (event.key === "Tab" && open) {
      setOpen(false);
      onBlur?.();
    }
  }

  return (
    <div ref={rootRef} className="relative">
      <input type="hidden" name={name} value={value} />
      <button
        ref={buttonRef}
        type="button"
        id={id}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-invalid={invalid || undefined}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={onMenuKeyDown}
        onBlur={(event) => {
          if (!rootRef.current?.contains(event.relatedTarget as Node)) {
            setOpen(false);
            onBlur?.();
          }
        }}
        className={cn(
          "flex w-full items-center justify-between gap-3 rounded-xl border px-3.5 py-2.5 text-left text-sm shadow-sm outline-none transition-[border-color,box-shadow,background-color,color]",
          "focus-visible:border-teal focus-visible:ring-2 focus-visible:ring-teal/25",
          open
            ? "border-teal bg-surface ring-2 ring-teal/20"
            : invalid
              ? "border-charcoal/40 bg-soft-teal/40 ring-1 ring-charcoal/15"
              : "border-teal/30 bg-soft-teal/45 hover:border-teal/50 hover:bg-soft-teal/75",
          selected ? "text-charcoal" : "text-text-secondary",
        )}
      >
        <span className="min-w-0 truncate font-medium">{label}</span>
        <span
          aria-hidden
          className={cn(
            "flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-teal/10 text-teal transition-transform duration-200",
            open && "rotate-180 bg-teal text-white",
          )}
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
            <path
              d="M4 6.25 8 10l4-3.75"
              stroke="currentColor"
              strokeWidth="1.75"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
      </button>

      {open ? (
        <ul
          id={listId}
          role="listbox"
          tabIndex={-1}
          aria-labelledby={id}
          aria-activedescendant={`${id}-opt-${activeIndex}`}
          className="absolute z-30 mt-2 max-h-64 w-full overflow-auto rounded-2xl border border-teal/20 bg-surface p-1.5 shadow-[0_18px_40px_-18px_rgba(25,32,42,0.35)] ring-1 ring-charcoal/5"
        >
          {portfolioChoices.map((opt, index) => {
            const isSelected = opt.value === value;
            const isActive = index === activeIndex;
            return (
              <li
                key={opt.value}
                id={`${id}-opt-${index}`}
                role="option"
                aria-selected={isSelected}
                onMouseEnter={() => setActiveIndex(index)}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => choose(opt.value)}
                className={cn(
                  "flex cursor-pointer items-center justify-between gap-3 rounded-xl px-3 py-2.5 text-sm transition-colors",
                  isSelected
                    ? "bg-soft-teal font-semibold text-charcoal"
                    : isActive
                      ? "bg-bg text-charcoal"
                      : "text-charcoal/85 hover:bg-soft-teal/70 hover:text-charcoal",
                )}
              >
                <span>{opt.label}</span>
                {isSelected ? (
                  <span
                    aria-hidden
                    className="flex h-5 w-5 items-center justify-center rounded-full bg-teal text-white"
                  >
                    <svg width="11" height="11" viewBox="0 0 12 12" fill="none">
                      <path
                        d="M2.5 6.2 4.8 8.5 9.5 3.5"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </span>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}

function Field({
  id,
  label,
  optional,
  error,
  children,
}: {
  id: string;
  label: string;
  optional?: boolean;
  error?: string;
  children: ReactNode;
}) {
  const errId = `${id}-err`;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-charcoal">
        {label}
        {optional ? (
          <span className="ml-1 font-normal text-text-secondary">Optional</span>
        ) : (
          <span className="sr-only"> Required</span>
        )}
      </label>
      {children}
      {error ? (
        <p id={errId} className="text-sm text-charcoal" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
