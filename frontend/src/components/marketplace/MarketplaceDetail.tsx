"use client";

import { type FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { Footer } from "@/components/layout/Footer";
import { Header } from "@/components/layout/Header";
import { Container } from "@/components/ui/Container";
import { clientApi } from "@/lib/clientApi";
import { apiErrorMessage } from "@/lib/opsApi";
import { locationLabel, rentLabel, type PublicListing } from "./shared";

export function MarketplaceDetail({ listingId }: { listingId: string }) {
  const [listing, setListing] = useState<PublicListing | null>(null);
  const [activePhoto, setActivePhoto] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [inquiryError, setInquiryError] = useState("");
  const [inquiryNotice, setInquiryNotice] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    clientApi
      .get<PublicListing>(`/api/v1/marketplace/listings/${listingId}/`, { skipAuth: true })
      .then(response => {
        if (!cancelled) setListing(response.data);
      })
      .catch(reason => {
        if (!cancelled) setError(apiErrorMessage(reason, "This listing is not available."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [listingId]);

  async function sendInquiry(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setSending(true);
    setInquiryError("");
    setInquiryNotice("");
    try {
      await clientApi.post(
        "/api/v1/marketplace/inquiries/",
        {
          listing: listingId,
          name: String(form.get("name") ?? ""),
          email: String(form.get("email") ?? ""),
          phone: String(form.get("phone") ?? ""),
          message: String(form.get("message") ?? ""),
        },
        { skipAuth: true },
      );
      formElement.reset();
      setInquiryNotice("Inquiry sent to the listing owner. This does not reserve the home or create a lease.");
    } catch (reason) {
      setInquiryError(apiErrorMessage(reason, "The inquiry could not be sent."));
    } finally {
      setSending(false);
    }
  }

  const photo = listing?.photos[activePhoto] ?? listing?.photos[0];

  return (
    <>
      <Header />
      <main id="main" className="bg-bg">
        <Container className="py-8 md:py-12">
          <Link href="/marketplace" className="text-sm font-semibold text-teal">Back to marketplace</Link>
          {loading && <p className="mt-8 text-text-secondary">Loading listing…</p>}
          {!loading && error && (
            <div className="mt-8 rounded-2xl border border-border bg-surface p-6" role="alert">
              <h1 className="text-2xl" style={{ fontFamily: "var(--font-fraunces), Georgia, serif" }}>Listing unavailable</h1>
              <p className="mt-2 text-sm text-text-secondary">{error} Drafts, occupied units, and homes with an active lease are not shown.</p>
            </div>
          )}
          {!loading && listing && (
            <div className="mt-6 grid gap-8 lg:grid-cols-[minmax(0,1.4fr)_minmax(280px,0.8fr)]">
              <div>
                <div className="overflow-hidden rounded-2xl border border-border bg-soft-teal">
                  {photo ? (
                    <img src={photo.url} alt={photo.caption || listing.title} className="aspect-[4/3] w-full object-cover" />
                  ) : (
                    <div className="flex aspect-[4/3] items-center justify-center text-sm text-text-secondary">No photo yet</div>
                  )}
                </div>
                {listing.photos.length > 1 && (
                  <ul className="mt-3 flex gap-2 overflow-x-auto">
                    {listing.photos.map((item, index) => (
                      <li key={item.id}>
                        <button type="button" className={`h-16 w-20 overflow-hidden rounded-lg border ${index === activePhoto ? "border-teal" : "border-border"}`} onClick={() => setActivePhoto(index)}>
                          <img src={item.url} alt={item.caption || `Photo ${index + 1}`} className="h-full w-full object-cover" />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                <p className="mt-6 text-xs font-semibold uppercase tracking-[0.14em] text-teal">{listing.available ? "Available" : "Unavailable"}</p>
                <h1 className="mt-2 text-3xl text-charcoal md:text-4xl" style={{ fontFamily: "var(--font-fraunces), Georgia, serif" }}>{listing.title}</h1>
                <p className="mt-2 text-text-secondary">{locationLabel(listing)} · {listing.property_name} · {listing.unit_label}</p>
                <p className="mt-4 text-2xl font-semibold text-charcoal">{rentLabel(listing.monthly_rent_minor)} <span className="text-base font-normal text-text-secondary">/ month</span></p>
                <dl className="mt-6 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                  <div className="rounded-xl border border-border bg-surface p-3"><dt className="text-text-secondary">Bedrooms</dt><dd className="font-semibold">{listing.bedrooms}</dd></div>
                  <div className="rounded-xl border border-border bg-surface p-3"><dt className="text-text-secondary">Bathrooms</dt><dd className="font-semibold">{listing.bathrooms}</dd></div>
                  <div className="rounded-xl border border-border bg-surface p-3"><dt className="text-text-secondary">Furnishing</dt><dd className="font-semibold">{listing.furnished ? "Furnished" : "Unfurnished"}</dd></div>
                  <div className="rounded-xl border border-border bg-surface p-3"><dt className="text-text-secondary">Size</dt><dd className="font-semibold">{listing.size_sqm ? `${listing.size_sqm} m²` : "—"}</dd></div>
                </dl>
                {listing.description && <p className="mt-6 max-w-2xl leading-relaxed text-text">{listing.description}</p>}
                {listing.amenities.length > 0 && (
                  <ul className="mt-6 flex flex-wrap gap-2">
                    {listing.amenities.map(amenity => (
                      <li key={amenity} className="rounded-full bg-soft-teal px-3 py-1 text-sm text-charcoal">{amenity}</li>
                    ))}
                  </ul>
                )}
              </div>
              <aside className="h-fit rounded-2xl border border-border bg-surface p-5 shadow-soft">
                <h2 className="text-xl" style={{ fontFamily: "var(--font-fraunces), Georgia, serif" }}>Ask about this home</h2>
                <p className="mt-2 text-sm leading-relaxed text-text-secondary">Your name, email, and message go to the organization that published the listing. Hodi does not book the unit from this form.</p>
                <form className="mt-4 space-y-3" onSubmit={event => void sendInquiry(event)}>
                  <label className="block text-sm text-text-secondary">Name<input className="auth-input mt-1" name="name" required maxLength={120} /></label>
                  <label className="block text-sm text-text-secondary">Email<input className="auth-input mt-1" name="email" type="email" required /></label>
                  <label className="block text-sm text-text-secondary">Phone<input className="auth-input mt-1" name="phone" maxLength={30} /></label>
                  <label className="block text-sm text-text-secondary">Message<textarea className="auth-input mt-1 min-h-28" name="message" required maxLength={2000} /></label>
                  {inquiryError && <p className="text-sm text-red-700" role="alert">{inquiryError}</p>}
                  {inquiryNotice && <p className="text-sm text-charcoal" role="status">{inquiryNotice}</p>}
                  <button type="submit" disabled={sending} className="h-11 w-full rounded-xl bg-teal text-sm font-semibold text-white disabled:opacity-60">
                    {sending ? "Sending…" : "Send inquiry"}
                  </button>
                </form>
              </aside>
            </div>
          )}
        </Container>
      </main>
      <Footer />
    </>
  );
}
