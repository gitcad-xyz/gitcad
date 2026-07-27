"""The viewer page — one self-contained HTML string, zero external assets.

ONE page; everything else is a tab in it (3d, schematics, checks, review,
drawing, activity), each addressable as a hash token composable with the
older deep links (#checks,x=0.6). WebGL2 with flat shading via
fragment-shader derivatives, orbit/zoom, live reload by content-hash
polling, and the live loop: a narration rail tailing /api/activity, a
camera that follows the assembly instance being worked on (the #follow
toggle), an ask banner that blocks a waiting agent on the human's answer,
and an activity tab holding the whole session — click an event to jump to
the part it touched. Plus a measure tool — raycast picking with vertex
snap, two picks give distance + per-axis deltas. Monospace dark aesthetic
to match gitcad.xyz.
"""

PAGE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>gitcad viewer</title>
<style>
  :root{--bg:#0d1117;--ink:#c9d1d9;--dim:#8b949e;--acc:#58a6ff;--line:#21262d}
  *{margin:0;box-sizing:border-box}
  body{background:var(--bg);color:var(--ink);height:100vh;overflow:hidden;
       font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
  #gl,#board{position:fixed;inset:0;width:100%;height:100%}
  #board{display:none;align-items:center;justify-content:center;padding:24px}
  #board svg{max-width:100%;max-height:100%}
  #sheets,#checks,#review,#activity{background:var(--bg)}  /* opaque over #board */
  #sheets{position:fixed;inset:0;display:none;overflow:auto;padding:44px 24px 24px}
  .sheet-card{background:#fff;border-radius:4px;margin:0 auto 18px;max-width:1200px;padding:10px}
  .sheet-card svg{display:block;width:100%;height:auto}
  .sheet-name{color:var(--dim);margin:0 auto 4px;max-width:1200px}
  .sheet-err{color:#f85149;margin:0 auto 18px;max-width:1200px}
  #tabs{position:fixed;left:12px;top:10px;display:flex;gap:8px;z-index:5}
  .tab{color:var(--dim);cursor:pointer;padding:2px 10px;border:1px solid var(--line);
       border-radius:4px;background:rgba(13,17,23,.8);user-select:none}
  .tab.on{color:var(--acc);border-color:var(--acc)}
  .tab.tool.on{color:#3fb950;border-color:#3fb950}
  #hud{position:fixed;left:12px;bottom:10px;color:var(--dim);pointer-events:none;white-space:pre}
  #hud b{color:var(--ink)}
  #measure{position:fixed;right:12px;bottom:10px;color:#3fb950;pointer-events:none;
           white-space:pre;text-align:right}
  #err{position:fixed;top:38px;left:12px;color:#f85149;white-space:pre-wrap}
  #logo{position:fixed;right:12px;top:10px;color:var(--acc);font-weight:700}
  #sel{position:fixed;left:12px;bottom:64px;color:#d29922;pointer-events:none;white-space:pre}
  #checks{position:fixed;inset:0;display:none;overflow:auto;padding:44px 24px 24px;
          font-size:13px}
  .chk{max-width:900px;margin:0 auto 14px;border:1px solid var(--line);
       border-radius:6px;padding:10px 14px}
  .chk h3{margin:0 0 6px;font-size:13px}
  .chk .ok{color:#3fb950} .chk .bad{color:#f85149}
  .chk li{color:#f85149;margin-left:1.2em;list-style:disc}
  #review{position:fixed;inset:0;display:none;overflow:auto;padding:44px 24px 24px;
          font-size:13px}
  .rev{max-width:1100px;margin:0 auto 16px;border:1px solid var(--line);
       border-radius:6px;padding:10px 14px}
  .rev h3{margin:0 0 6px;font-size:13px} .rev small{color:var(--dim)}
  .rev .bad{color:#f85149} .rev .good{color:#3fb950}
  .rev .sxs{display:flex;gap:10px;flex-wrap:wrap;margin-top:8px}
  .rev .pane{flex:1;min-width:300px;background:#fff;border-radius:4px;padding:6px}
  .rev .pane h4{color:#57606a;margin:0 0 4px;font-size:11px}
  .rev .pane svg{max-width:100%;height:auto;display:block}
  #drawing{position:fixed;inset:0;display:none;background:#fff}
  #drawing .dwrap{position:absolute;inset:38px 0 0 0;overflow:auto;text-align:center}
  #drawing .dwrap svg{max-width:98%;height:auto}
  #drawing .dbar{position:fixed;right:14px;top:10px;display:flex;gap:8px;z-index:6}
  #drawing .dbar a{color:#0969da;font-size:12px;text-decoration:none;background:#fff;
                   border:1px solid #d0d7de;border-radius:6px;padding:2px 9px}
  #explodebox{position:fixed;right:12px;top:40px;display:none;align-items:center;
              gap:8px;color:var(--dim);z-index:5}
  #explodebox input{width:140px;accent-color:var(--acc)}
  /* the live rail: what the agent is doing, right now. Always visible on
     every tab — watching the work happen is the point, not a view of it. */
  #live{position:fixed;right:12px;bottom:38px;width:330px;max-height:46vh;
        display:none;flex-direction:column;gap:3px;z-index:6;font-size:11px;
        overflow:hidden;pointer-events:none}
  #live .ev{background:rgba(13,17,23,.86);border-left:2px solid var(--line);
            padding:3px 8px;color:var(--dim);border-radius:0 3px 3px 0;
            white-space:pre-wrap;opacity:.55}
  #live .ev:last-child{opacity:1;color:var(--ink);border-left-color:#3fb950}
  #live .ev.problem{border-left-color:#f85149;color:#f85149;opacity:1}
  #live .ev.done{border-left-color:var(--acc)}
  #live .ev .who{color:#3fb950}
  #livehead{display:flex;align-items:center;gap:6px;color:#3fb950;
            background:rgba(13,17,23,.86);padding:3px 8px;border-radius:3px;
            pointer-events:auto}
  #livehead.idle{color:var(--dim)} #livehead.idle b{color:var(--dim)}
  #livedot{width:7px;height:7px;border-radius:50%;background:#3fb950;
           animation:pulse 1.4s ease-in-out infinite}
  #follow{margin-left:auto;cursor:pointer;border:1px solid var(--line);
          border-radius:3px;padding:0 6px;color:var(--dim);user-select:none}
  #follow.on{color:#3fb950;border-color:#3fb950}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
  /* the activity tab: the whole session, not the rail's last few lines */
  #activity{position:fixed;inset:0;display:none;overflow:auto;
            padding:44px 24px 24px;font-size:12px}
  .act{max-width:900px;margin:0 auto;display:flex;gap:10px;padding:2px 8px;
       border-left:2px solid var(--line);color:var(--dim)}
  .act time{opacity:.65;flex:0 0 auto} .act .who{color:#3fb950}
  .act.problem{border-left-color:#f85149;color:#f85149}
  .act.done{border-left-color:var(--acc);color:var(--ink)}
  .act.question{border-left-color:#d29922;color:#d29922}
  .act.answer{border-left-color:#3fb950;color:#3fb950}
  .act.click{cursor:pointer}
  .act.click:hover{background:rgba(88,166,255,.08)}
  #actempty{color:var(--dim);max-width:900px;margin:0 auto}
  /* a question BLOCKS the eye: the agent is stopped until this is answered */
  #ask{position:fixed;left:50%;top:44px;transform:translateX(-50%);z-index:9;
       display:none;max-width:620px;background:#161b22;border:1px solid #d29922;
       border-radius:8px;padding:12px 16px;box-shadow:0 8px 30px rgba(0,0,0,.6)}
  #ask h4{margin:0 0 8px;color:#d29922;font-size:12px;letter-spacing:.04em;
          text-transform:uppercase}
  #ask .q{color:var(--ink);font-size:13px;margin-bottom:10px;white-space:pre-wrap}
  #ask .opts{display:flex;gap:8px;flex-wrap:wrap}
  #ask button{font:inherit;font-size:12px;color:var(--ink);background:#21262d;
              border:1px solid var(--line);border-radius:5px;padding:4px 12px;
              cursor:pointer}
  #ask button:hover{border-color:#d29922;color:#d29922}
  #ask input{font:inherit;font-size:12px;color:var(--ink);background:#0d1117;
             border:1px solid var(--line);border-radius:5px;padding:4px 8px;
             flex:1;min-width:180px}
</style></head><body>
<canvas id="gl"></canvas><div id="board"></div><div id="sheets"></div>
<div id="checks"></div><div id="review"></div><div id="drawing"></div>
<div id="activity"></div>
<div id="tabs"></div>
<div id="explodebox"><span>explode</span>
  <input id="explodeslider" type="range" min="0" max="100" value="0"></div>
<div id="live"></div>
<div id="ask"><h4>the agent is waiting on you</h4>
  <div class="q"></div><div class="opts"></div></div>
<div id="hud"></div><div id="sel"></div><div id="measure"></div>
<div id="err"></div><div id="logo">gitcad</div>
<script>
"use strict";
const canvas = document.getElementById("gl");
const gl = canvas.getContext("webgl2", {antialias: true});
const hud = document.getElementById("hud"), err = document.getElementById("err");
const measureHud = document.getElementById("measure");

const VS = `#version 300 es
in vec3 pos; in vec3 col; uniform mat4 mvp; out vec3 vPos; out vec3 vCol;
void main(){ vPos = pos; vCol = col; gl_Position = mvp * vec4(pos, 1.0);
  gl_PointSize = 9.0; }`;
const FS = `#version 300 es
precision highp float; in vec3 vPos; in vec3 vCol; out vec4 color;
uniform bool flat_col; uniform bool zebra;
void main(){
  if(flat_col){ color = vec4(vCol, 1.0); return; }
  vec3 n = normalize(cross(dFdx(vPos), dFdy(vPos)));
  if(zebra){
    // surface-quality inspection: iso-normal bands (Gauss-map stripes).
    // Smooth surfaces show smoothly flowing stripes; tangency breaks and
    // creases show as stripe kinks. Per-facet at tessellation density.
    float s = fract(6.0 * dot(n, normalize(vec3(1.0, 0.7, 0.4))));
    float band = s < 0.5 ? 0.2 : 1.0;
    color = vec4(vec3(0.85, 0.9, 1.0) * band, 1.0); return;
  }
  float l = 0.25 + 0.65 * max(dot(n, normalize(vec3(0.5, 0.4, 0.8))), 0.0)
                 + 0.18 * max(dot(n, normalize(vec3(-0.6, -0.3, 0.2))), 0.0);
  color = vec4(vCol * l, 1.0);
}`;

function compile(type, src){
  const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
  if(!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw gl.getShaderInfoLog(s);
  return s;
}
const prog = gl.createProgram();
gl.attachShader(prog, compile(gl.VERTEX_SHADER, VS));
gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, FS));
gl.bindAttribLocation(prog, 0, "pos"); gl.bindAttribLocation(prog, 1, "col");
gl.linkProgram(prog); gl.useProgram(prog);
const uMvp = gl.getUniformLocation(prog, "mvp");
const uFlat = gl.getUniformLocation(prog, "flat_col");
const uZebra = gl.getUniformLocation(prog, "zebra");
gl.enable(gl.DEPTH_TEST);
let zebraOn = location.hash.includes("zebra");
gl.uniform1i(uZebra, zebraOn ? 1 : 0);

let nIndices = 0, center = [0,0,0], radius = 50;
let yaw = 0.7, pitch = 0.5, dist = 3;   // dist in units of radius
let meshPos = null, meshIdx = null;     // LIVE positions (explode applied)
let basePos = null, baseCols = null;    // as-designed positions/colors
let groups = [];                        // {name, part, i0, i1, v0, v1, centroid}
let selected = -1, explode = 0;
let vb = null, cb = null;
const vao = gl.createVertexArray();

function upload(mesh){
  gl.bindVertexArray(vao);
  vb = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, vb);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(mesh.positions), gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
  const nVerts = mesh.positions.length / 3;
  let cols = mesh.colors;
  if(!cols || cols.length !== mesh.positions.length){
    cols = new Array(mesh.positions.length);
    for(let i = 0; i < nVerts; i++){ cols[3*i] = 0.35; cols[3*i+1] = 0.62; cols[3*i+2] = 0.85; }
  }
  cb = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, cb);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(cols), gl.STATIC_DRAW);
  gl.enableVertexAttribArray(1); gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 0, 0);
  const ib = gl.createBuffer();
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, ib);
  gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint32Array(mesh.indices), gl.STATIC_DRAW);
  nIndices = mesh.indices.length;
  basePos = new Float32Array(mesh.positions);
  baseCols = new Float32Array(cols);
  meshPos = new Float32Array(mesh.positions);
  meshIdx = new Uint32Array(mesh.indices);
  // group index/vertex ranges + centroids, for selection and explode
  groups = []; selected = -1;
  let i0 = 0;
  for(const g of (mesh.groups || [])){
    const i1 = i0 + g.triangles * 3;
    let v0 = Infinity, v1 = -1;
    for(let k = i0; k < i1; k++){ const v = meshIdx[k];
      if(v < v0) v0 = v; if(v > v1) v1 = v; }
    let cx = 0, cy = 0, cz = 0, n = Math.max(1, v1 - v0 + 1);
    for(let v = v0; v <= v1; v++){ cx += basePos[3*v]; cy += basePos[3*v+1]; cz += basePos[3*v+2]; }
    const cen = [cx/n, cy/n, cz/n];
    let r2 = 0;                       // group radius, for framing the camera
    for(let v = v0; v <= v1; v++){
      const dx = basePos[3*v] - cen[0], dy = basePos[3*v+1] - cen[1],
            dz = basePos[3*v+2] - cen[2];
      const q = dx*dx + dy*dy + dz*dz;
      if(q > r2) r2 = q;
    }
    groups.push({name: g.name, part: g.part, i0, i1, v0, v1,
                 centroid: cen, radius: Math.sqrt(r2)});
    i0 = i1;
  }
  const [lo, hi] = mesh.bbox;
  modelCenter = [(lo[0]+hi[0])/2, (lo[1]+hi[1])/2, (lo[2]+hi[2])/2];
  center = modelCenter.slice(); tween = null;
  radius = Math.max(1e-6, Math.hypot(hi[0]-lo[0], hi[1]-lo[1], hi[2]-lo[2]) / 2);
  const s = mesh.stats;
  const dims = `bbox ${(hi[0]-lo[0]).toFixed(2)} x ${(hi[1]-lo[1]).toFixed(2)} x ${(hi[2]-lo[2]).toFixed(2)} mm`;
  if(mesh.groups){
    const names = mesh.groups.map(g => `${g.name}(${g.part})`).join(" · ");
    hud.textContent = `assembly: ${names}\n${dims}\n${s.triangles} tris · kernel ${s.kernel} · drag orbit · wheel zoom`;
  } else {
    hud.textContent = `${s.features} features · ${s.triangles} tris · vol ${s.volume_mm3} mm³ · ${dims}\n` +
                      `kernel ${s.kernel} · drag orbit · wheel zoom`;
  }
  // a rebuild mid-watch must not lose either highlight, nor the camera's
  // attention on the part being worked on
  recolor();
  if(follow && activeName) focusActive();
}

// -- tiny matrix math ---------------------------------------------------------
function perspective(fovy, aspect, near, far){
  const f = 1/Math.tan(fovy/2), nf = 1/(near-far);
  return [f/aspect,0,0,0, 0,f,0,0, 0,0,(far+near)*nf,-1, 0,0,2*far*near*nf,0];
}
function mul(a,b){ const o=new Array(16).fill(0);
  for(let i=0;i<4;i++)for(let j=0;j<4;j++)for(let k=0;k<4;k++)o[j*4+i]+=a[k*4+i]*b[j*4+k];
  return o; }
function lookAt(eye, at, up){
  const z=norm3(sub3(eye,at)), x=norm3(cross3(up,z)), y=cross3(z,x);
  return [x[0],y[0],z[0],0, x[1],y[1],z[1],0, x[2],y[2],z[2],0,
          -dot3(x,eye),-dot3(y,eye),-dot3(z,eye),1];
}
const sub3=(a,b)=>[a[0]-b[0],a[1]-b[1],a[2]-b[2]];
const add3=(a,b)=>[a[0]+b[0],a[1]+b[1],a[2]+b[2]];
const scl3=(a,s)=>[a[0]*s,a[1]*s,a[2]*s];
const cross3=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const dot3=(a,b)=>a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
const norm3=a=>{const l=Math.hypot(...a)||1;return[a[0]/l,a[1]/l,a[2]/l];};

function eyePos(){
  const d = dist * radius;
  return [center[0] + d*Math.cos(pitch)*Math.cos(yaw),
          center[1] + d*Math.cos(pitch)*Math.sin(yaw),
          center[2] + d*Math.sin(pitch)];
}

// -- camera attention: follow the part being worked on ------------------------
// The live rail names the instance under the agent's hands; colour alone does
// not draw the eye when that part is small or off-screen. With follow on, the
// camera target glides to frame it — and pulls back out when the work is done.
// Orbit stays the human's: a drag or wheel cancels only the glide in flight,
// never the mode. The #follow toggle on the rail head is the mode.
let follow = true, tween = null, modelCenter = [0, 0, 0];
function glideTo(c, d){
  tween = {c0: center.slice(), c1: c, d0: dist, d1: d,
           t0: performance.now(), dur: 650};
}
function stepTween(now){
  if(!tween) return;
  let k = Math.min(1, (now - tween.t0) / tween.dur);
  k = k * k * (3 - 2 * k);                                    // smoothstep
  center = [tween.c0[0] + (tween.c1[0] - tween.c0[0]) * k,
            tween.c0[1] + (tween.c1[1] - tween.c0[1]) * k,
            tween.c0[2] + (tween.c1[2] - tween.c0[2]) * k];
  dist = tween.d0 + (tween.d1 - tween.d0) * k;
  if(k >= 1) tween = null;
}
function groupCenter(g){          // centroid, exploded-view offset included
  if(!(explode > 0) || groups.length < 2) return g.centroid.slice();
  let d = sub3(g.centroid, modelCenter);
  const l = Math.hypot(...d);
  d = l < 1e-6 ? [0, 0, 1] : scl3(d, 1 / l);
  return add3(g.centroid, scl3(d, explode * radius * 0.9));
}
function frameGroup(g){
  glideTo(groupCenter(g),
          Math.max(0.35, Math.min(12, (g.radius * 3.0) / radius)));
}
function focusActive(){
  if(!follow || !basePos) return;
  const g = activeName ? groups.find(x => x.name === activeName) : null;
  if(g) frameGroup(g);
  else glideTo(modelCenter.slice(), 3);   // work finished: pull back out
}

// -- measure tool -------------------------------------------------------------
let measureMode = false;
let picks = [];                          // up to 2 picked [x,y,z]
const measVao = gl.createVertexArray();
const measVb = gl.createBuffer(), measCb = gl.createBuffer();
gl.bindVertexArray(measVao);
gl.bindBuffer(gl.ARRAY_BUFFER, measVb);
gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
gl.bindBuffer(gl.ARRAY_BUFFER, measCb);
gl.enableVertexAttribArray(1); gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 0, 0);
gl.bindVertexArray(null);

function pickRay(px, py){
  // camera basis matching perspective(0.8, aspect) + lookAt(eye, center, +z)
  const w = canvas.clientWidth, h = canvas.clientHeight;
  const eye = eyePos();
  const fwd = norm3(sub3(center, eye));
  const right = norm3(cross3(fwd, [0,0,1]));
  const up = cross3(right, fwd);
  const t = Math.tan(0.8/2);
  const nx = (2*px/w - 1) * t * (w/h), ny = (1 - 2*py/h) * t;
  return {orig: eye, dir: norm3(add3(fwd, add3(scl3(right, nx), scl3(up, ny))))};
}
function rayTriangle(o, d, a, b, c){    // Moller-Trumbore; returns t or null
  const e1 = sub3(b,a), e2 = sub3(c,a), p = cross3(d, e2), det = dot3(e1, p);
  if(Math.abs(det) < 1e-12) return null;
  const inv = 1/det, tv = sub3(o, a), u = dot3(tv, p) * inv;
  if(u < 0 || u > 1) return null;
  const q = cross3(tv, e1), v = dot3(d, q) * inv;
  if(v < 0 || u + v > 1) return null;
  const t = dot3(e2, q) * inv;
  return t > 1e-9 ? t : null;
}
function raycast(px, py){
  if(!meshPos) return null;
  const {orig, dir} = pickRay(px, py);
  let best = null, bestTri = null, bestI = -1;
  for(let i = 0; i < meshIdx.length; i += 3){
    const a = [meshPos[3*meshIdx[i]], meshPos[3*meshIdx[i]+1], meshPos[3*meshIdx[i]+2]];
    const b = [meshPos[3*meshIdx[i+1]], meshPos[3*meshIdx[i+1]+1], meshPos[3*meshIdx[i+1]+2]];
    const c = [meshPos[3*meshIdx[i+2]], meshPos[3*meshIdx[i+2]+1], meshPos[3*meshIdx[i+2]+2]];
    const t = rayTriangle(orig, dir, a, b, c);
    if(t !== null && (best === null || t < best)){ best = t; bestTri = [a, b, c]; bestI = i; }
  }
  if(best === null) return null;
  return {orig, dir, t: best, tri: bestTri, index: bestI};
}

// -- selection: click a body, see what it is ---------------------------------
const selHud = document.getElementById("sel");
let activeName = null;                   // the instance the AGENT is working on

// One recolour pass carries BOTH highlights: the human's selection (amber) and
// the agent's current subject (green). They are different questions — "what am
// I looking at" and "what is being changed under me" — so one must never clear
// the other.
function recolor(){
  const cols = new Float32Array(baseCols);
  const paint = (g, r, gr, b, k) => {
    for(let v = g.v0; v <= g.v1; v++){
      cols[3*v]   = Math.min(1, cols[3*v]   * k + r);
      cols[3*v+1] = Math.min(1, cols[3*v+1] * k + gr);
      cols[3*v+2] = Math.min(1, cols[3*v+2] * k + b);
    }
  };
  const ai = activeName ? groups.findIndex(g => g.name === activeName) : -1;
  if(ai >= 0) paint(groups[ai], 0.05, 0.55, 0.15, 0.35);      // green
  if(selected >= 0) paint(groups[selected], 0.55, 0.45, 0.10, 0.5);  // amber
  if(selected >= 0){
    const g = groups[selected];
    selHud.textContent = `selected: ${g.name}  (${g.part})\n` +
      `centroid (${g.centroid.map(v=>v.toFixed(1)).join(", ")}) · ` +
      `${(g.i1 - g.i0) / 3} tris · click again to deselect`;
  } else {
    selHud.textContent = "";
  }
  gl.bindBuffer(gl.ARRAY_BUFFER, cb);
  gl.bufferData(gl.ARRAY_BUFFER, cols, gl.STATIC_DRAW);
  syncSheetHighlight(selected >= 0 ? groups[selected].name
                                   : (ai >= 0 ? activeName : null));
}
function applySelection(idx){ selected = idx; recolor(); }
function setActive(name){
  if(name === activeName) return;
  activeName = name;
  if(basePos){ recolor(); focusActive(); }
}
function selectAt(px, py){
  const hit = raycast(px, py);
  let idx = -1;
  if(hit) idx = groups.findIndex(g => hit.index >= g.i0 && hit.index < g.i1);
  if(idx === selected && hit) idx = -1;           // click again to deselect
  applySelection(idx);
}
// cross-probe: 3D selection highlights the matching ref on the sheets…
const probed = [];
function syncSheetHighlight(name){
  while(probed.length){ const [el, f, w] = probed.pop();
    el.setAttribute("fill", f); el.setAttribute("font-weight", w || ""); }
  if(!name) return;
  for(const t of document.querySelectorAll("#sheets svg text")){
    if(t.textContent.trim() === name){
      probed.push([t, t.getAttribute("fill"), t.getAttribute("font-weight")]);
      t.setAttribute("fill", "#f85149");
      t.setAttribute("font-weight", "bold");
    }
  }
}
// …and clicking a ref on a sheet selects its body in 3D
document.getElementById("sheets").addEventListener("click", e => {
  const t = e.target.closest("text");
  if(!t) return;
  const idx = groups.findIndex(g => g.name === t.textContent.trim());
  if(idx < 0) return;
  activeTab = "3d"; writeTabHash(); showTab(); renderTabs();
  applySelection(idx);
});

// -- exploded view: a display projection, never a model edit (ADR-0014) ------
function applyExplode(){
  const out = new Float32Array(basePos);
  if(explode > 0 && groups.length > 1){
    for(const g of groups){
      let d = sub3(g.centroid, modelCenter);
      const l = Math.hypot(...d);
      d = l < 1e-6 ? [0, 0, 1] : scl3(d, 1 / l);
      const off = scl3(d, explode * radius * 0.9);
      for(let v = g.v0; v <= g.v1; v++){
        out[3*v] += off[0]; out[3*v+1] += off[1]; out[3*v+2] += off[2];
      }
    }
  }
  meshPos = out;
  gl.bindBuffer(gl.ARRAY_BUFFER, vb);
  gl.bufferData(gl.ARRAY_BUFFER, out, gl.STATIC_DRAW);
  picks = []; updateMeasure();
}

function pick(px, py){
  const hit = raycast(px, py);
  if(!hit) return;
  const bestTri = hit.tri;
  let hitp = add3(hit.orig, scl3(hit.dir, hit.t));
  // vertex snap: nearest corner of the hit triangle within 4% of model radius
  let snap = null, snapD = radius * 0.04;
  for(const v of bestTri){
    const dd = Math.hypot(...sub3(v, hitp));
    if(dd < snapD){ snapD = dd; snap = v; }
  }
  if(snap) hitp = snap;
  picks.push(hitp);
  if(picks.length > 2) picks = [hitp];
  updateMeasure();
}
function updateMeasure(){
  const pts = [], cols = [];
  for(const p of picks){ pts.push(...p); cols.push(0.25, 0.95, 0.4); }
  gl.bindBuffer(gl.ARRAY_BUFFER, measVb);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(pts), gl.DYNAMIC_DRAW);
  gl.bindBuffer(gl.ARRAY_BUFFER, measCb);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(cols), gl.DYNAMIC_DRAW);
  if(picks.length === 2){
    const d = sub3(picks[1], picks[0]);
    measureHud.textContent =
      `dist ${Math.hypot(...d).toFixed(3)} mm\n` +
      `dx ${d[0].toFixed(3)}  dy ${d[1].toFixed(3)}  dz ${d[2].toFixed(3)}\n` +
      `A (${picks[0].map(v=>v.toFixed(2)).join(", ")})\n` +
      `B (${picks[1].map(v=>v.toFixed(2)).join(", ")})`;
  } else if(picks.length === 1){
    measureHud.textContent = `A (${picks[0].map(v=>v.toFixed(2)).join(", ")})\npick a second point`;
  } else {
    measureHud.textContent = measureMode ? "click a point to measure" : "";
  }
}

function draw(){
  stepTween(performance.now());
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if(canvas.width !== w || canvas.height !== h){ canvas.width = w; canvas.height = h; }
  gl.viewport(0, 0, w, h);
  gl.clearColor(0.051, 0.067, 0.09, 1);
  gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
  if(nIndices){
    const mvp = mul(perspective(0.8, w/h, radius*0.01, radius*40),
                    lookAt(eyePos(), center, [0,0,1]));
    gl.uniformMatrix4fv(uMvp, false, new Float32Array(mvp));
    gl.uniform1i(uFlat, 0);
    gl.bindVertexArray(vao);
    gl.drawElements(gl.TRIANGLES, nIndices, gl.UNSIGNED_INT, 0);
    if(picks.length){
      gl.disable(gl.DEPTH_TEST);
      gl.uniform1i(uFlat, 1);
      gl.bindVertexArray(measVao);
      gl.drawArrays(gl.POINTS, 0, picks.length);
      if(picks.length === 2) gl.drawArrays(gl.LINES, 0, 2);
      gl.enable(gl.DEPTH_TEST);
    }
  }
  requestAnimationFrame(draw);
}
requestAnimationFrame(draw);

let dragging = false, moved = false, px = 0, py = 0;
canvas.addEventListener("pointerdown", e => {
  dragging = true; moved = false; px = e.clientX; py = e.clientY; });
addEventListener("pointerup", e => {
  if(dragging && !moved && canvas.style.display !== "none" && e.target === canvas){
    if(measureMode) pick(e.clientX, e.clientY);
    else if(groups.length) selectAt(e.clientX, e.clientY);
  }
  dragging = false;
});
addEventListener("pointermove", e => {
  if(!dragging) return;
  if(Math.abs(e.clientX - px) + Math.abs(e.clientY - py) > 2){ moved = true; tween = null; }
  yaw -= (e.clientX - px) * 0.008;
  pitch = Math.max(-1.5, Math.min(1.5, pitch + (e.clientY - py) * 0.008));
  px = e.clientX; py = e.clientY;
});
addEventListener("wheel", e => { tween = null;
  dist = Math.max(0.35, Math.min(12, dist * (e.deltaY > 0 ? 1.1 : 0.9))); });
addEventListener("keydown", e => {
  if(e.key === "Escape"){ picks = []; updateMeasure(); }
  if(e.key === "z"){ zebraOn = !zebraOn; gl.uniform1i(uZebra, zebraOn ? 1 : 0); draw(); }
});

// -- tabs ---------------------------------------------------------------------
// ONE page, addressable: the active tab is a hash token (#checks, #review,
// #drawing,#activity,#sheets), composable with the older tokens (#x=0.6,
// #zebra) as "#checks,x=0.6". Switching tabs rewrites the hash; editing the
// hash switches tabs.
const tabsEl = document.getElementById("tabs");
const TABS = ["3d", "sheets", "checks", "review", "drawing", "activity"];
function hashTokens(){
  return location.hash.replace(/^#/, "").split(",").filter(Boolean);
}
let activeTab = hashTokens().find(t => TABS.includes(t)) || "3d", sheetCount = 0;
function writeTabHash(){
  const rest = hashTokens().filter(t => !TABS.includes(t));
  const toks = (activeTab === "3d" ? [] : [activeTab]).concat(rest);
  history.replaceState(null, "",
    toks.length ? "#" + toks.join(",") : location.pathname + location.search);
}
addEventListener("hashchange", () => {
  const t = hashTokens().find(x => TABS.includes(x)) || "3d";
  if(t !== activeTab){ activeTab = t; showTab(); renderTabs(); }
});
function renderTabs(){
  tabsEl.innerHTML = "";
  const mk = (id, label, cls) => {
    const t = document.createElement("div");
    t.className = "tab " + (cls || "") + (id === activeTab || (id === "measure" && measureMode) ? " on" : "");
    t.textContent = label;
    t.onclick = () => {
      if(id === "measure"){ measureMode = !measureMode; if(!measureMode){ picks = []; } updateMeasure(); }
      else { activeTab = id; writeTabHash(); showTab(); }
      renderTabs();
    };
    tabsEl.appendChild(t);
  };
  mk("3d", "3d");
  if(sheetCount) mk("sheets", `schematics (${sheetCount})`);
  if(checksState) mk("checks",
    checksState.ok ? "checks ✓" : `checks (${checksState.total_violations})`);
  if(reviewState) mk("review",
    reviewState.gate_ok ? "review ✓" : `review (${reviewState.summary.introduced})`);
  if(drawingAvail) mk("drawing", "drawing");
  mk("activity", "activity");
  if(activeTab === "3d") mk("measure", "measure", "tool");
}
function loadDrawing(){
  const v = version || "", el = document.getElementById("drawing");
  el.innerHTML = `<div class="dbar"><a href="/api/drawing.pdf?v=${v}" target="_blank">download PDF ⤓</a></div><div class="dwrap">loading drawing…</div>`;
  fetch(`/api/drawing.svg?v=${v}`).then(r => r.text()).then(svg => {
    el.querySelector(".dwrap").innerHTML = svg;      // inline SVG, one page
  }).catch(e => { el.querySelector(".dwrap").textContent = "drawing unavailable: " + e; });
}
function showTab(){
  document.getElementById("sheets").style.display = activeTab === "sheets" ? "block" : "none";
  document.getElementById("checks").style.display = activeTab === "checks" ? "block" : "none";
  document.getElementById("review").style.display = activeTab === "review" ? "block" : "none";
  document.getElementById("drawing").style.display = activeTab === "drawing" ? "block" : "none";
  document.getElementById("activity").style.display = activeTab === "activity" ? "block" : "none";
  if(activeTab === "drawing") loadDrawing();
  if(activeTab === "activity"){          // the tab replaces the rail, at once
    renderActivity();
    document.getElementById("live").style.display = "none";
  }
  const three = activeTab === "3d";
  canvas.style.display = three ? "block" : "none";
  hud.style.display = three ? "block" : "none";
  measureHud.style.display = three ? "block" : "none";
}
let checksState = null, reviewState = null, drawingAvail = false;
async function loadReview(baseRef){
  if(!baseRef){ reviewState = null; return; }
  try {
    reviewState = await (await fetch("/api/review")).json();
    if(reviewState.error) throw new Error(reviewState.error);
    const el = document.getElementById("review");
    el.innerHTML = "";
    const head = document.createElement("div");
    head.className = "rev";
    head.innerHTML = `<h3>review vs <code>${baseRef}</code> — ` +
      `<span class="${reviewState.gate_ok ? "good" : "bad"}">` +
      `${reviewState.gate_ok ? "gate PASS" : "gate FAIL"}</span> · ` +
      `${reviewState.summary.changed} file(s) · ` +
      `${reviewState.summary.introduced} introduced · ` +
      `${reviewState.summary.fixed} fixed</h3>`;
    el.appendChild(head);
    for(const f of reviewState.files){
      const card = document.createElement("div");
      card.className = "rev";
      let html = `<h3>${f.file} <small>(${f.kind}, ${f.status})</small></h3>`;
      for(const v of f.violations_introduced)
        html += `<div class="bad">introduced: ${v}</div>`;
      for(const v of f.violations_fixed)
        html += `<div class="good">fixed: ${v}</div>`;
      if(f.render_old || f.render_new){
        html += '<div class="sxs">' +
          `<div class="pane"><h4>base</h4>${f.render_old || ""}</div>` +
          `<div class="pane"><h4>head</h4>${f.render_new || ""}</div></div>`;
      }
      card.innerHTML = html;
      el.appendChild(card);
    }
    renderTabs();
  } catch(e){ reviewState = null; }
}
async function loadChecks(){
  try {
    checksState = await (await fetch("/api/checks")).json();
    if(checksState.error) throw new Error(checksState.error);
    const el = document.getElementById("checks");
    el.innerHTML = "";
    for(const r of checksState.results){
      const card = document.createElement("div");
      card.className = "chk";
      const h = document.createElement("h3");
      h.innerHTML = `${r.check} <span class="${r.ok ? "ok" : "bad"}">` +
        `${r.ok ? "✓ pass" : r.violations.length + " violation(s)"}</span>`;
      card.appendChild(h);
      if(!r.ok){
        const ul = document.createElement("ul");
        for(const v of r.violations.slice(0, 200)){
          const li = document.createElement("li");
          li.textContent = v;
          ul.appendChild(li);
        }
        card.appendChild(ul);
      }
      el.appendChild(card);
    }
    renderTabs();
  } catch(e){ checksState = null; }
}
async function loadSheets(){
  try {
    const data = await (await fetch("/api/schematics")).json();
    const sheets = data.sheets || [];
    sheetCount = sheets.length;
    const el = document.getElementById("sheets");
    el.innerHTML = "";
    for(const s of sheets){
      const name = document.createElement("div");
      name.className = "sheet-name"; name.textContent = s.name + "  (" + s.file + ")";
      el.appendChild(name);
      if(s.error){
        const e2 = document.createElement("div");
        e2.className = "sheet-err"; e2.textContent = s.error;
        el.appendChild(e2);
      } else {
        const card = document.createElement("div");
        card.className = "sheet-card"; card.innerHTML = s.svg;
        el.appendChild(card);
      }
    }
    renderTabs();
  } catch(e){ /* schematics are optional — the 3D view stands alone */ }
}

// -- live reload --------------------------------------------------------------
let version = null;
async function poll(){
  try {
    const v = await (await fetch("/api/version")).json();
    if(v.error) throw new Error(v.error);
    document.title = v.name + " — gitcad viewer";
    if(v.version !== version){
      version = v.version;
      err.textContent = "";
      drawingAvail = v.kind === "model";
      if(activeTab === "drawing") loadDrawing();
      renderTabs();
      if(v.kind === "board" || v.kind === "schematic"){
        const svg = await (await fetch("/api/board.svg")).text();
        document.getElementById("board").innerHTML = svg;
        document.getElementById("board").style.display = "flex";
        canvas.style.display = "none";
        hud.textContent = v.name;
      } else {
        const mesh = await (await fetch("/api/mesh")).json();
        if(mesh.error) throw new Error(mesh.error);
        upload(mesh);
        picks = []; updateMeasure();
        // explode slider only makes sense for multi-instance assemblies;
        // #x=0.6 deep-links an exploded state (a display projection —
        // the model text never changes, ADR-0014)
        const box = document.getElementById("explodebox");
        box.style.display = groups.length > 1 ? "flex" : "none";
        const m = location.hash.match(/x=([0-9.]+)/);
        explode = m ? Math.min(1, parseFloat(m[1])) : explode;
        document.getElementById("explodeslider").value = String(explode * 100);
        applyExplode();
        showTab();
      }
      loadSheets();
      loadChecks();
      loadReview(v.review_base);
    }
  } catch(e){ err.textContent = String(e); }
  setTimeout(poll, 1000);
}
document.getElementById("explodeslider").addEventListener("input", e => {
  explode = Number(e.target.value) / 100;
  applyExplode();
});

// -- the live rail: watch the agent work --------------------------------------
// Polled faster than the geometry, and independently: narration should arrive
// while a build is still running, not after it lands on disk.
const liveEl = document.getElementById("live");
const askEl = document.getElementById("ask");
let liveSeq = 0, liveLog = [], answering = null;
let lastActive = null, lastIdle = null;

function ago(t){
  const s = Math.max(0, Date.now() / 1000 - t);
  return s < 60 ? `${s | 0}s` : s < 3600 ? `${s / 60 | 0}m` : `${s / 3600 | 0}h`;
}
function renderLive(active, idle){
  // the activity tab IS the rail, expanded — no point showing both
  if(!liveLog.length || activeTab === "activity"){
    liveEl.style.display = "none"; return;
  }
  liveEl.style.display = "flex";
  // idle_s keeps the pulse honest: an agent that stopped narrating (crashed,
  // or moved on) must not look busy forever
  const stale = idle != null && idle > 120;
  const fol = `<span id="follow" class="${follow ? "on" : ""}"` +
              ` title="camera follows the part being worked on">follow</span>`;
  const head = active
    ? (stale
       ? `<div id="livehead" class="idle">idle ${ago(Date.now() / 1000 - idle)}` +
         ` — was on <b>${esc(active.instance || "the design")}</b>${fol}</div>`
       : `<div id="livehead"><span id="livedot"></span>working on ` +
         `<b>${esc(active.instance || "the design")}</b>${fol}</div>`)
    : "";
  liveEl.innerHTML = head + liveLog.slice(-9).map(e => {
    const cls = e.kind === "problem" ? "problem" : e.kind === "done" ? "done" : "";
    const who = e.instance ? `<span class="who">${esc(e.instance)}</span> ` : "";
    return `<div class="ev ${cls}">${who}${esc(e.text || e.kind)}` +
           `<span style="float:right;opacity:.6">${ago(e.t)}</span></div>`;
  }).join("");
}
liveEl.addEventListener("click", e => {
  if(e.target.id !== "follow") return;
  follow = !follow;
  if(follow) focusActive(); else tween = null;
  renderLive(lastActive, lastIdle);
});
function esc(s){
  return String(s == null ? "" : s).replace(/[&<>"]/g,
    c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
}
function renderAsk(q){
  if(!q || answering === q.id){ askEl.style.display = "none"; return; }
  askEl.style.display = "block";
  askEl.querySelector(".q").textContent = q.text || "";
  const opts = askEl.querySelector(".opts");
  opts.innerHTML = "";
  const send = async choice => {
    answering = q.id; askEl.style.display = "none";
    await fetch("/api/answer", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({id: q.id, choice: String(choice)})});
  };
  for(const o of (q.options || [])){
    const b = document.createElement("button");
    b.textContent = o; b.onclick = () => send(o);
    opts.appendChild(b);
  }
  if(!(q.options || []).length){       // free-text question
    const inp = document.createElement("input");
    inp.placeholder = "type an answer, then Enter";
    inp.onkeydown = e => { if(e.key === "Enter" && inp.value.trim())
                             send(inp.value.trim()); };
    opts.appendChild(inp);
    setTimeout(() => inp.focus(), 0);
  }
}
async function pollLive(){
  try {
    // since=0 on the first poll: a viewer opened mid-build replays the whole
    // session before tailing it — catching up is the same code as watching
    const s = await (await fetch("/api/activity?since=" + liveSeq)).json();
    if(s.events && s.events.length){
      liveLog = liveLog.concat(s.events).slice(-1000);
      liveSeq = s.seq;
      if(activeTab === "activity") renderActivity();
    }
    lastActive = s.active; lastIdle = s.idle_s;
    setActive(s.active ? s.active.instance : null);
    renderLive(s.active, s.idle_s);
    renderAsk(s.pending);
  } catch(e){ /* the log is optional; the viewer stands alone without it */ }
  setTimeout(pollLive, 500);
}

// -- the activity tab: the whole build story, scrubbable ----------------------
// The rail shows the last few seconds; this tab is the full session — every
// event, timestamped, newest at the bottom. Clicking an event that names an
// assembly instance jumps to that part in 3D: point at a line of history and
// see what it touched.
const actEl = document.getElementById("activity");
function actText(e){
  if(e.kind === "answer") return "answered: " + (e.choice || "");
  let t = e.text || e.kind;
  if(e.kind === "question" && (e.options || []).length)
    t += "  [" + e.options.join(" / ") + "]";
  return t;
}
function renderActivity(){
  if(!liveLog.length){
    actEl.innerHTML = '<div id="actempty">no activity yet — narration lands ' +
      'here while an agent works on this design</div>';
    return;
  }
  const stick = actEl.scrollTop + actEl.clientHeight >= actEl.scrollHeight - 40;
  actEl.innerHTML = liveLog.map(e => {
    const cls = e.kind === "status" ? "" : esc(e.kind);
    const canJump = e.instance && groups.some(g => g.name === e.instance);
    const who = e.instance ? `<span class="who">${esc(e.instance)}</span>` : "";
    const hms = new Date((e.t || 0) * 1000).toLocaleTimeString();
    return `<div class="act ${cls}${canJump ? " click" : ""}"` +
           `${e.instance ? ` data-inst="${esc(e.instance)}"` : ""}>` +
           `<time>${hms}</time>${who}<span>${esc(actText(e))}</span></div>`;
  }).join("");
  if(stick) actEl.scrollTop = actEl.scrollHeight;
}
actEl.addEventListener("click", e => {
  const row = e.target.closest(".act");
  if(!row || !row.dataset.inst) return;
  const idx = groups.findIndex(g => g.name === row.dataset.inst);
  if(idx < 0) return;
  activeTab = "3d"; writeTabHash(); showTab(); renderTabs();
  applySelection(idx);
  frameGroup(groups[idx]);
});

renderTabs();
poll();
pollLive();
</script></body></html>
"""
