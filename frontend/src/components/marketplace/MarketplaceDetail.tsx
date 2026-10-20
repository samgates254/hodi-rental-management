"use client";

import { type FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { Footer } from "@/components/layout/Footer";
import { Header } from "@/components/layout/Header";
import { Container } from "@/components/ui/Container";
import { clientApi } from "@/lib/clientApi";
import { apiErrorMessage } from "@/lib/opsApi";
import { Gallery } from "./Gallery";
import { locationLabel, rentLabel, type PublicListing } from "./shared";

export function MarketplaceDetail({ listingId }: { listingId: string }) {
  const [listing, setListing] = useState<PublicListing | null>(null);
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
    const viewingInput = String(form.get("viewing_requested_for") ?? "");
    const viewingDate = viewingInput ? new Date(viewingInput) : null;
    if (viewingDate && Number.isNaN(viewingDate.getTime())) {
      setInquiryError("Choose a valid viewing date and time.");
      return;
    }
    const viewingRequestedFor = viewingDate?.toISOString();
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
          ...(viewingRequestedFor ? { viewing_requested_for: viewingRequestedFor } : {}),
        },
        { skipAuth: true },
      );
      formElement.reset();
      setInquiryNotice("Inquiry sent to the listing contact. This does not reserve the home or create a lease.");
    } catch (reason) {
      setInquiryError(apiErrorMessage(reason, "The inquiry could not be sent."));
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      <Header />
      <main id="main" className="hodi-listing-page">
        <Container className="py-8 md:py-12">
          <Link href="/marketplace" className="hodi-back-link">Back to marketplace</Link>
          {loading && (
            <div className="hodi-listing-layout mt-8" role="status" aria-label="Loading listing" aria-busy="true">
              <div className="hodi-listing-stage motion-safe:animate-pulse" />
              <div className="hodi-inquiry">
                <div className="h-8 w-2/3 bg-soft-teal motion-safe:animate-pulse" />
                <p className="mt-4 text-sm text-text-secondary">Loading listing details…</p>
              </div>
            </div>
          )}
          {!loading && error && (
            <div className="mt-8 border border-border bg-surface p-8" role="alert">
              <h1 className="hodi-listing-title">Listing unavailable</h1>
              <p className="mt-3 max-w-xl text-sm leading-relaxed text-text-secondary">{error} Drafts, occupied units, and homes with an active lease are not shown.</p>
            </div>
          )}
          {!loading && listing && (
            <div className="hodi-listing-layout">
              <article>
                <Gallery photos={listing.photos} title={listing.title} />
                <header className="hodi-listing-heading">
                  <p>{listing.available ? "Available" : "Unavailable"} · {locationLabel(listing)}</p>
                  <h1 className="hodi-listing-title">{listing.title}</h1>
                  <p className="hodi-listing-rent">{rentLabel(listing.monthly_rent_minor)} <span>/ month</span></p>
                  <p className="hodi-listing-where">{listing.property_name} · {listing.unit_label}</p>
                </header>
                <dl className="hodi-listing-facts">
                  <div><dt>Bedrooms</dt><dd>{listing.bedrooms}</dd></div>
                  <div><dt>Bathrooms</dt><dd>{listing.bathrooms}</dd></div>
                  <div><dt>Furnishing</dt><dd>{listing.furnished ? "Furnished" : "Unfurnished"}</dd></div>
                  <div><dt>Size</dt><dd>{listing.size_sqm ? `${listing.size_sqm} m²` : "—"}</dd></div>
                  {listing.floor != null && <div><dt>Floor</dt><dd>{listing.floor}</dd></div>}
                </dl>
                {listing.description && <p className="hodi-listing-copy">{listing.description}</p>}
                {listing.amenities.length > 0 && (
                  <ul className="hodi-listing-amenities">
                    {listing.amenities.map(amenity => (
                      <li key={amenity}>{amenity}</li>
                    ))}
                  </ul>
                )}
              </article>
              <aside className="hodi-inquiry">
                <h2>Ask about this home</h2>
                <p>Your contact details go to the agent or property organization managing the listing. A viewing request is not a booking.</p>
                <form onSubmit={event => void sendInquiry(event)}>
                  <label>Name<input className="auth-input mt-1" name="name" required maxLength={120} /></label>
                  <label>Email<input className="auth-input mt-1" name="email" type="email" required /></label>
                  <label>Phone<input className="auth-input mt-1" name="phone" maxLength={30} /></label>
                  <label>Request a viewing (optional)<input className="auth-input mt-1" name="viewing_requested_for" type="datetime-local" /><span>Choose a future date and time.</span></label>
                  <label>Message<textarea className="auth-input mt-1 min-h-28" name="message" required maxLength={2000} /></label>
                  {inquiryError && <p className="text-sm text-red-700" role="alert">{inquiryError}</p>}
                  {inquiryNotice && <p className="text-sm text-charcoal" role="status">{inquiryNotice}</p>}
                  <button type="submit" disabled={sending}>
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
