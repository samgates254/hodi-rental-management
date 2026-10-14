"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { clientApi } from "@/lib/clientApi";
import { formatMinor } from "@/lib/money";
import { RemotePhoto } from "@/components/marketplace/RemotePhoto";

type Listing = {
  id: number;
  kind: string;
  category: string;
  title: string;
  description: string;
  supplier_name: string;
  price_minor: number | null;
  currency: string;
  price_unit: string;
  photos: Array<{ id: number; url: string; caption: string }>;
};

type Order = {
  id: number;
  listing: number;
  listing_title: string;
  supplier_name: string;
  quantity: string;
  request_details: string;
  status: string;
  payment_status: string;
};

export default function LivingPage() {
  const [list, setList] = useState<Listing[]>([]);
  const [categoryOptions, setCategoryOptions] = useState<string[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [kind, setKind] = useState("");
  const [category, setCategory] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [details, setDetails] = useState<Record<number, string>>({});
  const [quantities, setQuantities] = useState<Record<number, string>>({});

  const load = useCallback(async () => {
    setError("");
    try {
      const [filtered, all, mine] = await Promise.all([
        clientApi.get<Listing[]>("/api/v1/marketplace/commerce/listings/", {
          params: { ...(kind ? { kind } : {}), ...(category ? { category } : {}) },
        }),
        clientApi.get<Listing[]>("/api/v1/marketplace/commerce/listings/"),
        clientApi.get<Order[]>("/api/v1/marketplace/commerce/orders/"),
      ]);
      setList(filtered.data);
      setCategoryOptions(Array.from(new Set(all.data.map((item) => item.category))).sort());
      setOrders(mine.data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Could not load Hodi Living.");
    } finally {
      setLoading(false);
    }
  }, [kind, category]);

  useEffect(() => {
    void load();
  }, [load]);

  async function request(item: Listing) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await clientApi.post("/api/v1/marketplace/commerce/orders/", {
        listing: item.id,
        quantity: quantities[item.id] || "1",
        request_details: details[item.id] || "",
      });
      setNotice("Your request was sent. It is not a confirmed booking, and no payment has been taken.");
      setDetails((current) => ({ ...current, [item.id]: "" }));
      await load();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not submit request.");
    } finally {
      setBusy(false);
    }
  }

  async function cancel(id: number) {
    setError("");
    try {
      await clientApi.delete(`/api/v1/marketplace/commerce/orders/${id}/`);
      await load();
    } catch (cancelError) {
      setError(cancelError instanceof Error ? cancelError.message : "Could not cancel request.");
    }
  }

  return (
    <main className="hodi-record">
      <div className="hodi-record-wrap">
        <Link className="hodi-record-back" href="/clients">← Tenant dashboard</Link>
        <p className="hodi-record-kicker">Hodi Living</p>
        <h1>Services and household goods</h1>
        <p className="hodi-record-lead">
          Send a request to a provider and follow its status here. A request is not an order confirmation. Hodi Living does not take payment.
        </p>

        <div className="hodi-record-filters">
          <label>
            Listing type
            <select aria-label="Listing type" value={kind} onChange={(event) => setKind(event.target.value)}>
              <option value="">All services and products</option>
              <option value="SERVICE">Services</option>
              <option value="PRODUCT">Products</option>
            </select>
          </label>
          <label>
            Category
            <select aria-label="Category" value={category} onChange={(event) => setCategory(event.target.value)}>
              <option value="">All categories</option>
              {categoryOptions.map((option) => (
                <option key={option}>{option}</option>
              ))}
            </select>
          </label>
          <button type="button" className="secondary" onClick={() => void load()}>Refresh</button>
        </div>

        {error && <p className="hodi-record-alert" role="alert">{error}</p>}
        {notice && <p className="hodi-record-ok" role="status">{notice}</p>}
        {loading && <p className="hodi-record-note">Loading listings…</p>}

        <section className="hodi-record-grid" aria-label="Available listings">
          {list.map((item) => (
            <article className="hodi-record-card" key={item.id}>
              {item.photos[0] && (
                <span className="hodi-record-photo">
                  <RemotePhoto
                    src={item.photos[0].url}
                    alt={item.photos[0].caption || item.title}
                    fill
                    sizes="(max-width: 800px) 100vw, 33vw"
                  />
                </span>
              )}
              <p className="hodi-record-meta">{item.category} · {item.kind.toLowerCase()}</p>
              <h2>{item.title}</h2>
              <p>{item.description}</p>
              <p>Provided by {item.supplier_name}</p>
              <strong className="hodi-record-price">
                {item.price_minor == null
                  ? "Price on request"
                  : `${formatMinor(item.price_minor, item.currency || "KES")} / ${item.price_unit}`}
              </strong>
              <label>
                Quantity
                <input
                  type="number"
                  min="0.001"
                  step="0.001"
                  value={quantities[item.id] || "1"}
                  onChange={(event) => setQuantities((current) => ({ ...current, [item.id]: event.target.value }))}
                />
              </label>
              <label>
                Request details
                <textarea
                  value={details[item.id] || ""}
                  onChange={(event) => setDetails((current) => ({ ...current, [item.id]: event.target.value }))}
                  maxLength={2000}
                  placeholder="Add preferences or delivery details"
                />
              </label>
              <button type="button" disabled={busy} onClick={() => void request(item)}>
                {busy ? "Sending…" : "Request"}
              </button>
            </article>
          ))}
        </section>
        {!loading && !list.length && !error && (
          <p className="hodi-record-note">No listings are currently available in this category.</p>
        )}

        <section>
          <h2>Your requests</h2>
          {orders.map((order) => (
            <article className="hodi-record-row" key={order.id}>
              <div>
                <strong>{order.listing_title}</strong>
                <p className="hodi-record-note">
                  {order.status.replaceAll("_", " ")} · Provider: {order.supplier_name} · Payment: not processed ({order.payment_status})
                </p>
              </div>
              {order.status === "REQUESTED" && (
                <button type="button" className="secondary" onClick={() => void cancel(order.id)}>Cancel request</button>
              )}
            </article>
          ))}
          {!loading && !error && !orders.length && <p className="hodi-record-note">Your requests will appear here.</p>}
        </section>
      </div>
    </main>
  );
}
