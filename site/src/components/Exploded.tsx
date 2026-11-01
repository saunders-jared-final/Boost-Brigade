/**
 * Exploded-view 3D island (three.js). Loads one or more GLBs, remembers each top-level
 * node's rest position and offsets it along an explode direction as the slider moves.
 * Node naming is data-driven (see src/data/parts.ts) so it works for the KiCad board
 * (refdes nodes) and the enclosure (body nodes) alike.
 */
import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js';

export interface PartInfo { match: string | string[]; label: string; body: string; explode?: [number, number, number]; }
export interface Props { src: string; parts: PartInfo[]; defaultExplode?: number; height?: string; up?: 'y' | 'z'; }

function matches(name: string, m: string | string[]) {
  const arr = Array.isArray(m) ? m : [m];
  return arr.some((p) => (p.endsWith('*') ? name.startsWith(p.slice(0, -1)) : name === p));
}

export default function Exploded({ src, parts, defaultExplode = 0, height = 'min(70vh, 640px)', up = 'y' }: Props) {
  const mount = useRef<HTMLDivElement>(null);
  const [explode, setExplode] = useState(defaultExplode);
  const [selected, setSelected] = useState<PartInfo | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const api = useRef<{ setExplode: (t: number) => void } | null>(null);

  useEffect(() => {
    const el = mount.current!;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(40, 1, 0.01, 1000);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    scene.add(new THREE.HemisphereLight(0xffffff, 0x334455, 1.2));
    const key = new THREE.DirectionalLight(0xffffff, 2.2); key.position.set(3, 5, 4); scene.add(key);
    const fill = new THREE.DirectionalLight(0xffe0a0, 0.8); fill.position.set(-4, 2, -3); scene.add(fill);

    const movers: { obj: THREE.Object3D; rest: THREE.Vector3; dir: THREE.Vector3; part: PartInfo | null }[] = [];
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let root: THREE.Object3D | null = null;

    const loader = new GLTFLoader();
    loader.setMeshoptDecoder(MeshoptDecoder);
    loader.load(src, (gltf) => {
      root = gltf.scene;
      if (up === 'z') root.rotation.x = -Math.PI / 2;
      scene.add(root);
      // Fit camera
      const box = new THREE.Box3().setFromObject(root);
      const size = box.getSize(new THREE.Vector3());
      const center = box.getCenter(new THREE.Vector3());
      root.position.sub(center);
      const radius = Math.max(size.x, size.y, size.z);
      camera.position.set(radius * 0.9, radius * 0.7, radius * 1.1);
      camera.near = radius / 100; camera.far = radius * 20; camera.updateProjectionMatrix();
      controls.target.set(0, 0, 0);
      // Collect movers: nodes whose name matches a part, else top-level children
      const seen = new Set<THREE.Object3D>();
      root.traverse((o) => {
        if (seen.has(o)) return;
        for (const p of parts) {
          if (matches(o.name, p.match)) {
            seen.add(o);
            o.traverse((c) => seen.add(c));
            const c = new THREE.Box3().setFromObject(o).getCenter(new THREE.Vector3()).sub(root!.position);
            const dir = p.explode ? new THREE.Vector3(...p.explode) : c.clone().setX(0).setZ(0).normalize();
            if (dir.lengthSq() < 1e-6) dir.set(0, 1, 0);
            movers.push({ obj: o, rest: o.position.clone(), dir, part: p });
            o.userData.part = p;
            break;
          }
        }
      });
      api.current = { setExplode: (t) => movers.forEach((m) => m.obj.position.copy(m.rest).addScaledVector(m.dir, t * radius * 0.35)) };
      api.current.setExplode(defaultExplode);
      setStatus('ready');
    }, undefined, () => setStatus('error'));

    const onClick = (e: MouseEvent) => {
      const r = renderer.domElement.getBoundingClientRect();
      pointer.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
      raycaster.setFromCamera(pointer, camera);
      const hits = raycaster.intersectObjects(scene.children, true);
      for (const h of hits) {
        let o: THREE.Object3D | null = h.object;
        while (o) { if (o.userData.part) { setSelected(o.userData.part); return; } o = o.parent; }
      }
      setSelected(null);
    };
    renderer.domElement.addEventListener('click', onClick);

    const resize = () => { const w = el.clientWidth, h = el.clientHeight; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); };
    const ro = new ResizeObserver(resize); ro.observe(el); resize();
    let raf = 0;
    const tick = () => { controls.update(); renderer.render(scene, camera); raf = requestAnimationFrame(tick); };
    tick();
    return () => { cancelAnimationFrame(raf); ro.disconnect(); renderer.domElement.removeEventListener('click', onClick); controls.dispose(); renderer.dispose(); el.innerHTML = ''; };
  }, [src]);

  useEffect(() => { api.current?.setExplode(explode); }, [explode]);

  return (
    <div className="exploded">
      <div ref={mount} className="exploded-canvas" style={{ height }} aria-label="Interactive 3D model">
        {status === 'loading' && <div className="exploded-msg">Loading model…</div>}
        {status === 'error' && <div className="exploded-msg">Model not available yet. Run <code>site/scripts/prep_models.sh</code>.</div>}
      </div>
      <div className="exploded-ui">
        <label>
          <span className="mono small">Explode</span>
          <input type="range" min={0} max={1} step={0.01} value={explode} onChange={(e) => setExplode(parseFloat(e.target.value))} aria-label="Explode amount" />
        </label>
        <div className="exploded-info">
          {selected ? (<><strong>{selected.label}</strong><p className="small muted">{selected.body}</p></>) : (<p className="small muted">Drag to orbit, scroll to zoom, click a part to identify it.</p>)}
        </div>
      </div>
      <style>{`
        .exploded { border: 1px solid var(--line); border-radius: 14px; overflow: hidden; background: var(--bg-2); }
        .exploded-canvas { position: relative; width: 100%; }
        .exploded-canvas canvas { width: 100% !important; height: 100% !important; display: block; cursor: grab; }
        .exploded-msg { position: absolute; inset: 0; display: grid; place-items: center; color: var(--muted); font-size: .95rem; padding: 1rem; text-align: center; }
        .exploded-ui { display: grid; grid-template-columns: minmax(180px, 280px) 1fr; gap: 1rem; padding: .9rem 1rem; border-top: 1px solid var(--line); background: var(--surface); align-items: center; }
        .exploded-ui label { display: grid; gap: .3rem; }
        .exploded-ui input[type=range] { width: 100%; accent-color: var(--accent); }
        .exploded-info p { margin: .2rem 0 0; }
        @media (max-width: 640px) { .exploded-ui { grid-template-columns: 1fr; } }
      `}</style>
    </div>
  );
}
