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
    return (
      <div className="flex aspect-[16/10] flex-col items-center justify-center gap-2 rounded-2xl border border-border bg-soft-teal text-sm text-text-secondary" role="img" aria-label={`No listing photos available for ${title}`}>
        <svg aria-hidden="true" viewBox="0 0 32 32" className="h-10 w-10" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="m4 14 12-9 12 9v13H4z" />
          <path d="M12 27v-8h8v8M9 14h.01M23 14h.01" />
        </svg>
        <span>No listing photos</span>
      </div>
    );
  }

  return (
    <div>
      <button type="button" className="group block w-full overflow-hidden rounded-2xl border border-border bg-soft-teal focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal" onClick={() => setOpen(true)} aria-label={`Open photo: ${photo.caption || title}`}>
        {failed[active] ? (
          <div className="flex aspect-[16/10] flex-col items-center justify-center gap-2 text-sm text-text-secondary" role="img" aria-label={`Photo unavailable for ${title}`}>
            <svg aria-hidden="true" viewBox="0 0 32 32" className="h-10 w-10" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="m4 14 12-9 12 9v13H4z" />
              <path d="M12 27v-8h8v8M9 14h.01M23 14h.01" />
            </svg>
            <span>Photo unavailable</span>
          </div>
        ) : (
          <img
            src={photo.url}
            alt={photo.caption || title}
            decoding="async"
            sizes="(max-width: 1024px) 100vw, 65vw"
            onError={() => setFailed(current => ({ ...current, [active]: true }))}
            className="aspect-[16/10] w-full object-cover transition duration-200 group-hover:scale-[1.01]"
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
            <img src={photo.url} alt={photo.caption || title} sizes="100vw" className="mx-auto max-h-[78vh] w-full rounded-xl object-contain" />
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
