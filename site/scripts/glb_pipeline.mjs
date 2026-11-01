#!/usr/bin/env node
// Optimise a KiCad / CAD GLB for the web while KEEPING one named node per part.
//
//   node glb_pipeline.mjs in.glb out.glb [--ratio 0.5] [--error 0.0001] [--board] [--no-simplify]
//
// Why not `gltf-transform optimize`?  Its flatten/join/instance passes collapse the
// scene graph to ~10 anonymous nodes, which loses the per-refdes (C25, U8, L1 ...)
// nodes the showcase site needs for highlighting / exploded views.
//
// What this does instead:
//   1. (--board) names KiCad's anonymous board-level nodes by material/height:
//      copper, silkscreen_top/bottom, soldermask_top/bottom, board_body; root -> "board".
//   2. For every top-level node (a refdes or enclosure part) bakes the sub-tree
//      transforms, joins all primitives per material into ONE mesh on that node
//      (19k draw calls -> a few hundred) and deletes the sub-tree.
//   3. weld -> simplify (meshoptimizer, target ratio) -> dedup -> prune -> meshopt
//      compression (EXT_meshopt_compression + KHR_mesh_quantization).
import { NodeIO, Document, Node } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import {
  dedup, prune, weld, simplify, joinPrimitives, transformMesh, meshopt, getBounds,
} from '@gltf-transform/functions';
import { MeshoptSimplifier, MeshoptEncoder } from 'meshoptimizer';
import { mat4 } from 'gl-matrix';
const { multiply, identity, equals } = mat4;

const args = process.argv.slice(2);
const positional = args.filter((a) => !a.startsWith('--'));
const flag = (name, dflt) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? args[i + 1] : dflt;
};
const [input, output] = positional;
if (!input || !output) {
  console.error('usage: glb_pipeline.mjs in.glb out.glb [--ratio 0.5] [--error 0.0001] [--board] [--no-simplify]');
  process.exit(2);
}
const ratio = parseFloat(flag('ratio', '0.5'));
const error = parseFloat(flag('error', '0.0001'));
const isBoard = args.includes('--board');
const doSimplify = !args.includes('--no-simplify');

await MeshoptSimplifier.ready;
await MeshoptEncoder.ready;
const io = new NodeIO()
  .registerExtensions(ALL_EXTENSIONS)
  .registerDependencies({ 'meshopt.encoder': MeshoptEncoder });

const doc = await io.read(input);
const root = doc.getRoot();
const scene = root.listScenes()[0];
const logger = doc.getLogger();

const countVerts = () =>
  root.listMeshes().reduce((s, m) => s + m.listPrimitives().reduce((t, p) => t + (p.getAttribute('POSITION')?.getCount() ?? 0), 0), 0);
const countPrims = () => root.listMeshes().reduce((s, m) => s + m.listPrimitives().length, 0);
console.log(`in : nodes=${root.listNodes().length} meshes=${root.listMeshes().length} prims=${countPrims()} verts=${countVerts()}`);

// ---------------------------------------------------------------- 1. board-level names
const IDENTITY = identity(new Float64Array(16));
const sceneRoots = scene.listChildren();
// KiCad wraps everything in one unnamed node; descend into it if so.
const partParents = sceneRoots.length === 1 && !sceneRoots[0].getName() && !sceneRoots[0].getMesh() ? sceneRoots : [];
if (partParents.length) partParents[0].setName(isBoard ? 'board' : 'root');
const parts = partParents.length ? partParents[0].listChildren() : sceneRoots;

if (isBoard) {
  const approx = (a, b) => Math.abs(a - b) < 0.03;
  const colourOf = (node) => node.getMesh()?.listPrimitives()[0]?.getMaterial()?.getBaseColorFactor() ?? [0, 0, 0, 1];
  const anon = parts.filter((n) => n.getMesh() && /^=>/.test(n.getName()));
  // reference height = centre of the board body (KiCad exports Y-up, board plane = XZ)
  const body = anon.find((n) => { const c = colourOf(n); return approx(c[0], 0.42) && approx(c[1], 0.45) && approx(c[2], 0.29); });
  const bb = getBounds(body ?? scene);
  const midY = (bb.min[1] + bb.max[1]) / 2;
  for (const node of anon) {
    const mesh = node.getMesh();
    const c = colourOf(node);
    const b = getBounds(node);
    const top = (b.min[1] + b.max[1]) / 2 > midY;
    let name = null;
    if (approx(c[0], 0.7) && approx(c[1], 0.61) && approx(c[2], 0.0)) name = 'copper';
    else if (approx(c[0], 1) && approx(c[1], 1) && approx(c[2], 1)) name = top ? 'silkscreen_top' : 'silkscreen_bottom';
    else if (approx(c[0], 0.08) && approx(c[1], 0.2) && approx(c[2], 0.14)) name = top ? 'soldermask_top' : 'soldermask_bottom';
    else if (node === body) name = 'board_body';
    if (name) {
      node.setName(name);
      mesh.setName(name);
      console.log(`  board node ${name}: prims=${mesh.listPrimitives().length}`);
    } else {
      console.warn(`  WARNING unrecognised board-level node ${node.getName()} colour=${c.map((x) => x.toFixed(2))}`);
    }
  }
}

// ---------------------------------------------------------------- 2. collapse each part to one mesh
function collectLeaves(node, parentMatrix, out) {
  const m = multiply(new Float64Array(16), parentMatrix, node.getMatrix());
  if (node.getMesh()) out.push({ node, mesh: node.getMesh(), matrix: m });
  for (const child of node.listChildren()) collectLeaves(child, m, out);
}

let collapsed = 0;
for (const part of parts) {
  const leaves = [];
  // transforms *below* the part node are baked; the part's own placement is kept.
  for (const child of part.listChildren()) collectLeaves(child, IDENTITY, leaves);
  if (part.getMesh()) leaves.push({ node: part, mesh: part.getMesh(), matrix: IDENTITY });
  if (leaves.length === 0) continue;
  const groups = new Map(); // material -> prims
  for (const { mesh, matrix } of leaves) {
    if (!equals(matrix, IDENTITY)) transformMesh(mesh, matrix);
    for (const prim of mesh.listPrimitives()) {
      const key = `${prim.getMaterial()?.getName() ?? ''}#${prim.getMode()}#${prim.listSemantics().sort().join(',')}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(prim);
    }
  }
  const name = part.getName();
  // mesh keeps the CAD/model name (e.g. C_0805_2012Metric); the NODE carries the refdes
  const merged = doc.createMesh(leaves[0].mesh.getName() || name);
  for (const prims of groups.values()) {
    merged.addPrimitive(prims.length === 1 ? prims[0] : joinPrimitives(prims));
  }
  // drop the old sub-tree (nodes + now-empty meshes); prune() removes orphans
  for (const child of part.listChildren()) child.traverse((n) => n.setMesh(null));
  for (const child of part.listChildren()) child.dispose();
  part.setMesh(merged);
  collapsed++;
}
console.log(`collapsed ${collapsed} parts -> nodes=${root.listNodes().length}`);

// ---------------------------------------------------------------- 3. optimise
const transforms = [dedup(), prune(), weld()];
if (doSimplify) transforms.push(simplify({ simplifier: MeshoptSimplifier, ratio, error }));
transforms.push(dedup(), prune(), meshopt({ encoder: MeshoptEncoder, level: 'high' }));
await doc.transform(...transforms);

console.log(`out: nodes=${root.listNodes().length} meshes=${root.listMeshes().length} prims=${countPrims()} verts=${countVerts()}`);
await io.write(output, doc);
const { statSync } = await import('node:fs');
console.log(`wrote ${output} (${(statSync(output).size / 1e6).toFixed(2)} MB)`);
