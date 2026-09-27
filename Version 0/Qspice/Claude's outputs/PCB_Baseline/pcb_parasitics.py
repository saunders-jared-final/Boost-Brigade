"""
pcb_parasitics.py - ballpark copper parasitics from the KiCad board file.

Reads "../../Version 0 project/Version 0 project.kicad_pcb" (read only), sums the copper of
each power/gate net (track segments, vias, filled zones) and writes parasitics.json with
per-net estimates plus the lumped R/L values used by gen_shuffler.py.

Method (deliberately simple, ballpark only):
  * Track resistance:  R = Rsheet * sum(length / width),   Rsheet = rho_Cu / t = 0.491 mOhm/sq (35 um)
  * Track inductance:  partial self inductance of a flat conductor in free space
        L[nH] = 0.2 * l * ( ln(2l/(w+t)) + 0.5 + 0.2235 (w+t)/l ),   l, w, t in mm
    scaled by kL (default 0.5) to account for return-current proximity on this 6-layer board.
  * Zones (copper pours): treated as one strip per filled polygon, long side = bounding-box
    long side, effective width = area / long side.
  * Vias: 0.5 mOhm + 0.5 nH each, assumed in parallel pairs per net.
  * Component parasitics (ESR/ESL/package) are fixed ballpark numbers listed in "components".
Edit parasitics.json by hand if you have better numbers; gen_shuffler.py only reads it.
"""

import json
import math
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "..", "..", "Version 0 project", "Version 0 project.kicad_pcb")
OUT = os.path.join(HERE, "parasitics.json")

COPPER_T_MM = 0.035
RHO_CU = 1.72e-8                      # Ohm.m
RSHEET_MOHM = RHO_CU / (COPPER_T_MM * 1e-3) * 1e3   # 0.491 mOhm per square
KL = 0.5                              # free-space partial inductance -> over-plane estimate
VIA_R_MOHM, VIA_L_NH = 0.5, 0.5

# lumps used by the model: name -> (kicad net, share of that net's copper attributed to this lump)
LUMPS = {
    "T1": ("PV1+", 1.0), "M1": ("PV2+", 0.5), "B1": ("PV3+", 0.5),
    "T2": ("PV2+", 0.5), "M2": ("PV3+", 0.5), "B2": ("GND", 0.5),
    "SWA1": ("/Shuffle Converter 1/M_T_Aph_S", 1.0), "SWB1": ("/Shuffle Converter 1/M_T_Bph_S", 1.0),
    "SWA2": ("/Shuffle Converter 2/M_T_Aph_S", 1.0), "SWB2": ("/Shuffle Converter 2/M_T_Bph_S", 1.0),
    "LA1": ("/Shuffle Converter 1/L_Aph2", 1.0), "LB1": ("/Shuffle Converter 1/L_Bph2", 1.0),
    "LA2": ("/Shuffle Converter 2/L_Aph2", 1.0), "LB2": ("/Shuffle Converter 2/L_Bph2", 1.0),
    "gTA1": ("/Shuffle Converter 1/M_T_Aph_G", 1.0), "gBA1": ("/Shuffle Converter 1/M_B_Aph_G", 1.0),
    "gTB1": ("/Shuffle Converter 1/M_T_Bph_G", 1.0), "gBB1": ("/Shuffle Converter 1/M_B_Bph_G", 1.0),
    "gTA2": ("/Shuffle Converter 2/M_T_Aph_G", 1.0), "gBA2": ("/Shuffle Converter 2/M_B_Aph_G", 1.0),
    "gTB2": ("/Shuffle Converter 2/M_T_Bph_G", 1.0), "gBB2": ("/Shuffle Converter 2/M_B_Bph_G", 1.0),
}

COMPONENTS = {
    "C130_ESR_mOhm": 28.0,   # TDK B40910A0137M000 130 uF hybrid polymer (value used in the earlier v3 sim)
    "C130_ESL_nH": 15.0,     # radial 10x16.5 mm can, ballpark
    "C100n_ESR_mOhm": 20.0,  # 0805 X7R
    "C100n_ESL_nH": 0.8,
    "C10u_ESR_mOhm": 5.0,    # 1210 X7R
    "C10u_ESL_nH": 1.0,
    "TO252_Ld_nH": 1.5,      # DPAK drain tab
    "TO252_Ls_nH": 3.0,      # DPAK source lead (common-source inductance)
    "TMCS_R_mOhm": 0.7,      # TMCS1126 conductor path, typ (check datasheet)
    "TMCS_L_nH": 0.5,
    "XT60_R_mOhm": 0.5,      # per contact pair
    "cable_R_mOhm_per_m": 4.3,   # 4 mm^2 copper
    "cable_L_nH_per_m": 500.0,   # per lead (~1 uH/m loop)
    "cable_len_m": 1.5,          # one lead, module to board
    "Cpv_nF": 10.0,              # PV module terminal capacitance, ballpark
}


def strip_L_nH(l_mm, w_mm, t_mm=COPPER_T_MM):
    """Partial self inductance of a flat rectangular conductor (Grover/Ruehli), nH."""
    if l_mm <= 0 or w_mm <= 0:
        return 0.0
    x = 2 * l_mm / (w_mm + t_mm)
    ln = math.log(x) if x > 1 else 0.0
    return 0.2 * l_mm * (ln + 0.5 + 0.2235 * (w_mm + t_mm) / l_mm)


def polygon_area_bbox(pts):
    a = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        a += x1 * y2 - x2 * y1
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return abs(a) / 2, (max(xs) - min(xs)), (max(ys) - min(ys))


def parse(pcb_text):
    nets = {}
    seg_re = re.compile(r'\(segment\s*\(start ([-\d.]+) ([-\d.]+)\)\s*\(end ([-\d.]+) ([-\d.]+)\)\s*'
                        r'\(width ([-\d.]+)\)\s*\(layer "([^"]+)"\)\s*\(net "([^"]*)"\)', re.S)
    for m in seg_re.finditer(pcb_text):
        x1, y1, x2, y2, w, layer, net = m.groups()
        length = math.hypot(float(x2) - float(x1), float(y2) - float(y1))
        d = nets.setdefault(net, {"segments": 0, "len_mm": 0.0, "R_trace_mOhm": 0.0, "L_trace_nH": 0.0,
                                  "layers": {}, "vias": 0, "zones": []})
        w = float(w)
        d["segments"] += 1
        d["len_mm"] += length
        d["R_trace_mOhm"] += RSHEET_MOHM * length / w
        d["L_trace_nH"] += strip_L_nH(length, w)
        d["layers"][layer] = d["layers"].get(layer, 0) + 1
    via_re = re.compile(r'\(via\s.*?\(net "([^"]*)"\)', re.S)
    for m in via_re.finditer(pcb_text):
        d = nets.setdefault(m.group(1), {"segments": 0, "len_mm": 0.0, "R_trace_mOhm": 0.0, "L_trace_nH": 0.0,
                                         "layers": {}, "vias": 0, "zones": []})
        d["vias"] += 1
    # top-level zones: "\n\t(zone" ... "\n\t)"
    for zm in re.finditer(r'\n\t\(zone\n(.*?)\n\t\)\n', pcb_text, re.S):
        body = zm.group(1)
        nm = re.search(r'\(net_name "([^"]*)"\)', body) or re.search(r'\(net "([^"]*)"\)', body)
        if not nm:
            continue
        net = nm.group(1)
        layer = re.search(r'\(layers? ("[^)]*")\)', body)
        layer = layer.group(1).replace('"', '') if layer else "?"
        d = nets.setdefault(net, {"segments": 0, "len_mm": 0.0, "R_trace_mOhm": 0.0, "L_trace_nH": 0.0,
                                  "layers": {}, "vias": 0, "zones": []})
        for fp in re.finditer(r'\(filled_polygon\s*\(layer "([^"]+)"\)\s*\(pts(.*?)\n\t\t\t\)', body, re.S):
            flayer, ptxt = fp.groups()
            pts = [(float(a), float(b)) for a, b in re.findall(r'\(xy ([-\d.]+) ([-\d.]+)\)', ptxt)]
            if len(pts) < 3:
                continue
            area, bw, bh = polygon_area_bbox(pts)
            if area < 1.0:
                continue
            long_side = max(bw, bh)
            w_eff = area / long_side
            d["zones"].append({"layer": flayer, "area_mm2": round(area, 1), "bbox_mm": [round(bw, 1), round(bh, 1)],
                               "R_mOhm": round(RSHEET_MOHM * long_side / w_eff, 3),
                               "L_nH": round(strip_L_nH(long_side, w_eff), 2)})
    for net, d in nets.items():
        # pours on a net act (roughly) in parallel: combine zone strips in parallel
        if d["zones"]:
            d["R_zone_mOhm"] = 1.0 / sum(1.0 / max(z["R_mOhm"], 1e-6) for z in d["zones"])
            d["L_zone_nH"] = 1.0 / sum(1.0 / max(z["L_nH"], 1e-6) for z in d["zones"])
        else:
            d["R_zone_mOhm"] = d["L_zone_nH"] = 0.0
        n_via_pairs = max(1, d["vias"] // 2) if d["vias"] else 0
        d["R_via_mOhm"] = VIA_R_MOHM / n_via_pairs if n_via_pairs else 0.0
        d["L_via_nH"] = VIA_L_NH / n_via_pairs if n_via_pairs else 0.0
        if d["zones"]:
            # the power path is the pour; the thin track branches feed sensing/drivers only
            d["path"] = "zone"
            d["R_est_mOhm"] = round(d["R_zone_mOhm"] + d["R_via_mOhm"], 3)
            d["L_est_nH"] = round(KL * d["L_zone_nH"] + d["L_via_nH"], 2)
        else:
            d["path"] = "tracks (series sum, pessimistic)"
            d["R_est_mOhm"] = round(d["R_trace_mOhm"] + d["R_via_mOhm"], 3)
            d["L_est_nH"] = round(KL * d["L_trace_nH"] + d["L_via_nH"], 2)
        for k in ("len_mm", "R_trace_mOhm", "L_trace_nH", "R_zone_mOhm", "L_zone_nH"):
            d[k] = round(d[k], 3)
    return nets


def main():
    text = open(PCB, encoding="utf-8").read().replace(chr(13) + chr(10), chr(10))
    nets = parse(text)
    lumps = {}
    for name, (net, share) in LUMPS.items():
        d = nets.get(net)
        if d is None:
            lumps[name] = {"from": net, "R_mOhm": 1.0, "L_nH": 2.0, "note": "net not found on PCB, default used"}
            continue
        lumps[name] = {"from": net, "share": share,
                       "R_mOhm": round(d["R_est_mOhm"] * share, 3),
                       "L_nH": round(d["L_est_nH"] * share, 2)}
    wanted = {v[0] for v in LUMPS.values()}
    report_nets = {n: nets[n] for n in nets if n in wanted}
    out = {"source": os.path.relpath(PCB, HERE), "copper_um": COPPER_T_MM * 1000,
           "sheet_mOhm_per_sq": round(RSHEET_MOHM, 4), "kL": KL,
           "components": COMPONENTS, "lumps": lumps, "nets": report_nets}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(f"wrote {OUT}")
    print(f"{'lump':6s} {'from net':40s} {'R mOhm':>8s} {'L nH':>7s}")
    for name, l in lumps.items():
        print(f"{name:6s} {l['from']:40s} {l['R_mOhm']:8.3f} {l['L_nH']:7.2f}")
    print("\nnet detail:")
    for n, d in report_nets.items():
        print(f"  {n:40s} segs={d['segments']:3d} len={d['len_mm']:7.1f}mm vias={d['vias']:3d} zones={len(d['zones'])} "
              f"Rtr={d['R_trace_mOhm']:.3f} Rz={d['R_zone_mOhm']:.3f} Ltr={d['L_trace_nH']:.2f} Lz={d['L_zone_nH']:.2f} -> R={d['R_est_mOhm']} L={d['L_est_nH']}")


if __name__ == "__main__":
    main()
