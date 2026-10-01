/** Shared site navigation — works from any route. */
export const primaryNav = [
  { label: "Platform", href: "/platform" },
  { label: "Solutions", href: "/solutions" },
  { label: "About", href: "/about" },
  { label: "Contact", href: "/contact" },
] as const;

export const footerProduct = [
  { label: "Platform", href: "/platform" },
  { label: "Solutions", href: "/solutions" },
  { label: "How it works", href: "/#how-it-works" },
] as const;

export const footerCompany = [
  { label: "About", href: "/about" },
  { label: "Contact", href: "/contact" },
] as const;

/** Real contact surface used across the site. */
export const contactEmail = "hello@hodi.app";
export const contactMailto = `mailto:${contactEmail}`;
export const demoMailto = "mailto:hello@hodi.app?subject=Talk%20to%20Hodi";
