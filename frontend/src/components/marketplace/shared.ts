export type ListingPhoto = {
  id: number;
  url: string;
  caption: string;
  position: number;
  is_primary: boolean;
};

export type PublicListing = {
  id: string;
  title: string;
  description: string;
  monthly_rent_minor: number;
  currency: string;
  bedrooms: number;
  bathrooms: number;
  floor: number | null;
  size_sqm: number | null;
  furnished: boolean;
  amenities: string[];
  area: string;
  city: string;
  country: string;
  property_name: string;
  unit_label: string;
  available: boolean;
  published_at: string | null;
  photos: ListingPhoto[];
};

export type ManagedListing = PublicListing & {
  unit: number;
  organization: number;
  unit_status: string;
  status: "DRAFT" | "PUBLISHED" | string;
  is_publicly_available: boolean;
  created_at: string;
  updated_at: string;
};

export function rentLabel(cents: number | null | undefined): string {
  const value = Number(cents ?? 0);
  const fraction = value % 100 === 0 ? 0 : 2;
  return new Intl.NumberFormat("en-KE", {
    style: "currency",
    currency: "KES",
    minimumFractionDigits: fraction,
    maximumFractionDigits: fraction,
  }).format(value / 100);
}

export function shillingsToCents(raw: string): number | undefined {
  const trimmed = raw.trim();
  if (!trimmed) return undefined;
  const amount = Number(trimmed);
  if (!Number.isFinite(amount) || amount < 0) return undefined;
  return Math.round(amount * 100);
}

export function primaryPhoto(photos: ListingPhoto[]): ListingPhoto | undefined {
  return photos.find(photo => photo.is_primary) ?? photos[0];
}

export function locationLabel(listing: { area: string; city: string; country: string }): string {
  return [listing.area, listing.city, listing.country].filter(Boolean).join(", ");
}
