"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { Footer } from "@/components/layout/Footer";
import { Header } from "@/components/layout/Header";
import { Container } from "@/components/ui/Container";
import { clientApi } from "@/lib/clientApi";
import { apiErrorMessage } from "@/lib/opsApi";
import { isPanoramaCaption, locationLabel, minorToShillingsInput, primaryPhoto, rentLabel, shillingsToCents, type PublicListing } from "./shared";
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
      <Link href={`/marketplace/${listing.id}`} className="hodi-listing-card group">
        <div className="hodi-listing-card-media">
          {photo && !failed ? (
            <RemotePhoto
              src={photo.url}
              alt={photo.caption || listing.title}
              fill
              sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
              className="object-cover transition duration-500 motion-safe:group-hover:scale-[1.03]"
              onFail={() => setFailed(true)}
            />
          ) : (
            <div className="hodi-listing-card-empty" aria-label={`No listing photo available for ${listing.title}`}>
              <svg aria-hidden="true" viewBox="0 0 32 32" className="h-9 w-9" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="m4 14 12-9 12 9v13H4z" />
                <path d="M12 27v-8h8v8M9 14h.01M23 14h.01" />
              </svg>
              <span>{photo ? "Photo unavailable" : "No listing photo"}</span>
            </div>
          )}
          <span className="hodi-listing-card-status">{listing.available ? "Available" : "Unavailable"}</span>
          {listing.photos.some(item => isPanoramaCaption(item.caption)) && <span className="hodi-listing-card-pano">360° photo</span>}
        </div>
        <div className="hodi-listing-card-body">
          <p className="hodi-listing-card-place">{locationLabel(listing) || listing.city}</p>
          <h2>{listing.title}</h2>
          <p className="hodi-listing-card-meta">{[listing.property_name, listing.unit_label].filter(Boolean).join(" · ")}</p>
          <p className="hodi-listing-card-facts">
            {listing.bedrooms} bed · {listing.bathrooms} bath · {listing.furnished ? "Furnished" : "Unfurnished"}
            {listing.amenities.length > 0 ? ` · ${listing.amenities.slice(0, 3).join(" · ")}` : ""}
          </p>
          <p className="hodi-listing-card-rent">{rentLabel(listing.monthly_rent_minor)} <span>/ month</span></p>
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
            className="hodi-market-filters"
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
            <div className="hodi-market-actions md:col-span-2">
              <button type="submit" className="hodi-market-submit">Search</button>
              <button
                type="button"
                className="hodi-market-clear"
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
            {loading && (
              <div role="status" aria-busy="true">
                <p className="sr-only">Loading published listings…</p>
                <ul className="hodi-listing-grid" aria-hidden="true">
                  {Array.from({ length: 6 }, (_, index) => (
                    <li key={index} className="hodi-listing-card hodi-listing-skeleton">
                      <div className="hodi-listing-card-media motion-safe:animate-pulse" />
                      <div className="hodi-listing-card-body">
                        <div className="h-3 w-1/3 bg-soft-teal motion-safe:animate-pulse" />
                        <div className="mt-3 h-6 w-4/5 bg-soft-teal motion-safe:animate-pulse" />
                        <div className="mt-3 h-4 w-1/2 bg-soft-teal motion-safe:animate-pulse" />
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {!loading && error && (
              <div className="hodi-market-error" role="alert">
                <p>{error}</p>
                <button type="button" className="hodi-text-action" onClick={() => setRetryKey(value => value + 1)}>Try again</button>
              </div>
            )}
            {!loading && !error && listings.length === 0 && (
              <div className="hodi-market-empty">
                <h2>{hasActiveFilters(filters) ? "No listings match" : "No homes are available yet"}</h2>
                <p>
                  {hasActiveFilters(filters)
                    ? "Nothing published is available for these filters. Try changing or clearing them. Occupied units and drafts stay off this page."
                    : "Published homes will appear here when an organization makes an available unit public."}
                </p>
                {hasActiveFilters(filters) && <button type="button" className="hodi-text-action" onClick={() => applyFilters(EMPTY_FILTERS)}>Clear filters</button>}
              </div>
            )}
            {!loading && !error && listings.length > 0 && (
              <>
                <p className="mb-4 text-sm text-text-secondary" role="status">{resultCount} {resultCount === 1 ? "home" : "homes"} found</p>
                <ul className="hodi-listing-grid">
                  {listings.map(listing => (
                    <BrowseListingCard key={listing.id} listing={listing} />
                  ))}
                </ul>
                {(hasPreviousPage || hasNextPage) && <nav className="hodi-page-nav" aria-label="Marketplace result pages">
                  <button type="button" onClick={() => changePage(page - 1)} disabled={!hasPreviousPage || loading}>Previous</button>
                  <span className="text-sm text-text-secondary">Page {page}</span>
                  <button type="button" onClick={() => changePage(page + 1)} disabled={!hasNextPage || loading}>Next</button>
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
