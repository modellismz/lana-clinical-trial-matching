// Force layout for the patient map, off the main thread.
// Similar patients are linked (pipeline/build_patient_map.py); links pull, every node pushes its neighbours
// away, a coarse far-field keeps unrelated clusters apart, and a weak gravity holds the whole web together.
// Deterministic: a seeded PRNG and a fixed tick count give the same picture on every load.

let N = 0, x, y, vx, vy, ea, eb, ew, el, es, ebias, deg, gid;
let tick = 0, ticks = 320, alive = false;

function prng(seed) {
  let s = seed >>> 0;
  return () => { s = (s + 0x6d2b79f5) >>> 0; let t = s; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

self.onmessage = (e) => {
  const m = e.data;
  if (m.type === 'init') init(m);
  else if (m.type === 'stop') alive = false;
};

function init({ nodes, edges, groups, seed = 7, nTicks = 320 }) {
  N = nodes.length;
  ticks = nTicks;
  x = new Float32Array(N); y = new Float32Array(N); vx = new Float32Array(N); vy = new Float32Array(N);
  gid = new Int16Array(N);
  const rnd = prng(seed);
  // seed each node near an anchor for its biomarker group, with a wide scatter: the anchors only fix the
  // orientation of the picture; the links decide where everything ends up.
  const G = groups;
  for (let i = 0; i < N; i++) {
    const g = nodes[i];
    gid[i] = g;
    const a = (g / G) * Math.PI * 2 - Math.PI / 2;
    const r = 260 * Math.sqrt(rnd());
    const t = rnd() * Math.PI * 2;
    x[i] = Math.cos(a) * 240 + Math.cos(t) * r;
    y[i] = Math.sin(a) * 240 + Math.sin(t) * r;
  }
  const E = edges.length;
  ea = new Int32Array(E); eb = new Int32Array(E); ew = new Float32Array(E); el = new Float32Array(E); es = new Float32Array(E); ebias = new Float32Array(E);
  deg = new Int32Array(N);
  for (let k = 0; k < E; k++) { deg[edges[k][0]]++; deg[edges[k][1]]++; }
  for (let k = 0; k < E; k++) {
    const a = edges[k][0], b = edges[k][1];
    ea[k] = a; eb[k] = b; ew[k] = edges[k][2];
    el[k] = 6 + (1 - ew[k]) * 60; // identical patients sit together; a 0.4 link rests ~42 units apart
    es[k] = (0.35 + 0.65 * ew[k]) / Math.min(deg[a], deg[b]); // d3-style: a well-connected node is not torn apart by its links
    ebias[k] = deg[a] / (deg[a] + deg[b]);
  }
  tick = 0;
  alive = true;
  run();
}

function run() {
  if (!alive) return;
  const batch = 2;
  for (let b = 0; b < batch && tick < ticks; b++) step();
  self.postMessage({ type: 'pos', x, y, tick, ticks, done: tick >= ticks });
  if (tick < ticks) setTimeout(run, 0);
  else alive = false;
}

const R = 18;           // local repulsion radius (layout units)
const COARSE = 14;      // far-field grid, COARSE × COARSE cells over the current bounds
const cnt = new Float32Array(COARSE * COARSE), cx = new Float32Array(COARSE * COARSE), cy = new Float32Array(COARSE * COARSE);

function step() {
  const alpha = Math.max(0.02, 1 - tick / ticks) ** 1.4; // cools from 1 to ~0
  const E = ea.length;
  // --- links: springs toward their rest length ---------------------------------------------------
  for (let k = 0; k < E; k++) {
    const a = ea[k], b = eb[k];
    let dx = x[b] - x[a], dy = y[b] - y[a];
    let d = Math.sqrt(dx * dx + dy * dy) || 1e-3;
    const f = (d - el[k]) / d * 0.6 * es[k] * alpha;
    dx *= f; dy *= f;
    const ba = ebias[k], bb = 1 - ba;
    vx[a] += dx * bb; vy[a] += dy * bb; vx[b] -= dx * ba; vy[b] -= dy * ba;
  }
  // --- local repulsion: uniform grid of cell size R ---------------------------------------------
  let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
  for (let i = 0; i < N; i++) { if (x[i] < minx) minx = x[i]; if (x[i] > maxx) maxx = x[i]; if (y[i] < miny) miny = y[i]; if (y[i] > maxy) maxy = y[i]; }
  const gw = Math.ceil((maxx - minx) / R) + 1, gh = Math.ceil((maxy - miny) / R) + 1;
  const head = new Int32Array(gw * gh).fill(-1), next = new Int32Array(N), cell = new Int32Array(N);
  for (let i = 0; i < N; i++) {
    const c = Math.floor((x[i] - minx) / R) + Math.floor((y[i] - miny) / R) * gw;
    cell[i] = c; next[i] = head[c]; head[c] = i;
  }
  const rep = 1.6 * alpha;
  for (let i = 0; i < N; i++) {
    const ci = cell[i] % gw, cj = (cell[i] / gw) | 0;
    for (let dj = -1; dj <= 1; dj++) {
      const j2 = cj + dj; if (j2 < 0 || j2 >= gh) continue;
      for (let di = -1; di <= 1; di++) {
        const i2 = ci + di; if (i2 < 0 || i2 >= gw) continue;
        for (let k = head[i2 + j2 * gw]; k >= 0; k = next[k]) {
          if (k <= i) continue;
          let dx = x[k] - x[i], dy = y[k] - y[i];
          let d2 = dx * dx + dy * dy;
          if (d2 >= R * R) continue;
          if (d2 < 0.01) { dx = (i % 7 - 3) * 0.1 + 0.05; dy = (k % 5 - 2) * 0.1 + 0.05; d2 = dx * dx + dy * dy; }
          const d = Math.sqrt(d2);
          const f = rep * (1 - d / R) ** 2 / d;
          dx *= f; dy *= f;
          vx[i] -= dx; vy[i] -= dy; vx[k] += dx; vy[k] += dy;
        }
      }
    }
  }
  // --- far field: coarse cells repel every node (keeps unrelated clusters apart) ---------------------
  cnt.fill(0); cx.fill(0); cy.fill(0);
  const cw = (maxx - minx) / COARSE + 1e-3, ch = (maxy - miny) / COARSE + 1e-3;
  for (let i = 0; i < N; i++) {
    const c = Math.min(COARSE - 1, Math.floor((x[i] - minx) / cw)) + Math.min(COARSE - 1, Math.floor((y[i] - miny) / ch)) * COARSE;
    cnt[c]++; cx[c] += x[i]; cy[c] += y[i];
  }
  const far = 0.55 * alpha;
  const soft = Math.max(cw, ch) * 1.2;
  for (let c = 0; c < COARSE * COARSE; c++) if (cnt[c]) { cx[c] /= cnt[c]; cy[c] /= cnt[c]; }
  for (let i = 0; i < N; i++) {
    let fx = 0, fy = 0;
    for (let c = 0; c < COARSE * COARSE; c++) {
      const m = cnt[c]; if (!m) continue;
      const dx = x[i] - cx[c], dy = y[i] - cy[c];
      const d2 = dx * dx + dy * dy + soft * soft;
      const f = m / d2;
      fx += dx * f; fy += dy * f;
    }
    vx[i] += fx * far; vy[i] += fy * far;
  }
  // --- gravity, integrate ---------------------------------------------------------------------------
  const g = 0.02 * alpha;
  const vmax = 12;
  for (let i = 0; i < N; i++) {
    vx[i] -= x[i] * g; vy[i] -= y[i] * g;
    vx[i] *= 0.55; vy[i] *= 0.55;
    const v = Math.sqrt(vx[i] * vx[i] + vy[i] * vy[i]);
    if (!(v <= vmax)) { const k = v > vmax ? vmax / v : 0; vx[i] *= k; vy[i] *= k; } // clamp; also catches NaN
    x[i] += vx[i]; y[i] += vy[i];
  }
  tick++;
}
