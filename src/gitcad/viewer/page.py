"""The viewer page — one self-contained HTML string, zero external assets.

~200 lines of WebGL2: indexed triangles, flat shading via fragment-shader
derivatives (no normals shipped), orbit/zoom controls, live reload by polling
the content hash. Boards short-circuit to the server-rendered SVG. Monospace
dark aesthetic to match gitcad.xyz.
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
  #hud{position:fixed;left:12px;bottom:10px;color:var(--dim);pointer-events:none;white-space:pre}
  #hud b{color:var(--ink)} #err{position:fixed;top:10px;left:12px;color:#f85149;white-space:pre-wrap}
  #logo{position:fixed;right:12px;top:10px;color:var(--acc);font-weight:700}
</style></head><body>
<canvas id="gl"></canvas><div id="board"></div>
<div id="hud"></div><div id="err"></div><div id="logo">gitcad</div>
<script>
"use strict";
const canvas = document.getElementById("gl");
const gl = canvas.getContext("webgl2", {antialias: true});
const hud = document.getElementById("hud"), err = document.getElementById("err");

const VS = `#version 300 es
in vec3 pos; in vec3 col; uniform mat4 mvp; out vec3 vPos; out vec3 vCol;
void main(){ vPos = pos; vCol = col; gl_Position = mvp * vec4(pos, 1.0); }`;
const FS = `#version 300 es
precision highp float; in vec3 vPos; in vec3 vCol; out vec4 color;
void main(){
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
gl.enable(gl.DEPTH_TEST);

let nIndices = 0, center = [0,0,0], radius = 50;
let yaw = 0.7, pitch = 0.5, dist = 3;   // dist in units of radius
const vao = gl.createVertexArray();

function upload(mesh){
  gl.bindVertexArray(vao);
  const vb = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, vb);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(mesh.positions), gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
  const nVerts = mesh.positions.length / 3;
  let cols = mesh.colors;
  if(!cols || cols.length !== mesh.positions.length){
    cols = new Array(mesh.positions.length);
    for(let i = 0; i < nVerts; i++){ cols[3*i] = 0.35; cols[3*i+1] = 0.62; cols[3*i+2] = 0.85; }
  }
  const cb = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, cb);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(cols), gl.STATIC_DRAW);
  gl.enableVertexAttribArray(1); gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 0, 0);
  const ib = gl.createBuffer();
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, ib);
  gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint32Array(mesh.indices), gl.STATIC_DRAW);
  nIndices = mesh.indices.length;
  const [lo, hi] = mesh.bbox;
  center = [(lo[0]+hi[0])/2, (lo[1]+hi[1])/2, (lo[2]+hi[2])/2];
  radius = Math.max(1e-6, Math.hypot(hi[0]-lo[0], hi[1]-lo[1], hi[2]-lo[2]) / 2);
  const s = mesh.stats;
  if(mesh.groups){
    const names = mesh.groups.map(g => `${g.name}(${g.part})`).join(" · ");
    hud.textContent = `assembly: ${names}\n${s.triangles} tris · kernel ${s.kernel} · drag orbit · wheel zoom`;
  } else {
    hud.textContent = `${s.features} features · ${s.triangles} tris · vol ${s.volume_mm3} mm³\n` +
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
const cross3=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const dot3=(a,b)=>a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
const norm3=a=>{const l=Math.hypot(...a)||1;return[a[0]/l,a[1]/l,a[2]/l];};

function draw(){
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if(canvas.width !== w || canvas.height !== h){ canvas.width = w; canvas.height = h; }
  gl.viewport(0, 0, w, h);
  gl.clearColor(0.051, 0.067, 0.09, 1);
  gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
  if(nIndices){
    const d = dist * radius;
    const eye = [center[0] + d*Math.cos(pitch)*Math.cos(yaw),
                 center[1] + d*Math.cos(pitch)*Math.sin(yaw),
                 center[2] + d*Math.sin(pitch)];
    const mvp = mul(perspective(0.8, w/h, radius*0.01, radius*40),
                    lookAt(eye, center, [0,0,1]));
    gl.uniformMatrix4fv(uMvp, false, new Float32Array(mvp));
    gl.bindVertexArray(vao);
    gl.drawElements(gl.TRIANGLES, nIndices, gl.UNSIGNED_INT, 0);
  }
  requestAnimationFrame(draw);
}
requestAnimationFrame(draw);

let dragging = false, px = 0, py = 0;
canvas.addEventListener("pointerdown", e => { dragging = true; px = e.clientX; py = e.clientY; });
addEventListener("pointerup", () => dragging = false);
addEventListener("pointermove", e => {
  if(!dragging) return;
  yaw -= (e.clientX - px) * 0.008;
  pitch = Math.max(-1.5, Math.min(1.5, pitch + (e.clientY - py) * 0.008));
  px = e.clientX; py = e.clientY;
});
addEventListener("wheel", e => { dist = Math.max(1.2, Math.min(12, dist * (e.deltaY > 0 ? 1.1 : 0.9))); });

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
      if(v.kind === "board"){
        const svg = await (await fetch("/api/board.svg")).text();
        document.getElementById("board").innerHTML = svg;
        document.getElementById("board").style.display = "flex";
        canvas.style.display = "none";
        hud.textContent = v.name;
      } else {
        const mesh = await (await fetch("/api/mesh")).json();
        if(mesh.error) throw new Error(mesh.error);
        upload(mesh);
        canvas.style.display = "block";
        document.getElementById("board").style.display = "none";
      }
    }
  } catch(e){ err.textContent = String(e); }
  setTimeout(poll, 1000);
}
poll();
</script></body></html>
"""
