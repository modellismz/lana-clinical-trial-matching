// The embedding map: 1,073 real colorectal trials projected from 1,024 dimensions to 2 (UMAP).
export const CLUSTER_COLORS = ['#FFB547', '#55D6E8', '#FF7FA3', '#52E0A1', '#B49BFF', '#FF8E5E', '#7FB2FF', '#E8D96B', '#9FE870'];

export class EmbedMap {
  constructor(canvas, data, onHover) {
    this.cv = canvas;
    this.ctx = canvas.getContext('2d');
    this.trials = data.trials;
    this.clusters = data.clusters;
    this.onHover = onHover;
    this.patient = null;
    this.hits = new Map(); // nct -> rank
    this.hover = -1;
    this.focus = -1;
    this.t0 = performance.now();
    this.dim = new Set();
    canvas.addEventListener('pointermove', (e) => this.move(e));
    canvas.addEventListener('pointerleave', () => { this.hover = -1; this.onHover(null); });
    new ResizeObserver(() => this.resize()).observe(canvas);
    this.resize();
    this.loop = this.loop.bind(this);
    requestAnimationFrame(this.loop);
  }

  resize() {
    const r = this.cv.getBoundingClientRect();
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    this.w = r.width;
    this.h = r.height;
    this.cv.width = Math.round(r.width * dpr);
    this.cv.height = Math.round(r.height * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.pad = 34;
  }

  px(x, y) {
    return [this.pad + x * (this.w - this.pad * 2), this.pad + (1 - y) * (this.h - this.pad * 2)];
  }

  setPatient(xy, ranked) {
    this.patient = xy;
    this.hits = new Map(ranked.map((id, i) => [id, i]));
    this.t0 = performance.now();
  }

  setFocus(nct) {
    this.focus = nct ? this.trials.findIndex((t) => t.id === nct) : -1;
  }

  setCluster(c) {
    this.activeCluster = c;
  }

  move(e) {
    const r = this.cv.getBoundingClientRect();
    const mx = e.clientX - r.left;
    const my = e.clientY - r.top;
    let best = -1;
    let bd = 12 * 12;
    this.trials.forEach((t, i) => {
      const [x, y] = this.px(t.x, t.y);
      const d = (x - mx) ** 2 + (y - my) ** 2;
      if (d < bd) { bd = d; best = i; }
    });
    this.hover = best;
    this.onHover(best >= 0 ? { trial: this.trials[best], x: e.clientX, y: e.clientY } : null);
  }

  loop(now) {
    const { ctx, w, h } = this;
    ctx.clearRect(0, 0, w, h);
    const t = (now - this.t0) / 1000;
    // faint grid
    ctx.strokeStyle = 'rgba(120,140,170,0.07)';
    ctx.lineWidth = 1;
    for (let i = 1; i < 8; i++) {
      const gx = this.pad + (i / 8) * (w - this.pad * 2);
      const gy = this.pad + (i / 8) * (h - this.pad * 2);
      ctx.beginPath(); ctx.moveTo(gx, this.pad); ctx.lineTo(gx, h - this.pad); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(this.pad, gy); ctx.lineTo(w - this.pad, gy); ctx.stroke();
    }
    const pxy = this.patient ? this.px(this.patient[0], this.patient[1]) : null;
    // lines to ranked hits
    if (pxy) {
      const reveal = Math.min(1, t / 1.2);
      this.hits.forEach((rank, id) => {
        const i = this.trials.findIndex((q) => q.id === id);
        if (i < 0) return;
        const [x, y] = this.px(this.trials[i].x, this.trials[i].y);
        const a = Math.max(0, 0.55 - rank * 0.035) * reveal;
        const grad = ctx.createLinearGradient(pxy[0], pxy[1], x, y);
        grad.addColorStop(0, `rgba(180,155,255,${a})`);
        grad.addColorStop(1, `rgba(85,214,232,${a * 0.6})`);
        ctx.strokeStyle = grad;
        ctx.lineWidth = rank === 0 ? 1.6 : 1;
        ctx.beginPath();
        const mx = (pxy[0] + x) / 2 + (y - pxy[1]) * 0.12;
        const my = (pxy[1] + y) / 2 - (x - pxy[0]) * 0.12;
        ctx.moveTo(pxy[0], pxy[1]);
        ctx.quadraticCurveTo(mx, my, x, y);
        ctx.stroke();
      });
    }
    // trials
    this.trials.forEach((tr, i) => {
      const [x, y] = this.px(tr.x, tr.y);
      const hit = this.hits.has(tr.id);
      const c = CLUSTER_COLORS[tr.c % CLUSTER_COLORS.length];
      const dimmed = this.activeCluster != null && this.activeCluster !== tr.c;
      ctx.globalAlpha = dimmed ? 0.12 : hit ? 1 : 0.62;
      ctx.fillStyle = c;
      const r = hit ? 4.6 : i === this.hover ? 5 : 2.5;
      ctx.beginPath(); ctx.arc(x, y, r, 0, 6.283); ctx.fill();
      if (hit) {
        ctx.globalAlpha = 0.28;
        ctx.beginPath(); ctx.arc(x, y, 9, 0, 6.283); ctx.fill();
      }
      if (tr.th) {
        ctx.globalAlpha = 0.95;
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 1.4;
        ctx.beginPath(); ctx.arc(x, y, 7.5, 0, 6.283); ctx.stroke();
      }
      if (i === this.focus) {
        ctx.globalAlpha = 1;
        ctx.strokeStyle = '#B49BFF';
        ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(x, y, 12, 0, 6.283); ctx.stroke();
      }
    });
    ctx.globalAlpha = 1;
    // patient
    if (pxy) {
      const pulse = (t * 0.9) % 1;
      ctx.strokeStyle = `rgba(244,239,230,${0.55 * (1 - pulse)})`;
      ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(pxy[0], pxy[1], 8 + pulse * 28, 0, 6.283); ctx.stroke();
      const g = ctx.createRadialGradient(pxy[0], pxy[1], 0, pxy[0], pxy[1], 22);
      g.addColorStop(0, 'rgba(244,239,230,0.9)');
      g.addColorStop(1, 'rgba(244,239,230,0)');
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(pxy[0], pxy[1], 22, 0, 6.283); ctx.fill();
      ctx.fillStyle = '#F4EFE6';
      ctx.beginPath(); ctx.arc(pxy[0], pxy[1], 5, 0, 6.283); ctx.fill();
    }
    requestAnimationFrame(this.loop);
  }
}
