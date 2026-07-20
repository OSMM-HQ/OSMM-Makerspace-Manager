# Space Works Brand

The **Space Works — Open Source Makerspace Manager** visual identity. This folder is the single source of
truth for the logo, colour, and type. The live app consumes the same values via
`frontend/src/components/SpaceWorksLogo.tsx`, `frontend/public/spaceworks-logo.svg` (favicon), and the Tailwind
theme tokens.

## Concept — the "Parts-Crate"

The logomark is a **parts bin**: an open crate whose **four compartments** are the colour system and,
in the lettered variant, spell **O-S-M-M** in pixel type. It says "a place for every part" — the
whole point of the product.

- **Plain crate** — pair with the "Space Works" wordmark in horizontal/stacked lockups (headers, banners).
- **Lettered crate** — stands alone where there's no wordmark: favicons, app icons, avatars.

## Assets in this folder

| File | Use |
|---|---|
| `logomark.svg` | Plain crate, ink stroke — for light surfaces / documents |
| `logomark-lettered.svg` | Crate with O-S-M-M pixels — standalone mark |
| `app-icon.svg` | Dark rounded tile + lettered mark — app/store icon |

The banner lockup lives at `../banner.svg`; the browser favicon at `../../frontend/public/spaceworks-logo.svg`.

## Colour

The four bin colours are the heart of the palette. Each pastel **fill** has a dark **ink** companion
for legible text/letters on top of it.

| Role | Fill | Ink (text on fill) |
|---|---|---|
| Blue | `#7dd3fc` | `#00374a` |
| Yellow | `#fcdf46` | `#3d3400` |
| Mint | `#74dd9c` | `#00321b` |
| Pink | `#f9a8d4` | `#5a1633` |

Neutrals:

| Role | Hex |
|---|---|
| Ink (near-black bg) | `#0c0d10` |
| Charcoal (mark on light) | `#16181d` |
| Cream (light page) | `#faf9f4` |
| Surface (light panel) | `#efeee9` |

## Type

- **Clash Display** (700) — the "Space Works" wordmark, letter-spacing ≈ 0.04em.
- **Space Grotesk** — supporting UI / marketing text.
- **Press Start 2P** — the O-S-M-M pixels inside the bins (lettered mark only).

## Usage

**Do**
- Keep the four bin colours in **O-S-M-M order** (blue, yellow, mint, pink).
- Use the **white** mark on dark, the **charcoal** mark on light.
- Give it room — at least **one bin-height** of clear space on all sides.

**Don't**
- Recolour the crate outline or stretch the mark.
- Add shadows, gradients, or outlines to the bins.
- Place the dark mark on a busy or low-contrast field.
