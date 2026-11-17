import { api, openStream, onAuthNeeded, setToken } from './api.js';
import { Eye } from './eye.js';
import { drawEquity, sparkPath } from './charts.js';

const bootstrapToken = new URLSearchParams(location.hash.slice(1)).get('token');
if (bootstrapToken) {
  setToken(bootstrapToken);
  history.replaceState(null, '', location.pathname + location.search);
}

/* ------------------------------------------------------------------ safe html */
class Safe { constructor(s) { this.s = s; } toString() { return this.s; } }
const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ESC[c]);
const val = (v) => (v == null || v === false ? '' : v instanceof Safe ? v.s : Array.isArray(v) ? v.map(val).join('') : esc(v));
const html = (s, ...v) => new Safe(s.reduce((o, x, i) => o + x + (i < v.length ? val(v[i]) : ''), ''));
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const put = (el, h) => { if (el) el.innerHTML = val(h); };
const ic = (n, c = 'i') => html`<svg class="${c}" aria-hidden="true"><use href="#i-${n}"/></svg>`;

/* ------------------------------------------------------------------ formatting */
const num = (n, d = 2) => (n == null || Number.isNaN(+n) ? '–' : (+n).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }));
const sgn = (n, d = 2) => (n == null ? '–' : (n > 0 ? '+' : n < 0 ? '−' : '') + num(Math.abs(n), d));
const cls = (n) => (n > 0 ? 'gain' : n < 0 ? 'loss' : '');
const px = (n) => (n == null ? '–' : (+n >= 100 ? (+n).toFixed(2) : (+n).toFixed(5)));
const hhmm = (ts) => new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
const dayStr = (ts) => new Date(ts * 1000).toLocaleDateString([], { month: 'short', day: 'numeric' });
const rel = (ts) => { const s = Math.max(0, Date.now() / 1000 - ts); return s < 60 ? 'just now' : s < 3600 ? Math.round(s / 60) + ' min ago' : s < 86400 ? Math.round(s / 3600) + ' h ago' : dayStr(ts); };
const short = (s, n = 24) => (s && s.length > n ? s.slice(0, n - 1) + '…' : s || '');
const modelLabel = (model) => {
  const id = String(model || '').trim();
  const modelId = id.split('/').pop() || id;
  if (/ibm-granite/i.test(id) && /^granite-/i.test(modelId)) {
    const version = modelId.slice('granite-'.length).replace(/-/g, ' ').replace(/\bh micro$/i, 'H-Micro');
    return `IBM Granite ${version}`;
  }
  return modelId;
};

const KIND = {
  plan: ['Plan', 'M12 3l8 9-8 9-8-9z'], reason: ['Reasoning', 'M12 3c.7 4.6 3.4 7.3 8 8-4.6.7-7.3 3.4-8 8-.7-4.6-3.4-7.3-8-8 4.6-.7 7.3-3.4 8-8z'],
  action: ['Order', 'M13 3 5 13.5h6L10 21l9-11h-6z'], trade_open: ['Fill', 'M7 17 17 7M9 7h8v8'], trade_close: ['Closed', 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM8 12.5l3 3 5-6'],
  lesson: ['Lesson', 'M5 19c0-8 5-13 14-14 0 9-5 14-13 14M5 19c2-5 5-8 9-10'], reflection: ['Reflection', 'M5 19c0-8 5-13 14-14 0 9-5 14-13 14M5 19c2-5 5-8 9-10'],
  world: ['World', 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18'],
  system: ['System', 'M12 8v5M12 16.5v.5M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z'], user: ['You', 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4.5 20c1-4 4-5.5 7.5-5.5s6.5 1.5 7.5 5.5'],
};
const kicon = (k) => html`<span class="ic"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="${(KIND[k] || KIND.system)[1]}"/></svg></span>`;

/* ------------------------------------------------------------------ store */
const S = { state: null, config: null, killSwitchActive: false, equity: [], feed: [], live: false, route: 'overview', eye: null, llmBusy: false, chat: [], jf: { kind: 'all', q: '' }, jEntries: [], jMore: true, prov: null, models: {}, thinking: false };
const NAV = [['overview', 'Overview', 'overview'], ['loop', 'Loop', 'loop'], ['journal', 'Journal', 'journal'], ['playbook', 'Playbook', 'playbook'], ['chat', 'Chat', 'chat'], ['settings', 'Settings', 'settings']];
const shell = $('#shell');
const main = $('#main');

/* ------------------------------------------------------------------ toasts & modal */
function toast(msg, kind = '') {
  const t = document.createElement('div'); t.className = 'toast ' + kind; t.textContent = msg; $('#toasts').append(t);
  setTimeout(() => { t.style.opacity = 0; t.style.transition = 'opacity .3s'; setTimeout(() => t.remove(), 300); }, kind === 'bad' ? 6500 : 3800);
}
function paintLegacyAnalysis() {
  const box = $('#legacyAnalysis');
  if (!box || !S.state) return;
  const rows = Array.isArray(S.state.legacy_analysis) ? S.state.legacy_analysis : [];
  put(box, html`<div class="sec-h"><h2>Legacy engine analysis</h2><span class="mute small">${rows.length ? 'Shared directly from the running Cthulu engine' : 'Waiting for the Legacy loop'}</span></div>
    ${rows.length ? html`<div class="set-grid">${rows.map((row) => {
        const signal = row.signal && typeof row.signal === 'object' ? row.signal : {};
        const indicators = Object.entries(row.indicators || {}).slice(0, 12);
        return html`<div class="notes"><b>${row.symbol}</b>${row.agent_symbol && row.agent_symbol !== row.symbol ? html` <span class="chip">Agent: ${row.agent_symbol}</span>` : ''} <span class="chip">${row.timeframe}</span> <span class="chip">${row.regime}</span>
          <div class="small mute">${rel(row.updated_at)} · ${row.strategy}${row.score == null ? '' : ` · score ${num(row.score, 3)}`}</div>
          ${signal.direction || signal.side ? html`<div class="small">Signal: ${signal.direction || signal.side}${signal.confidence == null ? '' : ` · confidence ${num(signal.confidence)}`}${signal.confluence_score == null ? '' : ` · confluence ${num(signal.confluence_score, 1)}`}</div>` : ''}
          ${row.rejection ? html`<div class="small amber">${row.rejection}</div>` : ''}
          <div class="small mute">${indicators.map(([name, value]) => `${name} ${typeof value === 'number' ? num(value, 3) : String(value)}`).join(' · ')}</div></div>`;
      })}</div>` : html`<p class="mute">Legacy strategy signals, indicator readings and confluence results will appear here as soon as the engine completes an analysis cycle.</p>`}`);
}
function paintWorld() {
  const box = $('#worldBrief');
  if (!box || !S.state) return;
  const brief = S.state.world, status = S.state.world_status || {}, feeds = status.native_feeds || {};
  put(box, html`<div class="sec-h"><h2>World Brief</h2><span class="mute small">${brief?.ts ? `Updated ${rel(brief.ts)}` : status.enabled ? 'Waiting for first brief' : 'World feeds disabled'}</span></div>
    ${brief?.summary
      ? html`<p>${brief.summary}</p>
        ${(brief.themes || []).length ? html`<div class="set-grid">${brief.themes.slice(0, 5).map((theme) => html`<div class="notes"><b>${theme.theme || 'Market theme'}</b> <span class="chip">${theme.bias || 'neutral'}</span><div class="small mute">${theme.why || ''}</div></div>`)}</div>` : ''}
        ${(brief.event_risk || []).length ? html`<p class="small"><b>Event risks:</b> ${brief.event_risk.slice(0, 4).map((event) => `${event.what || 'Event'}${event.when ? ` (${event.when})` : ''}`).join(' · ')}</p>` : ''}
        ${brief.stand_down ? html`<p class="amber"><b>Stand-down:</b> avoid new entries while the current shock risk is active.</p>` : ''}`
      : html`<p class="mute">No brief is available yet. The agent will retry automatically.</p>`}
    <div class="set-grid">${Object.entries(feeds).map(([id, feed]) => {
      const data = feed.data || {};
      const value = id === 'coingecko_bitcoin'
        ? `${num(data.usd)} USD${data.change_24h_pct == null ? '' : ` · ${num(data.change_24h_pct)}% 24h`}`
        : data.value == null ? 'No cached observation' : `${num(data.value)}${data.date ? ` · ${data.date}` : ''}`;
      const statusClass = feed.status === 'ok' ? 'lumen' : ['stale', 'unavailable'].includes(feed.status) ? 'loss' : 'mute';
      const statusLabel = feed.status === 'unavailable' ? 'unavailable' : feed.status;
      return html`<div class="notes"><b>${id}</b> <span class="${statusClass}">${statusLabel}</span><div class="small">${value}</div><div class="small mute">${feed.description || ''}${feed.fetched_at ? ` · ${rel(feed.fetched_at)}` : ''}</div></div>`;
    })}</div>
    `);
}
const ask = (title, body, ok = 'Confirm', danger = false) => new Promise((res) => {
  const m = $('#modal'); m.hidden = false;
  put(m, html`<div class="modal" role="dialog" aria-modal="true" aria-labelledby="mt"><h2 id="mt">${title}</h2><p class="mute">${body}</p><div style="display:flex;gap:10px;justify-content:flex-end"><button class="btn" data-m="0">Cancel</button><button class="btn ${danger ? 'danger' : 'primary'}" data-m="1">${ok}</button></div></div>`);
  const done = (v) => { m.hidden = true; m.innerHTML = ''; res(v); };
  m.onclick = (e) => { const b = e.target.closest('[data-m]'); if (b) done(b.dataset.m === '1'); else if (e.target === m) done(false); };
  $('[data-m="1"]', m).focus();
});
onAuthNeeded(() => new Promise((res) => {
  const m = $('#modal'); m.hidden = false;
  put(m, html`<form class="modal" id="tokForm"><h2>Dashboard token</h2><p class="mute">This server asks for the DASHBOARD_TOKEN from your .env file.</p><input type="password" id="tokIn" placeholder="Token" autocomplete="current-password" required><button class="btn primary">Unlock</button></form>`);
  $('#tokIn').focus();
  $('#tokForm').onsubmit = (e) => { e.preventDefault(); setToken($('#tokIn').value.trim()); m.hidden = true; m.innerHTML = ''; res(); };
}));
const guard = async (fn, okMsg) => { try { const r = await fn(); if (okMsg) toast(okMsg, 'ok'); return r; } catch (e) { toast(e.message, 'bad'); return null; } };

/* ------------------------------------------------------------------ shell */
function paintShell() {
  const items = NAV.map(([id, label, icon]) => {
    const n = id === 'overview' ? (S.state?.proposals?.length || 0) : 0;
    return { id, label, icon, n };
  });
  const navItem = (i) => html`<a href="#${i.id}" ${S.route === i.id ? raw0('aria-current="page"') : ''}>${ic(i.icon)}<span>${i.label}</span>${i.n ? html`<span class="dot">${i.n}</span>` : ''}</a>`;
  put($('#nav'), items.map(navItem));
  put($('#tabbar'), html`${items.map(navItem)}${controlButtons('mobile-action')}`);
  paintRailFoot();
}
const raw0 = (s) => new Safe(s);
function controlButtons(className) {
  const st = S.state?.status;
  const paused = Boolean(st?.paused);
  const killSwitchActive = S.killSwitchActive || Boolean(S.config?.system?.kill_switch_active);
  return html`
    <button class="${className} ${paused ? 'paused' : ''}" type="button" data-act="pause"
      aria-label="${paused ? 'Resume trading agent' : 'Pause trading agent'}"
      title="${paused ? 'Resume trading agent' : 'Pause trading agent'}" ${st?.running === true ? '' : 'disabled'}>
      ${ic(paused ? 'play' : 'pause')}
    </button>
    <button class="${className} danger" type="button" data-act="system-kill"
      aria-label="${killSwitchActive ? 'Kill switch active' : 'Engage kill switch'}"
      title="${killSwitchActive ? 'Kill switch active' : 'Kill switch'}" ${killSwitchActive ? 'disabled' : ''}>
      ${ic('stop')}
    </button>`;
}
function paintRailFoot() {
  const st = S.state?.status;
  put($('#railFoot'), html`
    <div><span class="status-dot ${S.live ? 'ok' : 'bad'}"></span>${S.live ? 'Live' : 'Reconnecting…'}</div>
    ${st ? html`<div>Broker <b>${st.broker === 'paper' ? 'Paper' : 'MetaTrader 5'}</b></div>
    ${st.llm?.model ? html`<div>Model <b>${modelLabel(st.llm.model)}</b></div>` : ''}` : ''}
    <div class="rail-actions" role="group" aria-label="Trading controls">
      ${controlButtons('rail-action')}
    </div>`);
}

/* ------------------------------------------------------------------ data */
let lastFetch = 0, pending = null;
async function refreshState(force = false) {
  if (!force && Date.now() - lastFetch < 1200) { if (!pending) pending = setTimeout(() => { pending = null; refreshState(true); }, 1300); return; }
  lastFetch = Date.now();
  try { S.state = await api('/api/state'); } catch (e) { if (!S.state) S.state = { status: { phase: 'offline', running: false, error: e.message, llm: { provider: '', model: '' } } }; return; }
  paintShell(); paintLive();
}
async function loadEquity() { try { S.equity = (await api('/api/equity?limit=500')).series; } catch { /* ignore */ } }
async function loadFeed() { try { S.feed = (await api('/api/journal?limit=16&kind=plan,reason,action,trade_open,trade_close,lesson,reflection,world')).entries; } catch { /* ignore */ } }

/* ------------------------------------------------------------------ hero text */
function heroLine(st) {
  if (!st || !st.running && st.phase === 'offline') return ['Not connected', 'The trading loop is not connected.'];
  const d = st.phase_detail;
  switch (st.phase) {
    case 'observe': return ['Reading the markets', ''];
    case 'plan': return ['Setting the plan', d && 'Because: ' + d];
    case 'reason': return ['Thinking it through', d && 'Trigger: ' + d];
    case 'adjust': return ['Adjusting after risk review', d];
    case 'execute': return ['Sending orders through the risk check', d];
    case 'reflect': return ['Checking what just happened', ''];
    case 'review': return ['Reviewing a closed trade', d];
    case 'meta review': return ['Improving how it improves', d];
    case 'world': return ['Reading the world feed', ''];
    case 'paused': return ['Paused', 'Existing stops stay at the broker.'];
    case 'waiting': return ['Waiting', d];
    default: return [S.state?.positions?.length || S.state?.pending?.length ? 'Watching the open book' : 'Watching for a setup', d];
  }
}
function latestThought() {
  const e = S.feed.find((x) => x.kind === 'reason' || x.kind === 'reflection');
  return e ? html`${e.title}<small>${rel(e.ts)}${e.kind === 'reflection' ? ' · reflection' : ''}</small>` : '';
}

/* ------------------------------------------------------------------ overview */
function viewOverview() {
  return html`
  <div id="banners"></div><div id="approvals"></div>
  <section class="hero">
    <div class="eye-wrap"><canvas id="eye" role="img" aria-label="The agent's loop: plan, reason, execute, reflect"></canvas></div>
    <div class="hero-copy">
      <div class="status-line" id="chips"></div>
      <h1 id="heroTitle" aria-live="polite"></h1>
      <p class="thought" id="thought"></p>
      <div class="hero-actions" id="heroBtns"></div>
    </div>
  </section>
  <div id="kpis"></div>
  <section class="sec"><div class="sec-h"><h2>Markets</h2><span class="mute small">Liquidity, sweeps and structure</span></div><div class="tape" id="tape"></div></section>
  <section class="sec"><div class="sec-h"><h2>Equity</h2><span class="mute small" id="eqmeta"></span></div>
    <div class="chart-box"><canvas id="eq" role="img" aria-label="Equity over time"></canvas><div class="chart-tip" id="tip"></div></div></section>
  <section class="sec" id="worldBrief"></section>
  <section class="sec" id="legacyAnalysis"></section>
  <div class="cols">
    <section class="sec"><div class="sec-h"><h2>Open book</h2><span class="mute small" id="bookmeta"></span></div><div id="book" class="rows"></div></section>
    <section class="sec"><div class="sec-h"><h2>What it has been doing</h2><a href="#journal" class="mute small">Full journal</a></div><div class="feed" id="feed"></div></section>
  </div>`;
}
function mountOverview() {
  S.eye = new Eye($('#eye'));
  paintLive(true);
}
function paintLive(first) {
  if (S.route === 'loop') return paintLoopLive();
  if (S.route !== 'overview' || !S.state) return;
  const st = S.state.status, r = S.state.risk, a = S.state.account;
  const [title, sub] = heroLine(st);
  const ht = $('#heroTitle'); if (ht && ht.textContent !== title) ht.textContent = title;
  const th = $('#thought'); if (th) put(th, sub ? html`${sub}${latestThought() ? html`<small>${latestThought()}</small>` : ''}` : latestThought());
  S.eye && S.eye.set({ phase: st.phase, busy: S.llmBusy || ['plan', 'reason', 'adjust', 'reflect', 'review', 'meta review', 'world'].includes(st.phase), paused: st.paused, halted: !!r?.halted, waiting: st.phase === 'waiting' });
  put($('#chips'), html`
    <span class="chip ${st.autonomy === 'autonomous' ? 'lumen' : st.autonomy === 'approval' ? 'amber' : ''}">${{ autonomous: 'Autonomous', approval: 'Asks before trading', observe: 'Observing only' }[st.autonomy] || st.autonomy}</span>
    ${st.llm?.model ? html`<span class="chip squid">${modelLabel(st.llm.model)}</span>` : ''}
    ${r ? html`<span class="chip">${r.tier} tier</span>` : ''}${r?.halted ? html`<span class="chip loss">Halted: ${r.halt_reason}</span>` : ''}${st.stand_down ? html`<span class="chip amber">World stand-down</span>` : ''}`);
  const heroActions = $('#heroBtns');
  const showReconnect = st.running === false && st.phase === 'offline';
  put(heroActions, showReconnect
    ? html`<button class="btn primary" data-act="reconnect">Connect broker</button><a class="btn" href="#settings">Open settings</a>`
    : '');
  if (heroActions) heroActions.hidden = !showReconnect;
  // banners
  const bn = [];
  if (st.running === false && st.phase === 'offline') bn.push(html`<div class="banner bad"><span class="grow"><b>The trading loop is not connected.</b> Check broker settings or reconnect.</span></div>`);
  else if (!st.llm?.configured) bn.push(html`<div class="banner"><span class="grow"><b>No language model key yet.</b> The agent protects open positions but can't reason until you add one.</span><a class="btn sm primary" href="#settings">Add a key</a></div>`);
  if (st.autonomy_note) bn.push(html`<div class="banner"><span class="grow">${st.autonomy_note}</span></div>`);
  if (st.backoff > 0) bn.push(html`<div class="banner"><span class="grow">The model is rate-limited or unreachable. Retrying in about ${st.backoff}s. Open positions keep their stops.</span></div>`);
  put($('#banners'), bn);
  put($('#approvals'), (S.state.proposals || []).map((p) => html`<div class="banner"><span class="grow"><b>Awaiting your approval:</b> ${p.summary}${p.volume ? html` · ${p.volume} lots · ${p.risk_pct}% risk` : ''}<br><span class="mute small">${short(p.thesis, 160)}</span></span><button class="btn sm primary" data-act="approve" data-id="${p.id}">Approve</button><button class="btn sm" data-act="reject" data-id="${p.id}">Reject</button></div>`));
  if (a) {
    const stt = S.state.stats;
    const today = stt.today;
    const todayReady = Boolean(today && today.date && typeof today.pnl === 'number');
    const todayDate = todayReady ? today.date : new Date().toISOString().slice(0, 10);
    const positions = S.state.positions || [];
    const floating = positions.reduce((total, position) => total + (Number(position.profit) || 0), 0);
    const profitFactor = stt.losses ? num(stt.profit_factor) : stt.wins ? '∞' : '–';
    const streak = stt.streak > 0 ? `${stt.streak} win${stt.streak === 1 ? '' : 's'}`
      : stt.streak < 0 ? `${Math.abs(stt.streak)} loss${stt.streak === -1 ? '' : 'es'}` : '–';
    put($('#kpis'), html`<div class="kpis">
      <div class="kpi"><b id="kEq" data-v="${a.equity}">${num(a.equity)}</b><span>Equity ${a.currency}</span></div>
      <div class="kpi"><b class="${todayReady ? cls(today.pnl) : ''}">${todayReady ? sgn(today.pnl) : '–'}</b><span>Realized today · ${todayDate} UTC · ${a.currency}</span>
        <small class="kpi-detail">${!todayReady ? 'Restart Agent to load dated trade statistics' : today.trades ? `${today.trades} closed · ${today.wins} wins · ${today.losses} losses · ${num(today.win_rate * 100, 1)}% win rate` : 'No closed trades today'}</small></div>
      <div class="kpi"><b class="${cls(floating)}">${sgn(floating)}</b><span>Floating P&amp;L · ${positions.length} open · ${a.currency}</span></div>
      <div class="kpi" title="The risk guard can include realized trades since its reset and current open losses.">
        <b class="${cls(r.daily_pnl)}">${sgn(r.daily_pnl)}</b><span>Risk guard P&amp;L · ${a.currency}</span>
        <small class="kpi-detail">${r.daily_loss_limit_enabled ? `Daily limit −${num(r.daily_limit)} ${a.currency}` : 'Daily loss guard disabled'}</small></div>
      <div class="kpi"><b class="${r.drawdown_pct > 0 ? 'amber' : ''}">${num(r.drawdown_pct)}%</b><span>Drawdown from peak</span></div>
      <div class="kpi"><b>${num(r.open_risk_pct)}%</b><span>Open risk · cap ${r.max_open_risk_pct}%</span></div>
    </div>
    <div style="margin-top:14px"><div class="ladder" title="Scaling ladder">${r.ladder.map((t, i) => { const ci = r.ladder.findIndex((x) => x.name === r.tier); const nxt = r.ladder[ci + 1]; const p = nxt ? Math.max(4, Math.min(100, ((a.equity - r.ladder[ci].min_equity) / (nxt.min_equity - r.ladder[ci].min_equity)) * 100)) : 100; return html`<i class="${i < ci ? 'on' : i === ci ? 'cur' : ''}" style="--p:${p}%"></i>`; })}</div>
    <div class="mute small" style="margin-top:8px">${r.next_tier ? html`Tier <b>${r.tier}</b> risks ${r.risk_pct}% per trade. ${num(r.next_tier_at - a.equity, 0)} to <b>${r.next_tier}</b>.` : html`Top tier: <b>${r.tier}</b>.`} Growth since start ${sgn(r.growth_pct)}%.</div></div>
    <section class="sec system-performance"><div class="sec-h"><h2>System performance</h2><span class="mute small">Closed trades · all time</span></div>
      <div class="performance-grid">
        <div class="performance-item"><span>Net realized · ${a.currency}</span><b class="${cls(stt.pnl)}">${sgn(stt.pnl)}</b><small>${stt.trades} closed trades</small></div>
        <div class="performance-item"><span>Win / loss count</span><b>${stt.wins} / ${stt.losses}</b><small>${stt.trades} total closes</small></div>
        <div class="performance-item"><span>Win rate</span><b>${stt.trades ? `${num(stt.win_rate * 100, 1)}%` : '–'}</b><small>Wins / closed trades</small></div>
        <div class="performance-item"><span>Profit factor</span><b>${profitFactor}</b><small>Gross profit / gross loss</small></div>
        <div class="performance-item"><span>Expectancy</span><b class="${cls(stt.avg_r)}">${stt.trades ? `${sgn(stt.avg_r)}R` : '–'}</b><small>Average R per closed trade</small></div>
        <div class="performance-item"><span>Current streak</span><b class="${cls(stt.streak)}">${streak}</b><small>Consecutive outcomes</small></div>
        <div class="performance-item"><span>Best trade · ${a.currency}</span><b class="gain">${stt.trades ? sgn(stt.best) : '–'}</b><small>Largest closed gain</small></div>
        <div class="performance-item"><span>Worst trade · ${a.currency}</span><b class="loss">${stt.trades ? sgn(stt.worst) : '–'}</b><small>Largest closed loss</small></div>
      </div>
    </section>`);
    const kv = $('#kEq'); if (kv && first !== true) animateNum(kv, a.equity);
  }
  paintWorld();
  paintLegacyAnalysis();
  put($('#bookmeta'), html`${S.state.positions?.length || 0} open · ${S.state.pending?.length || 0} resting`);
  put($('#book'), bookRows());
  put($('#tape'), tape());
  paintFeed();
  const eq = $('#eq'); if (eq && (first || !eq.dataset.n || +eq.dataset.n !== S.equity.length)) { eq.dataset.n = S.equity.length; drawEquity(eq, $('#tip'), S.equity, { fmt: (v) => num(v) }); }
  put($('#eqmeta'), S.equity.length > 1 ? html`${S.equity.length} samples · ${rel(S.equity[0].ts)} to now` : '');
}
const animCache = new WeakMap();
function animateNum(el, to) {
  const from = animCache.get(el) ?? to; animCache.set(el, to);
  if (matchMedia('(prefers-reduced-motion: reduce)').matches || Math.abs(from - to) < 0.005) { el.textContent = num(to); return; }
  const t0 = performance.now();
  const f = (ts) => { const p = Math.min(1, (ts - t0) / 600); el.textContent = num(from + (to - from) * (1 - Math.pow(1 - p, 3))); if (p < 1) requestAnimationFrame(f); };
  requestAnimationFrame(f);
}
function bookRows() {
  const P = S.state.positions || [], O = S.state.pending || [];
  if (!P.length && !O.length) return html`<div class="empty"><b>Nothing open</b><span>Positions and resting limit orders show up here, with the agent's reasoning for each.</span></div>`;
  return html`${P.map((p) => html`<div class="row"><div class="who"><b>${p.symbol}</b><span><span class="chip ${p.side}">${p.side}</span> <span class="mute small">${p.volume} lots · #${p.ticket}</span></span></div>
    <div class="nums"><span>Entry <b>${px(p.price_open)}</b></span><span>Now <b>${px(p.price_current)}</b></span><span>Stop <b>${p.sl ? px(p.sl) : 'none'}</b></span><span>Target <b>${p.tp ? px(p.tp) : 'none'}</b></span>${p.r_now != null ? html`<span>Open R <b class="${cls(p.r_now)}">${sgn(p.r_now)}</b></span>` : ''}</div>
    <div class="act"><div class="pnl ${cls(p.profit)}">${sgn(p.profit)}</div><button class="btn sm danger" data-act="close" data-t="${p.ticket}" aria-label="Close position ${p.ticket}">Close</button></div>
    ${p.thesis || p.skills?.length ? html`<div class="why">${p.thesis} ${(p.skills || []).map((s) => html`<span class="chip">${s}</span> `)}</div>` : ''}</div>`)}
    ${O.map((o) => html`<div class="row"><div class="who"><b>${o.symbol}</b><span><span class="chip amber">${o.kind.replace('_', ' ')}</span> <span class="mute small">${o.volume} lots · #${o.ticket}</span></span></div>
    <div class="nums"><span>Price <b>${px(o.price)}</b></span><span>Stop <b>${o.sl ? px(o.sl) : 'none'}</b></span><span>Target <b>${o.tp ? px(o.tp) : 'none'}</b></span>${o.expires ? html`<span>Expires <b>${Math.max(0, Math.round((o.expires - Date.now() / 1000) / 60))} min</b></span>` : ''}</div>
    <div class="act"><button class="btn sm" data-act="cancel" data-t="${o.ticket}" aria-label="Cancel order ${o.ticket}">Cancel</button></div>
    ${o.thesis || o.skills?.length ? html`<div class="why">${o.thesis} ${(o.skills || []).map((s) => html`<span class="chip">${s}</span> `)}</div>` : ''}</div>`)}`;
}
function tape() {
  const M = S.state.markets || {}; const keys = Object.keys(M);
  if (!keys.length) return html`<div class="empty"><span>Waiting for the first market read…</span></div>`;
  return keys.map((k) => { const m = M[k]; if (m.unavailable) return html`<div class="tick unavailable"><b>${k}</b><span class="mute small">Market data temporarily unavailable.</span></div>`;
    const sw = (m.sweeps || [])[0];
    const dir = m.trend?.dir === 'up' ? ['Uptrend', 'gain'] : m.trend?.dir === 'down' ? ['Downtrend', 'loss'] : ['Mixed', ''];
    return html`<div class="tick"><b class="symbol-name">${k}</b><span class="px">${px(m.price)}</span>
      <div class="meta"><span class="chip ${dir[1]}">${dir[0]}</span>${m.regime ? html`<span class="chip">${m.regime}</span>` : ''}${m.session ? html`<span class="chip">${m.session.replace(/_/g, ' ')}</span>` : ''}
      ${sw ? html`<span class="chip amber pulse" title="Level ${sw.level}">${sw.bias === 'bullish' ? 'Sell-side swept' : 'Buy-side swept'} · ${sw.bars_ago} bar${sw.bars_ago === 1 ? '' : 's'} ago</span>` : ''}</div>
      <svg class="spark" viewBox="0 0 220 34" preserveAspectRatio="none" aria-hidden="true"><path d="${sparkPath(m.candles)}" fill="none" stroke="${dir[1] === 'loss' ? 'var(--loss)' : 'var(--lumen)'}" stroke-width="1.6" stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg></div>`; });
}
function feedItem(e, isNew) {
  return html`<div class="fe k-${e.kind} ${isNew ? 'new' : ''}">${kicon(e.kind)}<div><div class="t">${e.title}</div><div class="s">${(KIND[e.kind] || ['', ''])[0]} · ${rel(e.ts)}</div></div></div>`;
}
function paintFeed(newId) {
  const f = $('#feed'); if (!f) return;
  const entries = S.feed.filter((e) => e.kind !== 'system');
  put(f, entries.length ? entries.slice(0, 14).map((e) => feedItem(e, e.id === newId)) : html`<div class="empty"><b>Quiet so far</b><span>Every plan, thought, order and lesson is written to the journal and appears here.</span></div>`);
}

/* ------------------------------------------------------------------ loop */
const PHASES = [['plan', 'Plan', 'Direction and todos'], ['reason', 'Reason', 'What to do now'], ['execute', 'Execute', 'Through the risk check'], ['reflect', 'Reflect', 'Learn from it']];
const P2 = { plan: 'plan', world: 'plan', reason: 'reason', adjust: 'reason', execute: 'execute', reflect: 'reflect', review: 'reflect', 'meta review': 'reflect' };
function viewLoop() {
  return html`<div class="page-h"><div><h1>The loop</h1><p>Plan, reason, adjust, execute, reflect. The agent keeps its own todo list and writes down why.</p></div>
    <div style="display:flex;gap:10px;flex-wrap:wrap"><button class="btn" data-act="think">Think now</button><button class="btn" data-act="replan">Re-plan</button></div></div>
    <div class="phases" id="phases"></div><div class="mute small" id="phaseMeta" style="margin:8px 2px 0"></div>
    <div class="plan"><section class="sec" id="planBox"></section><section class="sec"><div class="sec-h"><h2>Todos</h2><span class="mute small" id="todoMeta"></span></div><div id="todos"></div>
      <form class="add-row" id="todoForm"><input type="text" id="todoIn" placeholder="Add a todo for the agent…" maxlength="200" aria-label="New todo"><button class="btn primary" aria-label="Add todo">${ic('plus')}Add</button></form></section></div>
    <section class="sec"><div class="sec-h"><h2>Recent thinking</h2></div><div class="tl" id="thinking"></div></section>`;
}
async function mountLoop() {
  $('#todoForm').onsubmit = async (e) => { e.preventDefault(); const v = $('#todoIn').value.trim(); if (!v) return; $('#todoIn').value = ''; await guard(() => api('/api/todos', { title: v })); loadTodos(); };
  await refreshState(true); paintLoopLive(); loadThinking();
}
function paintLoopLive() {
  const st = S.state?.status; if (!st || !$('#phases')) return;
  const on = P2[st.phase];
  put($('#phases'), PHASES.map(([k, l, d]) => html`<div class="phase ${on === k ? 'on' : ''}"><b>${l}</b><span>${d}</span></div>`));
  put($('#phaseMeta'), html`${st.paused ? 'Paused.' : st.phase === 'idle' ? 'Idle between looks.' : 'Now: ' + st.phase + '.'} ${st.last_think ? html`Last reasoning pass ${rel(st.last_think)} (${st.last_think_reason}).` : ''} ${st.next_check > Date.now() / 1000 ? html`Next look in about ${Math.max(1, Math.round((st.next_check - Date.now() / 1000) / 60))} min.` : ''} ${st.thinks_last_hour} pass${st.thinks_last_hour === 1 ? '' : 'es'} in the last hour.`);
  const p = S.state.plan;
  put($('#planBox'), p ? html`<div class="sec-h"><h2>Current plan</h2><span class="mute small">${rel(p.ts)}</span></div><p class="focus">${p.focus}</p>
    <div class="bias">${Object.entries(p.bias || {}).map(([k, v]) => html`<span class="chip ${v === 'bullish' ? 'gain' : v === 'bearish' ? 'loss' : ''}">${k} ${v}</span>`)}</div>
    ${(p.watch || []).length ? html`<div class="watch">${p.watch.map((w) => html`<div><b>${w.symbol}</b> ${w.level != null ? '@ ' + w.level : ''} <span>${w.why}</span></div>`)}</div>` : ''}
    ${(p.risks || []).length ? html`<div class="watch" style="margin-top:14px"><span class="amber">Risks the agent sees</span>${p.risks.map((r) => html`<div>${r}</div>`)}</div>` : ''}
    ${p.notes ? html`<div class="notes">${p.notes}</div>` : ''}` : html`<div class="sec-h"><h2>Current plan</h2></div><div class="empty"><b>No plan yet</b><span>The agent writes its first plan on its first reasoning pass.</span></div>`);
  loadTodos();
}
async function loadTodos() {
  const box = $('#todos'); if (!box) return;
  let t = []; try { t = (await api('/api/todos')).todos; } catch { return; }
  const open = t.filter((x) => x.status === 'open' || x.status === 'doing'), done = t.filter((x) => x.status === 'done').slice(0, 5);
  put($('#todoMeta'), html`${open.length} open`);
  const row = (x) => html`<div class="todo ${x.status === 'done' ? 'done' : ''}"><button class="ck" data-act="tick" data-id="${x.id}" data-done="${x.status === 'done' ? 1 : 0}" aria-label="${x.status === 'done' ? 'Reopen' : 'Complete'}: ${x.title}">${ic('check')}</button>
    <div><div class="tt">${x.title}</div>${x.detail ? html`<div class="dd">${x.detail}</div>` : ''}${x.result ? html`<div class="dd lumen">${x.result}</div>` : ''}<div class="dd">${x.source === 'user' ? 'You' : 'Agent'} · ${rel(x.ts)}${x.priority === 1 ? ' · high priority' : ''}</div></div>
    ${x.status !== 'done' ? html`<button class="btn sm" data-act="drop" data-id="${x.id}" aria-label="Drop todo ${x.title}">${ic('x')}</button>` : ''}</div>`;
  put(box, open.length || done.length ? html`${open.map(row)}${done.map(row)}` : html`<div class="empty"><b>No todos</b><span>The agent adds checks and experiments here. You can add your own.</span></div>`);
}
async function loadThinking() {
  try { const r = await api('/api/journal?limit=8&kind=plan,reason,reflection,lesson'); put($('#thinking'), r.entries.length ? r.entries.map(jEntry) : html`<div class="empty"><span>Nothing yet.</span></div>`); } catch { /* ignore */ }
}

/* ------------------------------------------------------------------ journal */
const JF = [['all', 'All', 'all'], ['think', 'Thinking', 'plan,reason,reflection'], ['orders', 'Orders', 'action,trade_open,trade_close'], ['lessons', 'Lessons', 'lesson'], ['world', 'World', 'world'], ['notes', 'Notes', 'user']];
function jEntry(e) {
  return html`<div class="je k-${e.kind}"><time datetime="${new Date(e.ts * 1000).toISOString()}">${hhmm(e.ts)}<br>${dayStr(e.ts)}</time>${kicon(e.kind)}
    <div class="bd"><h3>${e.title}</h3>${(e.tags || []).length ? html`<div class="tags">${e.tags.map((t) => html`<span class="chip ${t === 'rejected' ? 'loss' : ''}">${t}</span>`)}</div>` : ''}
    ${e.body ? html`<details><summary>Show detail</summary><div class="txt">${e.body}</div></details>` : ''}</div></div>`;
}
function viewJournal() {
  return html`<div class="page-h"><div><h1>Journal</h1><p>Everything the agent plans, thinks, does and learns. It reads this back to improve.</p></div></div>
  <details style="margin-bottom:18px"><summary class="btn sm" style="display:inline-flex;list-style:none;cursor:pointer">${ic('plus')}Add a note</summary>
    <form id="noteForm" style="display:grid;gap:10px;margin-top:12px;max-width:620px"><input type="text" id="noteT" placeholder="Title" maxlength="200" required aria-label="Note title"><textarea id="noteB" placeholder="What should the agent know or remember?" aria-label="Note body"></textarea><div><button class="btn primary">Save note</button></div></form></details>
  <div class="filters"><div class="seg" role="group" aria-label="Filter entries">${JF.map(([k, l]) => html`<button data-act="jf" data-k="${k}" aria-pressed="${S.jf.kind === k}">${l}</button>`)}</div>
    <div class="search">${ic('search')}<input type="text" id="jq" placeholder="Search the journal" value="${S.jf.q}" aria-label="Search journal"></div></div>
  <div class="tl" id="jlist"></div><div style="margin-top:8px" id="jmore"></div>`;
}
async function loadJournal(reset) {
  if (reset) { S.jEntries = []; S.jMore = true; }
  const kinds = JF.find((f) => f[0] === S.jf.kind)[2];
  const before = S.jEntries.length ? S.jEntries[S.jEntries.length - 1].id : 0;
  let r; try { r = await api(`/api/journal?limit=30&kind=${encodeURIComponent(kinds)}&q=${encodeURIComponent(S.jf.q)}&before=${before}`); } catch (e) { return toast(e.message, 'bad'); }
  S.jEntries = S.jEntries.concat(r.entries); S.jMore = r.entries.length === 30; paintJournal();
}
function paintJournal() {
  const entries = S.jEntries.filter((e) => e.kind !== 'system');
  put($('#jlist'), entries.length ? entries.map(jEntry) : html`<div class="empty"><b>${S.jf.q ? 'No matches' : 'Nothing here yet'}</b><span>${S.jf.q ? 'Try fewer words.' : 'Entries appear as the agent works.'}</span></div>`);
  put($('#jmore'), S.jMore && S.jEntries.length ? html`<button class="btn" data-act="jmore">Load older entries</button>` : '');
}
function mountJournal() {
  $('#noteForm').onsubmit = async (e) => { e.preventDefault(); await guard(() => api('/api/journal', { title: $('#noteT').value, body: $('#noteB').value }), 'Saved to the journal'); $('#noteForm').reset(); loadJournal(true); };
  loadJournal(true);
}

/* ------------------------------------------------------------------ playbook */
async function viewPlaybook() {
  return html`<div class="page-h"><div><h1>Playbook</h1><p>The skills the agent trades with. Each one earns trust from results: confidence and the size it may risk follow the numbers, not the story.</p></div></div>
  <section><div class="sec-h"><h2>Scaling ladder</h2><span class="mute small">Risk per trade shrinks as equity grows, and shrinks further in drawdown</span></div><div class="tiers" id="tiers"></div><div id="scaleNotes"></div></section>
  <section class="sec"><div class="sec-h"><h2>Skills</h2><span class="mute small" id="skMeta"></span></div><div id="skills"></div></section>
  <section class="sec"><div class="sec-h"><h2 id="skFormT">Add a skill</h2></div>
    <form id="skForm" style="display:grid;gap:12px;max-width:720px"><div class="set-grid"><label class="f">Name<input type="text" id="skName" placeholder="e.g. london_open_raid" required maxlength="48"></label>
    <label class="f">Kind<select id="skKind"><option value="setup">Setup</option><option value="rule">Rule</option><option value="skill">Skill</option></select></label></div>
    <label class="f">What it is and when to use it<textarea id="skBody" required maxlength="1500" placeholder="Describe the pattern, how to enter, where the stop goes, when to stay out."></textarea></label><div><button class="btn primary">Save skill</button></div></form></section>`;
}
async function mountPlaybook() {
  const r = S.state?.risk;
  put($('#tiers'), r ? r.ladder.map((t, i) => { const ci = r.ladder.findIndex((x) => x.name === r.tier); return html`<div class="tier ${i === ci ? 'cur' : i < ci ? 'past' : ''}"><b>${t.name}</b><span>from ${num(t.min_equity, 0)}</span><span>${t.risk_pct}% per trade</span></div>`; }) : '');
  put($('#scaleNotes'), html`${S.state?.scaling_notes ? html`<div class="notes"><b>The agent's scaling notes</b><br>${S.state.scaling_notes}</div>` : ''}${S.state?.process_notes ? html`<div class="notes"><b>Process notes</b><br>${S.state.process_notes}</div>` : ''}`);
  $('#skForm').onsubmit = async (e) => { e.preventDefault(); const r2 = await guard(() => api('/api/playbook', { name: $('#skName').value, kind: $('#skKind').value, body: $('#skBody').value }), 'Skill saved'); if (r2) { $('#skForm').reset(); $('#skFormT').textContent = 'Add a skill'; loadSkills(); } };
  loadSkills();
}
let SK = [];
async function loadSkills() {
  try { SK = (await api('/api/playbook')).skills; } catch (e) { return toast(e.message, 'bad'); }
  put($('#skMeta'), html`${SK.filter((s) => s.status === 'active').length} active · ${SK.filter((s) => s.status === 'probation').length} on probation · ${SK.filter((s) => s.status === 'retired').length} retired`);
  put($('#skills'), SK.map((s) => { const C = 2 * Math.PI * 22, col = s.status === 'active' ? 'var(--lumen)' : s.status === 'probation' ? 'var(--amber)' : 'var(--mist)';
    return html`<div class="skill" id="sk-${s.name}"><div class="meter" title="Confidence ${Math.round(s.confidence * 100)}%"><svg viewBox="0 0 54 54"><circle cx="27" cy="27" r="22" fill="none" stroke="var(--tide)" stroke-width="5"/><circle cx="27" cy="27" r="22" fill="none" stroke="${col}" stroke-width="5" stroke-linecap="round" stroke-dasharray="${(s.confidence * C).toFixed(1)} ${C.toFixed(1)}"/></svg><b>${Math.round(s.confidence * 100)}</b></div>
      <div><h3>${s.name.replaceAll('_', ' ')} <span class="chip">${s.kind}</span> <span class="chip ${s.status === 'active' ? 'lumen' : s.status === 'probation' ? 'amber' : ''}">${s.status}</span></h3>
      <div class="st"><span>${s.uses} trade${s.uses === 1 ? '' : 's'}</span>${s.uses ? html`<span>${Math.round(s.win_rate * 100)}% wins</span><span class="${cls(s.expectancy_r)}">${sgn(s.expectancy_r)}R expectancy</span>` : html`<span>No track record yet</span>`}<span>v${s.version}${s.origin !== 'agent' ? ' · ' + s.origin : ''}</span></div></div>
      <div class="seg" role="group" aria-label="Status of ${s.name}">${['active', 'probation', 'retired'].map((x) => html`<button data-act="skstatus" data-n="${s.name}" data-s="${x}" aria-pressed="${s.status === x}">${x}</button>`)}</div>
      <div class="body">${s.body}</div>
      <div style="grid-column:2/4;display:flex;gap:8px;flex-wrap:wrap"><button class="btn sm" data-act="skedit" data-n="${s.name}">Edit</button><button class="btn sm" data-act="skhist" data-n="${s.name}">History</button></div><div id="hist-${s.name}" style="grid-column:2/4"></div></div>`; }));
}

/* ------------------------------------------------------------------ chat */
function msgHtml(m) {
  return html`<div class="msg ${m.role}"><div class="bub">${m.content}</div>${(m.actions || []).length ? html`<div class="acts">${m.actions.map((a) => html`<span class="chip ${a.ok ? 'lumen' : 'loss'}">${a.ok ? '✓' : '✕'} ${a.type.replaceAll('_', ' ')}${a.detail ? ': ' + short(a.detail, 60) : ''}</span>`)}</div>` : ''}</div>`;
}
function viewChat() {
  const Q = ['What is your plan?', 'How are we doing?', 'What have you learned lately?', 'Tighten risk', 'Pause trading', '/status'];
  return html`<div class="page-h"><div><h1>Chat</h1><p>Ask what it's thinking, or tell it what to change. It can adjust settings, manage orders and edit its playbook, always inside the hard limits.</p></div></div>
  <div class="chat"><div class="msgs" id="msgs" role="log" aria-live="polite" aria-label="Conversation"></div>
  <div class="composer"><div class="quick">${Q.map((q) => html`<button class="btn sm" data-act="quick" data-q="${q}">${q}</button>`)}<button class="btn sm danger" data-act="flatten">Flatten everything</button></div>
  <form class="cbox" id="chatForm"><textarea id="chatIn" rows="1" placeholder="Ask anything, or try /status" aria-label="Message to the agent" maxlength="4000"></textarea><button class="btn primary" aria-label="Send">${ic('send')}</button></form></div></div>`;
}
async function mountChat() {
  try { S.chat = (await api('/api/chat')).messages; } catch { S.chat = []; }
  const box = $('#msgs');
  put(box, S.chat.length ? S.chat.map(msgHtml) : html`<div class="empty"><b>Nothing said yet</b><span>Try "What is your plan?" or "Move the stop on my gold trade to breakeven".</span></div>`);
  box.scrollTop = box.scrollHeight;
  const inp = $('#chatIn');
  inp.addEventListener('input', () => { inp.style.height = 'auto'; inp.style.height = Math.min(140, inp.scrollHeight) + 'px'; });
  inp.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('#chatForm').requestSubmit(); } });
  $('#chatForm').onsubmit = (e) => { e.preventDefault(); const v = inp.value.trim(); if (!v) return; inp.value = ''; inp.style.height = 'auto'; sendChat(v); };
}
async function sendChat(text) {
  const box = $('#msgs'); if (!box) return;
  if (box.querySelector('.empty')) box.innerHTML = '';
  box.insertAdjacentHTML('beforeend', msgHtml({ role: 'user', content: text }).s);
  box.insertAdjacentHTML('beforeend', '<div class="msg assistant" id="typing"><div class="bub typing"><i></i><i></i><i></i></div></div>');
  box.scrollTop = box.scrollHeight;
  try { const r = await api('/api/chat', { text }); $('#typing')?.remove(); box.insertAdjacentHTML('beforeend', msgHtml({ role: 'assistant', content: r.reply, actions: r.actions }).s); refreshState(true); }
  catch (e) { $('#typing')?.remove(); box.insertAdjacentHTML('beforeend', msgHtml({ role: 'assistant', content: e.message, actions: [] }).s); }
  box.scrollTop = box.scrollHeight;
}

/* ------------------------------------------------------------------ settings */
const PEND = {};
const TUNE_GROUPS = { behaviour: ['AGENT_SYMBOLS', 'AGENT_TIMEFRAME', 'AGENT_MANAGE_INTERVAL', 'AGENT_IDLE_THINK_MINUTES', 'AGENT_MAX_THINKS_PER_HOUR', 'AGENT_PLAN_EVERY', 'AGENT_MANAGE_FOREIGN', 'AGENT_EMERGENCY_SL'],
  risk: ['RISK_MAX_PER_TRADE_PCT', 'RISK_MAX_POSITIONS', 'RISK_MAX_POSITIONS_PER_SYMBOL', 'RISK_MAX_PENDING', 'RISK_MAX_OPEN_RISK_PCT', 'RISK_MIN_RR', 'RISK_DAILY_LOSS_PCT', 'RISK_DRAWDOWN_HALT_PCT', 'RISK_MAX_ENTRY_ATR', 'RISK_MAX_SPREAD_ATR'] };
const AUTONOMY = { observe: ['Observe', 'Reads, plans and journals. Never sends an order.'], approval: ['Ask me', 'Proposes entries and waits for your approval. Protective moves still happen on their own.'], autonomous: ['Autonomous', 'Places, moves and closes orders itself, inside the risk limits.'] };
function tune(k) {
  const t = S.config.agent[k]; if (!t) return '';
  const v = PEND[k] ?? t.value;
  if (t.type === 'choice') return html`<div class="rng wide"><div class="top"><span>${t.label}</span></div><div class="seg">${t.options.map((o) => html`<button data-act="tchoice" data-k="${k}" data-v="${o}" aria-pressed="${v === o}">${o.replaceAll('_', ' ')}</button>`)}</div></div>`;
  if (t.type === 'bool') return html`<div class="rng"><div class="top"><span>${t.label}</span></div><div class="seg"><button data-act="tchoice" data-k="${k}" data-v="true" aria-pressed="${v === 'true'}">On</button><button data-act="tchoice" data-k="${k}" data-v="false" aria-pressed="${v === 'false'}">Off</button></div></div>`;
  if (t.type === 'str') return html`<label class="f wide">${t.label}<input type="text" data-key="${k}" value="${v}" maxlength="300"></label>`;
  const step = t.type === 'int' ? Math.max(1, Math.round((t.max - t.min) / 300)) : t.max <= 5 ? 0.05 : 0.5;
  return html`<div class="rng"><div class="top"><span>${t.label}</span><b data-lab="${k}">${v}</b></div><input type="range" data-key="${k}" min="${t.min}" max="${t.max}" step="${step}" value="${v}" aria-label="${t.label}"></div>`;
}
function viewSettings() { return html`<div class="page-h"><div><h1>Settings</h1><p>Most changes take effect immediately. Dashboard network access changes require a restart.</p></div></div><div id="setBody"></div>`; }
async function mountSettings() {
  try { S.config = await api('/api/config'); S.killSwitchActive = Boolean(S.config.system.kill_switch_active); } catch (e) { toast(e.message, 'bad'); return put($('#setBody'), html`<div class="banner bad">Settings are temporarily unavailable.</div>`); }
  paintShell();
  S.prov = S.prov || S.config.llm.active; paintSettings();
}
function paintSettings() {
  const c = S.config, L = c.llm, p = L.providers[S.prov], ms = S.models[S.prov] || [];
  const st = S.state?.status;
  const strategyProfile = PEND.AGENT_STRATEGY_PROFILE ?? c.agent.AGENT_STRATEGY_PROFILE.value;
  put($('#setBody'), html`
  <section><div class="sec-h"><h2>Language model</h2><span class="mute small">Provider-agnostic and hot-swappable. Keys are saved to ${c.env_file} and never sent back to this page.</span></div>
    <div class="seg" role="tablist" aria-label="Provider" style="margin-bottom:18px">${Object.entries(L.providers).map(([id, x]) => html`<button role="tab" data-act="prov" data-p="${id}" aria-pressed="${S.prov === id}"><span class="status-dot ${x.configured ? 'ok' : ''}"></span>${x.label}${L.active === id ? ' · active' : ''}</button>`)}</div>
    <div class="prov-card"><p class="mute small">${p.hint}</p>
      ${S.prov === 'cloudflare' ? html`<div class="set-grid">
      <label class="f">Cloudflare Account ID<input type="text" id="accountId" value="${p.account_id}" placeholder="32-character account ID" autocomplete="off"></label>
      <label class="f">AI Gateway ID<input type="text" id="gatewayId" value="${p.gateway_id || 'default'}" placeholder="default" autocomplete="off"></label></div>
      ${!p.account_id ? html`<p class="small amber">Add your Cloudflare Account ID to enable model discovery and connection tests.</p>` : ''}`
      : html`<label class="f">Base URL<input type="url" id="baseUrl" value="${p.base_url}" placeholder="${p.default_base_url}" autocomplete="off"></label>`}
      <div class="set-grid">
      <label class="f">API key<div class="key-row"><input type="password" id="apiKey" placeholder="${p.has_key ? 'Saved ' + p.key_hint + '. Paste to replace' : 'Paste your key'}" autocomplete="off"><button class="btn" data-act="llm-discover">Find models</button></div></label></div>
      <label class="f">Model<input type="text" id="modelIn" value="${p.model}" placeholder="${p.default_model}" autocomplete="off"></label>
      ${ms.length ? html`<div><input type="text" id="modelFilter" placeholder="Filter ${ms.length} models" aria-label="Filter models" style="margin-bottom:8px"><div class="models" id="modelList" role="listbox" aria-label="Models">${modelList(ms, p.model)}</div></div>` : ''}
      <div style="display:flex;gap:10px;flex-wrap:wrap"><button class="btn primary" data-act="llm-save" data-use="${L.active !== S.prov ? 1 : 0}">${L.active === S.prov ? 'Save' : 'Save and use this provider'}</button><button class="btn" data-act="llm-test">Test connection</button>${p.has_key ? html`<button class="btn danger" data-act="llm-clearkey">Remove key</button>` : ''}</div>
      <div class="small mute" id="llmStat">${p.stats?.calls ? html`${p.stats.calls} calls · ${p.stats.tokens_in + p.stats.tokens_out} tokens${p.stats.last_latency ? ' · last ' + p.stats.last_latency + 's' : ''}` : ''}</div></div></section>
  <section class="sec"><div class="sec-h"><h2>Cthulu services</h2><span class="mute small">${c.system.kill_switch_active ? 'Kill switch active · trading services stopped' : 'Kill switch inactive · dashboard supervisor enabled'}</span></div>
    <p class="mute small">Saved launch: ${c.execution_mode.mode} · ${c.system.trading_mode} · ${c.system.config_name}. Restart re-runs the selected launcher; HFT restarts repeat the safety preflight. Existing positions are not closed by stopping services.</p>
    <div style="display:flex;gap:10px;flex-wrap:wrap">
      <button class="btn danger" data-act="system-kill" ${c.system.kill_switch_active ? 'disabled' : ''}>${c.system.kill_switch_active ? 'Kill switch active' : 'Kill and stay down'}</button>
      <button class="btn primary" data-act="system-restart">Restart services</button>
    </div>
  </section>
  <section class="sec"><div class="sec-h"><h2>Dashboard network access</h2><span class="mute small">Choose where this dashboard listens. Remote API and chat require a shared token.</span></div>
    <div class="seg" role="group" aria-label="Dashboard network access">
      <button data-act="network-mode" data-mode="loopback" aria-pressed="${c.network.mode === 'loopback'}">This device only</button>
      <button data-act="network-mode" data-mode="lan" aria-pressed="${c.network.mode === 'lan'}">Local network</button>
      <button data-act="network-mode" data-mode="tailscale" aria-pressed="${c.network.mode === 'tailscale'}">Tailscale</button>
    </div>
    <p class="mute small" style="margin-top:10px">${c.network.mode === 'loopback'
      ? 'Loopback: only this computer can connect.'
      : c.network.mode === 'lan'
        ? 'LAN: binds to network interfaces and prints private LAN URLs at startup.'
        : c.network.mode === 'tailscale'
          ? 'Tailscale: binds only to this computer’s Tailscale IPv4 address and prints the URL at startup. Tailscale must be installed and connected.'
          : 'Invalid network mode; remote access is disabled.'}
      ${c.network.mode !== 'loopback' ? html`<br>Token ${c.network.token_configured ? 'is configured' : 'will be generated when remote access is enabled'}; enter it on each remote device before using chat or controls.` : ''}
      <br>Changing this setting requires restarting the agent. ${c.network.port ? html`Dashboard port: ${c.network.port}.` : ''}</p>
    </section>
  <section class="sec"><div class="sec-h"><h2>Shared execution mode</h2><span class="mute small">Legacy always runs; Agentic mode adds the agent in parallel.</span></div>
    <div class="seg" role="group" aria-label="Execution owner">
      <button data-act="execution-mode" data-mode="agentic" aria-pressed="${c.execution_mode.mode === 'agentic'}">Legacy + Agentic</button>
      <button data-act="execution-mode" data-mode="legacy" aria-pressed="${c.execution_mode.mode === 'legacy'}">Legacy only</button>
    </div>
    <p class="mute small" style="margin-top:10px">${c.execution_mode.mode === 'agentic'
      ? 'Hybrid mode: Legacy keeps generating, filtering and executing its signals. The agent can also analyze and manage the shared account under its autonomy and risk checks.'
      : c.execution_mode.mode === 'legacy'
        ? 'Legacy-only mode: the Legacy engine runs normally; agent order placement and management are disabled.'
        : 'No valid execution owner is configured; all trading actions are blocked.'}
      Enabling hybrid mode may be done with existing trades. Returning to Legacy-only requires a connected, flat account with no pending orders.</p></section>
  <section class="sec"><div class="sec-h"><h2>How much it may do</h2></div>
    <div class="seg">${Object.entries(AUTONOMY).map(([k, [l]]) => html`<button data-act="tchoice" data-k="AGENT_AUTONOMY" data-v="${k}" aria-pressed="${(PEND.AGENT_AUTONOMY ?? c.agent.AGENT_AUTONOMY.value) === k}">${l}</button>`)}</div>
    <p class="mute small" style="margin-top:10px">${AUTONOMY[PEND.AGENT_AUTONOMY ?? c.agent.AGENT_AUTONOMY.value][1]}${st?.autonomy_note ? html`<br><span class="amber">${st.autonomy_note}</span>` : ''}</p></section>
  <section class="sec"><div class="sec-h"><h2>Strategy and entry controls</h2><span class="mute small">Agentic profile is a reasoning preference; entry mode is enforced by the risk engine.</span></div>
    <div class="set-grid">${tune('AGENT_STRATEGY_PROFILE')}${tune('AGENT_ENTRY_MODE')}</div>
    <p class="mute small" style="margin-top:10px">${c.strategy_catalog.agent_profiles[strategyProfile]}</p>
    <p class="mute small">Legacy strategies and mindsets remain configured and active in the Legacy loop in both modes; the Agentic runtime does not execute or reconfigure those implementations, and their risk presets are never copied into Agentic risk settings.</p>
    <div class="set-grid">${Object.entries(c.strategy_catalog.legacy_strategies).map(([name, description]) => html`<div class="notes"><b>${name}</b><div class="small mute">${description}</div></div>`)}${Object.entries(c.strategy_catalog.legacy_mindsets).map(([name, description]) => html`<div class="notes"><b>${name}</b><div class="small mute">${description}</div></div>`)}</div>
    <p class="small mute">Aliases: ${Object.entries(c.strategy_catalog.legacy_aliases.strategies).map(([alias, target]) => `${alias} → ${target}`).join(' · ')} · ${Object.entries(c.strategy_catalog.legacy_aliases.mindsets).map(([alias, target]) => `${alias} → ${target}`).join(' · ')}</p></section>
  <section class="sec"><div class="sec-h"><h2>Behaviour</h2><span class="mute small">What it watches and how often it thinks</span></div><div class="set-grid">${TUNE_GROUPS.behaviour.map(tune)}</div></section>
  <section class="sec"><div class="sec-h"><h2>Risk limits</h2><span class="mute small">Hard caps. Neither the model nor chat can go past these.</span></div><div class="set-grid">${TUNE_GROUPS.risk.map(tune)}</div>
    <div style="margin-top:20px"><button class="btn primary" data-act="tsave">Save behaviour and risk</button></div></section>
  <section class="sec"><div class="sec-h"><h2>World feed</h2><span class="mute small">Native public market and macro feeds, cached in Cthulu</span></div>
    <label class="f">Native Cthulu feeds<select id="wNative"><option value="true" ${c.world.native_enabled ? 'selected' : ''}>Enabled</option><option value="false" ${!c.world.native_enabled ? 'selected' : ''}>Disabled</option></select></label>
    <div class="set-grid"><label class="f wide">API URL<input type="url" id="wUrl" value="${c.world.url}" placeholder="https://your-aggregator.example/api"></label>
    <label class="f">API key<input type="password" id="wKey" placeholder="${c.world.has_key ? 'Saved. Paste to replace' : 'Optional'}" autocomplete="off"></label>
    <label class="f">Refresh every (minutes)<input type="number" id="wRef" min="1" value="${c.world.refresh_min}"></label>
    <label class="f">Auth header<input type="text" id="wHdr" value="${c.world.header}"></label><label class="f">Scheme<input type="text" id="wSch" value="${c.world.scheme}" placeholder="Bearer"></label>
    <label class="f wide">Paths to fetch (comma separated, optional)<input type="text" id="wPaths" value="${c.world.paths}" placeholder="/geopolitics, /markets, /events"></label></div></div>
    <p class="mute small" style="margin:12px 0">Built-in feeds: CoinGecko Bitcoin USD, US 10-year Treasury yield, broad dollar index, and WTI spot price. Snapshots are cached in the agent database; no external aggregator is required. Optional push endpoint: <b>/api/world/ingest</b>.</p>
    <div class="set-grid">${Object.entries(c.world.native_feeds || {}).map(([id, feed]) => html`<div class="notes"><b>${id}</b> <span class="${feed.status === 'ok' ? 'lumen' : feed.status === 'stale' || feed.status === 'unavailable' ? 'loss' : 'mute'}">${feed.status}</span><br><span class="small">${feed.description}</span></div>`)}</div>
    <div style="display:flex;gap:10px;flex-wrap:wrap"><button class="btn primary" data-act="world-save">Save</button><button class="btn" data-act="world-refresh">Fetch now</button></div></section>
  <section class="sec"><div class="sec-h"><h2>Broker</h2><span class="mute small">${c.broker.connected ? 'Connected' : 'Not connected'}</span></div>
    <div class="seg" style="margin-bottom:16px"><button data-act="bk" data-b="paper" aria-pressed="${(S.bk || c.broker.broker) === 'paper'}">Paper (simulated)</button><button data-act="bk" data-b="mt5" aria-pressed="${(S.bk || c.broker.broker) === 'mt5'}">MetaTrader 5</button></div>
    ${(S.bk || c.broker.broker) === 'mt5' ? html`<div class="set-grid"><label class="f">Login<input type="text" id="mLogin" value="${c.broker.mt5_login}" inputmode="numeric"></label><label class="f">Password<input type="password" id="mPass" placeholder="${c.broker.has_password ? 'Saved. Paste to replace' : ''}" autocomplete="off"></label>
      <label class="f">Server<input type="text" id="mServer" value="${c.broker.mt5_server}"></label><label class="f">Terminal path (optional)<input type="text" id="mPath" value="${c.broker.mt5_path}"></label>
      <div class="rng wide"><div class="top"><span>Allow fully autonomous trading on a real-money account</span></div><div class="seg"><button data-act="live" data-v="1" aria-pressed="${c.broker.live_confirm}">Allowed</button><button data-act="live" data-v="0" aria-pressed="${!c.broker.live_confirm}">Ask me first</button></div></div></div>`
      : html`<div class="set-grid">${tune('PAPER_BALANCE')}${tune('PAPER_SPEED')}</div><p class="mute small" style="margin-top:10px">The paper market is simulated and includes stop runs. It starts fresh whenever you reconnect.</p>`}
    <div style="margin-top:18px"><button class="btn primary" data-act="bk-save">Save and reconnect</button></div></section>`);
}
const modelList = (ms, cur, f = '') => ms.filter((m) => !f || (m.id + ' ' + (m.name || '')).toLowerCase().includes(f.toLowerCase())).slice(0, 300).map((m) => html`<button role="option" aria-selected="${m.id === cur}" data-act="pick-model" data-id="${m.id}"><span>${m.id}</span>${m.free ? html`<span class="chip lumen">free</span>` : ''}</button>`);

/* ------------------------------------------------------------------ actions */
const val$ = (id) => ($('#' + id) ? $('#' + id).value.trim() : '');
const ACTIONS = {
  'network-mode': async (b) => {
    const mode = b.dataset.mode;
    if (mode !== 'loopback' && !(await ask(
      `Enable ${mode === 'lan' ? 'LAN' : 'Tailscale'} access?`,
      'Remote devices can reach the dashboard, but must provide its shared token to use chat, view account data, or control trading. Restart the agent to apply this network change.',
      'Save access mode',
      true,
    ))) return;
    const r = await guard(() => api('/api/config/network', { mode }), `Dashboard access mode saved: ${mode}`);
    if (!r) return;
    S.config = r;
    paintSettings();
    if (r.token_once) {
      setToken(r.token_once);
      window.prompt('Copy and keep this one-time dashboard token. You will need it on remote devices:', r.token_once);
    }
    if (r.restart_required) toast('Restart the agent to apply the new network binding.', 'ok');
  },
  'execution-mode': async (b) => {
    const mode = b.dataset.mode;
    if (mode === 'agentic' && !(await ask('Enable hybrid execution?', 'The Legacy engine keeps running. The agent will also be able to place and manage orders under its autonomy and risk settings. Existing positions may be adopted and managed.', 'Enable hybrid mode', true))) return;
    if (mode === 'legacy' && !(await ask('Disable Agentic trade actions?', 'The Legacy engine keeps running, but the agent will no longer place or manage orders. Flatten positions and cancel pending orders first.', 'Enable Legacy-only mode', true))) return;
    const r = await guard(() => api('/api/config/execution', { mode }), `Execution owner set to ${mode}`);
    if (r) { S.config = r; paintSettings(); refreshState(true); }
  },
  'system-kill': async () => {
    if (!(await ask('Stop Cthulu and the Agent?', 'The persistent kill switch stops both trading services and prevents automatic restarts. Open positions are not closed; broker-side stops remain in effect.', 'Kill and stay down', true))) return;
    const r = await guard(() => api('/api/system/kill', {}));
    if (r) {
      toast('Kill switch engaged. Cthulu services are stopping.', 'ok');
      S.killSwitchActive = true;
      if (S.config?.system) S.config.system.kill_switch_active = true;
      paintShell();
      if (S.route === 'settings') paintSettings();
    }
  },
  'system-restart': async () => {
    if (!(await ask('Restart Cthulu services?', 'This restarts the Legacy engine and Agent dashboard using the saved mode. The agent may resume autonomous order actions; HFT runs its safety preflight first.', 'Restart services', true))) return;
    const r = await guard(() => api('/api/system/restart', {}));
    if (r) toast('Restart queued. The dashboard may briefly disconnect while services restart.', 'ok');
  },
  think: () => guard(() => api('/api/control', { action: 'think_now' }), 'Thinking now'),
  replan: () => guard(() => api('/api/control', { action: 'think_now', replan: true }), 'Re-planning'),
  pause: () => guard(() => api('/api/control', { action: S.state.status.paused ? 'resume' : 'pause' }).then(() => refreshState(true))),
  reconnect: () => guard(async () => { const r = await api('/api/control', { action: 'reconnect' }); if (!r.ok) throw new Error(r.error || 'Could not connect'); await refreshState(true); }, 'Connected'),
  approve: (b) => guard(async () => { const r = await api('/api/proposals/' + b.dataset.id, { approve: true }); if (!r.ok) throw new Error(r.error || r.detail); await refreshState(true); }, 'Approved'),
  reject: (b) => guard(() => api('/api/proposals/' + b.dataset.id, { approve: false }).then(() => refreshState(true))),
  close: async (b) => { if (await ask('Close this position?', 'It closes at the current market price.', 'Close position', true)) guard(() => api(`/api/positions/${b.dataset.t}/close`, {}).then(() => refreshState(true)), 'Closed'); },
  cancel: (b) => guard(() => api(`/api/orders/${b.dataset.t}/cancel`, {}).then(() => refreshState(true)), 'Order cancelled'),
  flatten: async () => { if (await ask('Flatten everything?', 'Closes every open position and cancels every resting order.', 'Flatten', true)) guard(() => api('/api/control', { action: 'flatten' }).then(() => refreshState(true)), 'Flattened'); },
  tick: (b) => guard(() => api('/api/todos/' + b.dataset.id, { status: b.dataset.done === '1' ? 'open' : 'done' }, 'PATCH')).then(loadTodos),
  drop: (b) => guard(() => api('/api/todos/' + b.dataset.id, undefined, 'DELETE')).then(loadTodos),
  jf: (b) => { S.jf.kind = b.dataset.k; $$('[data-act=jf]').forEach((x) => x.setAttribute('aria-pressed', x === b)); loadJournal(true); },
  jmore: () => loadJournal(false),
  quick: (b) => sendChat(b.dataset.q),
  skstatus: (b) => guard(() => api(`/api/playbook/${b.dataset.n}/status`, { status: b.dataset.s }), 'Updated').then(loadSkills),
  skedit: (b) => { const s = SK.find((x) => x.name === b.dataset.n); $('#skName').value = s.name; $('#skKind').value = s.kind; $('#skBody').value = s.body; $('#skFormT').textContent = 'Edit ' + s.name.replaceAll('_', ' '); $('#skForm').scrollIntoView({ behavior: 'smooth', block: 'center' }); },
  skhist: async (b) => { const box = $('#hist-' + b.dataset.n); if (box.innerHTML) return (box.innerHTML = ''); const r = await guard(() => api(`/api/playbook/${b.dataset.n}/versions`)); if (r) put(box, html`<div class="notes">${r.versions.map((v) => html`<div style="margin-bottom:10px"><b>v${v.version}</b> <span class="mute small">${rel(v.ts)}${v.reason ? ' · ' + short(v.reason, 120) : ''}</span><div style="white-space:pre-wrap;margin-top:4px">${v.body}</div></div>`)}</div>`); },
  prov: (b) => { S.prov = b.dataset.p; paintSettings(); },
  'pick-model': (b) => { $('#modelIn').value = b.dataset.id; $$('#modelList [role=option]').forEach((x) => x.setAttribute('aria-selected', x === b)); },
  'llm-discover': async (b) => { b.disabled = true; const r = await guard(() => api('/api/models/discover', { provider: S.prov, api_key: val$('apiKey'), base_url: val$('baseUrl'), account_id: val$('accountId'), gateway_id: val$('gatewayId') })); b.disabled = false; if (r) { S.models[S.prov] = r.models; const keep = { b: val$('baseUrl'), k: $('#apiKey').value, m: val$('modelIn'), a: val$('accountId'), g: val$('gatewayId') }; paintSettings(); if ($('#baseUrl')) $('#baseUrl').value = keep.b; $('#apiKey').value = keep.k; $('#modelIn').value = keep.m; if ($('#accountId')) $('#accountId').value = keep.a; if ($('#gatewayId')) $('#gatewayId').value = keep.g; toast(`Found ${r.models.length} models`, 'ok'); } },
  'llm-save': async (b) => { const body = { provider: S.prov, model: val$('modelIn'), activate: b.dataset.use === '1' }; if ($('#baseUrl')) body.base_url = val$('baseUrl'); if ($('#accountId')) body.account_id = val$('accountId'); if ($('#gatewayId')) body.gateway_id = val$('gatewayId'); if (val$('apiKey')) body.api_key = val$('apiKey'); const r = await guard(() => api('/api/config/llm', body), body.activate ? 'Saved and switched' : 'Saved'); if (r) { S.config = r; refreshState(true); paintSettings(); } },
  'llm-test': async (b) => { b.disabled = true; const keyTyped = val$('apiKey'); const body = { provider: S.prov, model: val$('modelIn') }; if ($('#baseUrl')) body.base_url = val$('baseUrl'); if ($('#accountId')) body.account_id = val$('accountId'); if ($('#gatewayId')) body.gateway_id = val$('gatewayId'); if (keyTyped) body.api_key = keyTyped; await api('/api/config/llm', body).catch(() => {}); const r = await guard(() => api('/api/llm/test', { provider: S.prov })); b.disabled = false; if (r) toast(r.ok ? `Connected. ${r.model} answered in ${r.latency}s` : 'Failed: ' + r.error, r.ok ? 'ok' : 'bad'); S.config = await api('/api/config'); paintSettings(); },
  'llm-clearkey': async () => { if (await ask('Remove this key?', 'It is deleted from your .env file.', 'Remove', true)) { S.config = await api('/api/config/llm', { provider: S.prov, clear_key: true }); paintSettings(); toast('Key removed', 'ok'); } },
  tchoice: (b) => { PEND[b.dataset.k] = b.dataset.v; paintSettings(); },
  tsave: async () => { const body = { ...PEND }; $$('[data-key]').forEach((el) => { if (el.value !== undefined && (el.type === 'range' || el.type === 'text' || el.type === 'number')) body[el.dataset.key] = el.value; }); const r = await guard(() => api('/api/config/agent', body), 'Saved'); if (r) { S.config = r; Object.keys(PEND).forEach((k) => delete PEND[k]); refreshState(true); paintSettings(); } },
  'world-save': async () => { const body = { native_enabled: val$('wNative') === 'true', url: val$('wUrl'), header: val$('wHdr'), scheme: val$('wSch'), paths: val$('wPaths'), refresh_min: val$('wRef') }; if (val$('wKey')) body.api_key = val$('wKey'); const r = await guard(() => api('/api/config/world', body), 'World feed saved'); if (r) { S.config = r; paintSettings(); } },
  'world-refresh': async () => { const r = await guard(() => api('/api/world/refresh', {})); if (r) { toast(r.ok ? 'Fetched. The agent will digest it next pass' : 'Fetch failed: ' + (r.error || 'no data'), r.ok ? 'ok' : 'bad'); refreshState(true); } },
  bk: (b) => { S.bk = b.dataset.b; paintSettings(); },
  live: async (b) => { if (b.dataset.v === '1' && !(await ask('Allow autonomous trading with real money?', 'Only enable this after the agent has proved itself on paper or a demo account. It will place and close orders without asking.', 'Allow', true))) return; S.config = await api('/api/config/broker', { live_confirm: b.dataset.v === '1' }); paintSettings(); },
  'bk-save': async () => { const kind = S.bk || S.config.broker.broker; const body = { broker: kind }; if (kind === 'mt5') Object.assign(body, { mt5_login: val$('mLogin'), mt5_server: val$('mServer'), mt5_path: val$('mPath') }, val$('mPass') ? { mt5_password: val$('mPass') } : {}); else { const bal = $('[data-key=PAPER_BALANCE]'), sp = $('[data-key=PAPER_SPEED]'); await guard(() => api('/api/config/agent', { PAPER_BALANCE: bal.value, PAPER_SPEED: sp.value })); } await guard(() => api('/api/config/broker', body)); const r = await guard(() => api('/api/control', { action: 'reconnect' })); if (r) { toast(r.ok ? 'Reconnected' : 'Could not connect: ' + r.error, r.ok ? 'ok' : 'bad'); S.config = await api('/api/config'); refreshState(true); paintSettings(); } },
};
shell.addEventListener('click', (e) => { const b = e.target.closest('[data-act]'); if (b && ACTIONS[b.dataset.act]) { e.preventDefault(); ACTIONS[b.dataset.act](b); } });
let jqT;
main.addEventListener('input', (e) => {
  const t = e.target;
  if (t.id === 'jq') { clearTimeout(jqT); jqT = setTimeout(() => { S.jf.q = t.value.trim(); loadJournal(true); }, 260); }
  if (t.id === 'modelFilter') put($('#modelList'), modelList(S.models[S.prov] || [], val$('modelIn'), t.value));
  if (t.type === 'range') { const l = $(`[data-lab="${t.dataset.key}"]`); if (l) l.textContent = t.value; PEND[t.dataset.key] = t.value; }
});

/* ------------------------------------------------------------------ live events */
let throttle = 0;
function onEvent(e) {
  const d = e.data || {};
  switch (e.type) {
    case 'phase': if (S.state) { S.state.status.phase = d.phase; S.state.status.phase_detail = d.detail; } paintLive(); break;
    case 'llm': S.llmBusy = d.busy > 0; S.eye && S.eye.set({ busy: S.llmBusy }); if (d.ok === false && d.error) toast(`Model error: ${d.error}`, 'bad'); break;
    case 'journal': { const en = d.entry; if (en.kind === 'system') break; S.feed.unshift(en); S.feed.length = Math.min(S.feed.length, 30);
      if (S.route === 'overview') paintFeed(en.id); if (S.route === 'loop') loadThinking();
      if (S.route === 'journal' && !S.jf.q) { const ks = JF.find((f) => f[0] === S.jf.kind)[2]; if (ks === 'all' || ks.split(',').includes(en.kind)) { S.jEntries.unshift(en); paintJournal(); } } break; }
    case 'state': case 'plan': case 'proposal': case 'playbook': case 'world': refreshState(); if (e.type === 'playbook' && S.route === 'playbook') loadSkills(); break;
    case 'trade': S.eye && S.eye.blink(); refreshState(true); if (d.kind === 'filled') toast(`${d.symbol} order filled`, 'ok'); if (d.kind === 'closed') toast(`${d.symbol} closed ${sgn(d.pnl)} (${sgn(d.r)}R)`, d.pnl >= 0 ? 'ok' : ''); if (d.kind === 'placed') toast(`Order placed on ${d.symbol}`, 'ok'); break;
    case 'todo': if (S.route === 'loop') loadTodos(); break;
    case 'alert': toast(d.message, d.level === 'error' ? 'bad' : ''); break;
    default: break;
  }
  if (Date.now() - throttle > 20000 && S.route === 'overview') { throttle = Date.now(); loadEquity().then(() => paintLive()); }
}

/* ------------------------------------------------------------------ router */
const VIEWS = { overview: [viewOverview, mountOverview], loop: [viewLoop, mountLoop], journal: [viewJournal, mountJournal], playbook: [viewPlaybook, mountPlaybook], chat: [viewChat, mountChat], settings: [viewSettings, mountSettings] };
async function route() {
  const r = (location.hash || '#overview').slice(1);
  S.route = VIEWS[r] ? r : 'overview';
  if (S.eye) { S.eye.destroy(); S.eye = null; }
  const [v, m] = VIEWS[S.route];
  main.dataset.route = S.route;
  put(main, await v()); paintShell(); window.scrollTo(0, 0); main.focus({ preventScroll: true });
  document.title = (NAV.find((n) => n[0] === S.route)[1]) + ' · Cthulu';
  if (S.route === 'overview' || S.route === 'playbook') await loadFeed();
  m();
}
addEventListener('hashchange', route);
(async function init() {
  paintShell();
  await Promise.all([refreshState(true), loadEquity(), loadFeed()]);
  await route();
  openStream(onEvent, (ok) => { S.live = ok; paintRailFoot(); if (ok) refreshState(true); });
  setInterval(() => { if (!S.live) refreshState(true); }, 12000);
  setInterval(() => {
    const statsDate = S.state?.stats?.today?.date;
    if (statsDate && statsDate !== new Date().toISOString().slice(0, 10)) refreshState(true);
  }, 60000);
})();
