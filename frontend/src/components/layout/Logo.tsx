import Image from "next/image";
import Link from "next/link";
import { cn } from "@/lib/cn";

type LogoProps = {
  className?: string;
  /** Rendered mark size in CSS pixels. Default 36. */
  size?: number;
  /** Mark only — hide the Hodi wordmark. */
  markOnly?: boolean;
  wordmarkClassName?: string;
};

/**
 * Hodi lockup — official mark (transparent PNG, multi-resolution) + wordmark.
 * Uses a 2x/3x src so the mark stays sharp on retina displays.
 */
export function Logo({
  className,
  size = 36,
  markOnly = false,
  wordmarkClassName,
}: LogoProps) {
  const markPx = Math.max(24, Math.round(size));

  return (
    <Link
      href="/"
      className={cn(
        "group inline-flex items-center gap-2.5 rounded-sm outline-none",
        "focus-visible:ring-2 focus-visible:ring-teal focus-visible:ring-offset-2 focus-visible:ring-offset-bg",
        className,
      )}
      aria-label="Hodi home"
    >
      <span
        className="relative shrink-0"
        style={{ width: markPx, height: markPx }}
      >
        <Image
          src="/brand/hodi-mark-hd.png"
          alt=""
          width={1024}
          height={1024}
          priority
          sizes={`${markPx}px`}
          className="h-full w-full object-contain drop-shadow-[0_0.5px_0.5px_rgba(25,32,42,0.06)]"
          aria-hidden
        />
      </span>
      {!markOnly ? (
        <span
          className={cn(
            "font-display text-[1.125rem] font-semibold tracking-[-0.02em] text-charcoal",
            "transition-colors group-hover:text-charcoal/90",
            wordmarkClassName,
          )}
        >
          Hodi
        </span>
      ) : null}
    </Link>
  );
}
