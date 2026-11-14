// Small canvas/SVG charts. Equity curve with hover, and sparklines.
const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

export function drawEquity(canvas, tipEl, series, opts = {}) {
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const d = Math.min(devicePixelRatio || 1, 2);
  const r = canvas.getBoundingClientRect();
  canvas.width = r.width * d; canvas.height = r.height * d;
  const x = canvas.getContext('2d'); x.setTransform(d, 0, 0, d, 0, 0);
  const W = r.width, H = r.height, padL = 8, padR = 64, padT = 14, padB = 24;
  const pts = (series || []).map((p) => ({ t: p.ts * 1000, v: p.equity }));
  const lumen = css('--lumen'), mist = css('--mist'), line = css('--line');
  const paint = (prog, hover) => {
    x.clearRect(0, 0, W, H);
    if (pts.length < 2) {
      x.fillStyle = mist; x.font = '14px "Hanken Grotesk", sans-serif'; x.textAlign = 'left'; x.fillText('Collecting equity history…', padL, H / 2);
      return;
    }
    let lo = Math.min(...pts.map((p) => p.v)), hi = Math.max(...pts.map((p) => p.v));
    if (hi - lo < 1e-9) { lo -= 1; hi += 1; }
    const pad = (hi - lo) * 0.12; lo -= pad; hi += pad;
    const t0 = pts[0].t, t1 = pts[pts.length - 1].t || t0 + 1;
    const X = (t) => padL + ((t - t0) / (t1 - t0 || 1)) * (W - padL - padR);
    const Y = (v) => padT + (1 - (v - lo) / (hi - lo)) * (H - padT - padB);
    x.strokeStyle = line; x.lineWidth = 1; x.fillStyle = mist; x.font = '12px "Hanken Grotesk", sans-serif'; x.textAlign = 'left'; x.textBaseline = 'middle';
    for (let i = 0; i < 4; i++) {
      const v = lo + ((hi - lo) * i) / 3, y = Y(v);
      x.globalAlpha = 0.5; x.beginPath(); x.moveTo(padL, y); x.lineTo(W - padR + 6, y); x.stroke(); x.globalAlpha = 1;
      const dec = hi - lo < 5 ? 2 : hi - lo < 50 ? 1 : 0;
      x.fillText(v >= 1e5 ? (v / 1000).toFixed(0) + 'k' : v.toLocaleString(undefined, { minimumFractionDigits: dec, maximumFractionDigits: dec }), W - padR + 10, y);
    }
    const n = Math.max(2, Math.floor(pts.length * prog));
    const g = x.createLinearGradient(0, padT, 0, H - padB);
    g.addColorStop(0, lumen + '55'); g.addColorStop(1, lumen + '00');
    x.beginPath(); pts.slice(0, n).forEach((p, i) => (i ? x.lineTo(X(p.t), Y(p.v)) : x.moveTo(X(p.t), Y(p.v))));
    const last = pts[n - 1];
    x.lineTo(X(last.t), H - padB); x.lineTo(X(t0), H - padB); x.closePath(); x.fillStyle = g; x.fill();
    x.beginPath(); pts.slice(0, n).forEach((p, i) => (i ? x.lineTo(X(p.t), Y(p.v)) : x.moveTo(X(p.t), Y(p.v))));
    x.strokeStyle = lumen; x.lineWidth = 2; x.lineJoin = 'round'; x.stroke();
    x.beginPath(); x.arc(X(last.t), Y(last.v), 4, 0, 6.3); x.fillStyle = lumen; x.fill();
    x.beginPath(); x.arc(X(last.t), Y(last.v), 8, 0, 6.3); x.strokeStyle = lumen + '55'; x.stroke();
    if (hover != null) {
      let best = pts[0]; pts.forEach((p) => { if (Math.abs(X(p.t) - hover) < Math.abs(X(best.t) - hover)) best = p; });
      x.strokeStyle = mist; x.globalAlpha = 0.6; x.beginPath(); x.moveTo(X(best.t), padT); x.lineTo(X(best.t), H - padB); x.stroke(); x.globalAlpha = 1;
      x.beginPath(); x.arc(X(best.t), Y(best.v), 5, 0, 6.3); x.fillStyle = css('--foam'); x.fill();
      if (tipEl) {
        tipEl.style.opacity = 1; tipEl.style.left = X(best.t) + 'px'; tipEl.style.top = Y(best.v) + 'px';
        tipEl.textContent = (opts.fmt ? opts.fmt(best.v) : best.v.toFixed(2)) + '  ·  ' + new Date(best.t).toLocaleString([], { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' });
      }
    } else if (tipEl) tipEl.style.opacity = 0;
  };
  let hoverX = null, raf = 0;
  const redraw = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(() => paint(1, hoverX)); };
  canvas.onpointermove = (e) => { hoverX = e.clientX - canvas.getBoundingClientRect().left; redraw(); };
  canvas.onpointerleave = () => { hoverX = null; redraw(); };
  if (reduced || opts.noAnim) { paint(1, null); return; }
  const t0 = performance.now();
  const step = (ts) => { const p = Math.min(1, (ts - t0) / 800); paint(1 - Math.pow(1 - p, 3), hoverX); if (p < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
}

export function sparkPath(candles, w = 220, h = 34) {
  if (!candles || candles.length < 2) return '';
  const v = candles.map((c) => c[4]); const lo = Math.min(...v), hi = Math.max(...v), rng = hi - lo || 1;
  return v.map((p, i) => `${i ? 'L' : 'M'}${((i / (v.length - 1)) * w).toFixed(1)},${(h - 3 - ((p - lo) / rng) * (h - 6)).toFixed(1)}`).join(' ');
}
