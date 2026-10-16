"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import { isPanoramaCaption, visibleCaption } from "@/lib/listingMedia";
import type { ListingPhoto } from "./shared";
import { RemotePhoto } from "./RemotePhoto";

const PanoramaViewer = dynamic(
  () => import("./PanoramaViewer").then(mod => mod.PanoramaViewer),
  {
    ssr: false,
    loading: () => <p className="absolute inset-0 grid place-items-center text-sm text-white">Loading 360° photograph…</p>,
  },
);

function orderedPhotos(photos: ListingPhoto[]) {
  return [...photos].sort((left, right) => left.position - right.position || left.id - right.id);
}

export function Gallery({ photos, title }: { photos: ListingPhoto[]; title: string }) {
  const frames = orderedPhotos(photos);
  const [active, setActive] = useState(0);
  const [open, setOpen] = useState(false);
  const [failed, setFailed] = useState<Record<number, boolean>>({});
  const [panoramaFailed, setPanoramaFailed] = useState(false);
  const [preferStill, setPreferStill] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const photo = frames[active];
  const caption = photo ? visibleCaption(photo.caption) : "";
  const panorama = Boolean(photo && isPanoramaCaption(photo.caption) && !panoramaFailed && !preferStill);

  useEffect(() => {
    setPanoramaFailed(false);
    setPreferStill(false);
  }, [active, photo?.id]);

  useEffect(() => {
    if (!open) return;
    openerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previously = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
      if (event.key === "ArrowRight" && frames.length > 1) setActive(index => (index + 1) % frames.length);
      if (event.key === "ArrowLeft" && frames.length > 1) setActive(index => (index - 1 + frames.length) % frames.length);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previously;
      window.removeEventListener("keydown", onKey);
      openerRef.current?.focus();
    };
  }, [open, frames.length]);

  if (!photo) {
    return (
      <div className="hodi-listing-stage hodi-listing-card-empty" role="img" aria-label={`No listing photos available for ${title}`}>
        <svg aria-hidden="true" viewBox="0 0 32 32" className="h-10 w-10" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="m4 14 12-9 12 9v13H4z" />
          <path d="M12 27v-8h8v8M9 14h.01M23 14h.01" />
        </svg>
        <span>No listing photos</span>
      </div>
    );
  }

  const alt = caption || title;
  const stage = (contained: boolean) => (
    failed[active] ? (
      <div className={`hodi-stage-missing${contained ? " h-full" : ""}`} role="img" aria-label={`Photo unavailable for ${title}`}>
        <span>Photo unavailable</span>
      </div>
    ) : panorama ? (
      <PanoramaViewer src={photo.url} label={`${alt}. 360 degree photograph. Drag to look around.`} onUnavailable={() => setPanoramaFailed(true)} />
    ) : (
      <RemotePhoto
        src={photo.url}
        alt={alt}
        fill
        sizes={contained ? "100vw" : "(max-width: 1024px) 100vw, 65vw"}
        className="object-cover"
        onFail={() => setFailed(current => ({ ...current, [active]: true }))}
      />
    )
  );

  return (
    <div>
      <div className="hodi-stage">
        <div className="hodi-listing-stage">
          {open ? null : stage(false)}
          {!open && !panorama && !failed[active] && (
            <button
              type="button"
              className="absolute inset-0 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal"
              onClick={() => setOpen(true)}
              aria-label={`Open photo: ${alt}`}
            />
          )}
        </div>
        <div className="hodi-stage-bar">
          <p className="text-text-secondary">
            {panorama ? "360° photograph. Drag to look around. This is not a measured 3D model." : caption || `${active + 1} of ${frames.length}`}
          </p>
          <div className="flex flex-wrap gap-2">
            {isPanoramaCaption(photo.caption) && (
              <button
                type="button"
                className="min-h-11 rounded-lg border border-border px-3 text-sm font-semibold"
                onClick={() => {
                  setPanoramaFailed(false);
                  setPreferStill(current => !current);
                }}
              >
                {preferStill || panoramaFailed ? "View as 360° photo" : "View as still photo"}
              </button>
            )}
            <button type="button" className="min-h-11 rounded-lg border border-border px-3 text-sm font-semibold" onClick={() => setOpen(true)}>
              Full screen
            </button>
          </div>
        </div>
      </div>
      {frames.length > 1 && (
        <div className="mt-3 flex gap-2 overflow-x-auto" role="tablist" aria-label="Listing photos">
          {frames.map((item, index) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={index === active}
              aria-label={visibleCaption(item.caption) || `Photo ${index + 1}${isPanoramaCaption(item.caption) ? ", 360 degree photograph" : ""}`}
              className={`hodi-stage-thumb ${index === active ? "is-active" : ""}`}
              onClick={() => setActive(index)}
            >
              {failed[index] ? (
                <span className="flex h-full items-center justify-center text-[10px] text-text-secondary">Unavailable</span>
              ) : (
                <span className="relative block h-full w-full">
                  <RemotePhoto src={item.url} alt="" fill sizes="80px" className="object-cover" onFail={() => setFailed(current => ({ ...current, [index]: true }))} />
                </span>
              )}
              {isPanoramaCaption(item.caption) && <span className="absolute bottom-1 left-1 bg-[#102820] px-1 text-[10px] font-semibold tracking-wide text-[#f4efe4]">360°</span>}
            </button>
          ))}
        </div>
      )}
      {open && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={panorama ? "360 degree photograph" : "Photo gallery"}
          className="hodi-gallery-lightbox fixed inset-0 z-50 flex items-center justify-center bg-[#102820]/94 p-4"
          onClick={() => setOpen(false)}
        >
          <div className="w-full max-w-5xl" onClick={event => event.stopPropagation()}>
            <div className="relative mx-auto h-[78vh] w-full">
              {stage(true)}
            </div>
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-white">
              <button type="button" className="min-h-11 rounded-full px-3 py-2 hover:bg-white/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white disabled:opacity-40" onClick={() => setActive(index => (index - 1 + frames.length) % frames.length)} disabled={frames.length < 2}>Previous</button>
              <span>{active + 1} / {frames.length}{panorama ? " · 360° photograph" : ""}</span>
              <button type="button" className="min-h-11 rounded-full px-3 py-2 hover:bg-white/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white disabled:opacity-40" onClick={() => setActive(index => (index + 1) % frames.length)} disabled={frames.length < 2}>Next</button>
              <button ref={closeRef} type="button" className="min-h-11 rounded-full px-3 py-2 hover:bg-white/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white" onClick={() => setOpen(false)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
