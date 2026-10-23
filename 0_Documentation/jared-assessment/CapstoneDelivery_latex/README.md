# EGH490-2 Project Delivery Report — LaTeX project

Overleaf-ready source for *Controlling Differential Power Processors in Solar Powered
Applications* (Jared Saunders, n11034459). Compiler: **pdfLaTeX** + **BibTeX**, main file
`main.tex`. Zip this folder and upload it to Overleaf (New Project → Upload Project).

## Layout

| Path | What |
|---|---|
| `main.tex` | document skeleton, section order, bibliography |
| `preamble.tex` | packages, 12 pt Times, 20 mm margins, colours, the `talking` / `\note` / `\ev` helpers |
| `titlepage.tex` | title page in the QUT template layout |
| `sections/01…07` | Executive summary, Abstract, Introduction, Literature review, Methodology, Results, Conclusion |
| `appendices/A…M` | Timeline, Risk register, Analytical derivation, Pseudocode, Firmware/peripherals/protocol, Gain sets, Simulink validate figures, Analytical/QSPICE/Simulink runs, Bench raw data, Solar raw data, Synthesis tables + overlays, Thermal/scope, Photos |
| `tables/*.tex` | **generated** from `8_Results/analysis/out/tables/*.csv` by `tools/make_tables.py` (do not edit by hand) |
| `figures/tikz/*.tex` | diagrams drawn in TikZ/circuitikz (pipeline V-model, shuffler circuit, N-string ladder, control loop, state machine, system architecture, gain pipeline, test set-ups, ADC timing, timeline) |
| `figures/pipeline/` | PDFs from `8_Results/analysis/out/figures/` (hardware overviews, event zooms, analytical, QSPICE, carpark, validate suites, compare, energy). File names had their dots replaced by `p` (`k0.3` → `k0p3`) so graphicx does not read them as extensions |
| `figures/sim/` | MATLAB validate-suite PDFs from `4_Simulink/*/figs` |
| `figures/slides/` | images extracted from the presentation PDF (`img-<page>-<n>.png`, page 1 render) |
| `figures/photos/` | downscaled photos from `0_Documentation/Photos` |
| `figures/misc/` | thermal plots, scope captures, V-model picture |
| `refs.bib` | your Zotero export (`MPPT Solar.bib`, file/abstract/keyword fields stripped) plus datasheet entries |

## Authoring conventions

* **Purple `▷` bullets** (`\begin{talking} … \end{talking}`) are talking points to turn into prose.
  `\tpoff` in `main.tex` prints them in black; `\tphide` drops them from the PDF.
* **Orange `[note]`** (`\note{…}`) marks something to confirm or a decision for you.
* **Green numbers** (`\ev{…}`) are values taken from the results pipeline tables; the table they come from
  is referenced next to them.
* Figures from the presentation keep their slide image; the raw-data slides are replaced by the regenerated
  overview figures (RUN rows only, no stale values).

## Regenerating the evidence tables

```
cd 8_Results/analysis && make all          # rebuilds out/tables/*.csv from 8_Results/TestCases
cd 0_Documentation/jared-assessment/CapstoneDelivery_latex && python3 tools/make_tables.py
```

## Page budget

The rubric allows 20 pages for the main body. The body is written compactly but with every figure it will
exceed that; move figures to the appendices (they are all cross-referenced) or drop the subfigure panels
first. The appendices have no limit.

## Local build (optional)

```
pdflatex main && bibtex main && pdflatex main && pdflatex main
```
`IEEEtran.bst` is used if present, otherwise `ieeetr`. The local TeX Live used for checking lacked
`siunitx`, `biblatex` and `algorithm2e`, so none of those are used.
