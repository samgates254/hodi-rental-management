"use client";

import Image from "next/image";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import { clientApi } from "@/lib/clientApi";
import { apiErrorMessage, asList } from "@/lib/opsApi";
import { isPanoramaCaption, minorToShillingsInput, rentLabel, shillingsToCents, type ManagedListing } from "./shared";

type Id = number | string;

type UnitRow = { id: Id; building: Id; name: string; status: string; bedrooms: number };
type BuildingRow = { id: Id; property: Id; name: string };
type PropertyRow = { id: Id; name: string; city: string };

function unitLabel(unit: UnitRow, buildings: BuildingRow[], properties: PropertyRow[]) {
  const building = buildings.find(item => String(item.id) === String(unit.building));
  const property = properties.find(item => String(item.id) === String(building?.property));
  return `${property?.name ?? "Property"} · ${building?.name ?? "Building"} · ${unit.name}`;
}

function AuthThumb({ url, alt }: { url: string; alt: string }) {
  const [src, setSrc] = useState("");
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let objectUrl = "";
    let cancelled = false;
    setFailed(false);
    setSrc("");
    clientApi.get<Blob>(url, { responseType: "blob" }).then(response => {
      if (cancelled) return;
      objectUrl = URL.createObjectURL(response.data);
      setSrc(objectUrl);
    }).catch(() => {
      if (!cancelled) setFailed(true);
    });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [url]);
  if (!src) return <span role={failed ? "img" : "status"} aria-label={failed ? `Photo unavailable: ${alt}` : `Loading photo: ${alt}`} style={{ display: "inline-grid", width: 64, height: 48, placeItems: "center", borderRadius: 6, background: "var(--hodi-surface-raised)", color: "var(--hodi-muted)", fontSize: 10 }}>{failed ? "Unavailable" : "Loading…"}</span>;
  return <Image src={src} alt={alt} width={64} height={48} loading="lazy" decoding="async" unoptimized style={{ width: 64, height: 48, objectFit: "cover", borderRadius: 6 }} />;
}

export default function MarketplaceManager({
  units,
  buildings,
  properties,
}: {
  units: UnitRow[];
  buildings: BuildingRow[];
  properties: PropertyRow[];
}) {
  const [listings, setListings] = useState<ManagedListing[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<ManagedListing | null>(null);
  const [inquiries, setInquiries] = useState<Record<string, { id: number; name: string; email: string; phone: string; message: string; created_at: string }[]>>({});
  const [panoramaUpload, setPanoramaUpload] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await clientApi.get<ManagedListing[]>("/api/v1/marketplace/manage/listings/");
      setListings(asList(response.data));
    } catch (reason) {
      setError(apiErrorMessage(reason, "Listings could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const listedUnitIds = new Set(listings.map(listing => String(listing.unit)));

  async function createListing(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const unit = units.find(item => String(item.id) === String(form.get("unit")));
    const building = buildings.find(item => String(item.id) === String(unit?.building));
    const property = properties.find(item => String(item.id) === String(building?.property));
    const rent = shillingsToCents(String(form.get("rent") ?? ""));
    if (!rent) {
      setError("Enter the advertised monthly rent in shillings.");
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await clientApi.post("/api/v1/marketplace/manage/listings/", {
        unit: Number(form.get("unit")),
        title: String(form.get("title") ?? "").trim(),
        description: String(form.get("description") ?? "").trim(),
        monthly_rent_minor: rent,
        currency: "KES",
        bedrooms: Number(form.get("bedrooms") ?? unit?.bedrooms ?? 0),
        bathrooms: Number(form.get("bathrooms") ?? 0),
        floor: form.get("floor") ? Number(form.get("floor")) : null,
        size_sqm: form.get("size_sqm") ? Number(form.get("size_sqm")) : null,
        furnished: form.get("furnished") === "true",
        amenities: String(form.get("amenities") ?? "").split(",").map(item => item.trim()).filter(Boolean),
        area: String(form.get("area") ?? "").trim(),
        city: String(form.get("city") ?? "").trim() || property?.city || "",
        country: "Kenya",
      });
      event.currentTarget.reset();
      setNotice("Draft saved. Publish it when the unit is available.");
      await load();
    } catch (reason) {
      setError(apiErrorMessage(reason, "The listing could not be saved."));
    } finally {
      setSaving(false);
    }
  }

  async function saveEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing) return;
    const form = new FormData(event.currentTarget);
    const rent = shillingsToCents(String(form.get("rent") ?? ""));
    if (!rent) {
      setError("Enter the advertised monthly rent in shillings.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await clientApi.patch(`/api/v1/marketplace/manage/listings/${editing.id}/`, {
        title: String(form.get("title") ?? "").trim(),
        description: String(form.get("description") ?? "").trim(),
        monthly_rent_minor: rent,
        bedrooms: Number(form.get("bedrooms") ?? 0),
        bathrooms: Number(form.get("bathrooms") ?? 0),
        furnished: form.get("furnished") === "true",
        amenities: String(form.get("amenities") ?? "").split(",").map(item => item.trim()).filter(Boolean),
        area: String(form.get("area") ?? "").trim(),
        city: String(form.get("city") ?? "").trim(),
      });
      setEditing(null);
      setNotice("Listing updated.");
      await load();
    } catch (reason) {
      setError(apiErrorMessage(reason, "The listing could not be updated."));
    } finally {
      setSaving(false);
    }
  }

  async function run(listing: ManagedListing, action: "publish" | "unpublish" | "delete") {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      if (action === "delete") {
        await clientApi.delete(`/api/v1/marketplace/manage/listings/${listing.id}/`);
        setNotice("Listing deleted.");
      } else {
        await clientApi.post(`/api/v1/marketplace/manage/listings/${listing.id}/${action}/`);
        setNotice(action === "publish" ? "Listing published." : "Listing unpublished.");
      }
      await load();
    } catch (reason) {
      setError(apiErrorMessage(reason, "That listing action failed."));
    } finally {
      setSaving(false);
    }
  }

  async function uploadPhoto(listing: ManagedListing, file: File) {
    const body = new FormData();
    body.set("image", file);
    body.set("is_primary", listing.photos.length ? "false" : "true");
    if (panoramaUpload[listing.id]) body.set("caption", "360:");
    setSaving(true);
    setError("");
    try {
      await clientApi.post(`/api/v1/marketplace/manage/listings/${listing.id}/photos/`, body);
      setNotice("Photo added.");
      await load();
    } catch (reason) {
      setError(apiErrorMessage(reason, "The photo could not be uploaded."));
    } finally {
      setSaving(false);
    }
  }

  async function showInquiries(listing: ManagedListing) {
    setSaving(true);
    setError("");
    try {
      const response = await clientApi.get<{ id: number; name: string; email: string; phone: string; message: string; created_at: string }[]>(
        `/api/v1/marketplace/manage/listings/${listing.id}/inquiries/`,
      );
      setInquiries(current => ({ ...current, [listing.id]: asList(response.data) }));
    } catch (reason) {
      setError(apiErrorMessage(reason, "Inquiries could not be loaded."));
    } finally {
      setSaving(false);
    }
  }

  async function removePhoto(listing: ManagedListing, photoId: number) {
    setSaving(true);
    setError("");
    try {
      await clientApi.delete(`/api/v1/marketplace/manage/listings/${listing.id}/photos/${photoId}/`);
      await load();
    } catch (reason) {
      setError(apiErrorMessage(reason, "The photo could not be deleted."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section id="marketplace" className="landlord-section">
      <div className="landlord-section-heading">
        <div>
          <span className="landlord-eyebrow">MARKETPLACE</span>
          <h2>Listing desk</h2>
        </div>
        <span className="landlord-section-count">{listings.length} listings</span>
      </div>
      <p className="landlord-form-note">
        A listing publishes only when its unit is available and has no active lease. Tenants, caretakers, and accountants cannot manage these records.
      </p>
      {error && <div className="landlord-alert" role="alert">{error}</div>}
      {notice && <div className="landlord-notice" role="status">{notice}</div>}
      {loading ? <p>Loading your listings…</p> : null}

      <form className="landlord-form" onSubmit={event => void createListing(event)}>
        <div className="landlord-form-grid">
          <label>Unit
            <select name="unit" required defaultValue="">
              <option value="" disabled>Choose a unit</option>
              {units.map(unit => (
                <option key={unit.id} value={unit.id} disabled={listedUnitIds.has(String(unit.id))}>
                  {unitLabel(unit, buildings, properties)} · {unit.status}{listedUnitIds.has(String(unit.id)) ? " · listed" : ""}
                </option>
              ))}
            </select>
          </label>
          <label>Title<input name="title" required maxLength={200} /></label>
          <label>Monthly rent (KES)<input name="rent" inputMode="decimal" required placeholder="45000" /></label>
          <label>Bedrooms<input name="bedrooms" type="number" min="0" max="30" defaultValue="1" /></label>
          <label>Bathrooms<input name="bathrooms" type="number" min="0" max="30" defaultValue="1" /></label>
          <label>Floor<input name="floor" type="number" min="0" max="200" /></label>
          <label>Size (m²)<input name="size_sqm" type="number" min="1" /></label>
          <label>Furnished
            <select name="furnished" defaultValue="false">
              <option value="false">Unfurnished</option>
              <option value="true">Furnished</option>
            </select>
          </label>
          <label>Area<input name="area" maxLength={120} /></label>
          <label>City<input name="city" maxLength={100} placeholder="Uses the property city if empty" /></label>
          <label>Amenities<input name="amenities" placeholder="Water, Parking" /></label>
        </div>
        <label>Description<textarea name="description" rows={3} /></label>
        <button className="landlord-button landlord-button--primary" disabled={saving || units.length === 0}>
          {saving ? "Saving…" : "Save draft"}
        </button>
      </form>

      {editing && (
        <form className="landlord-form" onSubmit={event => void saveEdit(event)}>
          <h3>Edit {editing.title}</h3>
          <div className="landlord-form-grid">
            <label>Title<input name="title" required defaultValue={editing.title} /></label>
            <label>Monthly rent (KES)<input name="rent" required defaultValue={minorToShillingsInput(editing.monthly_rent_minor)} /></label>
            <label>Bedrooms<input name="bedrooms" type="number" min="0" defaultValue={editing.bedrooms} /></label>
            <label>Bathrooms<input name="bathrooms" type="number" min="0" defaultValue={editing.bathrooms} /></label>
            <label>Furnished
              <select name="furnished" defaultValue={editing.furnished ? "true" : "false"}>
                <option value="false">Unfurnished</option>
                <option value="true">Furnished</option>
              </select>
            </label>
            <label>Area<input name="area" defaultValue={editing.area} /></label>
            <label>City<input name="city" required defaultValue={editing.city} /></label>
            <label>Amenities<input name="amenities" defaultValue={editing.amenities.join(", ")} /></label>
          </div>
          <label>Description<textarea name="description" rows={3} defaultValue={editing.description} /></label>
          <div className="landlord-section-actions">
            <button className="landlord-button landlord-button--primary" disabled={saving}>Save changes</button>
            <button type="button" className="landlord-button" onClick={() => setEditing(null)}>Cancel</button>
          </div>
        </form>
      )}

      {listings.length === 0 && !loading ? (
        <div className="landlord-empty-state">
          <h3>No listings yet</h3>
          <p>Choose one of your units and save a draft. Nothing is published until you say so.</p>
        </div>
      ) : (
        <div className="landlord-table-wrap">
          <table className="landlord-table">
            <thead>
              <tr>
                <th>Listing</th>
                <th>Unit</th>
                <th>Rent</th>
                <th>Status</th>
                <th>Photos</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {listings.map(listing => {
                const unit = units.find(item => String(item.id) === String(listing.unit));
                return (
                  <tr key={listing.id}>
                    <td>
                      <strong>{listing.title}</strong>
                      <div>{listing.city}{listing.area ? ` · ${listing.area}` : ""}</div>
                    </td>
                    <td>{unit ? unitLabel(unit, buildings, properties) : listing.unit_label}<div>{listing.unit_status}</div></td>
                    <td>{rentLabel(listing.monthly_rent_minor)}</td>
                    <td>
                      <span className={`landlord-status ${listing.is_publicly_available ? "is-active" : ""}`}>
                        {listing.status}{listing.is_publicly_available ? " · public" : ""}
                      </span>
                    </td>
                    <td>
                      <div className="flex flex-wrap gap-2">
                        {listing.photos.map(photo => (
                          <span key={photo.id}>
                            <AuthThumb url={photo.url} alt={photo.caption || listing.title} />
                            {isPanoramaCaption(photo.caption) && <span>360° photo</span>}
                            <button type="button" onClick={() => void removePhoto(listing, photo.id)} disabled={saving}>Remove{photo.is_primary ? " primary" : ""}</button>
                          </span>
                        ))}
                      </div>
                      <label>
                        Add photo
                        <input
                          type="file"
                          accept="image/jpeg,image/png,image/webp,image/gif"
                          disabled={saving}
                          onChange={event => {
                            const file = event.target.files?.[0];
                            event.target.value = "";
                            if (file) void uploadPhoto(listing, file);
                          }}
                        />
                      </label>
                      <label>
                        <input
                          type="checkbox"
                          checked={Boolean(panoramaUpload[listing.id])}
                          onChange={event => setPanoramaUpload(current => ({ ...current, [listing.id]: event.target.checked }))}
                        />
                        {" "}Mark the next upload as an equirectangular 360° photograph
                      </label>
                      <p>Use this only for a real 360° photo. Visitors can drag around inside it. It is not a 3D scan or a digital twin.</p>
                    </td>
                    <td>
                      <button type="button" className="landlord-button" onClick={() => setEditing(listing)} disabled={saving}>Edit</button>
                      {listing.status === "PUBLISHED" ? (
                        <button type="button" className="landlord-button" onClick={() => void run(listing, "unpublish")} disabled={saving}>Unpublish</button>
                      ) : (
                        <button type="button" className="landlord-button landlord-button--primary" onClick={() => void run(listing, "publish")} disabled={saving || listing.unit_status !== "AVAILABLE"}>Publish</button>
                      )}
                      <button type="button" className="landlord-button" onClick={() => void showInquiries(listing)} disabled={saving}>Inquiries</button>
                      <button type="button" className="landlord-button" onClick={() => void run(listing, "delete")} disabled={saving}>Delete</button>
                      {inquiries[listing.id] && (
                        <ul>
                          {inquiries[listing.id].length === 0 && <li>No inquiries yet.</li>}
                          {inquiries[listing.id].map(inquiry => (
                            <li key={inquiry.id}>{inquiry.name} · {inquiry.email} · {inquiry.message}</li>
                          ))}
                        </ul>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
