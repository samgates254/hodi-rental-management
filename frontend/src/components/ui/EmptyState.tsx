import type { ReactNode } from "react";
import { Button } from "@/components/ui/Button";

type EmptyStateProps = {
  icon: ReactNode;
  title: string;
  description: string;
  cta: {
    label: string;
    href?: string;
    onClick?: () => void;
  };
};

export function EmptyState({ icon, title, description, cta }: EmptyStateProps) {
  return (
    <section className="hodi-empty" aria-label={title}>
      <div className="hodi-empty-mark">
        {icon}
      </div>
      <h2>{title}</h2>
      <p className="mt-2 max-w-md text-sm leading-6 text-text-secondary">{description}</p>
      {cta.href ? (
        <Button href={cta.href} className="mt-5 min-h-11">{cta.label}</Button>
      ) : (
        <Button onClick={cta.onClick} className="mt-5 min-h-11">{cta.label}</Button>
      )}
    </section>
  );
}