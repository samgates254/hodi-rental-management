"use client";

import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";
import { useMagnetic } from "@/hooks/useMagnetic";

type Variant = "primary" | "secondary" | "ghost" | "outline-light";
type Size = "md" | "lg" | "sm";

const variants: Record<Variant, string> = {
  primary:
    "bg-teal text-brand-contrast hover:bg-[var(--hodi-brand-hover)] shadow-soft focus-visible:ring-teal",
  secondary:
    "bg-surface text-charcoal border border-border hover:border-charcoal/25 hover:bg-bg shadow-soft",
  ghost: "bg-transparent text-charcoal hover:bg-soft-teal/60",
  "outline-light":
    "bg-transparent text-white border border-white/35 hover:bg-white/10",
};

const sizes: Record<Size, string> = {
  sm: "h-9 px-3.5 text-sm",
  md: "h-11 px-5 text-sm",
  lg: "h-12 px-6 text-[0.9375rem]",
};

type BaseProps = {
  variant?: Variant;
  size?: Size;
  className?: string;
  magnetic?: boolean;
  children: ReactNode;
};

type ButtonAsButton = BaseProps &
  Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className" | "children"> & {
    href?: undefined;
  };

type ButtonAsLink = BaseProps & {
  href: string;
  external?: boolean;
};

export function Button(props: ButtonAsButton | ButtonAsLink) {
  const variant = props.variant ?? "primary";
  const size = props.size ?? "md";
  const magnetic = props.magnetic ?? (variant === "primary" || variant === "secondary");
  const { className, children } = props;

  const magneticRef = useMagnetic<HTMLAnchorElement | HTMLButtonElement>(
    magnetic ? 0.32 : 0,
    magnetic ? 8 : 0
  );

  const classes = cn(
    "inline-flex items-center justify-center gap-2 rounded-md font-medium tracking-tight transition-colors duration-200 select-none",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-bg",
    "disabled:pointer-events-none disabled:opacity-50",
    variants[variant],
    sizes[size],
    className
  );

  if ("href" in props && props.href) {
    const { href, external } = props;
    if (external) {
      return (
        <a
          ref={magneticRef as React.Ref<HTMLAnchorElement>}
          href={href}
          className={classes}
          target="_blank"
          rel="noopener noreferrer"
        >
          {children}
        </a>
      );
    }
    return (
      <Link
        ref={magneticRef as React.Ref<HTMLAnchorElement>}
        href={href}
        className={classes}
      >
        {children}
      </Link>
    );
  }

  const buttonProps = props as ButtonAsButton;
  const {
    type = "button",
    disabled,
    onClick,
    id,
    name,
    value,
    form,
    "aria-label": ariaLabel,
  } = buttonProps;

  return (
    <button
      ref={magneticRef as React.Ref<HTMLButtonElement>}
      type={type}
      className={classes}
      disabled={disabled}
      onClick={onClick}
      id={id}
      name={name}
      value={value}
      form={form}
      aria-label={ariaLabel}
    >
      {children}
    </button>
  );
}
