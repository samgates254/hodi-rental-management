# Open-source register

Decisions for the October 2026 frontend polish. Packages already in `frontend/package.json` stay. No new runtime dependency was added.

## Adopted

| Project | Source | Version | Licence | Use | Modifications | Attribution and redistribution | Concerns |
| --- | --- | --- | --- | --- | --- | --- | --- |
| three.js | https://github.com/mrdoob/three.js | `three@0.186.1` (lockfile), licence text at r186 | MIT. Copyright © 2010-2026 three.js authors. The notice ships in `node_modules/three/LICENSE`. | Existing illustrated homepage building, plus a small equirectangular photo viewer loaded only when a listing photo is explicitly marked `360:`. | Hodi wrote `frontend/src/components/marketplace/PanoramaViewer.tsx`. No three.js source was copied. | Keep the package licence with the dependency. Do not present the viewer as a measured model. | WebGL is optional. Ordinary photos remain the fallback. |

## Evaluated and not copied

| Project | Source | Licence found | Why it was not adopted |
| --- | --- | --- | --- |
| 3D Real-Estate Viewer | https://github.com/vtsekalo/3D-Real-Estate-Viewer | No `LICENSE` file in the repository file list (checked 16 Oct 2026). Three commits and no stated licence. | Procedural apartments, not Hodi listings. Copying would present generated rooms as property tours. Unknown licence, so no code was copied. |
| Aura Plan | https://github.com/sujalvk888/aura-plan | MIT. Copyright (c) 2026 Sujal V Kanchan. | Full Next.js, Prisma, and PostgreSQL application with its own accounts. Bringing it in would duplicate Hodi's backend. Its room builder would also imply a digital twin Hodi does not have captures for. |
| SPHR | https://github.com/lukehollis/sphr | MIT. The README asks for a citation when the project is useful. Latest activity was current in October 2026. | A complete tour host for lidar, Gaussian splats, and 360 media, with its own application shell. Too large for a listing page, and Hodi has no scan assets. The useful idea — a browser 360 photograph — was implemented directly with the three.js dependency already installed. |
| Casita | https://github.com/rohitguta2432/casita | MIT. | A furniture-placement prototype made of boxes and cylinders, with four commits. It does not display a real home. Using it on a listing would look like an accurate model. |

## Already in the product, left unchanged

Next.js 15, React 19, Tailwind CSS 4, Playwright, and Fontsource (DM Sans, Fraunces) were already installed. shadcn/ui, Radix, TanStack Table, Recharts, React Hook Form, Zod, and Storybook were not added. The current tables, forms, and charts are small enough that another component system would be a redesign rather than a fix.

## Obligations that still apply

- MIT notices for dependencies remain in `node_modules` and must stay with any redistribution of those packages.
- No GPL, AGPL, or source-available code was copied.
- Do not add a scan, splat, or glTF viewer until Hodi has a real asset, a stored URL, and a checked licence for that asset.
