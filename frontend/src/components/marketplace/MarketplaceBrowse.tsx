"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Footer } from "@/components/layout/Footer";
import { Header } from "@/components/layout/Header";
import { Container } from "@/components/ui/Container";
import { clientApi } from "@/lib/clientApi";
import { apiErrorMessage, asList } from "@/lib/opsApi";
import { locationLabel, primaryPhoto, rentLabel, shillingsToCents, type PublicListing } from "./shared";

type Filters = {
  location: string;
  minRent: string;
  maxRent: string;
  bedrooms: string;
  bathrooms: string;
  furnished: string;
  amenity: string;
  ordering: string;
};

const EMPTY_FILTERS: Filters = {
  location: "",
  minRent: "",
  maxRent: "",
  bedrooms: "",
  bathrooms: "",
  furnished: "",
  amenity: "",
  ordering: "newest",
};

export function MarketplaceBrowse() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [draft, setDraft] = useState<Filters>(EMPTY_FILTERS);
  const [listings, setListings] = useState<PublicListing[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    const minRent = shillingsToCents(filters.minRent);
    const maxRent = shillingsToCents(filters.maxRent);
    clientApi
      .get<PublicListing[]>("/api/v1/marketplace/listings/", {
        skipAuth: true,
        params: {
          location: filters.location,
          min_rent: minRent,
          max_rent: maxRent,
          bedrooms: filters.bedrooms,
          bathrooms: filters.bathrooms,
          furnished: filters.furnished,
          amenity: filters.amenity,
          ordering: filters.ordering,
        },
      })
      .then(response => {
        if (!cancelled) setListings(asList(response.data));
      })
      .catch(reason => {
        if (!cancelled) setError(apiErrorMessage(reason, "The marketplace could not be loaded."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [filters]);

  function updateDraft(key: keyof Filters, value: string) {
    setDraft(current => ({ ...current, [key]: value }));
  }

  return (
    <>
      <Header />
      <main id="main" className="bg-bg">
        <section className="border-b border-border bg-charcoal text-white">
          <Container className="py-14 md:py-20">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal">Hodi marketplace</p>
            <h1 className="mt-3 max-w-2xl text-4xl leading-tight text-white md:text-5xl" style={{ fontFamily: "var(--font-fraunces), Georgia, serif" }}>
              Homes ready to rent
            </h1>
            <p className="mt-4 max-w-xl text-base leading-relaxed text-white/75">
              Published listings from Hodi organizations. An available card means the unit is open and has no active lease. Sending an inquiry does not reserve it.
            </p>
          </Container>
        </section>

        <Container className="py-8 md:py-12">
          <form
            className="grid gap-3 rounded-2xl border border-border bg-surface p-4 shadow-soft md:grid-cols-4"
            onSubmit={event => {
              event.preventDefault();
              setFilters(draft);
            }}
          >
            <label className="text-sm text-text-secondary md:col-span-2">
              Location
              <input className="auth-input mt-1" value={draft.location} placeholder="City or area" onChange={event => updateDraft("location", event.target.value)} />
            </label>
            <label className="text-sm text-text-secondary">
              Min rent (KES)
              <input className="auth-input mt-1" inputMode="decimal" value={draft.minRent} onChange={event => updateDraft("minRent", event.target.value)} />
            </label>
            <label className="text-sm text-text-secondary">
              Max rent (KES)
              <input className="auth-input mt-1" inputMode="decimal" value={draft.maxRent} onChange={event => updateDraft("maxRent", event.target.value)} />
            </label>
            <label className="text-sm text-text-secondary">
              Bedrooms
              <input className="auth-input mt-1" inputMode="numeric" value={draft.bedrooms} onChange={event => updateDraft("bedrooms", event.target.value)} />
            </label>
            <label className="text-sm text-text-secondary">
              Bathrooms
              <input className="auth-input mt-1" inputMode="numeric" value={draft.bathrooms} onChange={event => updateDraft("bathrooms", event.target.value)} />
            </label>
            <label className="text-sm text-text-secondary">
              Furnished
              <select className="auth-input mt-1" value={draft.furnished} onChange={event => updateDraft("furnished", event.target.value)}>
                <option value="">Any</option>
                <option value="true">Furnished</option>
                <option value="false">Unfurnished</option>
              </select>
            </label>
            <label className="text-sm text-text-secondary">
              Amenity
              <input className="auth-input mt-1" value={draft.amenity} placeholder="Parking" onChange={event => updateDraft("amenity", event.target.value)} />
            </label>
            <label className="text-sm text-text-secondary md:col-span-2">
              Order
              <select className="auth-input mt-1" value={draft.ordering} onChange={event => updateDraft("ordering", event.target.value)}>
                <option value="newest">Newest</option>
                <option value="rent">Rent, low to high</option>
                <option value="-rent">Rent, high to low</option>
              </select>
            </label>
            <div className="flex items-end gap-2 md:col-span-2">
              <button type="submit" className="h-11 rounded-xl bg-teal px-5 text-sm font-semibold text-white">Search</button>
              <button
                type="button"
                className="h-11 rounded-xl border border-border px-4 text-sm"
                onClick={() => {
                  setDraft(EMPTY_FILTERS);
                  setFilters(EMPTY_FILTERS);
                }}
              >
                Clear
              </button>
            </div>
          </form>

          <div className="mt-8" aria-live="polite">
            {loading && <p className="text-text-secondary">Loading published listings…</p>}
            {!loading && error && (
              <div className="rounded-2xl border border-border bg-surface p-6" role="alert">
                <p>{error}</p>
                <button type="button" className="mt-3 text-sm font-semibold text-teal" onClick={() => setFilters({ ...filters })}>Try again</button>
              </div>
            )}
            {!loading && !error && listings.length === 0 && (
              <div className="rounded-2xl border border-dashed border-border bg-surface p-8">
                <h2 className="text-xl" style={{ fontFamily: "var(--font-fraunces), Georgia, serif" }}>No listings match</h2>
                <p className="mt-2 max-w-lg text-sm leading-relaxed text-text-secondary">
                  Nothing published is available for these filters. Occupied units and drafts stay off this page.
                </p>
              </div>
            )}
            {!loading && !error && listings.length > 0 && (
              <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
                {listings.map(listing => {
                  const photo = primaryPhoto(listing.photos);
                  return (
                    <li key={listing.id}>
                      <Link href={`/marketplace/${listing.id}`} className="block overflow-hidden rounded-2xl border border-border bg-surface shadow-soft transition hover:-translate-y-0.5">
                        <div className="aspect-[4/3] bg-soft-teal">
                          {photo ? (
                            <img src={photo.url} alt={photo.caption || listing.title} className="h-full w-full object-cover" />
                          ) : (
                            <div className="flex h-full items-center justify-center text-sm text-text-secondary">No photo yet</div>
                          )}
                        </div>
                        <div className="space-y-2 p-4">
                          <div className="flex items-start justify-between gap-3">
                            <h2 className="text-lg leading-snug text-charcoal">{listing.title}</h2>
                            <span className="shrink-0 rounded-full bg-soft-teal px-2 py-1 text-xs font-semibold text-charcoal">Available</span>
                          </div>
                          <p className="text-sm text-text-secondary">{locationLabel(listing)}</p>
                          <p className="text-base font-semibold text-charcoal">{rentLabel(listing.monthly_rent_minor)} <span className="font-normal text-text-secondary">/ month</span></p>
                          <p className="text-sm text-text-secondary">
                            {listing.bedrooms} bed · {listing.bathrooms} bath · {listing.furnished ? "Furnished" : "Unfurnished"}
                          </p>
                          {listing.amenities.length > 0 && (
                            <p className="text-sm text-text-secondary">{listing.amenities.slice(0, 4).join(" · ")}</p>
                          )}
                          <p className="text-sm font-semibold text-teal">View home</p>
                        </div>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </Container>
      </main>
      <Footer />
    </>
  );
}
