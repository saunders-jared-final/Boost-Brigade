# 3D models for the showcase site

`prep_models.sh` builds everything in `site/public/models/` from the KiCad and CAD sources
without modifying them (a patched *copy* of the `.kicad_pcb` is made in `work/`).

```
site/scripts/prep_models.sh          # from anywhere in WSL
FORCE=1 site/scripts/prep_models.sh  # re-run kicad-cli even if the raw export looks current
```

| output | contents | size |
|---|---|---|
| `board.glb` | components, pads, silkscreen, soldermask; one node per refdes | ~0.8 MB |
| `board_full.glb` | as above + tracks and zones (copper node) | ~1.3 MB |
| `enclosure.glb` | mechanical assembly, one node per solid | stage 2 |

Node names in the board files: the root is `board`; children are the refdes (`C25`, `U8`,
`L1`, `L2`, `Q1`, `U14` ...) plus `copper`, `silkscreen_top`, `soldermask_top`,
`soldermask_bottom`, `board_body`. Each refdes node has exactly one mesh (identical parts
share a mesh). Units are metres, Y up (KiCad convention); the board lies in the XZ plane.
Extensions: `EXT_meshopt_compression`, `KHR_mesh_quantization` (three.js: set
`MeshoptDecoder` on the GLTFLoader).

Helper scripts: `glb_pipeline.mjs` (hierarchy-preserving optimiser, replaces
`gltf-transform optimize`, which flattens every refdes into ~10 anonymous nodes),
`glb_nodes.py` (dump node tree: `python3 glb_nodes.py file.glb 40 L1 L2`),
`step_to_glb.py` (STEP -> named-node GLB via cadquery).

## Stage 2: enclosure - if cadquery is not available

`prep_models.sh` first tries `python3 -c "import cadquery"` and converts
`9_Mechanical_Enclosure_CAD/shuffler_assembly.step` itself. If that is not installed
(`pip install --user cadquery`, ~400 MB), export a mesh from Fusion 360 by hand
(about 10 minutes):

1. Open `9_Mechanical_Enclosure_CAD/shuffler_assembly.f3z` in Fusion 360
   (File > Open > "Open from my computer").
2. In the browser, right-click the root component > **Save As Mesh**.
3. Format **OBJ**, Structure **One file per body** is *not* wanted - choose **One file**
   (we need one OBJ with named groups), Refinement **Medium**, Units **mm**,
   tick *Preserve body names* if offered.
4. Save as `site/scripts/work/enclosure.obj` (create the `work` folder if needed;
   it is gitignored). A sidecar `.mtl` is fine.
5. Back in WSL:

```bash
cd site/scripts/work
npx --yes obj2gltf -i enclosure.obj -o enclosure.raw.glb
node ../glb_pipeline.mjs enclosure.raw.glb ../../public/models/enclosure.glb --ratio 0.3
python3 ../glb_nodes.py ../../public/models/enclosure.glb 60      # check node names
```

or simply re-run `site/scripts/prep_models.sh`: stage 2 picks up `work/enclosure.obj`
automatically when cadquery is absent. Target: `enclosure.glb` < 8 MB, one node per body
(lid, base, heatsink, board, pod ...). If the OBJ groups are lost (all one node), re-export
with "One file per body" and run `obj2gltf` per file, then merge with
`npx --yes @gltf-transform/cli@4 merge a.glb b.glb ... enclosure.raw.glb`.
