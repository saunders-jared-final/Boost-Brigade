#!/usr/bin/env python3
"""Dump node names / mesh / vertex counts of a .glb (no deps). Usage: glb_nodes.py file.glb [max_nodes]"""
import json, struct, sys
p = sys.argv[1]; maxn = int(sys.argv[2]) if len(sys.argv) > 2 else 40
with open(p, 'rb') as f:
    magic, ver, length = struct.unpack('<III', f.read(12))
    clen, ctype = struct.unpack('<II', f.read(8))
    g = json.loads(f.read(clen))
nodes = g.get('nodes', []); meshes = g.get('meshes', []); acc = g.get('accessors', [])
verts = sum(acc[pr['attributes']['POSITION']]['count'] for m in meshes for pr in m['primitives'] if 'POSITION' in pr['attributes'])
print(f"file={p} nodes={len(nodes)} meshes={len(meshes)} vertices={verts} ext={g.get('extensionsUsed')}")
named = [n.get('name', '') for n in nodes]
print(f"named_nodes={sum(1 for n in named if n)} unnamed={sum(1 for n in named if not n)}")
roots = g['scenes'][0]['nodes'] if g.get('scenes') else []
print(f"scene_root_nodes={len(roots)}")
def show(i, depth=0, budget=[maxn]):
    if budget[0] <= 0: return
    budget[0] -= 1
    n = nodes[i]; m = n.get('mesh')
    print('  ' * depth + f"[{i}] {n.get('name','')!r}" + (f" mesh={m} ({meshes[m].get('name','')})" if m is not None else '') + (f" children={len(n['children'])}" if n.get('children') else ''))
    for c in n.get('children', []): show(c, depth + 1, budget)
for r in roots: show(r)
pat = [a.lower() for a in sys.argv[3:]]
if pat:
    print('--- matches:', pat)
    for i, n in enumerate(nodes):
        nm = n.get('name', '')
        if any(q in nm.lower() for q in pat): print(f"[{i}] {nm!r} mesh={n.get('mesh')} children={len(n.get('children', []))}")
