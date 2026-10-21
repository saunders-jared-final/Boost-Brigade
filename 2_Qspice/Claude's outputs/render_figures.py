#!/usr/bin/env python3
"""
render_figures.py - figures of the Power_Shuffler_Integrated sheets for reports and slides.

    python render_figures.py            -> figures/<sheet>.svg + .png      (every sheet, complete)
                                           figures/slides/*.png            (slide-ready crops, see SLIDES)

The slide figures crop each sheet to what reads at slide size: the system diagram of the top sheet without its
text columns, the text columns on their own, the two shufflers, the controller and its halves, the modulator.
They use a darker ink than the build-book renderer and are rasterised at 2x so wires and glyphs stay crisp.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "PCB_Baseline"))
from build_power_shuffler_integrated import TOP, QDIR          # noqa: E402
import qsch_render                                              # noqa: E402

FIG = os.path.join(HERE, "figures")
SLIDE_COLOURS = {"acc": "#b5652a", "ink": "#1d2622", "muted": "#4f5e57", "wire": "#1d2622", "label": "#0b5d3b",
                 "fill_acc": "#f3e3d6", "fill": "#e9eeec", "directive": "#1b2d55"}
# name -> (sheet, crop (x0, y0, x1, y1) or None for the whole sheet, scale)
SLIDES = {
    "Top_System":       (TOP, (-12600, -7300, 13400, 7500), 0.09),
    "Top_String":       (TOP, (-12600, -7300, 1500, 7500), 0.12),
    "Top_Blocks":       (TOP, (1500, -7300, 13400, 4500), 0.12),
    "Top_Directives":   (TOP, (-12600, -11300, 16500, -7400), 0.12),
    "Top_Notes":        (TOP, (-12600, 7300, 10000, 10100), 0.12),
    "Shuffler_1":       ("Shuffler_1", None, 0.1),
    "Shuffler_2":       ("Shuffler_2", None, 0.1),
    "Controller":       ("Controller", None, 0.09),
    "Controller_Left":  ("Controller", (-600, -2700, 9800, 7000), 0.12),
    "Controller_Right": ("Controller", (9200, -2700, 24000, 7000), 0.12),
    "PWM_Modulator":    ("PWM_Modulator", None, 0.14),
}


def extent(path):
    """Bounding box of everything on the sheet, including the run of the sheet texts."""
    comps, wires, nets, juncs, texts = qsch_render.parse_schematic(path, want_texts=True)
    xs = [c["x"] for c in comps] + [w[0][0] for w in wires] + [w[0][2] for w in wires] + [n["x"] for n in nets]
    ys = [c["y"] for c in comps] + [w[0][1] for w in wires] + [w[0][3] for w in wires] + [n["y"] for n in nets]
    for t in texts:
        xs += [t["x"], t["x"] + int(len(t["s"]) * 85 * (t["size"] or 1.0) * 0.55)]
        ys.append(t["y"])
    return min(xs) - 700, min(ys) - 700, max(xs) + 700, max(ys) + 700


def png(svg, out, density):
    subprocess.run(["convert", "-density", str(density), "-background", "white", "-flatten", svg, out], check=False)


def render_sheets(density=96):
    os.makedirs(FIG, exist_ok=True)
    out = []
    for name, scale in ((TOP, 0.07), ("Shuffler_1", 0.1), ("Shuffler_2", 0.1), ("Controller", 0.09), ("PWM_Modulator", 0.14)):
        path = os.path.join(QDIR, name + ".qsch")
        svg = os.path.join(FIG, name + ".svg")
        open(svg, "w", encoding="utf-8").write(qsch_render.render(path, extent(path), scale))
        png(svg, os.path.join(FIG, name + ".png"), density)
        out += [name + ".svg", name + ".png"]
    return out


def render_slides(density=192):
    d = os.path.join(FIG, "slides")
    os.makedirs(d, exist_ok=True)
    out = []
    for name, (sheet, crop, scale) in SLIDES.items():
        path = os.path.join(QDIR, sheet + ".qsch")
        crop = crop or extent(path)
        svg = os.path.join(d, name + ".svg")
        open(svg, "w", encoding="utf-8").write(qsch_render.render(path, crop, scale, colours=SLIDE_COLOURS))
        png(svg, os.path.join(d, name + ".png"), density)
        os.remove(svg)
        w, h = (crop[2] - crop[0]) * scale * density / 96, (crop[3] - crop[1]) * scale * density / 96
        out.append(f"{name}.png ({w:.0f}x{h:.0f}, {(crop[2] - crop[0]) / (crop[3] - crop[1]):.2f}:1)")
    return out


if __name__ == "__main__":
    print("sheets:", ", ".join(render_sheets()))
    print("slides:", "\n        ".join(render_slides()))
