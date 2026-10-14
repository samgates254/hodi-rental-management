import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export function SectionHeading({
  eyebrow,
  title,
  description,
  align = "left",
  light = false,
  className,
}: {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  align?: "left" | "center";
  light?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "max-w-2xl",
        align === "center" && "mx-auto text-center",
        className,
      )}
    >
      {eyebrow ? (
        <p className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-[#a8874f]">
          {eyebrow}
        </p>
      ) : null}
      <h2
        className={cn(
          "font-[family-name:var(--hodi-editorial)] text-3xl font-normal leading-[1.15] tracking-[-0.03em] text-balance sm:text-4xl",
          light ? "text-white" : "text-charcoal",
        )}
      >
        {title}
      </h2>
      {description ? (
        <p
          className={cn(
            "mt-4 text-base leading-relaxed text-pretty sm:text-lg",
            light ? "text-white/75" : "text-text-secondary",
          )}
        >
          {description}
        </p>
      ) : null}
    </div>
  );
}
