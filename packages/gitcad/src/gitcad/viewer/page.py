"""The viewer page — one self-contained HTML string, zero external assets.

WebGL2 with flat shading via fragment-shader derivatives, orbit/zoom, live
reload by content-hash polling. Design review additions: a Schematics tab
(the electrical sheets underlying a 3D assembly, served by /api/schematics)
and a measure tool — raycast picking with vertex snap, two picks give
distance + per-axis deltas. Monospace dark aesthetic to match gitcad.xyz.
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
  #explodebox{position:fixed;right:12px;top:40px;display:none;align-items:center;
              gap:8px;color:var(--dim);z-index:5}
  #explodebox input{width:140px;accent-color:var(--acc)}
</style></head><body>
<canvas id="gl"></canvas><div id="board"></div><div id="sheets"></div>
<div id="tabs"></div>
<div id="explodebox"><span>explode</span>
  <input id="explodeslider" type="range" min="0" max="100" value="0"></div>
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
uniform bool flat_col;
void main(){
  if(flat_col){ color = vec4(vCol, 1.0); return; }
  vec3 n = normalize(cross(dFdx(vPos), dFdy(vPos)));
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
gl.enable(gl.DEPTH_TEST);

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
    groups.push({name: g.name, part: g.part, i0, i1, v0, v1,
                 centroid: [cx/n, cy/n, cz/n]});
    i0 = i1;
  }
  const [lo, hi] = mesh.bbox;
  center = [(lo[0]+hi[0])/2, (lo[1]+hi[1])/2, (lo[2]+hi[2])/2];
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
function selectAt(px, py){
  const hit = raycast(px, py);
  const before = selected;
  selected = -1;
  if(hit) selected = groups.findIndex(g => hit.index >= g.i0 && hit.index < g.i1);
  if(selected === before && hit) selected = -1;   // click again to deselect
  const cols = new Float32Array(baseCols);
  if(selected >= 0){
    const g = groups[selected];
    for(let v = g.v0; v <= g.v1; v++){
      cols[3*v] = Math.min(1, cols[3*v] * 0.5 + 0.55);
      cols[3*v+1] = Math.min(1, cols[3*v+1] * 0.5 + 0.45);
      cols[3*v+2] = Math.min(1, cols[3*v+2] * 0.3 + 0.1);
    }
    selHud.textContent = `selected: ${g.name}  (${g.part})\n` +
      `centroid (${g.centroid.map(v=>v.toFixed(1)).join(", ")}) · ` +
      `${(g.i1 - g.i0) / 3} tris · click again to deselect`;
  } else {
    selHud.textContent = "";
  }
  gl.bindBuffer(gl.ARRAY_BUFFER, cb);
  gl.bufferData(gl.ARRAY_BUFFER, cols, gl.STATIC_DRAW);
}

// -- exploded view: a display projection, never a model edit (ADR-0014) ------
function applyExplode(){
  const out = new Float32Array(basePos);
  if(explode > 0 && groups.length > 1){
    for(const g of groups){
      let d = sub3(g.centroid, center);
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
  if(Math.abs(e.clientX - px) + Math.abs(e.clientY - py) > 2) moved = true;
  yaw -= (e.clientX - px) * 0.008;
  pitch = Math.max(-1.5, Math.min(1.5, pitch + (e.clientY - py) * 0.008));
  px = e.clientX; py = e.clientY;
});
addEventListener("wheel", e => { dist = Math.max(1.2, Math.min(12, dist * (e.deltaY > 0 ? 1.1 : 0.9))); });
addEventListener("keydown", e => { if(e.key === "Escape"){ picks = []; updateMeasure(); } });

// -- tabs ---------------------------------------------------------------------
const tabsEl = document.getElementById("tabs");
let activeTab = location.hash === "#sheets" ? "sheets" : "3d", sheetCount = 0;
function renderTabs(){
  tabsEl.innerHTML = "";
  const mk = (id, label, cls) => {
    const t = document.createElement("div");
    t.className = "tab " + (cls || "") + (id === activeTab || (id === "measure" && measureMode) ? " on" : "");
    t.textContent = label;
    t.onclick = () => {
      if(id === "measure"){ measureMode = !measureMode; if(!measureMode){ picks = []; } updateMeasure(); }
      else { activeTab = id; showTab(); }
      renderTabs();
    };
    tabsEl.appendChild(t);
  };
  mk("3d", "3d");
  if(sheetCount) mk("sheets", `schematics (${sheetCount})`);
  if(activeTab === "3d") mk("measure", "measure", "tool");
}
function showTab(){
  document.getElementById("sheets").style.display = activeTab === "sheets" ? "block" : "none";
  const three = activeTab === "3d";
  canvas.style.display = three ? "block" : "none";
  hud.style.display = three ? "block" : "none";
  measureHud.style.display = three ? "block" : "none";
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
    }
  } catch(e){ err.textContent = String(e); }
  setTimeout(poll, 1000);
}
document.getElementById("explodeslider").addEventListener("input", e => {
  explode = Number(e.target.value) / 100;
  applyExplode();
});
renderTabs();
poll();
</script></body></html>
"""
