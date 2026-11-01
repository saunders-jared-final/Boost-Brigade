#!/usr/bin/env python3
"""STEP assembly -> glTF (.glb) with ONE NAMED NODE PER SOLID, for the showcase exploded view.

    python3 step_to_glb.py shuffler_assembly.step enclosure.raw.glb [--tol 0.1] [--ang 0.2]

Names come from the STEP product structure (XCAF) when it can be read; otherwise solid_NN.
Requires cadquery (pip install --user cadquery).  Output is raw/uncompressed: run
glb_pipeline.mjs on it afterwards (prep_models.sh does this).
"""
import argparse
import re
import sys
import time
from collections import Counter

import cadquery as cq


def _xcaf_parts(path):
    """Yield (name, TopoDS_Shape located in world coords) for every leaf part of the STEP."""
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDF import TDF_Label, TDF_LabelSequence
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    doc = TDocStd_Document(TCollection_ExtendedString("step"))
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    if reader.ReadFile(path) != IFSelect_RetDone:
        raise RuntimeError("STEPCAFControl_Reader.ReadFile failed")
    reader.Transfer(doc)
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())

    def label_name(label):
        n = TDataStd_Name()
        if label.FindAttribute(TDataStd_Name.GetID_s(), n):
            return n.Get().ToExtString()
        return ""

    def walk(label, loc, path_names):
        # a component label refers to a prototype label; follow the reference
        if st.IsReference_s(label):
            ref = TDF_Label()
            st.GetReferredShape_s(label, ref)
            loc = loc.Multiplied(st.GetLocation_s(label))
            name = label_name(label) or label_name(ref)
            yield from walk(ref, loc, path_names + [name])
            return
        name = label_name(label)
        if st.IsAssembly_s(label):
            comps = TDF_LabelSequence()
            st.GetComponents_s(label, comps)
            for i in range(1, comps.Length() + 1):
                yield from walk(comps.Value(i), loc, path_names + [name])
        else:
            shape = st.GetShape_s(label)
            yield (name or (path_names[-1] if path_names else "")), shape.Moved(loc)

    free = TDF_LabelSequence()
    st.GetFreeShapes(free)
    for i in range(1, free.Length() + 1):
        yield from walk(free.Value(i), TopLoc_Location(), [])


def clean(name):
    name = re.sub(r"\s+", "_", name.strip())
    name = re.sub(r"[^A-Za-z0-9_.\-:()]+", "", name)
    name = re.sub(r"(:\d+)+$", "", name)           # Fusion appends ":1", ":2" instance suffixes
    name = re.sub(r"_v\d+$", "", name)              # ... and "v12" version suffixes
    return name or "part"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step")
    ap.add_argument("out")
    ap.add_argument("--tol", type=float, default=0.1, help="linear tessellation tolerance (mm)")
    ap.add_argument("--ang", type=float, default=0.2, help="angular tessellation tolerance (rad)")
    ap.add_argument("--no-xcaf", action="store_true", help="skip XCAF names, use solid_NN")
    a = ap.parse_args()

    t0 = time.time()
    parts = []  # (name, cq.Shape)
    if not a.no_xcaf:
        try:
            for name, shape in _xcaf_parts(a.step):
                wrapped = cq.Shape.cast(shape)
                solids = wrapped.Solids() if wrapped.ShapeType() != "Solid" else [wrapped]
                if not solids:
                    continue
                if len(solids) == 1:
                    parts.append((clean(name), solids[0]))
                else:
                    for k, s in enumerate(solids, 1):
                        parts.append((f"{clean(name)}_{k:02d}", s))
            print(f"XCAF: {len(parts)} solids with product names ({time.time() - t0:.0f} s)")
        except Exception as e:  # noqa: BLE001
            print(f"XCAF name extraction failed ({e!r}); falling back to importStep", file=sys.stderr)
            parts = []
    if not parts:
        wp = cq.importers.importStep(a.step)
        for k, s in enumerate(wp.solids().vals(), 1):
            parts.append((f"solid_{k:02d}", s))
        print(f"importStep: {len(parts)} solids ({time.time() - t0:.0f} s)")

    # make names unique (node names are the site's handle on each part)
    seen = Counter()
    assy = cq.Assembly(name="enclosure")
    for name, solid in parts:
        seen[name] += 1
        uname = name if seen[name] == 1 else f"{name}_{seen[name]:02d}"
        col = None
        assy.add(solid, name=uname, color=col)
    print("parts:", ", ".join(n for n, _ in parts[:60]) + (" ..." if len(parts) > 60 else ""))

    assy.save(a.out, exportType="GLTF", tolerance=a.tol, angularTolerance=a.ang)
    print(f"wrote {a.out} ({time.time() - t0:.0f} s)")


if __name__ == "__main__":
    main()
