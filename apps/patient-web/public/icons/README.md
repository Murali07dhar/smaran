# Icons — TODO before shipping

`icon.svg` is the source mark. The PWA manifest (see `vite.config.ts`)
references three raster PNGs that still need generating from it:

- `icon-192.png` (192x192)
- `icon-512.png` (512x512)
- `icon-512-maskable.png` (512x512, safe-zone padded for maskable icons)

Generate with any SVG rasterizer, e.g.:

```sh
npx sharp-cli -i icon.svg -o icon-192.png resize 192 192
npx sharp-cli -i icon.svg -o icon-512.png resize 512 512
```

This was not done in-session because the build container has no image
rasterizer and no network access to fetch one. Listed as a known gap in
HANDOFF.md.
