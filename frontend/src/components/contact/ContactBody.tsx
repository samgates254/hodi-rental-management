"use client";

import { useState } from "react";
import {
  ContactForm,
  contactReasons,
} from "@/components/contact/ContactForm";
import { Container } from "@/components/ui/Container";
import { cn } from "@/lib/cn";
import { contactEmail, contactMailto } from "@/lib/site";

const details = [
  {
    label: "Email",
    value: contactEmail,
    href: contactMailto,
  },
  {
    label: "Response time",
    value: "Within 1 business day",
  },
  {
    label: "Best for",
    value: "Demos, portfolios, partnerships, product questions",
  },
] as const;

export function ContactBody() {
  const [reasonId, setReasonId] = useState("");

  return (
    <section
      className="border-b border-border bg-surface"
      aria-labelledby="contact-body-heading"
    >
      <Container className="py-14 md:py-16 lg:py-20">
        <div className="grid items-start gap-12 lg:grid-cols-12 lg:gap-14">
          {/* Left: pitch + chips + direct contact */}
          <div className="lg:col-span-5">
            <p className="text-sm font-medium tracking-wide text-teal">
              Reach the team
            </p>
            <h2
              id="contact-body-heading"
              className="mt-3 font-display text-2xl font-semibold tracking-[-0.02em] text-charcoal text-balance sm:text-3xl"
            >
              Write once. We take it from there.
            </h2>
            <p className="mt-4 text-base leading-relaxed text-text-secondary text-pretty">
              Share a little context — role, portfolio shape, and what you want
              to solve. The more specific you are, the faster we can help.
            </p>

            <div className="mt-8">
              <p className="text-sm font-medium text-charcoal">I want to…</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {contactReasons.map((r) => {
                  const selected = reasonId === r.id;
                  return (
                    <button
                      key={r.id}
                      type="button"
                      onClick={() => {
                        setReasonId(r.id);
                        document
                          .getElementById("contact-form")
                          ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
                      }}
                      aria-pressed={selected}
                      className={cn(
                        "rounded-full border px-3.5 py-1.5 text-sm transition-colors",
                        selected
                          ? "border-teal bg-soft-teal text-charcoal"
                          : "border-border bg-bg text-text-secondary hover:border-charcoal/25 hover:text-charcoal",
                      )}
                    >
                      {r.label}
                    </button>
                  );
                })}
              </div>
            </div>

            <dl className="mt-10 space-y-5 border-t border-border pt-8">
              {details.map((item) => (
                <div key={item.label}>
                  <dt className="text-xs font-medium uppercase tracking-wide text-text-secondary">
                    {item.label}
                  </dt>
                  <dd className="mt-1.5 text-sm text-charcoal sm:text-base">
                    {"href" in item && item.href ? (
                      <a
                        href={item.href}
                        className="font-medium text-teal underline-offset-2 hover:underline"
                      >
                        {item.value}
                      </a>
                    ) : (
                      item.value
                    )}
                  </dd>
                </div>
              ))}
            </dl>

            <p className="mt-8 text-sm leading-relaxed text-text-secondary">
              Prefer email only?{" "}
              <a
                href={contactMailto}
                className="font-medium text-charcoal underline-offset-2 hover:underline"
              >
                {contactEmail}
              </a>
            </p>
          </div>

          {/* Right: form card */}
          <div className="lg:col-span-7">
            <div className="border border-border bg-bg p-6 sm:p-8 lg:p-10">
              <div className="mb-6 border-b border-border pb-5">
                <h3 className="font-display text-xl font-semibold tracking-[-0.02em] text-charcoal">
                  Send a message
                </h3>
                <p className="mt-1.5 text-sm text-text-secondary">
                  Required fields take under two minutes.
                </p>
              </div>
              <ContactForm
                reasonId={reasonId}
                onReasonIdChange={setReasonId}
              />
            </div>
          </div>
        </div>
      </Container>
    </section>
  );
}
