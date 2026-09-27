/**
 * Homepage imagery — local assets under /public/images (Unsplash License originals).
 * Local files avoid remote optimizer/network failures that show alt text as a broken image.
 */
export const images = {
  hero: {
    src: "/images/hero.jpg",
    alt: "Modern residential property exterior",
  },
  living: {
    src: "/images/living.jpg",
    alt: "Bright furnished apartment living room",
  },
  operations: {
    src: "/images/operations.jpg",
    alt: "Technician performing residential maintenance work",
  },
  skyline: {
    src: "/images/skyline.jpg",
    alt: "City residential skyline at dusk",
  },
} as const;
