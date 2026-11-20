/**
 * Exploded-view 3D island (three.js). Loads a GLB, remembers each matched node's rest position
 * and lifts it along the board/assembly normal as the slider moves (taller parts lift further).
 * Clicking (or choosing from the list) highlights the part and opens a card with its role,
 * package, datasheet and links; numbered badges can be shown over the model.
 * Node naming is data-driven (src/data/parts.ts): KiCad refdes for the board, body names for
 * the enclosure.
 */
import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js';

export interface PartInfo {
  match: string | string[];
  label: string;
  body: string;
  /** short tag for the badge, e.g. "L1" */
  tag?: string;
  /** 0..1, how far the part lifts relative to the others */
  lift?: number;
  package?: string;
  datasheet?: { label: string; href: string };
  /** URL of a thumbnail (datasheet first page or render) */
  thumb?: string;
  /** reference designator to locate on the schematic / board viewers */
  ref?: string;
  /** schematic sheet link */
  sheet?: { label: string; href: string };
  /** explode direction override */
  dir?: [number, number, number];
  /** 'key' parts get a filled badge and are labelled by default; 'support' parts (passives,
   *  test points, accessories) get an outline badge shown only with "all labels". */
  tier?: 'key' | 'support';
}
export interface Props {
  src: string; parts: PartInfo[]; defaultExplode?: number; height?: string; up?: 'y' | 'z' | '-z'; labels?: boolean; viewers?: boolean;
  /** camera position as multiples of the model radius */ camera?: [number, number, number];
  /** board positions (mm, from kicad_index.json) of every refdes: parts the 3D export has no mesh
   *  for (connectors, switches, test points) get a marker there, calibrated on the parts that do. */
  refPos?: Record<string, [number, number]>;
}
type LabelMode = 'key' | 'all' | 'none';

function matches(name: string, m: string | string[]) {
  const arr = Array.isArray(m) ? m : [m];
  const n = name.toLowerCase();
  return arr.some((p) => {
    const q = p.toLowerCase();
    if (q.startsWith('*') && q.endsWith('*')) return n.includes(q.slice(1, -1));
    if (q.endsWith('*')) return n.startsWith(q.slice(0, -1));
    if (q.startsWith('*')) return n.endsWith(q.slice(1));
    return n === q;
  });
}

type Mover = { obj: THREE.Object3D; rest: THREE.Vector3; dir: THREE.Vector3; dirWorld: THREE.Vector3; lift: number; part: PartInfo; centre: THREE.Vector3 };

/** Least-squares fit of world = a·bx + b·by + c for one axis. */
function fitAxis(pts: { bx: number; by: number; w: number }[]): [number, number, number] {
  let sxx = 0, sxy = 0, sx = 0, syy = 0, sy = 0, n = 0, sxw = 0, syw = 0, sw = 0;
  for (const p of pts) { sxx += p.bx * p.bx; sxy += p.bx * p.by; sx += p.bx; syy += p.by * p.by; sy += p.by; n++; sxw += p.bx * p.w; syw += p.by * p.w; sw += p.w; }
  const A = [[sxx, sxy, sx], [sxy, syy, sy], [sx, sy, n]], B = [sxw, syw, sw];
  const det = (m: number[][]) => m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]);
  const D = det(A) || 1;
  return [0, 1, 2].map((k) => det(A.map((row, i) => row.map((v, j) => (j === k ? B[i] : v)))) / D) as [number, number, number];
}

export default function Exploded({ src, parts, defaultExplode = 0, height = 'min(72vh, 660px)', up = 'y', labels = true, viewers = true, camera: camPos = [0.95, 0.8, 1.05], refPos }: Props) {
  const mount = useRef<HTMLDivElement>(null);
  const overlay = useRef<HTMLDivElement>(null);
  const [explode, setExplode] = useState(defaultExplode);
  const [selected, setSelected] = useState<PartInfo | null>(null);
  const [labelMode, setLabelMode] = useState<LabelMode>(labels ? 'key' : 'none');
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [found, setFound] = useState<PartInfo[]>([]);
  const api = useRef<{ setExplode: (t: number) => void; select: (p: PartInfo | null) => void; focus: (p: PartInfo) => void; reset: () => void; setLabels: (m: LabelMode) => void } | null>(null);

  useEffect(() => {
    const el = mount.current!;
    const ov = overlay.current!;
    // dev aid: ?cam=x,y,z overrides the camera position (multiples of the model radius)
    const camQ = new URLSearchParams(location.search).get('cam');
    const cam = camQ ? (camQ.split(',').map(Number) as [number, number, number]) : camPos;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(38, 1, 0.01, 1000);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    scene.add(new THREE.HemisphereLight(0xffffff, 0x3a4a60, 1.1));
    const key = new THREE.DirectionalLight(0xffffff, 2.0); key.position.set(3, 5, 4); scene.add(key);
    const fill = new THREE.DirectionalLight(0xffe4b0, 0.9); fill.position.set(-4, 2, -3); scene.add(fill);
    const rim = new THREE.DirectionalLight(0xbfd8ff, 0.6); rim.position.set(0, -3, -4); scene.add(rim);

    const movers: Mover[] = [];
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let root: THREE.Object3D | null = null;
    let radius = 1;
    let target = defaultExplode, current = defaultExplode;
    let selectedObjs: THREE.Object3D[] = [];
    let selectedPart: PartInfo | null = null;
    const saved = new Map<THREE.Mesh, THREE.Material | THREE.Material[]>();
    let labelMode: LabelMode = labels ? 'key' : 'none';
    // camera tween for zoom-to-part / reset
    let home: { pos: THREE.Vector3; target: THREE.Vector3 } | null = null;
    let tween: { pos: THREE.Vector3; target: THREE.Vector3 } | null = null;

    const setEmissive = (obj: THREE.Object3D | null, on: boolean) => {
      obj?.traverse((c) => {
        const m = c as THREE.Mesh;
        if (!m.isMesh) return;
        if (on) {
          if (!saved.has(m)) saved.set(m, m.material);
          const mats = Array.isArray(m.material) ? m.material : [m.material];
          m.material = mats.map((mm) => { const cl = (mm as THREE.MeshStandardMaterial).clone(); if ('emissive' in cl) { (cl as THREE.MeshStandardMaterial).emissive = new THREE.Color(0xffa500); (cl as THREE.MeshStandardMaterial).emissiveIntensity = 0.55; } return cl; }) as any;
          if (!Array.isArray(saved.get(m))) m.material = (m.material as THREE.Material[])[0];
        } else if (saved.has(m)) { m.material = saved.get(m)!; saved.delete(m); }
      });
    };
    // every member of a set lights up (Q1–Q8 are eight nodes of one part)
    const select = (p: PartInfo | null) => {
      selectedObjs.forEach((o) => setEmissive(o, false));
      selectedObjs = p ? movers.filter((m) => m.part === p).map((m) => m.obj) : [];
      selectedObjs.forEach((o) => setEmissive(o, true));
      selectedPart = p;
      setSelected(p);
    };
    // zoom to fit the whole selected set, keeping the current viewing direction
    const focus = (p: PartInfo) => {
      const objs = movers.filter((m) => m.part === p).map((m) => m.obj);
      if (!objs.length) return;
      const box = new THREE.Box3(); objs.forEach((o) => box.expandByObject(o));
      const c = box.getCenter(new THREE.Vector3());
      const size = Math.max(box.getSize(new THREE.Vector3()).length(), radius * 0.12);
      const dist = (size * 0.9) / Math.tan((camera.fov * Math.PI) / 360);
      const dirv = camera.position.clone().sub(controls.target).normalize();
      tween = { pos: c.clone().addScaledVector(dirv, dist), target: c };
    };
    const reset = () => { if (home) tween = { pos: home.pos.clone(), target: home.target.clone() }; };

    const loader = new GLTFLoader();
    loader.setMeshoptDecoder(MeshoptDecoder);
    loader.load(src, (gltf) => {
      root = gltf.scene;
      if (up === 'z') root.rotation.x = -Math.PI / 2;
      if (up === '-z') root.rotation.x = Math.PI / 2;
      scene.add(root);
      root.updateMatrixWorld(true);
      const box = new THREE.Box3().setFromObject(root);
      const size = box.getSize(new THREE.Vector3());
      const center = box.getCenter(new THREE.Vector3());
      root.position.sub(center);
      root.updateMatrixWorld(true);
      radius = Math.max(size.x, size.y, size.z);
      camera.position.set(radius * cam[0], radius * cam[1], radius * cam[2]);
      camera.near = radius / 100; camera.far = radius * 20; camera.updateProjectionMatrix();
      controls.target.set(0, 0, 0);
      home = { pos: camera.position.clone(), target: new THREE.Vector3() };
      const seen = new Set<THREE.Object3D>();
      const hits: PartInfo[] = [];
      root.traverse((o) => {
        if (seen.has(o) || o === root) return;
        for (const p of parts) {
          if (matches(o.name, p.match)) {
            seen.add(o); o.traverse((c) => seen.add(c));
            const b = new THREE.Box3().setFromObject(o);
            const c = b.getCenter(new THREE.Vector3());
            const h = b.max.y - b.min.y; // world space (after the up rotation)
            const dirWorld = (p.dir ? new THREE.Vector3(...p.dir) : new THREE.Vector3(0, 1, 0)).normalize();
            const dir = dirWorld.clone().applyQuaternion(root!.quaternion.clone().invert()); // into the root's local frame
            movers.push({ obj: o, rest: o.position.clone(), dir, dirWorld, lift: p.lift ?? Math.min(1, h / (radius * 0.08)), part: p, centre: c });
            o.userData.part = p;
            if (!hits.includes(p)) hits.push(p);
            break;
          }
        }
      });
      // Parts the 3D export has no mesh for: markers at their KiCad board positions. The board-mm to
      // world map is fitted on the meshed parts that also have a board position.
      if (refPos) {
        const cal: { bx: number; by: number; c: THREE.Vector3 }[] = [];
        for (const m of movers) { const ref = m.obj.name; if (refPos[ref]) cal.push({ bx: refPos[ref][0], by: refPos[ref][1], c: m.centre }); }
        const bodyNode = root.getObjectByName('board_body');
        if (cal.length >= 4 && bodyNode) {
          const fx = fitAxis(cal.map((q) => ({ bx: q.bx, by: q.by, w: q.c.x })));
          const fz = fitAxis(cal.map((q) => ({ bx: q.bx, by: q.by, w: q.c.z })));
          const top = new THREE.Box3().setFromObject(bodyNode).max.y;
          const mmScale = Math.hypot(fx[0], fz[0]) || radius / 175;
          const allRefs = Object.keys(refPos);
          for (const p of parts) {
            if (hits.includes(p)) continue;
            const pats = Array.isArray(p.match) ? p.match : [p.match];
            const refs = allRefs.filter((r) => matches(r, pats)).sort((a, b) => a.localeCompare(b, 'en', { numeric: true }));
            if (!refs.length) continue;
            for (const r of refs) {
              const [bx, by] = refPos[r];
              const g = new THREE.Mesh(
                new THREE.CylinderGeometry(3.2 * mmScale, 3.2 * mmScale, 1.6 * mmScale, 24),
                new THREE.MeshStandardMaterial({ color: 0x9fb2cf, transparent: true, opacity: 0.85, roughness: 0.6 }),
              );
              g.name = r;
              g.position.set(fx[0] * bx + fx[1] * by + fx[2], top + 1.2 * mmScale, fz[0] * bx + fz[1] * by + fz[2]);
              scene.add(g);
              const dirWorld = (p.dir ? new THREE.Vector3(...p.dir) : new THREE.Vector3(0, 1, 0)).normalize();
              movers.push({ obj: g, rest: g.position.clone(), dir: dirWorld.clone(), dirWorld, lift: p.lift ?? 0.35, part: p, centre: g.position.clone() });
              g.userData.part = p;
            }
            hits.push(p);
          }
        }
      }
      setFound(hits.sort((a, b) => parts.indexOf(a) - parts.indexOf(b)));
      api.current = {
        setExplode: (t) => { target = t; },
        select, focus, reset,
        setLabels: (m) => { labelMode = m; },
      };
      setStatus('ready');
    }, undefined, () => setStatus('error'));

    const onClick = (e: MouseEvent) => {
      const r = renderer.domElement.getBoundingClientRect();
      pointer.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
      raycaster.setFromCamera(pointer, camera);
      const hits = raycaster.intersectObjects(scene.children, true);
      for (const h of hits) {
        let o: THREE.Object3D | null = h.object;
        while (o) { if (o.userData.part) { select(o.userData.part); return; } o = o.parent; }
      }
      select(null);
    };
    renderer.domElement.addEventListener('click', onClick);

    const resize = () => { const w = el.clientWidth, h = el.clientHeight; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); };
    const ro = new ResizeObserver(resize); ro.observe(el); resize();

    // badges: one per tagged PART, pinned to the member nearest the set's centroid (so a set's
    // badge sits on a real part rather than floating between them). Mouse-only: the chips are
    // the keyboard path, so badges stay out of the tab order.
    const badges = new Map<PartInfo, { el: HTMLButtonElement; movers: Mover[]; anchor?: Mover }>();
    const ensureBadges = () => {
      for (const m of movers) {
        if (!m.part.tag) continue;
        let b = badges.get(m.part);
        if (!b) {
          const el = document.createElement('button'); el.type = 'button'; el.tabIndex = -1;
          el.className = 'exploded-badge' + (m.part.tier === 'support' ? ' support' : ''); el.textContent = m.part.tag; el.title = m.part.label;
          el.addEventListener('click', (e) => { e.stopPropagation(); select(m.part); });
          ov.appendChild(el); b = { el, movers: [] }; badges.set(m.part, b);
        }
        if (!b.movers.includes(m)) { b.movers.push(m); b.anchor = undefined; }
      }
      for (const b of badges.values()) {
        if (b.anchor) continue;
        const c = new THREE.Vector3(); b.movers.forEach((m) => c.add(m.centre)); c.multiplyScalar(1 / b.movers.length);
        b.anchor = b.movers.reduce((best, m) => (m.centre.distanceTo(c) < best.centre.distanceTo(c) ? m : best), b.movers[0]);
      }
    };
    const v = new THREE.Vector3();
    let raf = 0;
    const tick = () => {
      if (tween) {
        camera.position.lerp(tween.pos, 0.14); controls.target.lerp(tween.target, 0.14);
        if (camera.position.distanceTo(tween.pos) < radius * 0.002) tween = null;
      }
      controls.update();
      current += (target - current) * 0.12;
      for (const m of movers) m.obj.position.copy(m.rest).addScaledVector(m.dir, current * radius * (0.12 + 0.55 * m.lift));
      renderer.render(scene, camera);
      if (movers.length) ensureBadges();
      const w = el.clientWidth, h = el.clientHeight;
      for (const [part, b] of badges) {
        const show = part === selectedPart || labelMode === 'all' || (labelMode === 'key' && part.tier !== 'support');
        if (!show || !b.anchor) { b.el.hidden = true; continue; }
        b.el.hidden = false;
        const m = b.anchor;
        v.copy(m.centre).addScaledVector(m.dirWorld, current * radius * (0.12 + 0.55 * m.lift)).project(camera);
        b.el.style.transform = `translate(${((v.x + 1) / 2) * w}px, ${((1 - v.y) / 2) * h}px) translate(-50%,-50%)`;
        b.el.style.opacity = v.z < 1 ? '1' : '0';
        b.el.classList.toggle('sel', part === selectedPart);
      }
      raf = requestAnimationFrame(tick);
    };
    tick();
    const onHi = (e: Event) => { const ref = (e as CustomEvent).detail?.ref; const p = parts.find((pp) => pp.ref === ref); if (p && (e as CustomEvent).detail?.source !== 'exploded') select(p); };
    document.addEventListener('bb:highlight', onHi);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); document.removeEventListener('bb:highlight', onHi); renderer.domElement.removeEventListener('click', onClick); controls.dispose(); renderer.dispose(); el.innerHTML = ''; ov.innerHTML = ''; };
  }, [src]);

  useEffect(() => { api.current?.setExplode(explode); }, [explode]);
  useEffect(() => { api.current?.setLabels(labelMode); }, [labelMode]);
  const keyParts = found.filter((p) => p.tier !== 'support');
  const supportParts = found.filter((p) => p.tier === 'support');
  const chipText = (p: PartInfo) => (p.tag && /^\d+$/.test(p.tag) ? `${p.tag} ${p.label.split(/[,(]/)[0].trim().slice(0, 22)}` : (p.tag ?? p.label));
  const chip = (p: PartInfo) => <button type="button" key={p.label} title={p.label} aria-pressed={selected === p} className={'chip' + (p.tier === 'support' ? ' chip-support' : '') + (selected === p ? ' chip-accent' : '')} onClick={() => { api.current?.select(selected === p ? null : p); }}>{chipText(p)}</button>;

  const locate = (ref: string) => document.dispatchEvent(new CustomEvent('bb:highlight', { detail: { ref, source: 'exploded' } }));

  return (
    <div className="exploded">
      <div className="exploded-stage">
        <div ref={mount} className="exploded-canvas" style={{ height }} aria-label="Interactive 3D model">
          {status === 'loading' && <div className="exploded-msg">Loading model…</div>}
          {status === 'error' && <div className="exploded-msg">The 3D model could not be loaded in this browser. The photos and tables on this page cover the same parts.</div>}
        </div>
        <div ref={overlay} className="exploded-overlay" aria-hidden="true" />
        {selected && (
          <div className="exploded-card" role="dialog" aria-label={selected.label}>
            <button type="button" className="exploded-close" onClick={() => api.current?.select(null)} aria-label="Close">×</button>
            {selected.thumb && <img src={selected.thumb} alt="" className="exploded-thumb" loading="lazy" />}
            <div>
              <strong>{selected.label}</strong>
              {selected.package && <div className="mono small muted">{selected.package}</div>}
              <p className="small">{selected.body}</p>
              <div className="row" style={{ gap: '.4rem' }}>
                {selected.datasheet && <a className="btn btn-sm ext" href={selected.datasheet.href} target="_blank" rel="noopener">{selected.datasheet.label}</a>}
                {selected.sheet && <a className="btn btn-sm ext" href={selected.sheet.href} target="_blank" rel="noopener">{selected.sheet.label}</a>}
                {viewers && selected.ref && <button type="button" className="btn btn-sm" onClick={() => locate(selected.ref!)}>Find on schematic and board</button>}
                <button type="button" className="btn btn-sm btn-ghost" onClick={() => api.current?.focus(selected)}>Zoom to {/^\d+$/.test(selected.tag ?? '') || !selected.tag ? 'part' : selected.tag}</button>
              </div>
            </div>
          </div>
        )}
      </div>
      <div className="exploded-ui">
        <label className="exploded-slider">
          <span className="mono small">Explode</span>
          <input type="range" min={0} max={1} step={0.01} value={explode} onChange={(e) => setExplode(parseFloat(e.target.value))} aria-label="Explode amount" />
        </label>
        <div className="exploded-modes" role="group" aria-label="Labels on the model">
          {supportParts.length > 0
            ? (['key', 'all', 'none'] as LabelMode[]).map((m) => <button type="button" key={m} className="chip" aria-pressed={labelMode === m} onClick={() => setLabelMode(m)}>{m === 'key' ? 'key parts' : m === 'all' ? 'all labels' : 'no labels'}</button>)
            : (['key', 'none'] as LabelMode[]).map((m) => <button type="button" key={m} className="chip" aria-pressed={labelMode === m} onClick={() => setLabelMode(m)}>{m === 'key' ? 'labels' : 'no labels'}</button>)}
          <button type="button" className="chip" onClick={() => api.current?.reset()}>reset view</button>
        </div>
        <div className="exploded-parts">
          {keyParts.map(chip)}
          {supportParts.length > 0 && <span className="exploded-sep small muted">supporting parts</span>}
          {supportParts.map(chip)}
        </div>
        <p className="small muted exploded-hint">Drag to orbit, scroll to zoom, click a part or a chip to identify it. Pale discs mark parts the 3D export has no model for.</p>
      </div>
      <style>{`
        .exploded { border: 1px solid var(--line); border-radius: 14px; overflow: hidden; background: radial-gradient(120% 90% at 50% 0%, color-mix(in srgb, var(--blue-soft) 70%, var(--bg-2)), var(--bg-2) 70%); }
        .exploded-stage { position: relative; }
        .exploded-canvas { position: relative; width: 100%; }
        .exploded-canvas canvas { width: 100% !important; height: 100% !important; display: block; cursor: grab; }
        .exploded-msg { position: absolute; inset: 0; display: grid; place-items: center; color: var(--muted); font-size: .95rem; padding: 1rem; text-align: center; }
        .exploded-overlay { position: absolute; inset: 0; pointer-events: none; overflow: hidden; }
        .exploded-badge { position: absolute; left: 0; top: 0; pointer-events: auto; border: 2px solid var(--surface); background: var(--blue); color: var(--on-color); font: 700 .68rem var(--font-mono); padding: .15rem .4rem; border-radius: 999px; box-shadow: 0 2px 8px rgba(0,0,0,.35); cursor: pointer; transition: opacity .2s; white-space: nowrap; }
        .exploded-badge.support { background: var(--surface); color: var(--blue-ink); border: 1.5px solid var(--blue); font-size: .6rem; padding: .08rem .32rem; box-shadow: 0 1px 4px rgba(0,0,0,.25); }
        .exploded-badge.sel { background: var(--accent); color: var(--on-accent); border-color: var(--surface); z-index: 2; }
        .exploded-card { position: absolute; right: .8rem; top: .8rem; width: min(360px, calc(100% - 1.6rem)); background: var(--surface); border: 1px solid var(--line); border-radius: 14px; box-shadow: var(--shadow); padding: .9rem 1rem; display: grid; grid-template-columns: auto 1fr; gap: .8rem; z-index: 5; }
        .exploded-card p { margin: .3rem 0 .6rem; }
        .exploded-thumb { width: 72px; height: 96px; object-fit: cover; object-position: top; border-radius: 8px; border: 1px solid var(--line); background: var(--paper); }
        .exploded-close { position: absolute; right: .4rem; top: .3rem; border: 0; background: transparent; font-size: 1.3rem; color: var(--muted); cursor: pointer; }
        .exploded-ui { display: grid; grid-template-columns: minmax(180px, 260px) auto 1fr; gap: .8rem 1rem; padding: .8rem 1rem; border-top: 1px solid var(--line); background: var(--surface); align-items: center; }
        .exploded-slider { display: grid; gap: .25rem; }
        .exploded-ui input[type=range] { width: 100%; accent-color: var(--accent); }
        .exploded-parts { display: flex; flex-wrap: wrap; gap: .3rem; grid-column: 1 / -1; }
        .exploded-parts .chip { cursor: pointer; }
        .exploded-parts .chip-support { background: transparent; }
        .exploded-sep { flex-basis: 100%; margin: .35rem 0 0; }
        .exploded-modes { display: flex; flex-wrap: wrap; gap: .3rem; }
        .exploded-modes [aria-pressed="true"] { background: var(--blue-soft); color: var(--blue-ink); border-color: var(--blue); }
        .exploded-hint { grid-column: 1 / -1; margin: 0; }
        @media (max-width: 640px) { .exploded-ui { grid-template-columns: 1fr; } .exploded-card { grid-template-columns: 1fr; } }
      `}</style>
    </div>
  );
}
