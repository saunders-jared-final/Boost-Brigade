/** Build-time lookups for prepared images (see scripts/prep_*.py). */
import type { ImageMetadata } from 'astro';

const photoMods = import.meta.glob<{ default: ImageMetadata }>('../assets/photos/*.webp', { eager: true });
const figureMods = import.meta.glob<{ default: ImageMetadata }>('../assets/figures/**/*.{webp,png,jpg}', { eager: true });
const notebookMods = import.meta.glob<{ default: ImageMetadata }>('../assets/notebooks/**/*.webp', { eager: true });
const svgMods = import.meta.glob<string>('../assets/figures/**/*.svg', { eager: true, query: '?url', import: 'default' });

function stem(p: string) { return p.split('/').pop()!.replace(/\.[a-z0-9]+$/i, ''); }

export const PHOTOS: Record<string, ImageMetadata> = {};
export const THUMBS: Record<string, ImageMetadata> = {};
for (const [p, m] of Object.entries(photoMods)) {
  const s = stem(p);
  if (s.endsWith('.thumb')) THUMBS[s.replace(/\.thumb$/, '')] = m.default; else PHOTOS[s] = m.default;
}

/** figures['results/solar_S02'] */
export const FIGURES: Record<string, ImageMetadata> = {};
for (const [p, m] of Object.entries(figureMods)) {
  const rel = p.replace(/^.*\/assets\/figures\//, '').replace(/\.[a-z0-9]+$/i, '');
  FIGURES[rel] = m.default;
}
/** SVG figure URLs keyed like FIGURES */
export const SVGS: Record<string, string> = {};
for (const [p, url] of Object.entries(svgMods)) {
  const rel = p.replace(/^.*\/assets\/figures\//, '').replace(/\.svg$/i, '');
  SVGS[rel] = url;
}
export const NOTEBOOK_IMGS: Record<string, ImageMetadata> = {};
for (const [p, m] of Object.entries(notebookMods)) {
  const rel = p.replace(/^.*\/assets\/notebooks\//, '').replace(/\.[a-z0-9]+$/i, '');
  NOTEBOOK_IMGS[rel] = m.default;
}

export function photo(stemName: string): ImageMetadata | undefined { return PHOTOS[stemName]; }
export function fig(key: string): ImageMetadata | undefined { return FIGURES[key]; }
export function figsIn(group: string): { key: string; img: ImageMetadata }[] {
  return Object.entries(FIGURES).filter(([k]) => k.startsWith(group + '/')).sort(([a], [b]) => a.localeCompare(b)).map(([key, img]) => ({ key, img }));
}
export function svgsIn(group: string): { key: string; url: string }[] {
  return Object.entries(SVGS).filter(([k]) => k.startsWith(group + '/')).sort(([a], [b]) => a.localeCompare(b)).map(([key, url]) => ({ key, url }));
}
