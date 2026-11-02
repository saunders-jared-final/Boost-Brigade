# site/ — Boost Brigade knowledge hub

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
`6_RTOS/ctrl_core`, the gain-set JSON files, `REPORT.md` findings and caveats.
If one of those files moves, the build fails on purpose so the handover cannot silently drift.

## Pages

| Route | What it holds |
|---|---|
| `/` | Hero, plain-language claims, intro video slot, the story in five beats (shading explainer, one shuffler, annotated board, control diagram, carpark result), where-to-next, team strip |
| `/story/` | Three Gantt views (proposal plan, control actual, hardware actual, both combined), the two-stream V-model, the converging two-rail timeline, lessons |
| `/hardware/` | Landing for the two hardware pages |
| `/hardware/pcb/` | 3D board (exploded, part cards with datasheets), requirements, QSPICE design models, schematic viewer (all sheets, callouts, refdes search), layer viewer, sensors, BOM, manufacturing, bench and solar set-ups, limitations |
| `/hardware/enclosure/` | Exploded Fusion assembly with numbered parts, enclosure BOM, dimensions, print notes, build photos |
| `/control/` | Animated switching states and currents, plant/modes/gains with a symbol table, R_sw, controller, supervisor, gain pipeline, sampling, peripherals (PWM/ADC/SPI/UART), C core, state machine, Raspberry Pi roles and flashing, remote controls |
| `/simulation/` | Rungs, notebook carousels, Simulink MIL/SIL, QSPICE integrated model and build book |
| `/results/` | Carpark and bench results, 21-window inventory, cross-phase comparison, findings and caveats from REPORT.md |
| `/handover/` | Quick starts, known issues per stream, future work per stream, repository map |
| `/media/`, `/about/` | Photos/videos/slides; team, acknowledgements, downloads |

## Asset pipeline (run locally, outputs are committed)

CI cannot regenerate these (PNG twins are gitignored in `8_Results`, KiCad/Fusion are Windows-only), so
run the scripts and commit what they write under `src/assets/`, `src/data/` and `public/`.

| Script | Writes | Needs |
|---|---|---|
| `scripts/prep_all.sh` | photos, figures, notebooks, embeds, Grafana JSON | python3 + Pillow, pdftocairo |
| `scripts/prep_photos.py` | `src/assets/photos/*.webp` (+ thumbs), `src/data/photos.json` | |
| `scripts/prep_figures.py` | `src/assets/figures/<group>/…` from the curated `FIGURES` dict | |
| `scripts/prep_notebooks.py` | `src/assets/notebooks/<nb>/NN.webp`, `src/data/notebooks.json` | nbformat |
| `scripts/prep_reports.py` | `src/assets/figures/hw/*` (hardware report figures), `figures/ctrl/*` (delivery report figures), `src/assets/datasheets/*` (first pages), `figures/misc/hero_render.webp` | `pip install --user pymupdf` |
| `scripts/prep_tikz.sh` | `src/assets/diagrams/*.svg` from the LaTeX TikZ sources | TeX Live, dvisvgm |
| `scripts/prep_kicad.sh` | `public/kicad/sch/*.svg` (every schematic sheet), `public/kicad/pcb/*.svg` (every layer, recoloured to `currentColor`), then `kicad_index.py` → `src/data/kicad_index.json` (refdes → sheet + position, board position) | KiCad 10 (Windows) |
| `scripts/prep_models.sh` | `public/models/board.glb` via `kicad-cli pcb export glb`; `enclosure.glb` from the STEP via cadquery → `glb_group.mjs` (named assemblies + colours) → `glb_pipeline.mjs` | KiCad 10, `pip install --user cadquery` |

See `scripts/README_models.md` for the manual Fusion 360 fallback if cadquery is not installed.

## Where content lives

- `src/data/claims.ts` the plain-language headline statements on the home page
- `src/data/timeline.ts` the two-stream story entries and the lessons
- `src/data/gantt.ts` planned (proposal) and actual schedules for both streams
- `src/data/parts.ts` 3D hotspot/part definitions for the board and the enclosure groups
- `src/data/bom.ts` board BOM (hardware report appendix 4) and enclosure BOM
- `src/data/schematic.ts` schematic sheets and their callouts (by refdes)
- `src/data/symbols.ts`, `peripherals.ts` the control page's symbol table and peripheral settings
- `src/data/handover.ts` known issues and future work, tagged by stream
- `src/data/testcases.ts` the 21 hardware windows; `vmodel.ts` the simulation rungs
- `src/pages/*.astro` the routes; `src/components/` the pieces (Exploded 3D, SchematicViewer, LayerViewer, ShufflerFlow, StreamTimeline, Gantt, VModel, Carousel, Annotated, Claim, PiDiagram, ShadingExplainer, Symbols, Figure with lightbox)

## Adding videos

Upload to YouTube (unlisted) and pass the id to `<YouTube id="…" title="…" />` in `src/pages/index.astro`
and `src/pages/media.astro`. Without an id the component plays the `mp4` prop (a direct link, e.g. the
bench clips streamed from the repository) or renders a "coming soon" card.

## Replacing the team photo

Drop the picture into `src/assets/photos/`, run `scripts/prep_photos.py` (or just reference it directly), and
change the name in `src/pages/about.astro` and the team strip at the bottom of `src/pages/index.astro`.

## Guard rails

`scripts/check_secrets.sh` fails the build if any lab credential or the old absolute KiCad model path appears
under `src/` or `public/`. Keep it that way: never copy `7_Pi/docker-compose.yml` or `pod.py` into the site.
