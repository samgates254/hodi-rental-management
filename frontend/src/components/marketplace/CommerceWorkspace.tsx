"use client";
import Image from "next/image";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { clientApi, getStoredAuthToken } from "@/lib/clientApi";
import { formatMinor, shillingsToCents } from "@/lib/money";
type Supplier = { id: number; organization: number; business_name: string };
type Listing = {
  id: number;
  organization: number;
  title: string;
  kind: string;
  category: string;
  description: string;
  price_minor: number | null;
  availability: string;
  is_published: boolean;
  photos: Array<{ id: number; url: string; caption: string }>;
};
type Order = {
  id: number;
  listing: number;
  listing_title: string;
  status: string;
  request_details: string;
  payment_status: string;
};
type Price = {
  material: string;
  unit: string;
  quantity: string;
  unit_price_cents: number;
  supplier: string;
  date: string;
  property: string;
};

function paymentStatusLabel(status: string) {
  if (status === "VERIFIED") return "Verified";
  return "Pending";
}

export default function CommerceWorkspace({
  organizationId,
}: {
  organizationId: string;
}) {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]),
    [listings, setListings] = useState<Listing[]>([]),
    [orders, setOrders] = useState<Order[]>([]),
    [prices, setPrices] = useState<Price[]>([]),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const load = useCallback(async () => {
    if (!organizationId) return;
    try {
      const [s, l, o] = await Promise.all([
        clientApi.get<Supplier[]>("/api/v1/marketplace/commerce/suppliers/"),
        clientApi.get<Listing[]>("/api/v1/marketplace/commerce/listings/", {
          params: { manage: 1 },
        }),
        clientApi.get<Order[]>("/api/v1/marketplace/commerce/orders/"),
      ]);
      const owned = l.data.filter(
        (x) => String(x.organization) === organizationId,
      );
      setSuppliers(
        s.data.filter((x) => String(x.organization) === organizationId),
      );
      setListings(owned);
      setOrders(
        o.data.filter((x) => owned.some((listing) => listing.id === x.listing)),
      );
      setError("");
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not load supplier workspace.",
      );
    }
  }, [organizationId]);
  useEffect(() => {
    void load();
  }, [load]);
  async function supplier(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    try {
      await clientApi.post("/api/v1/marketplace/commerce/suppliers/", {
        organization: Number(organizationId),
        business_name: f.get("business_name"),
        categories: String(f.get("categories") || "")
          .split(",")
          .map((x) => x.trim())
          .filter(Boolean),
      });
      e.currentTarget.reset();
      setNotice("Supplier profile saved.");
      await load();
    } catch (x) {
      setError(x instanceof Error ? x.message : "Could not save supplier.");
    }
  }
  async function listing(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    try {
      const { data: created } = await clientApi.post<Listing>(
        "/api/v1/marketplace/commerce/listings/",
        {
          organization: Number(organizationId),
          supplier: Number(f.get("supplier")),
          kind: f.get("kind"),
          availability: f.get("availability"),
          category: f.get("category"),
          title: f.get("title"),
          description: f.get("description"),
          price_minor: (() => {
            const raw = String(f.get("price") || "").trim();
            if (!raw) return null;
            const cents = shillingsToCents(raw);
            if (cents == undefined)
              throw new Error(
                "Enter a price in shillings with at most two decimal places.",
              );
            return cents;
          })(),
          price_unit: f.get("price_unit"),
          is_published: true,
        },
      );
      const image = f.get("image");
      if (image instanceof File && image.size) {
        const body = new FormData();
        body.append("image", image);
        const token = getStoredAuthToken();
        const response = await fetch(
          `/api/v1/marketplace/commerce/listings/${created.id}/photos/`,
          {
            method: "POST",
            headers: token ? { Authorization: `Token ${token}` } : {},
            body,
          },
        );
        if (!response.ok)
          throw new Error(
            "Listing saved, but its photo could not be uploaded.",
          );
      }
      e.currentTarget.reset();
      setNotice("Listing published.");
      await load();
    } catch (x) {
      setError(x instanceof Error ? x.message : "Could not save listing.");
    }
  }
  async function toggleListing(
    item: Listing,
    field: "is_published" | "availability",
    value: boolean | string,
  ) {
    try {
      await clientApi.patch(
        `/api/v1/marketplace/commerce/listings/${item.id}/`,
        { [field]: value },
      );
      setNotice("Listing updated.");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update listing.");
    }
  }
  async function transition(id: number, status: string) {
    try {
      await clientApi.patch(`/api/v1/marketplace/commerce/orders/${id}/`, {
        status,
      });
      setNotice(
        `Request updated to ${status.toLowerCase().replaceAll("_", " ")}.`,
      );
      await load();
    } catch (x) {
      setError(x instanceof Error ? x.message : "Could not update request.");
    }
  }
  async function compare(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    try {
      const { data } = await clientApi.get<Price[]>(
        "/api/v1/maintenance/price-history/",
        {
          params: { item: String(f.get("item")), unit: String(f.get("unit")) },
        },
      );
      setPrices(data);
    } catch (x) {
      setError(
        x instanceof Error ? x.message : "Could not load recorded prices.",
      );
    }
  }
  return (
    <section className="hodi-commerce-panel">
      <p className="flex items-center gap-2">HODI LIVING · PROCUREMENT <svg aria-hidden="true" viewBox="0 0 24 24" className="size-5 text-[var(--hodi-brand)]" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="m14.7 6.3 3-3a5 5 0 0 1-6.8 6.8L5 16a2.1 2.1 0 0 0 3 3l5.9-5.9a5 5 0 0 0 6.8-6.8l-3 3-3-3Z" /></svg></p>
      <h2>Suppliers, listings and requests</h2>
      <p>
        Only recorded supplier and purchase information is shown. Product prices
        come from the seller listing or recorded job purchases.
      </p>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      <form
        onSubmit={supplier}
        style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 20 }}
      >
        <input
          name="business_name"
          placeholder="Supplier business name"
          required
        />
        <input name="categories" placeholder="Categories, comma separated" />
        <button>Save supplier</button>
      </form>
      {suppliers.length > 0 && (
        <form
          onSubmit={listing}
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))",
            gap: 8,
            marginBottom: 24,
          }}
        >
          <select name="supplier" required defaultValue="">
            <option value="" disabled>
              Supplier
            </option>
            {suppliers.map((s) => (
              <option key={s.id} value={s.id}>
                {s.business_name}
              </option>
            ))}
          </select>
          <select name="kind">
            <option value="SERVICE">Service</option>
            <option value="PRODUCT">Product</option>
          </select>
          <select name="availability" required defaultValue="">
            <option value="" disabled>
              Choose availability
            </option>
            <option value="AVAILABLE">Available</option>
            <option value="UNAVAILABLE">Unavailable</option>
          </select>
          <input name="category" placeholder="Category slug" required />
          <input name="title" placeholder="Listing title" required />
          <input
            name="price"
            type="number"
            step="0.01"
            min="0.01"
            placeholder="Price (KES)"
          />
          <input
            name="price_unit"
            placeholder="Per item / visit"
            defaultValue="item"
          />
          <textarea name="description" placeholder="Description" required />
          <input
            name="image"
            type="file"
            accept="image/jpeg,image/png,image/webp"
          />
          <button>Publish listing</button>
        </form>
      )}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))",
          gap: 12,
        }}
      >
        {listings.map((x) => (
          <article
            key={x.id}
            style={{ padding: 14, border: "1px solid #ddd", borderRadius: 10 }}
          >
            {x.photos?.[0] && (
              <Image
                src={x.photos[0].url}
                alt={x.photos[0].caption || x.title}
                unoptimized
                width={640}
                height={160}
                style={{ width: "100%", height: 160, objectFit: "cover" }}
              />
            )}
            <strong>{x.title}</strong>
            <p>
              {x.category} · {x.kind} · {x.availability} ·{" "}
              {x.is_published ? "Published" : "Draft"}
            </p>
            <button
              onClick={() =>
                void toggleListing(
                  x,
                  "availability",
                  x.availability === "AVAILABLE" ? "UNAVAILABLE" : "AVAILABLE",
                )
              }
            >
              {x.availability === "AVAILABLE"
                ? "Mark unavailable"
                : "Mark available"}
            </button>{" "}
            <button
              onClick={() =>
                void toggleListing(x, "is_published", !x.is_published)
              }
            >
              {x.is_published ? "Unpublish" : "Publish"}
            </button>
          </article>
        ))}
      </div>
      <h3>Provider requests</h3>
      {orders.map((x) => (
        <article
          key={x.id}
          className="hodi-commerce-order"
        >
          {x.listing_title} · {x.status}{" "}
          <small>Payment: <strong className={x.payment_status === "VERIFIED" ? "text-[var(--hodi-success)]" : "text-[var(--hodi-warning)]"}>{paymentStatusLabel(x.payment_status)}</strong></small>
          {x.payment_status !== "VERIFIED" && <p role="status" className="hodi-payment-pending">Payment is pending verification. Do not treat this request as paid.</p>}
          <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
            {(
              {
                REQUESTED: ["ACCEPTED", "REJECTED"],
                ACCEPTED: ["IN_PROGRESS"],
                IN_PROGRESS: ["COMPLETED"],
              } as Record<string, string[]>
            )[x.status]?.map((next) => (
              <button key={next} onClick={() => void transition(x.id, next)}>
                {next.replaceAll("_", " ")}
              </button>
            ))}
          </div>
        </article>
      ))}
      <h3>Recorded purchase price comparison</h3>
      <form
        onSubmit={compare}
        style={{ display: "flex", gap: 8, flexWrap: "wrap" }}
      >
        <input name="item" placeholder="Exact material name" required />
        <input name="unit" placeholder="Exact unit (e.g. metre)" required />
        <button>Compare recorded prices</button>
      </form>
      {prices.map((x, i) => (
        <p key={`${x.date}-${i}`}>
          {x.material}, {x.quantity} {x.unit}: {formatMinor(x.unit_price_cents)}{" "}
          per {x.unit} · {x.supplier} · {x.date} · {x.property}
        </p>
      ))}
    </section>
  );
}
