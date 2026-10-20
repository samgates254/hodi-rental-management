const PANORAMA_CAPTION = /^360:\s*/i;

/** A listing photo is a 360° photograph only when its caption was explicitly marked. */
export function isPanoramaCaption(caption: string | null | undefined): boolean {
  return PANORAMA_CAPTION.test((caption ?? "").trim());
}

/** Store an equirectangular photo without dropping a human-readable caption. */
export function panoramaCaption(caption: string): string {
  const visible = caption.replace(PANORAMA_CAPTION, "").trim();
  return visible ? `360: ${visible}` : "360:";
}

/** Caption shown to visitors. The 360 marker is an implementation flag, not a description. */
export function visibleCaption(caption: string | null | undefined): string {
  return (caption ?? "").replace(PANORAMA_CAPTION, "").trim();
}
