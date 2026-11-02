// Group the ~1950 solids of the STEP-derived enclosure GLB into named assemblies
// (one scene child per group) so glb_pipeline.mjs collapses each group to one mesh.
//
//   node glb_group.mjs work/enclosure.raw.glb work/enclosure.grouped.glb
//
// Rules: name patterns first (enclosure bodies, heatsink, PCB, big board parts, pod parts,
// fasteners); everything else is assigned by position: in the pod bay -> Raspberry Pi,
// well above the board -> Nucleo, otherwise a small board component (dropped: the detailed
// board lives in board.glb).
import { NodeIO, getBounds } from '@gltf-transform/core';
import { prune } from '@gltf-transform/functions';

const [input, output] = process.argv.slice(2);
if (!input || !output) { console.error('usage: glb_group.mjs in.glb out.glb'); process.exit(1); }

const RULES = [
  ['Lid', /^Lid(_\d+)?$/],
  ['Side_Walls', /^Wall_[LR](_\d+)?$/],
  ['End_Panels', /^Panel_(XT60|Nucleo)(_\d+)?$/],
  ['Belly_Pan', /^Belly_Pan(_\d+)?$/],
  ['HS_Keepers', /^HS_Keepers(_\d+)?$/],
  ['UI_Pod', /^UI_Pod(_\d+)?$/],
  ['Heatsink', /^Altronics/i],
  ['PCB', /^VerBA7F_PCB/],
  ['XT60', /^XT60PW/],
  ['Inductors', /^a648ce3[789]/],
  ['Buck_modules', /^173950375/],
  ['Bulk_caps', /^CP_Elec/],
  ['Fasteners', /Screw|Washer|Pi_Spacer/i],
  ['LCD', /lcd_window|backlight|pcbboard|liquid_crystal|16pin_header|pcf8574p|trimpot|jumper|i2C_board|smt_cap|ssot3/i],
  ['IR_receiver', /^KY-022/],
  ['RGB_LED', /Led_RGB/i],
  ['Breadboard', /MiniBreadboard/],
];

const io = new NodeIO();
const doc = await io.read(input);
const root = doc.getRoot();
const scene = root.listScenes()[0];
const top = scene.listChildren()[0];
const solids = top.listChildren().length ? top.listChildren() : scene.listChildren();
console.log(`solids: ${solids.length}`);

const groups = new Map();
const group = (name) => { if (!groups.has(name)) { const g = doc.createNode(name); groups.set(name, g); } return groups.get(name); };
let dropped = 0;
const counts = {};
for (const n of solids) {
  const name = n.getName();
  let g = null;
  for (const [gname, re] of RULES) if (re.test(name)) { g = gname; break; }
  if (!g) {
    const b = getBounds(n);
    const cy = (b.min[1] + b.max[1]) / 2, cz = (b.min[2] + b.max[2]) / 2;
    if (cy > 84) g = 'Raspberry_Pi';
    else if (cz < -9) g = 'Nucleo';
    else { dropped++; n.setMesh(null); n.dispose(); continue; }
  }
  counts[g] = (counts[g] || 0) + 1;
  group(g).addChild(n);
}
// materials per group so the STEP (which has none) reads as PLA, aluminium, PCB, parts
const COLOURS = {
  Lid: [0.93, 0.93, 0.9], Side_Walls: [0.9, 0.9, 0.87], End_Panels: [0.9, 0.9, 0.87], Belly_Pan: [0.86, 0.86, 0.83], HS_Keepers: [0.86, 0.86, 0.83], UI_Pod: [0.93, 0.93, 0.9],
  Heatsink: [0.72, 0.74, 0.78], PCB: [0.1, 0.36, 0.22], Nucleo: [0.95, 0.95, 0.97], Raspberry_Pi: [0.12, 0.42, 0.24], XT60: [0.98, 0.78, 0.1],
  Inductors: [0.2, 0.18, 0.16], Buck_modules: [0.15, 0.15, 0.17], Bulk_caps: [0.35, 0.35, 0.38], Fasteners: [0.6, 0.6, 0.62], LCD: [0.1, 0.3, 0.5], IR_receiver: [0.2, 0.2, 0.22], RGB_LED: [0.8, 0.2, 0.2], Breadboard: [0.95, 0.95, 0.95],
};
const metal = new Set(['Heatsink', 'Fasteners']);
for (const [name, g] of groups) {
  const c = COLOURS[name] ?? [0.7, 0.7, 0.7];
  const mat = doc.createMaterial(name).setBaseColorFactor([c[0], c[1], c[2], 1]).setMetallicFactor(metal.has(name) ? 0.9 : 0).setRoughnessFactor(metal.has(name) ? 0.35 : 0.7);
  g.traverse((n) => { const m = n.getMesh(); if (m) for (const prim of m.listPrimitives()) prim.setMaterial(mat); });
}
for (const g of groups.values()) scene.addChild(g);
if (top !== scene && top.listChildren().length === 0) top.dispose();
console.log('groups:', Object.entries(counts).map(([k, v]) => `${k}=${v}`).join(' '), `dropped=${dropped}`);
await doc.transform(prune());
await io.write(output, doc);
console.log(`wrote ${output}`);
