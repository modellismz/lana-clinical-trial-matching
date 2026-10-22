// Thailand province map: modelled patient pool per province (choropleth) and trial sites.
export class ThaiMap {
  constructor(canvas, data, onHover, onClick) {
    this.cv = canvas;
    this.ctx = canvas.getContext('2d');
    this.data = data;
    this.byKey = new Map(data.provinces.map((p) => [p.key, p]));
    this.onHover = onHover;
    this.onClick = onClick;
    this.key = 'mcrc';
    this.sites = [];
    this.highlight = new Set();
    this.selected = null;
    this.hover = null;
    const pts = data.geo.features.flatMap((f) => f.geometry.coordinates.flatMap((poly) => poly[0]));
    this.bounds = { x0: Math.min(...pts.map((p) => p[0])), x1: Math.max(...pts.map((p) => p[0])), y0: Math.min(...pts.map((p) => p[1])), y1: Math.max(...pts.map((p) => p[1])) };
    canvas.addEventListener('pointermove', (e) => this.move(e));
    canvas.addEventListener('pointerleave', () => { this.hover = null; this.onHover(null); this.draw(); });
    canvas.addEventListener('click', () => { if (this.hover) this.onClick(this.hover); });
    new ResizeObserver(() => { this.resize(); this.draw(); }).observe(canvas);
    this.resize();
  }

  resize() {
    const r = this.cv.getBoundingClientRect();
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    this.w = r.width; this.h = r.height;
    this.cv.width = Math.round(r.width * dpr);
    this.cv.height = Math.round(r.height * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const b = this.bounds;
    const cos = Math.cos(((b.y0 + b.y1) / 2) * Math.PI / 180);
    const pad = 14;
    const kx = (this.w - pad * 2) / ((b.x1 - b.x0) * cos);
    const ky = (this.h - pad * 2) / (b.y1 - b.y0);
    this.k = Math.min(kx, ky);
    this.cos = cos;
    this.ox = (this.w - (b.x1 - b.x0) * cos * this.k) / 2;
    this.oy = (this.h - (b.y1 - b.y0) * this.k) / 2;
  }

  px(lon, lat) {
    return [this.ox + (lon - this.bounds.x0) * this.cos * this.k, this.oy + (this.bounds.y1 - lat) * this.k];
  }

  set({ key, sites, highlight, selected }) {
    if (key) this.key = key;
    if (sites) this.sites = sites;
    if (highlight) this.highlight = highlight;
    if (selected !== undefined) this.selected = selected;
    this.draw();
  }

  path(feature) {
    const { ctx } = this;
    ctx.beginPath();
    feature.geometry.coordinates.forEach((poly) => {
      poly[0].forEach((c, i) => { const [x, y] = this.px(c[0], c[1]); if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y); });
      ctx.closePath();
    });
  }

  draw() {
    const { ctx, w, h } = this;
    ctx.clearRect(0, 0, w, h);
    const max = Math.max(...this.data.provinces.map((p) => p.est[this.key].n), 1);
    this.data.geo.features.forEach((f) => {
      const p = this.byKey.get(f.properties.key);
      const n = p.est[this.key].n;
      const a = n ? 0.08 + 0.9 * Math.pow(n / max, 0.55) : 0.04;
      this.path(f);
      ctx.fillStyle = `rgba(255,181,71,${a.toFixed(3)})`;
      ctx.fill();
      const on = f.properties.key === this.hover || f.properties.key === this.selected;
      ctx.lineWidth = on ? 1.6 : 0.6;
      ctx.strokeStyle = on ? '#e6ebf2' : 'rgba(10,14,20,0.9)';
      ctx.stroke();
    });
    this.sites.forEach((s) => {
      if (s.lat == null) return;
      const [x, y] = this.px(s.lon, s.lat);
      const hl = this.highlight.has(s.facility);
      ctx.beginPath(); ctx.arc(x, y, hl ? 4 : 3, 0, 6.283);
      ctx.fillStyle = hl ? '#b49bff' : '#e6ebf2';
      ctx.fill();
      ctx.beginPath(); ctx.arc(x, y, hl ? 9 : 6.5, 0, 6.283);
      ctx.strokeStyle = hl ? '#b49bff' : 'rgba(230,235,242,0.7)';
      ctx.lineWidth = 1.4;
      ctx.stroke();
    });
  }

  hit(mx, my) {
    for (const f of this.data.geo.features) {
      for (const poly of f.geometry.coordinates) {
        const ring = poly[0];
        let inside = false;
        for (let i = 0, k = ring.length - 1; i < ring.length; k = i++) {
          const [xi, yi] = this.px(ring[i][0], ring[i][1]);
          const [xk, yk] = this.px(ring[k][0], ring[k][1]);
          if ((yi > my) !== (yk > my) && mx < ((xk - xi) * (my - yi)) / (yk - yi) + xi) inside = !inside;
        }
        if (inside) return f.properties.key;
      }
    }
    return null;
  }

  move(e) {
    const r = this.cv.getBoundingClientRect();
    const key = this.hit(e.clientX - r.left, e.clientY - r.top);
    if (key !== this.hover) { this.hover = key; this.draw(); }
    this.onHover(key ? { province: this.byKey.get(key), x: e.clientX, y: e.clientY } : null);
  }
}

export function km(a, b) {
  const R = 6371;
  const d2r = Math.PI / 180;
  const dLat = (b[0] - a[0]) * d2r;
  const dLon = (b[1] - a[1]) * d2r;
  const s = Math.sin(dLat / 2) ** 2 + Math.cos(a[0] * d2r) * Math.cos(b[0] * d2r) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}
