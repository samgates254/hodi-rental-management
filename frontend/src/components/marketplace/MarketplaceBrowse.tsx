"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { Footer } from "@/components/layout/Footer";
import { Header } from "@/components/layout/Header";
import { Container } from "@/components/ui/Container";
import { clientApi } from "@/lib/clientApi";
import { apiErrorMessage } from "@/lib/opsApi";
import { locationLabel, minorToShillingsInput, primaryPhoto, rentLabel, shillingsToCents, type PublicListing } from "./shared";
import { RemotePhoto } from "./RemotePhoto";

type Filters = {
  q: string;
  location: string;
  minRent: string;
  maxRent: string;
  bedrooms: string;
  bathrooms: string;
  furnished: string;
  amenity: string;
  ordering: string;
};

type PublicListingPage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: PublicListing[];
};

function BrowseListingCard({ listing }: { listing: PublicListing }) {
  const photo = primaryPhoto(listing.photos);
  const [failed, setFailed] = useState(false);
  return (
    <li>
      <Link
        href={`/marketplace/${listing.id}`}
        className="group block overflow-hidden border border-emerald-700 bg-surface transition duration-200 hover:-translate-y-0.5"
      >
        <div className="relative aspect-[16/10] overflow-hidden bg-soft-teal">
          {photo && !failed ? (
            <RemotePhoto
              src={photo.url}
              alt={photo.caption || listing.title}
              fill
              sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
              className="object-cover transition duration-200 group-hover:scale-[1.02]"
              onFail={() => setFailed(true)}
            />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-text-secondary" aria-label={`No listing photo available for ${listing.title}`}>
              <svg aria-hidden="true" viewBox="0 0 32 32" className="h-9 w-9" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="m4 14 12-9 12 9v13H4z" />
                <path d="M12 27v-8h8v8M9 14h.01M23 14h.01" />
              </svg>
              <span>{photo ? "Photo unavailable" : "No listing photo"}</span>
            </div>
          )}
        </div>
        <div className="space-y-2 p-4">
          <div className="flex items-start justify-between gap-3">
            <h2 className="font-[family-name:var(--hodi-editorial)] text-xl font-normal leading-snug text-charcoal">{listing.title}</h2>
            <span className="shrink-0 border border-border px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-charcoal">{listing.available ? "Available" : "Unavailable"}</span>
          </div>
          <p className="text-sm text-text-secondary">{[listing.property_name, listing.unit_label, locationLabel(listing)].filter(Boolean).join(" · ")}</p>
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
}

const EMPTY_FILTERS: Filters = {
  q: "",
  location: "",
  minRent: "",
  maxRent: "",
  bedrooms: "",
  bathrooms: "",
  furnished: "",
  amenity: "",
  ordering: "newest",
};

const PAGE_SIZE = 12;

function filtersFromParams(params: URLSearchParams): Filters {
  const rentInput = (key: string) => {
    const raw = params.get(key);
    if (raw === null) return "";
    const minor = Number(raw);
    return Number.isSafeInteger(minor) && minor >= 0 ? minorToShillingsInput(minor) : "!";
  };
  return {
    q: params.get("q") ?? "",
    location: params.get("location") ?? "",
    minRent: rentInput("min_rent"),
    maxRent: rentInput("max_rent"),
    bedrooms: params.get("bedrooms") ?? "",
    bathrooms: params.get("bathrooms") ?? "",
    furnished: params.get("furnished") ?? "",
    amenity: params.getAll("amenity").join(", "),
    ordering: params.get("ordering") ?? "newest",
  };
}

function pageFromParams(params: URLSearchParams): number {
  const page = Number(params.get("page") ?? "1");
  return Number.isSafeInteger(page) && page > 0 ? page : 1;
}

function validationMessage(filters: Filters): string {
  if (filters.q.trim().length > 100) return "Use 100 characters or fewer for keywords.";
  const minRent = filters.minRent.trim() ? shillingsToCents(filters.minRent) : undefined;
  const maxRent = filters.maxRent.trim() ? shillingsToCents(filters.maxRent) : undefined;
  if (filters.minRent.trim() && minRent == null) return "Enter a minimum rent with at most two decimal places.";
  if (filters.maxRent.trim() && maxRent == null) return "Enter a maximum rent with at most two decimal places.";
  if (minRent != null && maxRent != null && minRent > maxRent) return "Maximum rent must be at least the minimum rent.";
  for (const [label, value] of [["Bedrooms", filters.bedrooms], ["Bathrooms", filters.bathrooms]] as const) {
    if (value && (!/^\d+$/.test(value) || Number(value) > 30)) return `${label} must be a whole number from 0 to 30.`;
  }
  if (filters.amenity.split(",").some(value => value.trim().length > 40)) return "Use 40 characters or fewer for each amenity.";
  if (!(["newest", "rent", "-rent"] as string[]).includes(filters.ordering)) return "Choose a supported sort order.";
  return "";
}

function hasActiveFilters(filters: Filters): boolean {
  return Boolean(
    filters.q.trim() || filters.location.trim() || filters.minRent.trim() || filters.maxRent.trim() ||
    filters.bedrooms.trim() || filters.bathrooms.trim() || filters.furnished || filters.amenity.trim() ||
    filters.ordering !== "newest",
  );
}

function writeSearchUrl(filters: Filters, page: number) {
  const params = new URLSearchParams();
  for (const key of ["q", "location"] as const) {
    const value = filters[key].trim();
    if (value) params.set(key, value);
  }
  const scalarFilters: Array<[string, string | number | undefined]> = [
    ["min_rent", filters.minRent.trim() ? shillingsToCents(filters.minRent) : undefined],
    ["max_rent", filters.maxRent.trim() ? shillingsToCents(filters.maxRent) : undefined],
    ["bedrooms", filters.bedrooms.trim()],
    ["bathrooms", filters.bathrooms.trim()],
    ["furnished", filters.furnished],
  ];
  for (const [key, value] of scalarFilters) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  filters.amenity.split(",").map(value => value.trim()).filter(Boolean).forEach(value => params.append("amenity", value));
  if (filters.ordering !== "newest") params.set("ordering", filters.ordering);
  if (page > 1) params.set("page", String(page));
  const query = params.toString();
  window.history.pushState({}, "", query ? `/marketplace?${query}` : "/marketplace");
}

export function MarketplaceBrowse() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [draft, setDraft] = useState<Filters>(EMPTY_FILTERS);
  const [listings, setListings] = useState<PublicListing[]>([]);
  const [resultCount, setResultCount] = useState(0);
  const [hasPreviousPage, setHasPreviousPage] = useState(false);
  const [hasNextPage, setHasNextPage] = useState(false);
  const [page, setPage] = useState(1);
  const [ready, setReady] = useState(false);
  const [validationError, setValidationError] = useState("");
  const [retryKey, setRetryKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const restore = () => {
      const params = new URLSearchParams(window.location.search);
      const restoredFilters = filtersFromParams(params);
      setFilters(restoredFilters);
      setDraft(restoredFilters);
      setPage(pageFromParams(params));
      setValidationError(validationMessage(restoredFilters));
    };
    restore();
    setReady(true);
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, []);

  useEffect(() => {
    if (!ready) return;
    const invalid = validationMessage(filters);
    setValidationError(invalid);
    if (invalid) {
      setListings([]);
      setResultCount(0);
      setHasPreviousPage(false);
      setHasNextPage(false);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    const minRent = shillingsToCents(filters.minRent);
    const maxRent = shillingsToCents(filters.maxRent);
    clientApi
      .get<PublicListing[]>("/api/v1/marketplace/listings/", {
        skipAuth: true,
        params: {
          q: filters.q.trim(),
          location: filters.location,
          min_rent: minRent,
          max_rent: maxRent,
          bedrooms: filters.bedrooms,
          bathrooms: filters.bathrooms,
          furnished: filters.furnished,
          amenity: filters.amenity.split(",").map(value => value.trim()).filter(Boolean),
          ordering: filters.ordering,
          page,
          page_size: PAGE_SIZE,
        },
      })
      .then(response => {
        if (cancelled) return;
        const payload = response.data as PublicListingPage | PublicListing[];
        if (Array.isArray(payload)) {
          setListings(payload);
          setResultCount(payload.length);
          setHasPreviousPage(false);
          setHasNextPage(false);
          return;
        }
        setListings(payload.results ?? []);
        setResultCount(payload.count ?? payload.results?.length ?? 0);
        setHasPreviousPage(Boolean(payload.previous));
        setHasNextPage(Boolean(payload.next));
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
  }, [filters, page, ready, retryKey]);

  function updateDraft(key: keyof Filters, value: string) {
    setDraft(current => ({ ...current, [key]: value }));
  }

  function applyFilters(nextFilters: Filters) {
    const invalid = validationMessage(nextFilters);
    setValidationError(invalid);
    if (invalid) return;
    setFilters(nextFilters);
    setDraft(nextFilters);
    setPage(1);
    writeSearchUrl(nextFilters, 1);
  }

  function changePage(nextPage: number) {
    if (nextPage < 1) return;
    setPage(nextPage);
    writeSearchUrl(filters, nextPage);
  }

  return (
    <>
      <Header />
      <main id="main" className="bg-bg">
        <section className="hodi-market-hero">
          <div className="hodi-market-hero-copy">
            <p className="hodi-editorial-kicker"><span aria-hidden="true" />Marketplace</p>
            <h1>Homes organizations have published.</h1>
            <p>
              These cards come from the live marketplace. An available listing has no active lease. Sending an inquiry does not reserve the home.
            </p>
          </div>
          <figure>
            <Image src="/images/hodi/tower-balconies.jpg" alt="White residential tower with stacked balconies" fill priority sizes="(max-width: 800px) 100vw, 42vw" className="object-cover" />
            <figcaption>Illustrative architecture. Not a listing on this page.</figcaption>
          </figure>
        </section>

        <Container className="py-8 md:py-12">
          <form
            className="grid gap-3 rounded-2xl border border-border bg-surface p-4 shadow-soft md:grid-cols-4"
            onSubmit={event => {
              event.preventDefault();
              applyFilters(draft);
            }}
          >
            <label className="text-sm text-text-secondary md:col-span-2">
              Keywords
              <input className="auth-input mt-1" value={draft.q} maxLength={100} placeholder="Area, property, or feature" onChange={event => updateDraft("q", event.target.value)} />
            </label>
            <label className="text-sm text-text-secondary md:col-span-2">
              Location
              <input className="auth-input mt-1" value={draft.location} maxLength={100} placeholder="City or area" onChange={event => updateDraft("location", event.target.value)} />
            </label>
            <label className="text-sm text-text-secondary">
              Min rent (KES)
              <input className="auth-input mt-1" type="number" min="0" step="0.01" inputMode="decimal" value={draft.minRent} onChange={event => updateDraft("minRent", event.target.value)} />
            </label>
            <label className="text-sm text-text-secondary">
              Max rent (KES)
              <input className="auth-input mt-1" type="number" min="0" step="0.01" inputMode="decimal" value={draft.maxRent} onChange={event => updateDraft("maxRent", event.target.value)} />
            </label>
            <label className="text-sm text-text-secondary">
              Bedrooms
              <input className="auth-input mt-1" type="number" min="0" max="30" step="1" inputMode="numeric" value={draft.bedrooms} onChange={event => updateDraft("bedrooms", event.target.value)} />
            </label>
            <label className="text-sm text-text-secondary">
              Bathrooms
              <input className="auth-input mt-1" type="number" min="0" max="30" step="1" inputMode="numeric" value={draft.bathrooms} onChange={event => updateDraft("bathrooms", event.target.value)} />
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
              <input className="auth-input mt-1" maxLength={300} value={draft.amenity} placeholder="Parking, water" onChange={event => updateDraft("amenity", event.target.value)} />
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
              <button type="submit" className="h-11 rounded-xl bg-teal px-5 text-sm font-semibold text-brand-contrast">Search</button>
              <button
                type="button"
                className="h-11 rounded-xl border border-border px-4 text-sm"
                onClick={() => {
                  setDraft(EMPTY_FILTERS);
                  setFilters(EMPTY_FILTERS);
                  setPage(1);
                  setValidationError("");
                  window.history.pushState({}, "", "/marketplace");
                }}
              >
                Clear
              </button>
            </div>
          </form>

          {validationError && <p className="mt-3 text-sm text-red-700" role="alert">{validationError}</p>}

          <div className="mt-8" aria-live="polite">
            {loading && <p className="text-text-secondary">Loading published listings…</p>}
            {!loading && error && (
              <div className="rounded-2xl border border-border bg-surface p-6" role="alert">
                <p>{error}</p>
                <button type="button" className="mt-3 text-sm font-semibold text-teal" onClick={() => setRetryKey(value => value + 1)}>Try again</button>
              </div>
            )}
            {!loading && !error && listings.length === 0 && (
              <div className="rounded-2xl border border-dashed border-border bg-surface p-8">
                <h2 className="text-xl" style={{ fontFamily: "var(--font-fraunces), Georgia, serif" }}>{hasActiveFilters(filters) ? "No listings match" : "No homes are available yet"}</h2>
                <p className="mt-2 max-w-lg text-sm leading-relaxed text-text-secondary">
                  {hasActiveFilters(filters)
                    ? "Nothing published is available for these filters. Try changing or clearing them. Occupied units and drafts stay off this page."
                    : "Published homes will appear here when an organization makes an available unit public."}
                </p>
                {hasActiveFilters(filters) && <button type="button" className="mt-4 text-sm font-semibold text-teal" onClick={() => applyFilters(EMPTY_FILTERS)}>Clear filters</button>}
              </div>
            )}
            {!loading && !error && listings.length > 0 && (
              <>
                <p className="mb-4 text-sm text-text-secondary" role="status">{resultCount} {resultCount === 1 ? "home" : "homes"} found</p>
                <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
                  {listings.map(listing => (
                    <BrowseListingCard key={listing.id} listing={listing} />
                  ))}
                </ul>
                {(hasPreviousPage || hasNextPage) && <nav className="mt-8 flex items-center justify-between" aria-label="Marketplace result pages">
                  <button type="button" className="h-10 rounded-lg border border-border bg-surface px-4 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50" onClick={() => changePage(page - 1)} disabled={!hasPreviousPage || loading}>Previous</button>
                  <span className="text-sm text-text-secondary">Page {page}</span>
                  <button type="button" className="h-10 rounded-lg border border-border bg-surface px-4 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50" onClick={() => changePage(page + 1)} disabled={!hasNextPage || loading}>Next</button>
                </nav>}
              </>
            )}
          </div>
        </Container>
      </main>
      <Footer />
    </>
  );
}
