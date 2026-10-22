// The patient map: every real cohort patient is one dot, linked to its most similar peers.
// Layout runs in js/graph-worker.js; this class draws it, fits the camera, and handles hover / zoom / pan.
export class PatientGraph {
  constructor(canvas, data, { onHover, onSelect, onProgress } = {}) {
    this.cv = canvas;
    this.ctx = canvas.getContext('2d');
    this.data = data;
    this.N = data.nodes.length;
    this.edges = data.edges;
    this.onHover = onHover || (() => {});
    this.onSelect = onSelect || (() => {});
    this.onProgress = onProgress || (() => {});
    this.x = new Float32Array(this.N);
    this.y = new Float32Array(this.N);
    this.color = new Array(this.N).fill('#8794a8');
    this.key = new Int16Array(this.N); // legend key per node for the active colour mode
    this.isolate = null;               // legend key to isolate, or null
    this.hover = -1;
    this.selected = -1;
    this.pinned = -1;                  // the patient open in the rest of the app (pulsing ring)
    this.settled = false;
    this.cam = { s: 1, tx: 0, ty: 0 }; // world -> screen: sx = x*s + tx
    this.userCam = false;
    this.adj = this.adjacency();
    this.t0 = performance.now();
    this.reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.bindPointer();
    new ResizeObserver(() => { this.resize(); this.fit(true); this.draw(); }).observe(canvas);
    this.resize();
    this.startWorker();
  }

  adjacency() {
    const adj = Array.from({ length: this.N }, () => []);
    this.edges.forEach(([a, b], k) => { adj[a].push(k); adj[b].push(k); });
    return adj;
  }

  startWorker() {
    this.worker = new Worker(new URL('./graph-worker.js', import.meta.url));
    this.worker.onmessage = (e) => {
      const m = e.data;
      if (m.type !== 'pos') return;
      this.x = m.x; this.y = m.y;
      if (!this.userCam) this.fit(!this.settled && m.tick > 1);
      this.settled = m.done;
      this.onProgress(m.tick / m.ticks, m.done);
      this.draw();
      if (m.done) this.worker.terminate();
    };
    const gi = this.data.columns.indexOf('group');
    this.worker.postMessage({ type: 'init', nodes: this.data.nodes.map((n) => n[gi]), edges: this.edges, groups: this.data.groups.length, seed: 7, nTicks: 320 });
  }

  resize() {
    const r = this.cv.getBoundingClientRect();
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    this.w = r.width; this.h = r.height;
    this.cv.width = Math.round(r.width * dpr);
    this.cv.height = Math.round(r.height * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  /* ---------- camera ---------- */
  fit(smooth) {
    if (!this.N || !this.w) return;
    let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
    const { x, y } = this;
    for (let i = 0; i < this.N; i++) { if (x[i] < minx) minx = x[i]; if (x[i] > maxx) maxx = x[i]; if (y[i] < miny) miny = y[i]; if (y[i] > maxy) maxy = y[i]; }
    const pad = 36;
    const s = Math.min((this.w - pad * 2) / Math.max(1, maxx - minx), (this.h - pad * 2) / Math.max(1, maxy - miny));
    const tx = this.w / 2 - ((minx + maxx) / 2) * s;
    const ty = this.h / 2 - ((miny + maxy) / 2) * s;
    if (smooth && !this.reduced) {
      const k = 0.18;
      this.cam.s += (s - this.cam.s) * k; this.cam.tx += (tx - this.cam.tx) * k; this.cam.ty += (ty - this.cam.ty) * k;
    } else this.cam = { s, tx, ty };
    this.base = s;
  }

  resetCamera() { this.userCam = false; this.fit(false); this.draw(); }
  toScreen(i) { return [this.x[i] * this.cam.s + this.cam.tx, this.y[i] * this.cam.s + this.cam.ty]; }

  bindPointer() {
    const cv = this.cv;
    let drag = null;
    cv.addEventListener('pointerdown', (e) => { drag = { x: e.clientX, y: e.clientY, tx: this.cam.tx, ty: this.cam.ty, moved: false }; cv.setPointerCapture(e.pointerId); });
    cv.addEventListener('pointermove', (e) => {
      if (drag) {
        const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
        if (drag.moved) { this.cam.tx = drag.tx + dx; this.cam.ty = drag.ty + dy; this.userCam = true; this.draw(); }
        return;
      }
      const r = cv.getBoundingClientRect();
      const i = this.pick(e.clientX - r.left, e.clientY - r.top);
      if (i !== this.hover) { this.hover = i; this.draw(); }
      this.onHover(i >= 0 ? { i, x: e.clientX, y: e.clientY } : null);
    });
    cv.addEventListener('pointerup', (e) => {
      if (drag && !drag.moved) {
        const r = cv.getBoundingClientRect();
        const i = this.pick(e.clientX - r.left, e.clientY - r.top);
        this.selected = i;
        this.onSelect(i >= 0 ? i : null);
        this.draw();
      }
      drag = null;
    });
    cv.addEventListener('pointerleave', () => { if (this.hover >= 0) { this.hover = -1; this.draw(); } this.onHover(null); });
    cv.addEventListener('wheel', (e) => {
      e.preventDefault();
      const r = cv.getBoundingClientRect();
      const mx = e.clientX - r.left, my = e.clientY - r.top;
      const f = Math.exp(-e.deltaY * 0.0015);
      const s2 = Math.min(this.base * 14, Math.max(this.base * 0.6, this.cam.s * f));
      const k = s2 / this.cam.s;
      this.cam.tx = mx - (mx - this.cam.tx) * k; this.cam.ty = my - (my - this.cam.ty) * k; this.cam.s = s2;
      this.userCam = true;
      this.draw();
    }, { passive: false });
  }

  pick(mx, my) {
    const rad = Math.max(7, this.r() + 4);
    let best = -1, bd = rad * rad;
    const { x, y, cam } = this;
    for (let i = 0; i < this.N; i++) {
      const dx = x[i] * cam.s + cam.tx - mx, dy = y[i] * cam.s + cam.ty - my;
      const d = dx * dx + dy * dy;
      if (d < bd && this.visible(i)) { bd = d; best = i; }
    }
    return best;
  }

  /* ---------- styling ---------- */
  setColors(colors, keys) { this.color = colors; this.key = keys; this.isolate = null; this.baseKey = null; this.draw(); }
  setIsolate(k) { this.isolate = k; this.baseKey = null; this.draw(); }
  setPinned(i) { this.pinned = i; this.t0 = performance.now(); this.draw(); }
  visible(i) { return this.isolate == null || this.key[i] === this.isolate; }
  r() { return Math.min(6, 1.9 * Math.sqrt(Math.max(1, this.cam.s / (this.base || 1)))); }

  draw() {
    if (this.raf) return;
    this.raf = requestAnimationFrame(() => { this.raf = 0; this.paint(); });
  }

  // The static layer (links, dots, demo rings) is cached in an offscreen canvas and redrawn only when the
  // positions, camera, colours or isolation change; hover and pulse overlays are cheap on top of it.
  paintBase() {
    const key = `${this.cam.s},${this.cam.tx},${this.cam.ty},${this.w},${this.h},${this.settled},${this.isolate}`;
    if (this.baseKey === key && this.settled) return;
    this.baseKey = key;
    if (!this.off || this.off.width !== this.cv.width || this.off.height !== this.cv.height) {
      this.off = document.createElement('canvas');
      this.off.width = this.cv.width; this.off.height = this.cv.height;
    }
    const ctx = this.off.getContext('2d');
    const dpr = this.cv.width / this.w;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const { w, h, x, y, cam, N } = this;
    ctx.clearRect(0, 0, w, h);
    const r = this.r();
    ctx.lineWidth = Math.max(0.5, 0.5 * Math.sqrt(cam.s / (this.base || 1)));
    ctx.strokeStyle = 'rgba(150,170,200,0.2)';
    ctx.beginPath();
    for (let k = 0; k < this.edges.length; k++) {
      const [a, b] = this.edges[k];
      if (!this.visible(a) || !this.visible(b)) continue;
      ctx.moveTo(x[a] * cam.s + cam.tx, y[a] * cam.s + cam.ty);
      ctx.lineTo(x[b] * cam.s + cam.tx, y[b] * cam.s + cam.ty);
    }
    ctx.stroke();
    const dimAlpha = this.isolate != null ? 0.06 : 1;
    for (let i = 0; i < N; i++) {
      const sx = x[i] * cam.s + cam.tx, sy = y[i] * cam.s + cam.ty;
      if (sx < -8 || sy < -8 || sx > w + 8 || sy > h + 8) continue;
      ctx.globalAlpha = this.visible(i) ? 0.9 : dimAlpha;
      ctx.fillStyle = this.color[i];
      ctx.beginPath(); ctx.arc(sx, sy, r, 0, 6.283); ctx.fill();
    }
    ctx.globalAlpha = 1;
    const di = this.data.columns.indexOf('demo');
    ctx.lineWidth = 1.2;
    ctx.strokeStyle = 'rgba(244,239,230,0.9)';
    for (let i = 0; i < N; i++) {
      if (!this.data.nodes[i][di] || !this.visible(i)) continue;
      const sx = x[i] * cam.s + cam.tx, sy = y[i] * cam.s + cam.ty;
      ctx.beginPath(); ctx.arc(sx, sy, r + 2.6, 0, 6.283); ctx.stroke();
    }
  }

  paint() {
    this.paintBase();
    const { ctx, w, h, x, y, cam } = this;
    ctx.clearRect(0, 0, w, h);
    ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.drawImage(this.off, 0, 0); ctx.restore();
    const r = this.r();
    const focus = this.hover >= 0 ? this.hover : this.selected;
    const near = new Set();
    if (focus >= 0) this.adj[focus].forEach((k) => { const [a, b] = this.edges[k]; near.add(a === focus ? b : a); });
    if (focus >= 0) {
      ctx.fillStyle = 'rgba(10,14,20,0.42)'; // quieten the rest so the neighbourhood reads
      ctx.fillRect(0, 0, w, h);
      ctx.lineWidth = 1.2;
      this.adj[focus].forEach((k) => {
        const [a, b, wgt] = this.edges[k];
        const o = a === focus ? b : a;
        ctx.strokeStyle = `rgba(244,239,230,${0.25 + 0.6 * wgt})`;
        ctx.beginPath();
        ctx.moveTo(x[focus] * cam.s + cam.tx, y[focus] * cam.s + cam.ty);
        ctx.lineTo(x[o] * cam.s + cam.tx, y[o] * cam.s + cam.ty);
        ctx.stroke();
      });
      near.forEach((o) => {
        const sx = x[o] * cam.s + cam.tx, sy = y[o] * cam.s + cam.ty;
        ctx.fillStyle = this.color[o];
        ctx.beginPath(); ctx.arc(sx, sy, r + 1.4, 0, 6.283); ctx.fill();
        ctx.strokeStyle = 'rgba(244,239,230,0.7)'; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.arc(sx, sy, r + 2.4, 0, 6.283); ctx.stroke();
      });
      const [sx, sy] = this.toScreen(focus);
      const g = ctx.createRadialGradient(sx, sy, 0, sx, sy, 22);
      g.addColorStop(0, 'rgba(244,239,230,0.45)'); g.addColorStop(1, 'rgba(244,239,230,0)');
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(sx, sy, 22, 0, 6.283); ctx.fill();
      ctx.fillStyle = this.color[focus];
      ctx.beginPath(); ctx.arc(sx, sy, r + 2.5, 0, 6.283); ctx.fill();
      ctx.strokeStyle = '#f4efe6'; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(sx, sy, r + 5, 0, 6.283); ctx.stroke();
    }
    // the patient open in the app
    if (this.pinned >= 0 && this.visible(this.pinned)) {
      const [sx, sy] = this.toScreen(this.pinned);
      const pulse = this.reduced ? 0.5 : ((performance.now() - this.t0) / 1100) % 1;
      ctx.strokeStyle = `rgba(180,155,255,${0.9 * (1 - pulse)})`;
      ctx.lineWidth = 1.6;
      ctx.beginPath(); ctx.arc(sx, sy, r + 4 + pulse * 22, 0, 6.283); ctx.stroke();
      ctx.strokeStyle = '#b49bff'; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(sx, sy, r + 4, 0, 6.283); ctx.stroke();
      if (!this.reduced && this.settled) this.draw();
    }
  }
}
