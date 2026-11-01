# site/ — Boost Brigade showcase and handover website

Astro 7 static site deployed to GitHub Pages at <https://saunders-jared-final.github.io/Boost-Brigade/>
by `.github/workflows/pages.yml` (runs on every push to `main` that touches `site/`).

## Develop

```sh
cd site
npm install            # Node >= 22.23.4 (nvm: `nvm install 22`)
npm run dev            # http://localhost:4321/Boost-Brigade/
npm run build          # runs scripts/check_secrets.sh first, then astro build -> dist/
npm run preview
```

Pages read files from the parent repository at build time (`src/lib/repo.ts`): code snippets from
`6_RTOS/ctrl_core`, the gain-set JSON files, `REPORT.md` findings and caveats, the bench-day log.
If one of those files moves, the build fails on purpose so the handover cannot silently drift.

## Asset pipeline (run locally, outputs are committed)

CI cannot regenerate these (PNG twins are gitignored in `8_Results`, KiCad/Fusion are Windows-only), so
run the scripts and commit what they write under `src/assets/`, `src/data/` and `public/`.

| Script | Writes | Needs |
|---|---|---|
| `scripts/prep_all.sh` | photos, figures, notebooks, embeds, Grafana JSON | python3 + Pillow, pdftocairo |
| `scripts/prep_photos.py` | `src/assets/photos/*.webp` (+ thumbs), `src/data/photos.json` (captions from the report's photo appendix) | |
| `scripts/prep_figures.py` | `src/assets/figures/<group>/…` from the curated `FIGURES` dict at the top of the file | |
| `scripts/prep_notebooks.py` | `src/assets/notebooks/<nb>/NN.webp`, `src/data/notebooks.json` | nbformat |
| `scripts/prep_tikz.sh` | `src/assets/diagrams/*.svg` (real text, theme-friendly) from the LaTeX TikZ sources | TeX Live, dvisvgm |
| `scripts/prep_models.sh` | `public/models/board.glb` via `kicad-cli.exe pcb export glb`; `enclosure.glb` from a Fusion mesh export | KiCad 10 (Windows), npx gltf-transform |

See `scripts/README_models.md` for the manual Fusion 360 step that produces the enclosure mesh.

## Where content lives

- `src/data/stats.ts` headline numbers (each with its REPORT.md reference)
- `src/data/timeline.ts` design-evolution entries and the six lessons
- `src/data/gotchas.ts` handover gotcha cards (tagged)
- `src/data/future.ts` backlog board
- `src/data/testcases.ts` the 21 hardware windows
- `src/data/vmodel.ts` simulation-ladder rungs
- `src/data/parts.ts` 3D hotspot/part definitions (node names from `gltf-transform inspect`)
- `src/pages/*.astro` the nine routes; `src/components/` reusable pieces (Snippet, Diagram, Math, Compare, YouTube, Gallery, ModelView, Exploded)

## Adding videos

Upload to YouTube (unlisted) and pass the id to `<YouTube id="…" title="…" />` in `src/pages/index.astro`
and `src/pages/media.astro`. Without an id the component renders a "coming soon" card.

## Guard rails

`scripts/check_secrets.sh` fails the build if any lab credential or the old absolute KiCad model path appears
under `src/` or `public/`. Keep it that way: never copy `7_Pi/docker-compose.yml` or `pod.py` into the site.
