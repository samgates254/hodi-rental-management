import type { ReactNode } from "react";

export default function SectionHead({
  eyebrow,
  title,
  titleId,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  titleId: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="portal-section-heading">
      <div>
        <p className="portal-section-eyebrow">{eyebrow}</p>
        <h2 id={titleId}>{title}</h2>
        {description && <p className="portal-section-description">{description}</p>}
      </div>
      {action}
    </div>
  );
}
