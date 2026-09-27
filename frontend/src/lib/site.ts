/** Shared site navigation — works from any route. */
export const primaryNav = [
  { label: "Platform", href: "/platform" },
  { label: "How It Works", href: "/#how-it-works" },
  { label: "For Owners", href: "/#owners" },
  { label: "For Tenants", href: "/#tenants" },
  { label: "About", href: "/#about" },
] as const;

export const demoMailto =
  "mailto:hello@hodi.app?subject=Request%20a%20demo%20—%20Hodi";

export const contactMailto =
  "mailto:hello@hodi.app?subject=Talk%20to%20Hodi";
