import type { HTMLAttributes } from "react";

export default function Card({ className = "", ...props }: HTMLAttributes<HTMLElement>) {
  return (
    <article
      {...props}
      className={`rounded-xl border border-border bg-surface shadow-soft ${className}`}
    />
  );
}
