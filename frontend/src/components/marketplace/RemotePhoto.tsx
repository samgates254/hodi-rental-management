"use client";

import Image from "next/image";
import { useState } from "react";

/** Listing photos come from the API and may be any host. They are not optimized by Next. */
export function RemotePhoto({
  src,
  alt,
  className,
  sizes,
  fill = false,
  onFail,
}: {
  src: string;
  alt: string;
  className?: string;
  sizes?: string;
  fill?: boolean;
  onFail?: () => void;
}) {
  const [failed, setFailed] = useState(false);
  const allowed = src.startsWith("http://") || src.startsWith("https://") || src.startsWith("/");
  if (failed || !allowed) return null;
  const fail = () => {
    setFailed(true);
    onFail?.();
  };
  if (fill) {
    return (
      <Image
        src={src}
        alt={alt}
        fill
        unoptimized
        sizes={sizes}
        className={className}
        onError={fail}
      />
    );
  }
  return (
    <Image
      src={src}
      alt={alt}
      width={160}
      height={120}
      unoptimized
      sizes={sizes}
      className={className}
      onError={() => setFailed(true)}
    />
  );
}
