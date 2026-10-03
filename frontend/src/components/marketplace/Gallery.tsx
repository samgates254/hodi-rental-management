"use client";

import { useEffect, useState } from "react";
import type { ListingPhoto } from "./shared";

export function Gallery({ photos, title }: { photos: ListingPhoto[]; title: string }) {
  const [active, setActive] = useState(0);
  const [open, setOpen] = useState(false);
  const [failed, setFailed] = useState<Record<number, boolean>>({});
  const photo = photos[active];

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
      if (event.key === "ArrowRight") setActive(index => (index + 1) % photos.length);
      if (event.key === "ArrowLeft") setActive(index => (index - 1 + photos.length) % photos.length);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, photos.length]);

  if (!photo) {
    return <div className="flex aspect-[16/10] items-center justify-center rounded-2xl bg-[#e7eeec] text-sm text-text-secondary">No photo yet</div>;
  }

  return (
    <div>
      <button type="button" className="group block w-full overflow-hidden rounded-2xl bg-[#e7eeec] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal" onClick={() => setOpen(true)} aria-label="Open photo">
        {failed[active] ? (
          <div className="flex aspect-[16/10] items-center justify-center text-sm text-text-secondary">This photo could not be loaded</div>
        ) : (
          <img
            src={photo.url}
            alt={photo.caption || title}
            decoding="async"
            onError={() => setFailed(current => ({ ...current, [active]: true }))}
            className="aspect-[16/10] w-full object-cover transition duration-300 group-hover:scale-[1.02]"
          />
        )}
      </button>
      {photos.length > 1 && (
        <div className="mt-3 flex gap-2 overflow-x-auto">
          {photos.map((item, index) => (
            <button key={item.id} type="button" aria-label={item.caption || `Photo ${index + 1}`} aria-current={index === active} className={`h-16 w-20 shrink-0 overflow-hidden rounded-lg border focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal ${index === active ? "border-teal" : "border-border"}`} onClick={() => setActive(index)}>
              {failed[index] ? (
                <span className="flex h-full items-center justify-center text-[10px] text-text-secondary">Unavailable</span>
              ) : (
                <img src={item.url} alt="" loading="lazy" decoding="async" onError={() => setFailed(current => ({ ...current, [index]: true }))} className="h-full w-full object-cover" />
              )}
            </button>
          ))}
        </div>
      )}
      {open && !failed[active] && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Photo gallery"
          className="fixed inset-0 z-50 flex items-center justify-center bg-[#10151b]/92 p-4"
          onClick={() => setOpen(false)}
        >
          <div className="w-full max-w-5xl" onClick={event => event.stopPropagation()}>
            <img src={photo.url} alt={photo.caption || title} className="mx-auto max-h-[78vh] w-full rounded-xl object-contain" />
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-white">
              <button type="button" className="rounded-full px-3 py-2 hover:bg-white/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white" onClick={() => setActive(index => (index - 1 + photos.length) % photos.length)}>Previous</button>
              <span>{active + 1} / {photos.length}</span>
              <button type="button" className="rounded-full px-3 py-2 hover:bg-white/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white" onClick={() => setActive(index => (index + 1) % photos.length)}>Next</button>
              <button type="button" className="rounded-full px-3 py-2 hover:bg-white/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white" onClick={() => setOpen(false)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
