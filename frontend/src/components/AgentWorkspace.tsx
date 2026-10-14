"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Logo } from "@/components/layout/Logo";
import ThemeToggle from "@/components/theme/ThemeToggle";
import { ClientApiError, clientApi, setStoredAuthToken } from "@/lib/clientApi";
import { formatMinor, minorToShillingsInput, shillingsToCents } from "@/lib/money";
import "./agent-dashboard.css";

type AgentProfile = {
  id: number;
  display_name: string;
  public_email: string;
  public_phone: string;
  business_name: string;
  description: string;
  service_area: string;
  verification_status: "UNVERIFIED" | "PENDING" | "VERIFIED" | "REJECTED" | string;
  account_status: "ACTIVE" | "SUSPENDED" | string;
  updated_at: string;
};

type AuthorizedUnit = {
  authorization_id: number;
  unit: number;
  unit_name: string;
  building_name: string;
  property_name: string;
  city: string;
  bedrooms: number;
  unit_status: string;
  listing_id: string | null;
};

type Listing = {
  id: string;
  unit: number;
  unit_label: string;
  property_name: string;
  title: string;
  description: string;
  monthly_rent_minor: number;
  currency: string;
  bedrooms: number;
  bathrooms: number;
  area: string;
  city: string;
  status: "DRAFT" | "PUBLISHED" | "PAUSED" | "ARCHIVED" | string;
  is_publicly_available: boolean;
  photos: Array<{ id: number; url: string; caption: string; is_primary: boolean }>;
};

type ViewingRequest = {
  id: number;
  requested_for: string;
  status: string;
};

type Inquiry = {
  id: number;
  listing: string;
  name: string;
  email: string;
  phone: string;
  message: string;
  status: string;
  created_at: string;
  viewing_request: ViewingRequest | null;
};

const API = "/api/v1/marketplace";
const VERIFICATION_LABEL: Record<string, string> = {
  UNVERIFIED: "Unverified",
  PENDING: "Verification pending",
  VERIFIED: "Verified",
  REJECTED: "Verification needs an update",
};

function friendlyError(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function statusClass(value: string) {
  return `agent-status agent-status--${value.toLowerCase().replaceAll("_", "-")}`;
}

export default function AgentWorkspace() {
  const [profile, setProfile] = useState<AgentProfile | null>(null);
  const [units, setUnits] = useState<AuthorizedUnit[]>([]);
  const [listings, setListings] = useState<Listing[]>([]);
  const [inquiries, setInquiries] = useState<Inquiry[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [profileResult, unitResult, listingResult, inquiryResult] = await Promise.all([
        clientApi.get<AgentProfile>(`${API}/agents/me/`),
        clientApi.get<AuthorizedUnit[]>(`${API}/agents/me/authorized-units/`),
        clientApi.get<Listing[]>(`${API}/agents/listings/`),
        clientApi.get<Inquiry[]>(`${API}/agents/inquiries/`),
      ]);
      setProfile(profileResult.data);
      setUnits(unitResult.data);
      setListings(listingResult.data);
      setInquiries(inquiryResult.data);
    } catch (loadError) {
      if (loadError instanceof ClientApiError && loadError.status === 401) {
        window.location.assign("/signin?type=agent");
        return;
      }
      setError(friendlyError(loadError, "Your agent workspace could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!sessionStorage.getItem("hodi_api_token")) {
      window.location.replace("/signin?type=agent");
      return;
    }
    void load();
  }, [load]);

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setNotice("");
    const values = new FormData(event.currentTarget);
    try {
      const { data } = await clientApi.patch<AgentProfile>(`${API}/agents/me/`, {
        display_name: values.get("display_name"),
        public_email: values.get("public_email"),
        public_phone: values.get("public_phone"),
        business_name: values.get("business_name"),
        description: values.get("description"),
        service_area: values.get("service_area"),
      });
      setProfile(data);
      setNotice("Profile saved.");
    } catch (saveError) {
      setError(friendlyError(saveError, "Your profile could not be saved."));
    } finally {
      setSaving(false);
    }
  }

  async function requestVerification() {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await clientApi.post(`${API}/agents/me/request-verification/`, {});
      setNotice("Your profile is in the verification queue.");
      await load();
    } catch (requestError) {
      setError(friendlyError(requestError, "Your verification request could not be submitted."));
    } finally {
      setSaving(false);
    }
  }

  async function saveListing(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setNotice("");
    const formElement = event.currentTarget;
    const values = new FormData(formElement);
    const rent = shillingsToCents(String(values.get("rent") ?? ""));
    if (rent == null || rent <= 0) {
      setError("Enter a positive rent amount with no more than two decimal places.");
      setSaving(false);
      return;
    }
    const image = values.get("image");
    const payload = {
      unit: Number(values.get("unit")),
      title: String(values.get("title") ?? "").trim(),
      description: String(values.get("description") ?? "").trim(),
      monthly_rent_minor: rent,
      bedrooms: Number(values.get("bedrooms") ?? 0),
      bathrooms: Number(values.get("bathrooms") ?? 0),
      area: String(values.get("area") ?? "").trim(),
      city: String(values.get("city") ?? "").trim(),
    };
    try {
      const result = editingId
        ? await clientApi.patch<Listing>(`${API}/agents/listings/${editingId}/`, payload)
        : await clientApi.post<Listing>(`${API}/agents/listings/`, payload);
      if (image instanceof File && image.size > 0) {
        const photo = new FormData();
        photo.append("image", image);
        photo.append("is_primary", "true");
        try {
          await clientApi.post(`${API}/agents/listings/${result.data.id}/photos/`, photo);
        } catch (photoError) {
          setNotice(`Listing saved, but the photo was not added: ${friendlyError(photoError, "upload failed")}`);
          await load();
          formElement.reset();
          setEditingId(null);
          return;
        }
      }
      setNotice(editingId ? "Listing updated." : "Draft saved.");
      formElement.reset();
      setEditingId(null);
      await load();
    } catch (saveError) {
      setError(friendlyError(saveError, "The listing could not be saved."));
    } finally {
      setSaving(false);
    }
  }

  function editListing(listing: Listing) {
    if (!units.some(unit => unit.unit === listing.unit)) return;
    setEditingId(listing.id);
  }

  async function listingAction(id: string, action: "publish" | "pause" | "archive") {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await clientApi.post(`${API}/agents/listings/${id}/${action}/`, {});
      setNotice(`Listing ${action === "publish" ? "published" : `${action}d`}.`);
      await load();
    } catch (actionError) {
      setError(friendlyError(actionError, "The listing could not be updated."));
    } finally {
      setSaving(false);
    }
  }

  async function updateInquiry(id: number, next: string) {
    try {
      await clientApi.patch(`${API}/agents/inquiries/${id}/status/`, { status: next });
      setNotice("Enquiry status updated.");
      await load();
    } catch (updateError) {
      setError(friendlyError(updateError, "The enquiry status could not be updated."));
    }
  }

  async function updateViewing(id: number, next: string) {
    try {
      await clientApi.patch(`${API}/agents/viewings/${id}/status/`, { status: next });
      setNotice("Viewing status updated.");
      await load();
    } catch (updateError) {
      setError(friendlyError(updateError, "The viewing status could not be updated."));
    }
  }

  async function signOut() {
    try {
      await clientApi.post("/api/v1/accounts/logout/", {});
    } catch {
      // The local session is cleared even if the API token expired.
    }
    setStoredAuthToken(null);
    for (const key of ["hodi_account_type", "hodi_memberships", "hodi_first_name", "hodi_last_name", "hodi_email", "hodi_phone_number"]) {
      sessionStorage.removeItem(key);
    }
    window.location.assign("/");
  }

  const availableUnits = units.filter(unit => !unit.listing_id || unit.listing_id === editingId);

  useEffect(() => {
    if (!editingId) return;
    const listing = listings.find(item => item.id === editingId);
    const form = document.getElementById("agent-listing-form") as HTMLFormElement | null;
    if (!listing || !form) return;
    (form.elements.namedItem("unit") as HTMLSelectElement).value = String(listing.unit);
    (form.elements.namedItem("title") as HTMLInputElement).value = listing.title;
    (form.elements.namedItem("description") as HTMLTextAreaElement).value = listing.description;
    (form.elements.namedItem("rent") as HTMLInputElement).value = minorToShillingsInput(listing.monthly_rent_minor);
    (form.elements.namedItem("bedrooms") as HTMLInputElement).value = String(listing.bedrooms);
    (form.elements.namedItem("bathrooms") as HTMLInputElement).value = String(listing.bathrooms);
    (form.elements.namedItem("area") as HTMLInputElement).value = listing.area;
    (form.elements.namedItem("city") as HTMLInputElement).value = listing.city;
    form.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [editingId, listings]);

  return (
    <main className="agent-shell">
      <header className="agent-topbar">
        <Logo size={38} />
        <nav aria-label="Agent workspace links">
          <Link href="/marketplace">Browse homes</Link>
          <ThemeToggle />
          <button className="agent-button agent-button--quiet" type="button" onClick={signOut}>Sign out</button>
        </nav>
      </header>

      <div className="agent-content">
        {loading && !profile ? <p className="agent-loading" role="status">Loading your agent workspace…</p> : null}
        {error ? <p className="agent-message agent-message--error" role="alert">{error}</p> : null}
        {notice ? <p className="agent-message agent-message--success" role="status">{notice}</p> : null}
        {profile ? <>
          <section className="agent-heading">
            <div>
              <p className="agent-eyebrow">Property agent workspace</p>
              <h1>Good to see you, {profile.display_name}</h1>
              <p>Keep your professional profile current and manage the homes owners have authorized you to advertise.</p>
            </div>
            <span className={statusClass(profile.account_status === "SUSPENDED" ? "SUSPENDED" : profile.verification_status)}>
              {profile.account_status === "SUSPENDED" ? "Account suspended" : VERIFICATION_LABEL[profile.verification_status] ?? profile.verification_status}
            </span>
          </section>

          <section className="agent-counts" aria-label="Current workspace records">
            <div><strong>{listings.length}</strong><span>Your listings</span></div>
            <div><strong>{inquiries.filter(item => item.status !== "CLOSED").length}</strong><span>Open enquiries</span></div>
            <div><strong>{inquiries.filter(item => item.viewing_request).length}</strong><span>Viewing requests</span></div>
          </section>

          <div className="agent-columns">
            <section className="agent-panel" aria-labelledby="agent-profile-title">
              <div className="agent-panel-heading">
                <div><h2 id="agent-profile-title">Professional profile</h2><p>Share accurate contact and service details with property owners.</p></div>
              </div>
              <form className="agent-form" onSubmit={saveProfile}>
                <label>Display name<input name="display_name" defaultValue={profile.display_name} required maxLength={160} /></label>
                <div className="agent-form-row">
                  <label>Public email<input name="public_email" type="email" defaultValue={profile.public_email} maxLength={254} /></label>
                  <label>Phone<input name="public_phone" type="tel" defaultValue={profile.public_phone} maxLength={30} /></label>
                </div>
                <label>Agency or business name<input name="business_name" defaultValue={profile.business_name} maxLength={200} /></label>
                <label>Service area<input name="service_area" defaultValue={profile.service_area} maxLength={160} placeholder="e.g. Kilimani and Lavington" /></label>
                <label>Professional description<textarea name="description" defaultValue={profile.description} rows={4} maxLength={2000} /></label>
                <div className="agent-actions">
                  <button className="agent-button" type="submit" disabled={saving}>{saving ? "Saving…" : "Save profile"}</button>
                  {profile.verification_status !== "VERIFIED" && profile.verification_status !== "PENDING" && (
                    <button className="agent-button agent-button--outline" type="button" onClick={requestVerification} disabled={saving}>
                      Request verification
                    </button>
                  )}
                </div>
                {profile.verification_status === "PENDING" && <p className="agent-note">Your request is waiting for staff review. You can save drafts while it is pending.</p>}
                {profile.verification_status === "VERIFIED" && <p className="agent-note agent-note--verified">Verified agents can publish a listing after an owner authorizes its unit.</p>}
              </form>
            </section>

            <section className="agent-panel" aria-labelledby="authorized-homes-title">
              <div className="agent-panel-heading">
                <div><h2 id="authorized-homes-title">Authorized homes</h2><p>Owners grant access from their property workspace.</p></div>
                <span className="agent-record-count">{units.length}</span>
              </div>
              {units.length ? <ul className="agent-unit-list">
                {units.map(unit => <li key={unit.authorization_id}>
                  <strong>{unit.property_name} · {unit.unit_name}</strong>
                  <span>{unit.building_name}{unit.city ? `, ${unit.city}` : ""}</span>
                  <small>{unit.bedrooms} bedroom{unit.bedrooms === 1 ? "" : "s"} · {unit.unit_status.toLowerCase()}</small>
                </li>)}
              </ul> : <div className="agent-empty">
                <h3>No owner authorizations yet</h3>
                <p>Ask a property owner to authorize your account email for the unit you will advertise. Their approval is recorded in Hodi.</p>
              </div>}
            </section>
          </div>

          <section className="agent-panel" aria-labelledby="agent-listings-title">
            <div className="agent-panel-heading">
              <div><h2 id="agent-listings-title">Listings</h2><p>Save a draft first. Publishing requires a verified profile and an active owner authorization.</p></div>
              <span className="agent-record-count">{listings.length}</span>
            </div>
            {!units.length && !listings.length ? <div className="agent-empty"><h3>Waiting for an owner</h3><p>Your authorized units will appear here before you can create a listing draft.</p></div> : null}
            {listings.length ? <div className="agent-table-wrap" role="region" aria-label="Your property listings" tabIndex={0}>
              <table className="agent-table">
                <thead><tr><th>Listing</th><th>Rent</th><th>Status</th><th>Actions</th></tr></thead>
                <tbody>{listings.map(listing => <tr key={listing.id}>
                  <td><strong>{listing.title}</strong><small>{listing.property_name} · {listing.unit_label}{listing.photos.length ? ` · ${listing.photos.length} photo${listing.photos.length === 1 ? "" : "s"}` : ""}</small></td>
                  <td>{formatMinor(listing.monthly_rent_minor, listing.currency, { trailingZeros: false })}</td>
                  <td><span className={statusClass(listing.status)}>{listing.status.toLowerCase().replaceAll("_", " ")}</span></td>
                  <td><div className="agent-row-actions">
                    {listing.status !== "ARCHIVED" && units.some(unit => unit.unit === listing.unit) && <button className="agent-text-button" type="button" onClick={() => editListing(listing)}>Edit</button>}
                    {listing.status !== "PUBLISHED" && listing.status !== "ARCHIVED" && profile.verification_status === "VERIFIED" && units.some(unit => unit.unit === listing.unit) && <button className="agent-text-button" type="button" onClick={() => void listingAction(listing.id, "publish")} disabled={saving}>Publish</button>}
                    {listing.status === "PUBLISHED" && <button className="agent-text-button" type="button" onClick={() => void listingAction(listing.id, "pause")} disabled={saving}>Pause</button>}
                    {listing.status !== "ARCHIVED" && <button className="agent-text-button agent-text-button--muted" type="button" onClick={() => void listingAction(listing.id, "archive")} disabled={saving}>Archive</button>}
                  </div></td>
                </tr>)}</tbody>
              </table>
            </div> : null}
            {availableUnits.length > 0 && <form id="agent-listing-form" className="agent-form agent-listing-form" onSubmit={saveListing}>
              <h3>{editingId ? "Edit listing" : "Create a listing draft"}</h3>
              <div className="agent-form-row">
                <label>Authorized unit<select name="unit" required defaultValue="">
                  <option value="" disabled>Select a home</option>
                  {availableUnits.map(unit => <option key={unit.unit} value={unit.unit}>{unit.property_name} · {unit.unit_name}</option>)}
                </select></label>
                <label>Monthly rent (KES)<input name="rent" inputMode="decimal" required placeholder="45000" /></label>
              </div>
              <label>Listing title<input name="title" required maxLength={200} placeholder="Bright one-bedroom near town" /></label>
              <div className="agent-form-row">
                <label>Bedrooms<input name="bedrooms" type="number" min="0" max="30" defaultValue="0" /></label>
                <label>Bathrooms<input name="bathrooms" type="number" min="0" max="30" defaultValue="0" /></label>
                <label>Area<input name="area" maxLength={120} placeholder="Kilimani" /></label>
              </div>
              <label>City<input name="city" required maxLength={100} placeholder="Nairobi" /></label>
              <label>Description<textarea name="description" rows={4} maxLength={10000} /></label>
              <label>Property photo<input name="image" type="file" accept="image/jpeg,image/png,image/webp,image/gif" /></label>
              <div className="agent-actions">
                <button className="agent-button" type="submit" disabled={saving}>{saving ? "Saving…" : editingId ? "Save changes" : "Save draft"}</button>
                {editingId && <button className="agent-button agent-button--quiet" type="button" onClick={() => { setEditingId(null); (document.getElementById("agent-listing-form") as HTMLFormElement | null)?.reset(); }}>Cancel edit</button>}
              </div>
            </form>}
          </section>

          <section className="agent-panel" aria-labelledby="agent-enquiries-title">
            <div className="agent-panel-heading"><div><h2 id="agent-enquiries-title">Enquiries and viewings</h2><p>Contact details are shown only for enquiries on listings you currently manage.</p></div><span className="agent-record-count">{inquiries.length}</span></div>
            {inquiries.length ? <div className="agent-enquiry-list">{inquiries.map(inquiry => <article className="agent-enquiry" key={inquiry.id}>
              <div className="agent-enquiry-top"><div><h3>{inquiry.name}</h3><p>{inquiry.email}{inquiry.phone ? ` · ${inquiry.phone}` : ""}</p></div><span className={statusClass(inquiry.status)}>{inquiry.status.toLowerCase()}</span></div>
              <p className="agent-enquiry-message">{inquiry.message}</p>
              <p className="agent-enquiry-listing">{listings.find(listing => listing.id === inquiry.listing)?.title ?? "Listing"} · {new Date(inquiry.created_at).toLocaleDateString()}</p>
              <div className="agent-enquiry-actions">
                <label>Enquiry status<select value={inquiry.status} onChange={event => void updateInquiry(inquiry.id, event.target.value)}>
                  <option value="NEW">New</option><option value="CONTACTED">Contacted</option><option value="CLOSED">Closed</option>
                </select></label>
                {inquiry.viewing_request && <div className="agent-viewing">
                  <div><strong>Viewing request</strong><span>{new Date(inquiry.viewing_request.requested_for).toLocaleString()}</span></div>
                  <span className={statusClass(inquiry.viewing_request.status)}>{inquiry.viewing_request.status.toLowerCase()}</span>
                  {inquiry.viewing_request.status === "REQUESTED" && <div className="agent-row-actions"><button className="agent-text-button" type="button" onClick={() => void updateViewing(inquiry.viewing_request!.id, "CONFIRMED")}>Confirm</button><button className="agent-text-button agent-text-button--muted" type="button" onClick={() => void updateViewing(inquiry.viewing_request!.id, "DECLINED")}>Decline</button></div>}
                  {inquiry.viewing_request.status === "CONFIRMED" && <button className="agent-text-button" type="button" onClick={() => void updateViewing(inquiry.viewing_request!.id, "CANCELLED")}>Cancel viewing</button>}
                </div>}
              </div>
            </article>)}</div> : <div className="agent-empty"><h3>No enquiries yet</h3><p>Enquiries submitted for your published listings will appear here.</p></div>}
          </section>
        </> : null}
      </div>
    </main>
  );
}
