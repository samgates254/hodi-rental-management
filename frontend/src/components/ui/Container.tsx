import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

type Tag = "div" | "section" | "header" | "footer" | "nav";

export function Container({
  children,
  className,
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: Tag;
}) {
  return (
    <Tag
      className={cn(
        "container-hodi mx-auto w-full max-w-[1200px] px-5 sm:px-6 lg:px-8",
        className,
      )}
    >
      {children}
    </Tag>
  );
}
