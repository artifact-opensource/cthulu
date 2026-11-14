// The Eye: a living canvas whose four outer arcs are the agent's loop phases.
const TAU = Math.PI * 2;
const SEG = [
  { key: 'plan', label: 'Plan', a0: Math.PI * 1.0, a1: Math.PI * 1.5, lx: -0.62, ly: -0.68 },
  { key: 'reason', label: 'Reason', a0: Math.PI * 1.5, a1: Math.PI * 2.0, lx: 0.62, ly: -0.68 },
  { key: 'execute', label: 'Execute', a0: 0, a1: Math.PI * 0.5, lx: 0.62, ly: 0.74 },
  { key: 'reflect', label: 'Reflect', a0: Math.PI * 0.5, a1: Math.PI * 1.0, lx: -0.62, ly: 0.74 },
];
const PHASE_TO_SEG = { plan: 'plan', world: 'plan', reason: 'reason', adjust: 'reason', execute: 'execute', reflect: 'reflect', review: 'reflect', 'meta review': 'reflect' };
const COL = { lumen: [114, 240, 214], squid: [171, 150, 255], amber: [243, 201, 122], loss: [255, 115, 145], mist: [134, 168, 176], tide: [19, 53, 68], kelp: [36, 89, 106] };
const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;

export class Eye {
  constructor(canvas) {
    this.c = canvas; this.x = canvas.getContext('2d');
    this.reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.state = { phase: 'idle', busy: false, paused: false, halted: false, waiting: false };
    this.t = 0; this.busy = 0; this.lid = 0; this.blinkAt = -1; this.px = 0; this.py = 0; this.tx = 0; this.ty = 0;
    this.seg = {}; SEG.forEach((s) => (this.seg[s.key] = 0));
    this.motes = Array.from({ length: 30 }, () => ({ a: Math.random() * TAU, r: 0.3 + Math.random() * 0.2, s: 0.0004 + Math.random() * 0.0012, z: Math.random() }));
    this.raf = 0; this.last = 0; this.vis = true;
    this.onMove = (e) => {
      const r = this.c.getBoundingClientRect(); const p = e.touches ? e.touches[0] : e;
      this.tx = Math.max(-1, Math.min(1, ((p.clientX - r.left) / r.width - 0.5) * 2));
      this.ty = Math.max(-1, Math.min(1, ((p.clientY - r.top) / r.height - 0.5) * 2));
    };
    window.addEventListener('pointermove', this.onMove, { passive: true });
    this.io = new IntersectionObserver((e) => { this.vis = e[0].isIntersecting; if (this.vis) this.loop(); });
    this.io.observe(canvas);
    this.ro = new ResizeObserver(() => this.resize()); this.ro.observe(canvas);
    this.resize();
    this.loop();
  }
  destroy() { cancelAnimationFrame(this.raf); window.removeEventListener('pointermove', this.onMove); this.io.disconnect(); this.ro.disconnect(); }
  set(s) { Object.assign(this.state, s); if (this.reduced) this.draw(0); }
  blink() { this.blinkAt = this.t; }
  resize() {
    const d = Math.min(devicePixelRatio || 1, 2), r = this.c.getBoundingClientRect();
    this.W = Math.max(120, r.width); this.c.width = this.W * d; this.c.height = this.W * d; this.x.setTransform(d, 0, 0, d, 0, 0);
    if (this.reduced) this.draw(0);
  }
  loop() {
    if (this.reduced || !this.vis) return;
    cancelAnimationFrame(this.raf);
    this.raf = requestAnimationFrame((ts) => { const dt = Math.min(50, ts - (this.last || ts)); this.last = ts; this.draw(dt); this.loop(); });
  }
  tint() {
    const s = this.state;
    if (s.halted) return COL.loss; if (s.waiting) return COL.amber; if (s.paused) return COL.mist; return COL.lumen;
  }
  draw(dt) {
    const x = this.x, W = this.W, cx = W / 2, cy = W / 2, R = W * 0.3, s = this.state;
    this.t += dt;
    const t = this.t;
    const targetBusy = s.busy ? 1 : 0;
    this.busy += (targetBusy - this.busy) * Math.min(1, dt / 260);
    this.px += (this.tx - this.px) * Math.min(1, dt / 160); this.py += (this.ty - this.py) * Math.min(1, dt / 160);
    const active = PHASE_TO_SEG[s.phase];
    SEG.forEach((g) => { this.seg[g.key] += ((g.key === active ? 1 : 0) - this.seg[g.key]) * Math.min(1, dt / 220); });
    const tint = this.tint(), think = COL.squid;
    const dim = s.paused ? 0.45 : 1;
    x.clearRect(0, 0, W, W);

    // tendrils
    x.save(); x.translate(cx, cy); x.lineCap = 'round';
    for (let i = 0; i < 9; i++) {
      const a0 = (i / 9) * TAU + 0.3 + Math.sin(t * 0.0002 + i) * 0.08;
      x.beginPath();
      const amp = (0.012 + this.busy * 0.03) * W, wob = t * (0.0007 + this.busy * 0.0016) + i * 1.7;
      for (let k = 0; k <= 26; k++) {
        const u = k / 26, r = R * 1.14 + u * W * 0.16;
        const a = a0 + Math.sin(u * 5 + wob) * amp / r * 3;
        const px = Math.cos(a) * r, py = Math.sin(a) * r;
        k ? x.lineTo(px, py) : x.moveTo(px, py);
      }
      const g = x.createRadialGradient(0, 0, R * 1.1, 0, 0, W * 0.5);
      g.addColorStop(0, rgba(tint, 0.34 * dim)); g.addColorStop(1, rgba(tint, 0));
      x.strokeStyle = g; x.lineWidth = Math.max(1, W * 0.004); x.stroke();
    }
    x.restore();

    // motes
    this.motes.forEach((m) => {
      m.a += m.s * dt; const r = (m.r + Math.sin(t * 0.0004 + m.z * 9) * 0.015) * W * 1.55;
      const px = cx + Math.cos(m.a) * r, py = cy + Math.sin(m.a) * r * 0.92;
      x.fillStyle = rgba(think, (0.1 + m.z * 0.35) * dim * (0.5 + this.busy * 0.5)); x.beginPath(); x.arc(px, py, 0.8 + m.z * 1.6, 0, TAU); x.fill();
    });

    // phase arcs
    SEG.forEach((g) => {
      const v = this.seg[g.key], gap = 0.07;
      x.beginPath(); x.arc(cx, cy, R * 1.22, g.a0 + gap, g.a1 - gap);
      x.lineWidth = W * 0.016; x.lineCap = 'round';
      x.strokeStyle = rgba(COL.kelp, 0.55 - v * 0.2); x.stroke();
      if (v > 0.02) {
        x.save(); x.shadowColor = rgba(g.key === 'reason' ? think : tint, 0.9); x.shadowBlur = 16 * v;
        x.beginPath(); x.arc(cx, cy, R * 1.22, g.a0 + gap, g.a1 - gap);
        x.strokeStyle = rgba(g.key === 'reason' || g.key === 'plan' ? think : tint, 0.95 * v * dim); x.lineWidth = W * 0.016; x.stroke(); x.restore();
      }
      x.fillStyle = rgba(v > 0.4 ? COL.lumen : COL.mist, 0.55 + v * 0.45);
      x.font = `600 ${Math.max(10, W * 0.03)}px "Hanken Grotesk", system-ui, sans-serif`; x.textAlign = 'center'; x.textBaseline = 'middle';
      x.fillText(g.label, cx + g.lx * R * 1.5, cy + g.ly * R * 1.5);
    });

    // rotating dotted ring
    x.save(); x.translate(cx, cy); x.rotate(t * (0.00005 + this.busy * 0.0004));
    x.setLineDash([2, 9]); x.lineWidth = 1.4; x.strokeStyle = rgba(COL.mist, 0.35 * dim); x.beginPath(); x.arc(0, 0, R * 1.07, 0, TAU); x.stroke(); x.restore();

    // eyelid clip (blink)
    let lid = 0;
    if (this.blinkAt >= 0) { const p = (t - this.blinkAt) / 420; lid = p < 1 ? Math.sin(p * Math.PI) : 0; if (p >= 1) this.blinkAt = -1; }
    else if (!this.reduced && Math.sin(t * 0.00031 + 1.7) > 0.9995) this.blinkAt = t;
    const open = 1 - lid * 0.96;
    x.save();
    x.beginPath(); x.ellipse(cx, cy, R * 1.02, R * 0.72 * open + 0.5, 0, 0, TAU); x.clip();

    // sclera / iris
    const bg = x.createRadialGradient(cx, cy, R * 0.1, cx, cy, R);
    bg.addColorStop(0, rgba(COL.kelp, 0.9)); bg.addColorStop(0.55, rgba(COL.tide, 1)); bg.addColorStop(1, 'rgba(6,24,32,1)');
    x.fillStyle = bg; x.fillRect(cx - R * 1.1, cy - R, R * 2.2, R * 2);
    const ix = cx + this.px * R * 0.1, iy = cy + this.py * R * 0.07;
    x.save(); x.translate(ix, iy); x.rotate(t * 0.00004);
    for (let i = 0; i < 110; i++) {
      const a = (i / 110) * TAU, r1 = R * 0.26, r2 = R * (0.52 + 0.28 * ((Math.sin(i * 12.9898) * 43758.5453) % 1 + 1) % 1);
      x.strokeStyle = rgba(i % 5 === 0 ? think : tint, (0.05 + 0.2 * (i % 7) / 7) * dim * (0.7 + this.busy * 0.5)); x.lineWidth = 1;
      x.beginPath(); x.moveTo(Math.cos(a) * r1, Math.sin(a) * r1); x.lineTo(Math.cos(a) * r2, Math.sin(a) * r2); x.stroke();
    }
    x.restore();
    const ring = x.createRadialGradient(ix, iy, R * 0.5, ix, iy, R * 0.82);
    ring.addColorStop(0, 'rgba(0,0,0,0)'); ring.addColorStop(1, rgba(tint, 0.2 * dim)); x.fillStyle = ring; x.beginPath(); x.arc(ix, iy, R * 0.82, 0, TAU); x.fill();

    // pupil (slit that dilates while thinking)
    const w = R * (0.1 + this.busy * 0.2 + Math.sin(t * 0.0013) * 0.012), h = R * 0.58;
    const pg = x.createRadialGradient(ix, iy, 0, ix, iy, h);
    pg.addColorStop(0, '#010508'); pg.addColorStop(0.8, '#02090e'); pg.addColorStop(1, 'rgba(2,9,14,0.9)');
    x.fillStyle = pg; x.beginPath(); x.ellipse(ix + this.px * R * 0.05, iy + this.py * R * 0.04, w, h, 0, 0, TAU); x.fill();
    x.strokeStyle = rgba(tint, 0.5 * dim); x.lineWidth = 1.3; x.stroke();
    x.fillStyle = rgba([255, 255, 255], 0.55 * dim); x.beginPath(); x.ellipse(ix - w * 0.35 + this.px * R * 0.05, iy - h * 0.38, w * 0.2, h * 0.09, 0, 0, TAU); x.fill();
    x.restore();

    // lid edge
    x.beginPath(); x.ellipse(cx, cy, R * 1.02, R * 0.72 * open + 0.5, 0, 0, TAU);
    x.strokeStyle = rgba(tint, 0.75 * dim); x.lineWidth = Math.max(1.5, W * 0.006); x.stroke();
  }
}
