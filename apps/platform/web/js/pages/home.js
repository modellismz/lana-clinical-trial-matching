// Home: the whole patient map. Every real cohort patient is one dot; similar patients are linked and the
// force layout pulls them together, so a cluster on screen is a group of patients with the same facts.
import { $, $$, esc, fmt, pct, j, S, pageTitle, tip } from '../common.js';
import { PatientGraph } from '../graph.js';

let D = null;       // web/data/patient_map.json
let C = {};         // column name -> index
let graph = null;
let mode = 'group';

const STUDY_COLORS = ['#ffb547', '#e8d96b', '#ff7fa3', '#55d6e8'];
const BM = { 0: ['nd', 'not done'], 1: ['fl', 'failed'], 2: ['in', 'insufficient'], 3: ['neg', 'wild-type'], 4: ['pos', 'mutant'], 5: ['pos', 'non-V600'] };
const SITE_LABEL = { liver: 'liver', lung: 'lung', lymph_node: 'lymph node', peritoneum: 'peritoneum', bone: 'bone', brain: 'brain', ovary: 'ovary' };

// Colour modes: each gives a legend (ordered keys) and a key per node.
const MODES = {
  group: {
    label: 'Biomarker subgroup',
    legend: () => D.groups.map((g, i) => ({ k: i, label: g.label, color: g.color, n: g.n })),
    key: (n) => n[C.group],
  },
  study: {
    label: 'Source cohort',
    legend: () => D.studies.map((s, i) => ({ k: i, label: s.short, color: STUDY_COLORS[i], n: s.n, title: s.label })),
    key: (n) => n[C.study],
  },
  msi: {
    label: 'MSI testing',
    legend: () => {
      const keys = [[4, 'MSI-high', '#b49bff'], [3, 'MSS', '#52e0a1'], [0, 'not done', '#ffb547'], [1, 'failed / insufficient', '#ff6e6e']];
      const cnt = {};
      D.nodes.forEach((n) => { const k = MODES.msi.key(n); cnt[k] = (cnt[k] || 0) + 1; });
      return keys.map(([k, label, color]) => ({ k, label, color, n: cnt[k] || 0 }));
    },
    key: (n) => (n[C.msi] === 2 ? 1 : n[C.msi]),
  },
  stage: {
    label: 'Stage',
    legend: () => [{ k: 1, label: 'Stage IV / metastatic', color: '#ff7fa3', n: D.stage_iv }, { k: 0, label: 'Stage I–III', color: '#55d6e8', n: D.n - D.stage_iv }],
    key: (n) => n[C.stage_iv],
  },
};

export async function init() {
  D = await j('data/patient_map.json');
  D.columns.forEach((c, i) => { C[c] = i; });
}

export function render() {
  if (!$('#pmap')) skeleton();
  const di = C.demo;
  const idx = D.nodes.findIndex((n) => n[di] === S.sel);
  graph.setPinned(idx);
  $('#pin-note').innerHTML = idx >= 0 ? `<i class="pinring"></i>${esc(S.sel)} is open in the app` : '';
}

function skeleton() {
  pageTitle('Patient map', `<span><b>${fmt(D.n)}</b> real patients</span><span><b>${D.studies.length}</b> public cohorts</span><span><b>${fmt(D.n_profiles)}</b> distinct clinical profiles</span><span><b>${fmt(D.edges.length)}</b> similarity links · k=${D.k}</span><span class="tagc real">REAL</span>`);
  $('#page').innerHTML = `
    <div class="home-grid">
      <section class="panel pmap-panel">
        <div class="ph"><h3>Every patient we hold, placed next to the patients most like them</h3>
          <span class="right"><span id="pin-note" class="pin-note"></span><span id="sim-state" class="sim-state">laying out…</span><button class="btn ghost sm" id="refit" title="Fit the whole map">Fit</button></span></div>
        <div class="pb flush pmap-wrap">
          <canvas id="pmap" aria-label="Patient similarity map: one dot per patient, lines between similar patients"></canvas>
          <div class="pmap-ctl" role="group" aria-label="Colour by">
            <span class="lbl">colour by</span>
            ${Object.entries(MODES).map(([k, m]) => `<button data-mode="${k}" aria-pressed="${k === mode}">${m.label}</button>`).join('')}
          </div>
          <div class="pmap-legend" id="legend" role="group" aria-label="Legend"></div>
          <div class="pmap-hint">drag to pan · scroll to zoom · hover a dot · <i class="ring"></i> demo patient</div>
        </div>
      </section>
      <aside class="home-side">
        <section class="panel"><div class="ph"><h3>What the data holds</h3><span class="right">share of ${fmt(D.n)} with a result</span></div>
          <div class="pb avail" id="avail"></div></section>
        <section class="panel"><div class="ph"><h3>By cohort</h3><span class="right">cBioPortal</span></div>
          <div class="pb cohorts" id="cohorts"></div></section>
        <section class="panel"><div class="ph"><h3>Patient</h3><span class="right" id="pcard-sub">hover or click a dot</span></div>
          <div class="pb pcard" id="pcard"><p class="empty">A dot is one de-identified patient. Its links go to the patients whose recorded facts match most closely: RAS/RAF/HER2/PIK3CA/MSI results <em>and</em> whether each test was done, stage, metastasis sites, side, age, sex, TMB and cohort.</p></div></section>
        <section class="panel how"><div class="ph"><h3>How to read it</h3></div>
          <div class="pb"><ul>
            <li><b>Proximity is similarity.</b> Each patient links to its ${D.k} most similar clinical profiles (weighted cosine, links below ${D.min_sim} dropped). A spring layout pulls linked patients together.</li>
            <li><b>Dense knots</b> are many patients with the same profile. Loose strands are rare combinations.</li>
            <li><b>Not tested is its own feature.</b> A patient with MSI not done sits with other untested patients, never with MSS.</li>
            <li>Only <span class="tagc real">REAL</span> cBioPortal facts are used. Simulated fields (ECOG, labs) are not.</li>
          </ul></div></section>
      </aside>
    </div>`;

  graph = new PatientGraph($('#pmap'), D, {
    onHover: (h) => {
      if (!h) return tip(null);
      tip(cardHTML(h.i, true), h.x, h.y, 'pt');
      $('#pcard').innerHTML = cardHTML(h.i, false);
      $('#pcard-sub').textContent = `#${h.i + 1} · ${neighbourCount(h.i)} links`;
    },
    onSelect: (i) => {
      if (i == null) return;
      const demo = D.nodes[i][C.demo];
      if (demo) { location.href = `sources.html?p=${demo}`; return; }
      $('#pcard').innerHTML = cardHTML(i, false);
      $('#pcard-sub').textContent = `#${i + 1} · ${neighbourCount(i)} links · selected`;
    },
    onProgress: (p, done) => {
      const el = $('#sim-state');
      el.textContent = done ? 'settled' : `laying out… ${Math.round(p * 100)}%`;
      el.dataset.settled = done;
      $('#pmap').dataset.settled = done;
    },
  });
  applyMode();
  $('#refit').addEventListener('click', () => graph.resetCamera());
  $('.pmap-ctl').addEventListener('click', (e) => {
    const b = e.target.closest('[data-mode]');
    if (!b) return;
    mode = b.dataset.mode;
    $$('.pmap-ctl button').forEach((x) => x.setAttribute('aria-pressed', x.dataset.mode === mode));
    applyMode();
  });
  $('#legend').addEventListener('click', (e) => {
    const b = e.target.closest('[data-k]');
    if (!b) return;
    const on = b.getAttribute('aria-pressed') === 'true';
    $$('#legend button').forEach((x) => x.setAttribute('aria-pressed', 'false'));
    if (on) graph.setIsolate(null);
    else { b.setAttribute('aria-pressed', 'true'); graph.setIsolate(+b.dataset.k); }
  });

  $('#avail').innerHTML = D.availability.map((a) => `
    <div class="av"><span>${a.label}</span>
      <div class="bar" title="${pct(a.done)} with a result${a.failed ? `, ${pct(a.failed)} failed or insufficient` : ''}"><i style="width:${a.done * 100}%"></i>${a.failed ? `<i class="fl" style="width:${a.failed * 100}%"></i>` : ''}</div>
      <b>${pct(a.done)}</b></div>`).join('') + `<div class="legend"><span><i style="background:var(--c-real)"></i>result on record</span><span><i style="background:var(--not)"></i>test failed / insufficient</span><span>rest: not done</span></div>`;
  const maxn = Math.max(...D.studies.map((s) => s.n));
  $('#cohorts').innerHTML = D.studies.map((s, i) => `
    <div class="co"><span style="--cc:${STUDY_COLORS[i]}"><i></i>${s.short}</span><small>${esc(s.label)}</small>
      <div class="bar"><i style="width:${s.n / maxn * 100}%;background:${STUDY_COLORS[i]}"></i></div><b>${fmt(s.n)}</b></div>`).join('');
}

function applyMode() {
  const m = MODES[mode];
  const legend = m.legend();
  const colorOf = new Map(legend.map((l) => [l.k, l.color]));
  const keys = new Int16Array(D.n);
  const colors = new Array(D.n);
  D.nodes.forEach((n, i) => { const k = m.key(n); keys[i] = k; colors[i] = colorOf.get(k) || '#6e7f93'; });
  graph.setColors(colors, keys);
  $('#legend').innerHTML = legend.map((l) => `<button data-k="${l.k}" style="--cc:${l.color}" aria-pressed="false" title="${esc(l.title || l.label)} · click to isolate"><i></i>${esc(l.label)}<small>${fmt(l.n)}</small></button>`).join('');
}

const neighbourCount = (i) => graph.adj[i].length;

function bm(name, code, variant) {
  const [cls, txt] = BM[code] || ['nd', '?'];
  let label = txt;
  if (code === 4) label = name === 'HER2' ? 'amplified' : name === 'MSI' ? 'MSI-high' : name === 'BRAF' ? 'V600E mutant' : variant ? `${variant} mutant` : 'mutant';
  if (code === 5) label = 'non-V600 mutant';
  if (code === 3) label = name === 'HER2' ? 'not amplified' : name === 'MSI' ? 'MSS' : 'wild-type';
  return `<span class="bmrow"><span class="bn">${name}</span><span class="chip ${cls}">${esc(label)}</span></span>`;
}

function cardHTML(i, compact) {
  const n = D.nodes[i];
  const s = D.studies[n[C.study]];
  const g = D.groups[n[C.group]];
  const sex = ['male', 'female'][n[C.sex]] || 'sex n/a';
  const side = ['left-sided', 'right-sided'][n[C.side]];
  const mets = D.sites.filter((_, k) => n[C.mets] >> k & 1).map((x) => SITE_LABEL[x]);
  const demo = n[C.demo];
  const head = `<b style="--cc:${g.color}"><i class="gdot"></i>${esc(g.label)}</b>
    <small>${esc(s.short)} · ${n[C.age] != null ? n[C.age] + ' y' : 'age n/a'} · ${sex} · ${n[C.stage_iv] ? 'stage IV' : 'stage I–III'}${side ? ' · ' + side : ''}${n[C.tmb] != null ? ` · TMB ${n[C.tmb]}` : ''}</small>`;
  const bms = `<div class="bms">${bm('KRAS', n[C.kras], n[C.kras_variant])}${bm('NRAS', n[C.nras])}${bm('BRAF', n[C.braf])}${bm('HER2', n[C.her2])}${bm('MSI', n[C.msi])}${bm('PIK3CA', n[C.pik3ca])}</div>`;
  const metsRow = `<small class="mets">${mets.length ? 'metastases: ' + mets.join(', ') : 'no metastasis site recorded'}</small>`;
  const demoRow = demo ? `<small class="demo"><i class="ring"></i>demo patient <b>${esc(demo)}</b>${compact ? ' · click to open' : ` · <a href="sources.html?p=${demo}">open data input</a>`}</small>` : '';
  return head + bms + metsRow + demoRow;
}
