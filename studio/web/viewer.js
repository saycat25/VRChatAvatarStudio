/* Visualizador 3D mínimo em WebGL (sem dependências). Convenção Unity: Y para cima, avatar olha para +Z. */
"use strict";

const Mat = {
  mul(a, b) {
    const o = new Float32Array(16);
    for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) {
      let s = 0;
      for (let k = 0; k < 4; k++) s += a[k * 4 + r] * b[c * 4 + k];
      o[c * 4 + r] = s;
    }
    return o;
  },
  perspective(fovy, aspect, near, far) {
    const f = 1 / Math.tan(fovy / 2), o = new Float32Array(16);
    o[0] = f / aspect; o[5] = f; o[10] = (far + near) / (near - far); o[11] = -1; o[14] = 2 * far * near / (near - far);
    return o;
  },
  lookAt(e, t, up) {
    const n = (v) => { const l = Math.hypot(v[0], v[1], v[2]) || 1; return [v[0] / l, v[1] / l, v[2] / l]; };
    const cr = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
    const z = n([e[0] - t[0], e[1] - t[1], e[2] - t[2]]), x = n(cr(up, z)), y = cr(z, x);
    return new Float32Array([x[0], y[0], z[0], 0, x[1], y[1], z[1], 0, x[2], y[2], z[2], 0,
      -(x[0] * e[0] + x[1] * e[1] + x[2] * e[2]), -(y[0] * e[0] + y[1] * e[1] + y[2] * e[2]),
      -(z[0] * e[0] + z[1] * e[1] + z[2] * e[2]), 1]);
  },
};

function b64bytes(s) {
  const bin = atob(s), u = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
  return u;
}
const f32 = (s) => { const u = b64bytes(s); return new Float32Array(u.buffer, 0, u.byteLength >> 2); };
const u32 = (s) => { const u = b64bytes(s); return new Uint32Array(u.buffer, 0, u.byteLength >> 2); };
const u16 = (s) => { const u = b64bytes(s); return new Uint16Array(u.buffer, 0, u.byteLength >> 1); };

const VS = `
attribute vec3 aPos; attribute vec3 aNrm; attribute vec3 aCol;
uniform mat4 uVP; uniform mat4 uView;
varying vec3 vCol; varying vec3 vN;
void main() {
  vec3 p = vec3(aPos.x, aPos.y, -aPos.z);
  vN = mat3(uView) * vec3(aNrm.x, aNrm.y, -aNrm.z);
  vCol = aCol;
  gl_Position = uVP * vec4(p, 1.0);
}`;
const FS = `
precision mediump float;
varying vec3 vCol; varying vec3 vN;
uniform float uFlat; uniform vec3 uFlatCol;
void main() {
  if (uFlat > 0.5) { gl_FragColor = vec4(uFlatCol, 1.0); return; }
  vec3 n = normalize(vN);
  // Z is mirrored for the viewer's camera convention, so correct outward normals.
  if (gl_FrontFacing) n = -n;
  vec3 l1 = normalize(vec3(0.35, 0.72, 0.70));
  vec3 l2 = normalize(vec3(-0.62, 0.18, 0.44));
  vec3 viewDir = vec3(0.0, 0.0, 1.0);
  float key = max(dot(n, l1), 0.0);
  float fill = max(dot(n, l2), 0.0);
  vec3 halfDir = normalize(l1 + viewDir);
  float spec = pow(max(dot(n, halfDir), 0.0), 30.0) * 0.14;
  float rim = pow(1.0 - max(dot(n, viewDir), 0.0), 2.0) * 0.16;
  float lit = 0.54 + 0.43 * key + 0.14 * fill + rim;
  vec3 color = vCol * lit + vec3(spec);
  gl_FragColor = vec4(min(color, vec3(1.0)), 1.0);
}`;

class Viewer {
  constructor(canvas) {
    this.canvas = canvas;
    const gl = this.gl = canvas.getContext("webgl", { antialias: true, alpha: false, preserveDrawingBuffer: true });
    if (!gl) throw new Error("WebGL indisponível neste navegador.");
    this.uint = gl.getExtension("OES_element_index_uint");
    this.prog = this._program(VS, FS);
    this.loc = {
      aPos: gl.getAttribLocation(this.prog, "aPos"), aNrm: gl.getAttribLocation(this.prog, "aNrm"),
      aCol: gl.getAttribLocation(this.prog, "aCol"), uVP: gl.getUniformLocation(this.prog, "uVP"),
      uView: gl.getUniformLocation(this.prog, "uView"), uFlat: gl.getUniformLocation(this.prog, "uFlat"),
      uFlatCol: gl.getUniformLocation(this.prog, "uFlatCol"),
    };
    this.meshes = []; this.hidden = new Set(); this.weights = {}; this.showBones = false; this.boneBuf = null;
    this.yaw = 0.45; this.pitch = 0.1; this.dist = 3.4; this.target = [0, 0.8, 0]; this.height = 1.5;
    this.dirty = true; this._bind();
    const loop = () => { if (this.dirty) { this.dirty = false; this._draw(); } requestAnimationFrame(loop); };
    requestAnimationFrame(loop);
  }

  _program(vs, fs) {
    const gl = this.gl, mk = (t, src) => {
      const s = gl.createShader(t); gl.shaderSource(s, src); gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
      return s;
    };
    const p = gl.createProgram();
    gl.attachShader(p, mk(gl.VERTEX_SHADER, vs)); gl.attachShader(p, mk(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    return p;
  }

  _buf(target, data, usage) {
    const gl = this.gl, b = gl.createBuffer();
    gl.bindBuffer(target, b); gl.bufferData(target, data, usage || gl.STATIC_DRAW);
    return b;
  }

  setModel(model, keepCamera) {
    const gl = this.gl;
    for (const m of this.meshes) {
      for (const k of ["bp", "bn", "bc", "bi"]) gl.deleteBuffer(m[k]);
    }
    this.meshes = model.meshes.map((m) => {
      const pos = f32(m.pos), col = b64bytes(m.col), colf = new Float32Array(col.length);
      for (let i = 0; i < col.length; i++) colf[i] = col[i] / 255;
      const idx = m.wide ? u32(m.idx) : u16(m.idx);
      const shapes = m.shapes.map((s) => ({ name: s.name, idx: u32(s.idx), d: f32(s.d) }));
      return {
        name: m.name, label: m.label, base: pos, cur: new Float32Array(pos), shapes,
        bp: this._buf(gl.ARRAY_BUFFER, pos, gl.DYNAMIC_DRAW), bn: this._buf(gl.ARRAY_BUFFER, f32(m.nrm)),
        bc: this._buf(gl.ARRAY_BUFFER, colf), bi: this._buf(gl.ELEMENT_ARRAY_BUFFER, idx),
        n: idx.length, type: m.wide ? gl.UNSIGNED_INT : gl.UNSIGNED_SHORT,
      };
    });
    if (this.boneBuf) gl.deleteBuffer(this.boneBuf);
    const bones = f32(model.bones);
    this.boneBuf = this._buf(gl.ARRAY_BUFFER, bones); this.boneVerts = bones.length / 3;
    this.height = model.height;
    if (!keepCamera) { this.target = [0, model.height * 0.52, 0]; this.dist = model.height * 2.6; }
    this._applyShapes(); this.dirty = true;
  }

  setHidden(name, hide) { hide ? this.hidden.add(name) : this.hidden.delete(name); this.dirty = true; }
  setBones(v) { this.showBones = v; this.dirty = true; }
  setWeights(w) { this.weights = w; this._applyShapes(); this.dirty = true; }

  _applyShapes() {
    const gl = this.gl;
    for (const m of this.meshes) {
      if (!m.shapes.length) continue;
      m.cur.set(m.base);
      let any = false;
      for (const s of m.shapes) {
        const w = this.weights[s.name] || 0;
        if (!w) continue;
        any = true;
        for (let i = 0; i < s.idx.length; i++) {
          const v = s.idx[i] * 3;
          m.cur[v] += s.d[i * 3] * w; m.cur[v + 1] += s.d[i * 3 + 1] * w; m.cur[v + 2] += s.d[i * 3 + 2] * w;
        }
      }
      gl.bindBuffer(gl.ARRAY_BUFFER, m.bp);
      gl.bufferSubData(gl.ARRAY_BUFFER, 0, any ? m.cur : m.base);
    }
  }

  view(name) {
    const v = { front: [0, 0.08], side: [Math.PI / 2, 0.08], back: [Math.PI, 0.08], three: [0.5, 0.12], top: [0.3, 1.2] }[name];
    if (v) { this.yaw = v[0]; this.pitch = v[1]; this.dirty = true; }
  }

  focusHead(on) {
    this.target = on ? [0, this.height * 0.9, 0] : [0, this.height * 0.52, 0];
    this.dist = on ? this.height * 0.85 : this.height * 2.6; this.dirty = true;
  }

  resetCamera() {
    this.target = [0, this.height * 0.52, 0];
    this.yaw = 0.5; this.pitch = 0.12; this.dist = this.height * 2.6; this.dirty = true;
  }

  _bind() {
    const c = this.canvas;
    const pointers = new Map();
    let drag = null, pinch = null;
    const midpoint = (a, b) => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
    const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y) || 1;
    const panBy = (dx, dy) => {
      const k = this.dist * 0.0016;
      this.target[0] += Math.cos(this.yaw) * dx * k;
      this.target[2] += -Math.sin(this.yaw) * dx * k;
      this.target[1] += dy * k;
    };
    c.addEventListener("contextmenu", (e) => e.preventDefault());
    c.addEventListener("pointerdown", (e) => {
      c.setPointerCapture(e.pointerId);
      const point = { x: e.clientX, y: e.clientY, pan: e.button === 2 || e.shiftKey };
      pointers.set(e.pointerId, point);
      if (pointers.size === 1) drag = { id: e.pointerId, x: point.x, y: point.y, pan: point.pan };
      else if (pointers.size === 2) {
        const pair = Array.from(pointers.values());
        pinch = { distance: distance(pair[0], pair[1]), mid: midpoint(pair[0], pair[1]) };
        drag = null;
      }
    });
    c.addEventListener("pointermove", (e) => {
      if (!pointers.has(e.pointerId)) return;
      const old = pointers.get(e.pointerId);
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY, pan: old.pan });
      if (pointers.size >= 2) {
        const pair = Array.from(pointers.values()).slice(0, 2);
        const nextDistance = distance(pair[0], pair[1]);
        const nextMid = midpoint(pair[0], pair[1]);
        if (pinch) {
          this.dist = Math.max(0.25, Math.min(8, this.dist * pinch.distance / nextDistance));
          panBy(nextMid.x - pinch.mid.x, nextMid.y - pinch.mid.y);
        }
        pinch = { distance: nextDistance, mid: nextMid };
      } else if (drag && drag.id === e.pointerId) {
        const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        drag.x = e.clientX; drag.y = e.clientY;
        if (drag.pan) panBy(dx, dy);
        else {
          this.yaw -= dx * 0.008;
          this.pitch = Math.max(-1.45, Math.min(1.45, this.pitch + dy * 0.006));
        }
      }
      this.dirty = true;
    });
    const end = (e) => {
      if (!pointers.has(e.pointerId)) return;
      pointers.delete(e.pointerId);
      if (pointers.size >= 2) {
        const pair = Array.from(pointers.values()).slice(0, 2);
        pinch = { distance: distance(pair[0], pair[1]), mid: midpoint(pair[0], pair[1]) };
        drag = null;
      } else if (pointers.size === 1) {
        const entry = Array.from(pointers.entries())[0];
        drag = { id: entry[0], x: entry[1].x, y: entry[1].y, pan: entry[1].pan };
        pinch = null;
      } else { drag = null; pinch = null; }
    };
    c.addEventListener("pointerup", end); c.addEventListener("pointercancel", end); c.addEventListener("lostpointercapture", end);
    c.addEventListener("wheel", (e) => {
      e.preventDefault();
      this.dist = Math.max(0.25, Math.min(8, this.dist * Math.exp(e.deltaY * 0.0011))); this.dirty = true;
    }, { passive: false });
    c.addEventListener("dblclick", () => { this.focusHead(false); this.view("three"); });
    new ResizeObserver(() => { this.dirty = true; }).observe(c);
  }

  _draw() {
    const gl = this.gl, c = this.canvas, dpr = window.devicePixelRatio || 1;
    const w = Math.max(2, Math.round(c.clientWidth * dpr)), h = Math.max(2, Math.round(c.clientHeight * dpr));
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    gl.viewport(0, 0, w, h);
    const dark = document.documentElement.dataset.theme === "dark";
    const bg = dark ? [0.105, 0.115, 0.15] : [0.9, 0.915, 0.95];
    gl.clearColor(bg[0], bg[1], bg[2], 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST);
    const cp = Math.cos(this.pitch), t = this.target;
    // posição em coordenadas Unity (z invertido no shader)
    const eye = [t[0] + this.dist * Math.sin(this.yaw) * cp, t[1] + this.dist * Math.sin(this.pitch),
      -(t[2] + this.dist * Math.cos(this.yaw) * cp)];
    const view = Mat.lookAt(eye, [t[0], t[1], -t[2]], [0, 1, 0]);
    const proj = Mat.perspective(0.62, w / h, 0.05, 40);
    gl.useProgram(this.prog);
    gl.uniformMatrix4fv(this.loc.uVP, false, Mat.mul(proj, view));
    gl.uniformMatrix4fv(this.loc.uView, false, view);
    gl.uniform1f(this.loc.uFlat, 0);
    const L = this.loc;
    gl.enableVertexAttribArray(L.aPos); gl.enableVertexAttribArray(L.aNrm); gl.enableVertexAttribArray(L.aCol);
    for (const m of this.meshes) {
      if (this.hidden.has(m.name)) continue;
      gl.bindBuffer(gl.ARRAY_BUFFER, m.bp); gl.vertexAttribPointer(L.aPos, 3, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, m.bn); gl.vertexAttribPointer(L.aNrm, 3, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, m.bc); gl.vertexAttribPointer(L.aCol, 3, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, m.bi);
      gl.drawElements(gl.TRIANGLES, m.n, m.type, 0);
    }
    if (this.showBones && this.boneBuf) {
      gl.disable(gl.DEPTH_TEST);
      gl.uniform1f(L.uFlat, 1); gl.uniform3f(L.uFlatCol, 1.0, 0.82, 0.2);
      gl.disableVertexAttribArray(L.aNrm); gl.disableVertexAttribArray(L.aCol);
      gl.vertexAttrib3f(L.aNrm, 0, 0, 1); gl.vertexAttrib3f(L.aCol, 1, 1, 1);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.boneBuf); gl.vertexAttribPointer(L.aPos, 3, gl.FLOAT, false, 0, 0);
      gl.drawArrays(gl.LINES, 0, this.boneVerts);
    }
  }

  png() { this._draw(); return this.canvas.toDataURL("image/png"); }
}
window.Viewer = Viewer;
