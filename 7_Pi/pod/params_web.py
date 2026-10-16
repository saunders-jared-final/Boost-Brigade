#!/usr/bin/env python3
"""Shuffler control + run-time parameter page: http://<pi>:8080 (stdlib only, no extra packages).

Talks to the Nucleo through the pod's control socket (podlink.PodLink), so the pod service must be running.
The firmware owns the bounds and the apply classes (C,LIST); this page only shows and forwards:
  - table of every parameter: Nucleo value, params.yaml value, bounds, class; Set per row
  - Apply (swap the staged gain set, bumpless), Revert (firmware defaults, idle only)
  - Push params.yaml -> Nucleo (every value except hall_zero*, which the boot zero-cal owns), optional Apply
  - Save Nucleo -> params.yaml (values only; comments kept)
  - kscale quick steps (SET + APPLY), M + kp/fc/duty clamp from a shuffler_params.json file (staged)
  - Control panel: live status and the operator presets of actions.py (the same as the IR remote's digits);
    presets that start switching or turn the e-load on need a second click within 4 s
  - E-load (DL3021) panel: link / local-remote / mode / input / setpoint / V I P from the eload service
    (podlink.EloadLink, socket 127.0.0.1:5018), mode select + level entry; input on/off and local/remote are presets
  - Stop (C,EN,0) and E-stop (C,ESTOP) on every view
Only the commands in ALLOWED (Nucleo) and ALLOWED_E (e-load) are forwarded (no duty or calibration commands).
No authentication: keep the Pi on the bench / carpark network.

    python3 params_web.py [--port 8080] [--yaml params.yaml]      (params_web.service on the Pi)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from actions import ACTIONS, BY_KEY
from podlink import EloadLink, PodLink
from telemetry_parser import parse_line

log = logging.getLogger("params_web")
HERE = os.path.dirname(os.path.abspath(__file__))
N_Y = 4
ALLOWED = re.compile(r"^C,(SET,[a-z0-9_]+,[-+0-9.eE]+|SETM(,[-+0-9.eE]+){16}|APPLY|REVERT|GET,[a-z0-9_]+|LIST|EN,[01]|ESTOP|PING"
                     r"|MODE,(IDLE|OL|CL|OL1|CL1|OL2|CL2)|TEST,0|CLEAR)$")
ALLOWED_E = re.compile(r"^E,(STATUS|INPUT,[01]|LOCAL|REMOTE|MODE,(CC|CV|CR|CP)|SET,(CC|CV|CR|CP),[0-9.]+)$")
PUSH_SKIP = {"vstr_pi"} | {f"hall_zero{k}" for k in range(4)}
LINE_RE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*):(\s*)([^#\s]+)(.*)$")
MROW_RE = re.compile(r"^(\s*-\s*)\[([^\]]*)\](.*)$")


# --------------------------------------------------------------- params.yaml ---
def yaml_read(path: str) -> tuple[dict, list]:
    vals, M, in_m = {}, [], False
    with open(path) as f:
        for raw in f:
            line = raw.rstrip("\n")
            if line.strip().startswith("#") or not line.strip():
                continue
            if in_m:
                m = MROW_RE.match(line)
                if m:
                    M.append([float(x) for x in m.group(2).split(",")])
                    continue
                in_m = False
            if re.match(r"^\s*M:\s*(#.*)?$", line):
                in_m = True
                continue
            m = LINE_RE.match(line)
            if m:
                try:
                    vals[m.group(2)] = float(m.group(4))
                except ValueError:
                    pass
    return vals, M


def fmt(v: float) -> str:
    s = f"{v:.6g}"
    return s


def yaml_write(path: str, vals: dict, M: list | None):
    out, in_m, row = [], False, 0
    with open(path) as f:
        lines = f.read().split("\n")
    for line in lines:
        if in_m:
            m = MROW_RE.match(line)
            if m and M is not None and row < len(M):
                out.append(f"{m.group(1)}[{', '.join(fmt(x) for x in M[row])}]{m.group(3)}")
                row += 1
                continue
            if not m:
                in_m = False
            else:
                out.append(line)
                continue
        if re.match(r"^\s*M:\s*(#.*)?$", line):
            in_m, row = True, 0
            out.append(line)
            continue
        m = LINE_RE.match(line)
        if m and not line.strip().startswith("#") and m.group(2) in vals:
            old = m.group(4)
            new = fmt(vals[m.group(2)])
            pad = max(1, len(old) - len(new) + len(re.match(r"^\s*", m.group(5)).group(0))) if m.group(5) else 0
            rest = m.group(5).lstrip() if m.group(5) else ""
            out.append(f"{m.group(1)}{m.group(2)}:{m.group(3)}{new}{' ' * pad if rest else ''}{rest}")
            continue
        out.append(line)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write("\n".join(out))
    os.replace(tmp, path)


# ------------------------------------------------------------------ backend ---
class Backend:
    def __init__(self, yaml_path: str):
        self.pod = PodLink()
        self.eload = EloadLink()
        self.yaml_path = yaml_path
        self.lock = threading.Lock()

    def cmd(self, c: str) -> dict:
        c = c.strip()
        if c.startswith("E,"):
            if not ALLOWED_E.match(c):
                return {"ok": False, "lines": [f"refused by params_web: {c}"]}
            ans = self.eload.request(c)
            if ans is None:
                return {"ok": False, "lines": ["eload service not reachable (systemctl status eload)"]}
            return {"ok": ans.startswith(f"A,{c.split(',')[1]},OK"), "lines": [ans]}
        if not ALLOWED.match(c):
            return {"ok": False, "lines": [f"refused by params_web: {c}"]}
        ok, lines = self.pod.request(c)
        return {"ok": ok, "lines": lines}

    def action(self, key: str) -> dict:
        a = BY_KEY.get(key)
        if a is None:
            return {"ok": False, "lines": [f"unknown action {key}"]}
        out = []
        for c in a.cmds:
            r = self.cmd(c)
            out.append(f"{c}: " + ("OK" if r["ok"] else " ".join(r["lines"][-1:])))
            if not r["ok"]:
                return {"ok": False, "lines": out}
        return {"ok": True, "lines": out}

    def list(self) -> dict:
        ok, lines = self.pod.request("C,LIST", timeout=6.0)
        rows = []
        for t in lines:
            fr = parse_line(t)
            if fr and fr.kind == "P" and "class" in fr.values:
                rows.append(fr.values)
        note = lines[-1] if lines else ""
        return {"ok": ok, "rows": rows, "dirty": "staged changes pending" in note, "note": note}

    def state(self) -> dict:
        p = self.pod
        out = {"link": p.sock is not None, "age": time.time() - p.last_t_time if p.last_t_time else None}
        fr = parse_line(p.last_t) if p.last_t else None
        if fr:
            out.update(state=fr.state, fault=hex(fr.fault), kscale=fr.values.get("kscale"),
                       pset=fr.values.get("pset"), pver=fr.values.get("pver"),
                       VM=[fr.values.get(f"VM{k}") for k in (1, 2, 3)],
                       IL=[fr.values.get(n) for n in ("ILA1", "ILB1", "ILA2", "ILB2")],
                       D=[fr.values.get(n) for n in ("dA1", "dB1", "dA2", "dB2")])
        fs = parse_line(p.last_s) if p.last_s else None
        if fs:
            out["mode"] = fs.values.get("mode")
        out["eload"] = self.eload.status()     # None = eload service down
        return out

    def yaml(self) -> dict:
        vals, M = yaml_read(self.yaml_path)
        return {"vals": vals, "M": M, "path": self.yaml_path}

    def push(self, apply: bool) -> dict:
        vals, M = yaml_read(self.yaml_path)
        log_lines, errs = [], 0
        for k, v in vals.items():
            if k in PUSH_SKIP:
                continue
            r = self.cmd(f"C,SET,{k},{v:.7g}")
            errs += 0 if r["ok"] else 1
            log_lines.append(f"SET {k}={v:.7g}: {'OK' if r['ok'] else ' '.join(r['lines'][-1:])}")
        if len(M) == N_Y and all(len(r) == N_Y for r in M):
            flat = ",".join(f"{x:.7g}" for row in M for x in row)
            r = self.cmd(f"C,SETM,{flat}")
            errs += 0 if r["ok"] else 1
            log_lines.append(f"SETM: {'OK' if r['ok'] else ' '.join(r['lines'][-1:])}")
        if apply and errs == 0:
            r = self.cmd("C,APPLY")
            errs += 0 if r["ok"] else 1
            log_lines.append(f"APPLY: {'OK' if r['ok'] else ' '.join(r['lines'][-1:])}")
        elif apply:
            log_lines.append("APPLY skipped: fix the errors above first")
        return {"ok": errs == 0, "lines": log_lines}

    def save(self) -> dict:
        L = self.list()
        if not L["ok"]:
            return {"ok": False, "lines": ["C,LIST failed: " + L["note"]]}
        vals = {r["name"]: r["value"] for r in L["rows"]}
        have_m = all(f"m{i}{j}" in vals for i in range(N_Y) for j in range(N_Y))
        M = [[vals[f"m{i}{j}"] for j in range(N_Y)] for i in range(N_Y)] if have_m else None   # never write a partial M
        with self.lock:
            yaml_write(self.yaml_path, vals, M)
        return {"ok": True, "lines": [f"saved {len(vals)} values to {self.yaml_path}"]}


# --------------------------------------------------------------------- page ---
PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Shuffler control</title>
<style>
:root{--bg:#f4f6f8;--card:#fff;--ink:#1b2128;--mute:#5e6a75;--line:#d6dce2;--acc:#0e6a8e;--bad:#b3362c;--ok:#2f7d4a;--warn:#a86400}
@media (prefers-color-scheme:dark){:root{--bg:#12171c;--card:#1a2027;--ink:#e3e8ec;--mute:#97a3ad;--line:#2e3842;--acc:#5cc2e6;--bad:#f08a80;--ok:#6ccf8e;--warn:#f0b04e}}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,sans-serif}
header{position:sticky;top:0;background:var(--card);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;flex-wrap:wrap;gap:10px;align-items:center;z-index:2}
h1{font-size:17px;margin:0 12px 0 0}.pill{font:600 12px ui-monospace,monospace;padding:3px 7px;border-radius:3px;background:var(--bg)}
main{padding:12px 16px;display:flex;flex-direction:column;gap:14px;max-width:1100px}
section{background:var(--card);border:1px solid var(--line);padding:12px}
button{font:inherit;padding:6px 10px;border:1px solid var(--line);background:var(--bg);color:var(--ink);border-radius:3px;cursor:pointer}
button.pri{background:var(--acc);color:#fff;border-color:var(--acc)}button.bad{background:var(--bad);color:#fff;border-color:var(--bad);font-weight:700}
.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.tbl{overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:720px}
th,td{padding:5px 8px;border-bottom:1px solid var(--line);text-align:left;font-variant-numeric:tabular-nums}
th{font:600 11px ui-monospace,monospace;color:var(--mute);text-transform:uppercase}
td.n{font-family:ui-monospace,monospace}input{font:inherit;width:9em;padding:4px;background:var(--bg);color:var(--ink);border:1px solid var(--line)}
.diff{color:var(--warn);font-weight:600}.c-STAGED{color:var(--acc)}.c-IDLE{color:var(--warn)}
pre{white-space:pre-wrap;font:12px ui-monospace,monospace;margin:0;max-height:220px;overflow:auto}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin-bottom:12px}
.tile{border:1px solid var(--line);padding:8px 10px}.tile b{display:block;font:600 11px ui-monospace,monospace;color:var(--mute);text-transform:uppercase}
.tile span{font:600 18px ui-monospace,monospace;font-variant-numeric:tabular-nums}
.acts{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:8px}
.act{display:flex;gap:8px;align-items:center;text-align:left;padding:8px 10px}
.act .dg{font:700 13px ui-monospace,monospace;min-width:1.6em;height:1.6em;display:inline-grid;place-items:center;border:1px solid var(--line);border-radius:50%}
.act.go{border-color:var(--warn)}.act.arm{background:var(--warn);color:#fff;border-color:var(--warn)}
.st-FAULT{color:var(--bad)}.st-RUN{color:var(--ok)}
</style></head><body>
<header><h1>Shuffler control</h1><span class="pill" id="st">…</span><span class="pill" id="ks">…</span>
<span class="pill" id="pv">…</span><span style="flex:1"></span>
<button onclick="cmd('C,EN,0')">Stop (EN 0)</button><button class="bad" onclick="cmd('C,ESTOP')">E-STOP</button></header>
<main>
<section><div class="tiles">
<div class="tile"><b>State</b><span id="t_state">…</span></div><div class="tile"><b>Mode</b><span id="t_mode">…</span></div>
<div class="tile"><b>Fault</b><span id="t_fault">…</span></div><div class="tile"><b>VM1 / VM2 / VM3 [V]</b><span id="t_vm">…</span></div>
<div class="tile"><b>IL A1 B1 A2 B2 [A]</b><span id="t_il" style="font-size:14px">…</span></div><div class="tile"><b>Duties</b><span id="t_d" style="font-size:14px">…</span></div>
</div>
<div class="acts" id="acts"></div>
<p style="margin:8px 0 0;color:var(--mute)">Same presets as the IR remote digits. Orange buttons start switching or turn the load on: click once to arm, again within 4 s to send.</p></section>
<section><div class="tiles">
<div class="tile"><b>E-load (DL3021)</b><span id="e_link" style="font-size:14px">…</span></div><div class="tile"><b>Mode / input</b><span id="e_mode">…</span></div>
<div class="tile"><b>Setpoint</b><span id="e_set">…</span></div><div class="tile"><b>V / I / P at the load</b><span id="e_vip" style="font-size:14px">…</span></div>
<div class="tile"><b>Levels CC / CV / CR / CP</b><span id="e_lv" style="font-size:14px">…</span></div><div class="tile"><b>Protection (QUES reg)</b><span id="e_q" style="font-size:14px">…</span></div>
</div>
<div class="row"><b>Level</b>
<select id="e_m"><option>CV</option><option>CC</option><option>CR</option><option>CP</option></select>
<input id="e_v" type="number" step="any" placeholder="value" style="width:7em"><button onclick="eset()">Set level</button>
<button onclick="emode()">Switch mode (input off)</button>
<span style="color:var(--mute)">Input on/off and local/remote are presets 3–6 above. Levels this page accepts: CV 0–150 V, CC 0–15 A, CR 0.05–15 kΩ, CP 0–200 W. Local = front panel free, logging and vstr_pi forwarding paused.</span></div></section>
<section><div class="row"><b>Gain scale</b>
<span id="kbtns"></span><span style="color:var(--mute)">sets kscale and applies (bumpless). Bench: start 0.3, step up only while it settles cleanly.</span></div></section>
<section><div class="row">
<button class="pri" onclick="post('/api/cmd',{cmd:'C,APPLY'})">Apply staged</button>
<button onclick="post('/api/push',{apply:false})">Push params.yaml</button>
<button onclick="post('/api/push',{apply:true})">Push + Apply</button>
<button onclick="post('/api/save',{})">Save Nucleo → params.yaml</button>
<button onclick="post('/api/cmd',{cmd:'C,REVERT'})">Revert to firmware defaults</button>
<label>M from shuffler_params.json <input type="file" id="jf" accept=".json" style="width:16em"></label>
<button onclick="refresh()">Refresh</button></div><p id="dirty" style="margin:6px 0 0;color:var(--warn)"></p></section>
<section class="tbl"><table><thead><tr><th>Name</th><th>Nucleo</th><th>params.yaml</th><th>New</th><th></th><th>Min</th><th>Max</th><th>Class</th></tr></thead><tbody id="tb"></tbody></table></section>
<section><b>Log</b><pre id="log"></pre></section>
</main>
<script>
const KS=[0.1,0.2,0.3,0.4,0.5,0.7,1.0];
const $=id=>document.getElementById(id);
function logl(s){const l=$('log');l.textContent=(new Date().toLocaleTimeString()+'  '+s+'\n')+l.textContent;}
async function post(u,b){try{const r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});const j=await r.json();
 logl((j.ok?'OK  ':'ERR ')+(b.cmd||u)+'  '+(j.lines||[]).join(' | '));}catch(e){logl('ERR '+e);} refresh(); }
function cmd(c){return post('/api/cmd',{cmd:c});}
async function setk(k){await post('/api/cmd',{cmd:'C,SET,kscale,'+k});await post('/api/cmd',{cmd:'C,APPLY'});}
$('kbtns').innerHTML=KS.map(k=>`<button onclick="setk(${k})">${k}</button>`).join(' ');
function f(v){return (v===undefined||v===null)?'':(+v).toPrecision(6).replace(/\.?0+(e|$)/,'$1');}
async function refresh(){
 try{const [L,Y]=await Promise.all([fetch('/api/list').then(r=>r.json()),fetch('/api/yaml').then(r=>r.json())]);
 const yv=Object.assign({},Y.vals);(Y.M||[]).forEach((r,i)=>r.forEach((x,j)=>yv['m'+i+j]=x));
 $('dirty').textContent=L.dirty?'Staged gain changes are pending: press Apply.':'';
 $('tb').innerHTML=L.rows.map(r=>{const y=yv[r.name];const d=(y!==undefined&&Math.abs(y-r.value)>1e-6*Math.max(1,Math.abs(y)));
  return `<tr><td class="n">${r.name}</td><td class="n">${f(r.value)}</td><td class="n ${d?'diff':''}">${f(y)}</td>
  <td><input id="i_${r.name}" type="number" step="any" min="${r.min}" max="${r.max}" placeholder="${f(r.value)}"></td>
  <td><button onclick="setp('${r.name}')">Set</button></td><td class="n">${f(r.min)}</td><td class="n">${f(r.max)}</td><td class="c-${r.class}">${r.class}</td></tr>`}).join('');
 if(!L.ok) logl('LIST failed: '+L.note);}catch(e){logl('refresh failed: '+e);} }
async function setp(n){const v=$('i_'+n).value;if(v==='')return;await cmd('C,SET,'+n+','+v);}
async function eset(){const v=$('e_v').value;if(v==='')return;await cmd('E,SET,'+$('e_m').value+','+v);}
async function emode(){await cmd('E,MODE,'+$('e_m').value);}
function eload(e){const T=(id,v,c)=>{$(id).textContent=v;if(c!==undefined)$(id).className=c;};
 if(!e){T('e_link','no eload service','st-FAULT');for(const id of ['e_mode','e_set','e_vip','e_lv','e_q'])T(id,'–');return;}
 if(!e.link_ok){T('e_link','NO USB LINK','st-FAULT');for(const id of ['e_mode','e_set','e_vip','e_lv','e_q'])T(id,'–');return;}
 T('e_link',(e.paused?'LOCAL (panel free, logging paused)':'REMOTE (logging)')+(e.age>3&&!e.paused?' stale':''),e.paused?'st-FAULT':'st-RUN');
 T('e_mode',(e.mode||'?')+' · '+(e.input_on?'INPUT ON':'input off'),e.input_on?'st-RUN':'');
 const u={CC:'A',CV:'V',CR:'Ω',CP:'W'}[e.mode]||'';T('e_set',e.setpoint==null?'–':(+e.setpoint).toFixed(2)+' '+u);
 const n=(v,d)=>v==null?'–':(+v).toFixed(d);T('e_vip',n(e.v,2)+' V · '+n(e.i,3)+' A · '+n(e.p,1)+' W');
 T('e_lv',n(e.set_cc,2)+' A · '+n(e.set_cv,1)+' V · '+n(e.set_cr,1)+' Ω · '+n(e.set_cp,0)+' W');
 T('e_q',e.ques==null?'–':('0x'+(+e.ques).toString(16)+(e.err?' · '+e.err:'')),e.ques?'st-FAULT':'');}
async function state(){try{const s=await fetch('/api/state').then(r=>r.json());
 $('st').textContent=(s.state||'no link')+' fault '+(s.fault||'?')+(s.age>3?' (stale)':'');
 $('ks').textContent='kscale '+f(s.kscale)+' · set #'+(s.pset??'?');$('pv').textContent=s.pver||'';}catch(e){$('st').textContent='page server down';}}
$('jf').addEventListener('change',async ev=>{const t=await ev.target.files[0].text();const P=JSON.parse(t);const C=P.ctrl||{};
 if(!C.M||C.M.length!==4){logl('ERR json has no 4x4 ctrl.M');return;}
 await cmd('C,SETM,'+C.M.flat().map(x=>(+x).toPrecision(7)).join(','));
 for(const [k,j] of [['kp_v','kp_ratio_v'],['kp_i','kp_ratio_i'],['fc_lpf','fc_lpf'],['dmin','dmin'],['dmax','dmax']]) if(C[j]!==undefined) await cmd('C,SET,'+k+','+C[j]);
 logl('loaded '+(P.version||'json')+' as STAGED: press Apply');});
let armed=null,armT=0;
async function acts(){const A=await fetch('/api/actions').then(r=>r.json());
 $('acts').innerHTML=A.map(a=>`<button class="act ${a.starts?'go':''}" id="a_${a.key}" title="${a.cmds.join('  ')}" onclick="act('${a.key}',${a.starts})"><span class="dg">${a.digit??'·'}</span><span>${a.label}</span></button>`).join('');}
async function act(k,starts){const b=$('a_'+k);
 if(starts&&!(armed===k&&Date.now()-armT<4000)){document.querySelectorAll('.act.arm').forEach(x=>x.classList.remove('arm'));
  armed=k;armT=Date.now();b.classList.add('arm');setTimeout(()=>{b.classList.remove('arm');if(armed===k)armed=null;},4000);logl('armed '+k+': click again to start');return;}
 armed=null;b.classList.remove('arm');await post('/api/action',{key:k});}
const st0=state;
state=async function(){await st0();try{const s=await fetch('/api/state').then(r=>r.json());
 const T=(id,v,c)=>{$(id).textContent=v;if(c!==undefined)$(id).className=c;};
 eload(s.eload);
 if(!s.link){T('t_state','pod down');return;}
 if(!s.state||s.age>3){T('t_state','no Nucleo');T('t_mode','–');T('t_fault','–');T('t_vm','–');T('t_il','–');T('t_d','–');return;}
 T('t_state',s.state,'st-'+(s.state.startsWith('RUN')?'RUN':s.state));T('t_mode',s.mode||'?');T('t_fault',s.fault,s.fault!=='0x0'?'st-FAULT':'');
 T('t_vm',(s.VM||[]).map(v=>v==null||isNaN(v)?'–':(+v).toFixed(2)).join(' / '));
 T('t_il',(s.IL||[]).map(v=>v==null?'–':(+v).toFixed(2)).join(' '));T('t_d',(s.D||[]).map(v=>v==null?'–':(+v).toFixed(3)).join(' '));}catch(e){}};
acts();refresh();state();setInterval(state,1000);
</script></body></html>"""


def make_handler(be: Backend):
    class H(BaseHTTPRequestHandler):
        def log_message(self, fmt_, *args):
            log.debug(fmt_, *args)

        def _json(self, obj, code=200):
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if self.path == "/" or self.path.startswith("/?"):
                b = PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
            elif self.path == "/api/list":
                self._json(be.list())
            elif self.path == "/api/state":
                self._json(be.state())
            elif self.path == "/api/yaml":
                self._json(be.yaml())
            elif self.path == "/api/actions":
                self._json([{"key": a.key, "label": a.label, "digit": a.digit, "starts": a.starts, "cmds": a.cmds}
                            for a in ACTIONS])
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                body = {}
            if self.path == "/api/cmd":
                r = be.cmd(str(body.get("cmd", "")))
                log.info("%s -> %s", body.get("cmd"), "OK" if r["ok"] else r["lines"][-1:])
                self._json(r)
            elif self.path == "/api/action":
                r = be.action(str(body.get("key", "")))
                log.info("action %s -> %s", body.get("key"), r["lines"][-1:])
                self._json(r)
            elif self.path == "/api/push":
                self._json(be.push(bool(body.get("apply"))))
            elif self.path == "/api/save":
                self._json(be.save())
            else:
                self._json({"error": "not found"}, 404)
    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--yaml", default=os.path.join(HERE, "params.yaml"))
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if a.v else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    be = Backend(a.yaml)
    srv = ThreadingHTTPServer(("0.0.0.0", a.port), make_handler(be))
    log.info("parameter page on http://0.0.0.0:%d (yaml %s)", a.port, a.yaml)
    srv.serve_forever()


if __name__ == "__main__":
    main()
