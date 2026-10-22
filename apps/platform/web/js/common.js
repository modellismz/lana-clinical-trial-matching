// Shared state, formatting and the page shell (top bar, patient rail) used by every page.
import { reassess, LABELS, daysAgo, REF_DATE } from './evaluator.js';
import { anatomySVG, anatomyCompact } from './anatomy.js';

export const $ = (s, el = document) => el.querySelector(s);
export const $$ = (s, el = document) => [...el.querySelectorAll(s)];
export const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
export const pct = (x) => `${Math.round(x * 100)}%`;
export const fmt = (n) => Number(n).toLocaleString('en-US');
export const j = (u) => fetch(u).then((r) => { if (!r.ok) throw new Error(u); return r.json(); });
export const REF_ISO = REF_DATE.toISOString().slice(0, 10);
export { LABELS, daysAgo };

export const PAGES = [
  ['index.html', 'home', 'Patient map'],
  ['sources.html', 'sources', 'Data input'],
  ['match.html', 'match', 'Trial match'],
  ['embed.html', 'embed', 'Embedding'],
  ['referral.html', 'referral', 'Referral'],
  ['evidence.html', 'evidence', 'Evidence'],
  ['evaluation.html', 'evaluation', 'Evaluation'],
];

export const S = { patients: [], bench: null, sel: null, match: null, open: null, whatif: {}, filter: 'all', api: false, page: null, render: null };

/* ---------- formatting ---------- */
const UNIT = { anc: '×10⁹/L', platelets: '×10⁹/L', hemoglobin: 'g/dL', creatinine: 'mg/dL', crcl: 'mL/min', bilirubin: 'mg/dL', ast: 'U/L', alt: 'U/L', creatinine_uln: '× ULN', bilirubin_uln: '× ULN', transaminase_uln: '× ULN' };

export function valueText(name, f) {
  const v = f.value;
  if (v === null || v === undefined) return '—';
  switch (name) {
    case 'kras': case 'nras': return v === 'mutant' ? `${f.variant || ''} mutant`.trim() : 'wild-type';
    case 'braf': return v === 'mutant' ? 'V600E mutant' : v === 'non_v600_mutant' ? `non-V600 ${f.variant || ''}` : 'wild-type';
    case 'pik3ca': return v === 'mutant' ? `${f.variant || ''} mutant` : 'wild-type';
    case 'her2': return v === 'amplified' ? 'amplified' : 'not amplified';
    case 'msi': return v === 'msi_high' ? 'MSI-high' : 'MSS';
    case 'tmb': return `${Number(v).toFixed(1)} mut/Mb`;
    case 'stage_iv': return v ? 'stage IV / metastatic' : 'stage I–III';
    case 'measurable': return v ? 'measurable lesion' : 'none';
    case 'brain_mets': return v ? 'present' : 'negative';
    case 'consent': return v ? 'recorded' : 'not recorded';
    case 'hiv': case 'hbv': case 'hcv': return v;
    case 'ecog': return `ECOG ${v}`;
    case 'prior_lines': return `${v} prior line${v === 1 ? '' : 's'}`;
    default: return typeof v === 'number' ? `${v}${UNIT[name] ? ' ' + UNIT[name] : ''}` : String(v).replace('_', ' ');
  }
}

export function isPositive(name, f) {
  return (name === 'msi' && f.value === 'msi_high') || (name === 'her2' && f.value === 'amplified') || f.value === 'mutant' || f.value === 'non_v600_mutant';
}

export function chip(name, f) {
  if (f.status === 'done') return `<span class="chip ${isPositive(name, f) ? 'pos' : 'neg'}">${esc(valueText(name, f))}</span>`;
  const m = { not_done: ['nd', 'not done'], pending: ['pe', 'pending'], failed: ['fl', 'failed'], insufficient: ['in', 'insufficient sample'] }[f.status] || ['nd', f.status];
  return `<span class="chip ${m[0]}">${m[1]}</span>`;
}

export const srcTag = (src) => (String(src).startsWith('REAL') ? '<span class="tagc real">REAL</span>' : '<span class="tagc sim">SIM</span>');
export const dateBit = (f, win = 28) => {
  if (!f.date) return '';
  const d = daysAgo(f.date);
  return `<small class="when ${d > win ? 'stale' : ''}">${d} d${d > win ? ' · stale' : ''}</small>`;
};
export const kv = (rows) => rows.map(([k, v]) => `<div class="kv"><dt>${k}</dt><dd>${v}</dd></div>`).join('');

/* ---------- patient + what-if ---------- */
export const patient = () => S.patients.find((p) => p.id === S.sel);
export const openMatch = () => S.match?.matches.find((q) => q.nct_id === S.open) || S.match?.matches[0] || null;

export function effectiveFacts() {
  const base = structuredClone(patient().facts);
  Object.entries(S.whatif).forEach(([k, patch]) => { base[k] = { ...(base[k] || {}), ...patch }; });
  return base;
}

export function liveMatch(m) {
  if (!Object.keys(S.whatif).length) return { ...m, rows: m.criteria, counts: m.counts, verdict: m.verdict, whatif: false };
  const r = reassess(m, effectiveFacts());
  const verdict = r.verdict === 'ready' && m.coverage < 0.4 ? 'provisional' : r.verdict;
  return { ...m, rows: r.rows, counts: r.counts, verdict, whatif: true };
}

export function whatifOptions(fact) {
  switch (fact) {
    case 'msi': return [{ label: 'MSS', patch: { value: 'mss' } }, { label: 'MSI-high', patch: { value: 'msi_high' } }];
    case 'her2': return [{ label: 'not amplified', patch: { value: 'not_amplified' } }, { label: 'amplified', patch: { value: 'amplified' } }];
    case 'kras': return [{ label: 'wild-type', patch: { value: 'wild_type', variant: null } }, { label: 'G12C mutant', patch: { value: 'mutant', variant: 'G12C' } }, { label: 'G12D mutant', patch: { value: 'mutant', variant: 'G12D' } }];
    case 'nras': return [{ label: 'wild-type', patch: { value: 'wild_type', variant: null } }, { label: 'mutant', patch: { value: 'mutant', variant: 'Q61K' } }];
    case 'braf': return [{ label: 'wild-type', patch: { value: 'wild_type', variant: null } }, { label: 'V600E', patch: { value: 'mutant', variant: 'V600E' } }, { label: 'non-V600', patch: { value: 'non_v600_mutant', variant: 'K601E' } }];
    case 'ecog': return [0, 1, 2, 3].map((n) => ({ label: `ECOG ${n}`, patch: { value: n } }));
    case 'brain_mets': return [{ label: 'MRI negative', patch: { value: false } }, { label: 'metastases present', patch: { value: true } }];
    case 'measurable': return [{ label: 'measurable lesion', patch: { value: true } }];
    case 'anc': return [{ label: 'new: 4.2', patch: { value: 4.2 } }];
    case 'platelets': return [{ label: 'new: 250', patch: { value: 250 } }];
    case 'hemoglobin': return [{ label: 'new: 12.0', patch: { value: 12 } }];
    case 'crcl': return [{ label: 'new: 90', patch: { value: 90 } }];
    case 'creatinine_uln': case 'bilirubin_uln': case 'transaminase_uln': return [{ label: 'new: 0.6 × ULN', patch: { value: 0.6 } }];
    case 'creatinine': return [{ label: 'new: 0.9', patch: { value: 0.9 } }];
    case 'bilirubin': return [{ label: 'new: 0.7', patch: { value: 0.7 } }];
    case 'hiv': case 'hbv': case 'hcv': return [{ label: 'negative', patch: { value: 'negative' } }];
    case 'consent': return [{ label: 'recorded', patch: { value: true } }];
    default: return [];
  }
}

const WI_KEY = 'lana.whatif';
export function loadWhatif() {
  try {
    const st = JSON.parse(sessionStorage.getItem(WI_KEY) || 'null');
    S.whatif = st && st.p === S.sel ? st.whatif : {};
  } catch { S.whatif = {}; }
}
export function saveWhatif() {
  try { sessionStorage.setItem(WI_KEY, JSON.stringify({ p: S.sel, whatif: S.whatif })); } catch { /* private mode */ }
}

/* ---------- population subgroup for the Thailand hotspots ---------- */
export function popKeyFor(facts) {
  if (facts.kras.status === 'done' && facts.kras.variant === 'G12C') return 'kras_g12c';
  if (facts.braf.status === 'done' && facts.braf.variant === 'V600E') return 'braf_v600e';
  if (facts.msi.status === 'done' && facts.msi.value === 'msi_high') return 'msi_h';
  if (facts.her2.status === 'done' && facts.her2.value === 'amplified') return 'her2_amp';
  if (facts.kras.status === 'done' && facts.kras.value === 'mutant') return 'kras_mut';
  if (facts.kras.status === 'done' && facts.nras.status === 'done' && facts.kras.value === 'wild_type' && facts.nras.value === 'wild_type') return 'ras_wt';
  return 'mcrc';
}

/* ---------- URL state ---------- */
export function url(file) {
  const q = new URLSearchParams();
  if (S.sel) q.set('p', S.sel);
  if (S.open) q.set('t', S.open);
  const s = q.toString();
  return file + (s ? '?' + s : '');
}
export function syncUrl() {
  const here = location.pathname.split('/').pop() || 'index.html';
  history.replaceState(null, '', url(here));
  $$('#nav a').forEach((a) => { a.href = url(a.dataset.file); });
}

/* ---------- shell ---------- */
export const FILTERS = [
  ['all', 'All', () => true],
  ['g12c', 'KRAS G12C', (p) => p.facts.kras.variant === 'G12C'],
  ['v600e', 'BRAF V600E', (p) => p.facts.braf.variant === 'V600E'],
  ['msih', 'MSI-high', (p) => p.facts.msi.value === 'msi_high'],
  ['her2', 'HER2 amp', (p) => p.facts.her2.value === 'amplified'],
  ['nd', 'MSI not done', (p) => p.facts.msi.status === 'not_done'],
  ['fail', 'Test failed', (p) => ['failed', 'insufficient'].includes(p.facts.msi.status)],
  ['asia', 'Asian cohort', (p) => p.study === 'crc_sysucc_2022'],
];

export function renderShell() {
  $('#nav').innerHTML = PAGES.map(([file, id, label], i) => `<a href="${url(file)}" data-file="${file}" class="${id === S.page ? 'on' : ''}${id === 'home' ? ' home' : ''}" ${id === S.page ? 'aria-current="page"' : ''}>${id === 'home' ? '<b aria-hidden="true">⌂</b>' : `<b>0${i}</b>`}${label}</a>`).join('');
  // Keep the current page visible in the horizontally scrollable mobile navigation.
  requestAnimationFrame(() => {
    const nav = $('#nav'), active = nav.querySelector('[aria-current="page"]');
    if (active && nav.scrollWidth > nav.clientWidth) nav.scrollLeft = active.offsetLeft - nav.offsetLeft - (nav.clientWidth - active.offsetWidth) / 2;
  });
  renderStatus();
  fetch('/api/health').then((r) => r.ok).then((ok) => { S.api = ok; renderStatus(); }).catch(() => {});
  if (!$('#plist')) return; // pages without the patient rail (home)
  $('#filters').innerHTML = FILTERS.map(([id, label]) => `<button class="fchip" data-f="${id}" aria-pressed="${id === S.filter}">${label}</button>`).join('');
  $('#filters').addEventListener('click', (e) => {
    const b = e.target.closest('[data-f]');
    if (!b) return;
    S.filter = b.dataset.f;
    $$('.fchip').forEach((x) => x.setAttribute('aria-pressed', x.dataset.f === S.filter));
    renderRail();
  });
  $('#plist').addEventListener('click', (e) => {
    const b = e.target.closest('[data-id]');
    if (b) selectPatient(b.dataset.id);
  });
  renderRail();
}

export function renderStatus() {
  const b = S.bench;
  const real = b.inventory.filter((x) => x.kind === 'REAL' && x.id !== 'ctgov' && x.id !== 'trec').reduce((a, x) => a + x.n, 0);
  $('#status').innerHTML = `
    <span class="pill"><i class="dot real"></i>${fmt(real)} patients</span>
    <span class="pill"><i class="dot trial"></i>${fmt(b.n_trials)} trials</span>
    <span class="pill"><i class="dot irisd"></i>IRIS · ${S.api ? 'live' : 'snapshot'}</span>`;
}

function pip(letter, name, f) {
  let cls = 'wt';
  if (f.status !== 'done') cls = { not_done: 'nd', failed: 'fl', insufficient: 'in', pending: 'pe' }[f.status];
  else if (isPositive(name, f)) cls = 'mut';
  return `<i class="pip ${cls}" title="${LABELS[name]}: ${esc(f.status === 'done' ? valueText(name, f) : f.status.replace('_', ' '))}">${letter}</i>`;
}

export function renderRail() {
  const pred = FILTERS.find((f) => f[0] === S.filter)[2];
  const list = S.patients.filter(pred);
  $('#rail-sub').textContent = `${list.length} / ${S.patients.length}`;
  $('#plist').innerHTML = list.map((p) => `
    <li><button class="pi" data-id="${p.id}" aria-pressed="${p.id === S.sel}">
      <span class="pid">${p.id}</span>
      <span class="meta">${p.study_short} · ${p.age ?? '—'} ${p.sex?.[0]?.toUpperCase() ?? ''}${p.side ? ' · ' + p.side : ''}</span>
      <span class="pips">${pip('K', 'kras', p.facts.kras)}${pip('N', 'nras', p.facts.nras)}${pip('B', 'braf', p.facts.braf)}${pip('H', 'her2', p.facts.her2)}${pip('M', 'msi', p.facts.msi)}</span>
      <span class="vd" title="ready · provisional · blocked"><i class="r">${p.verdicts.ready}</i><i class="p">${p.verdicts.provisional}</i><i class="b">${p.verdicts.blocked}</i></span>
    </button></li>`).join('');
}

export function renderRailAnat() {
  const p = patient();
  const el = $('#rail-anat');
  if (!p || !el) return;
  el.innerHTML = `<div class="ra-h"><span class="lbl">Tumour map</span><span class="tagc real">REAL</span><span class="ra-view">anterior</span></div><div class="ra-body">${anatomySVG(p)}${anatomyCompact(p)}</div>`;
}

export async function selectPatient(id, nct = null) {
  S.sel = id;
  $$('.pi').forEach((x) => x.setAttribute('aria-pressed', x.dataset.id === id));
  renderRailAnat();
  S.match = await j(`data/matches/${id}.json`);
  const keep = nct || S.open;
  S.open = S.match.matches.some((m) => m.nct_id === keep) ? keep : (S.match.matches[0]?.nct_id || null);
  loadWhatif();
  syncUrl();
  S.render?.();
}

export function setOpen(nct) {
  S.open = nct;
  syncUrl();
}

export function pageTitle(title, meta) {
  $('#pt').innerHTML = `<h1>${title}</h1><div class="meta">${meta}</div>`;
}

/* ---------- tooltip ---------- */
export function tip(html, x, y, cls = '') {
  const el = $('#tip');
  if (!html) { el.hidden = true; el.className = 'tip'; return; }
  if (el.innerHTML !== html) el.innerHTML = html;
  el.className = `tip ${cls}`;
  el.hidden = false;
  const w = el.offsetWidth, h = el.offsetHeight;
  el.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, x + 14)) + 'px';
  el.style.top = Math.max(8, Math.min(window.innerHeight - h - 8, y + 14)) + 'px';
}
