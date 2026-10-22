// 06 Evaluation: abridged golden-set evaluation of the retrieval stage, the automated schedules, and every match time from the last 7 days.
import { $, $$, esc, fmt, S, j, pageTitle, tip } from '../common.js';

let E = null;
export async function init() { E = await j('data/evaluation.json'); }

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const d2 = (n) => String(n).padStart(2, '0');
const when = (iso) => { if (!iso) return '—'; const d = new Date(iso); return `${MON[d.getMonth()]} ${d.getDate()} · ${d2(d.getHours())}:${d2(d.getMinutes())}`; };
function rel(iso) {
  if (!iso) return '';
  const m = Math.round((new Date(iso) - new Date(E.generated)) / 60000);
  const a = Math.abs(m), s = m < 0 ? 'ago' : 'ahead';
  const t = a < 60 ? `${a} min` : a < 48 * 60 ? `${Math.round(a / 60)} h` : `${Math.round(a / 1440)} d`;
  return `${t} ${s}`;
}
const num = (v, d = 2) => (v == null ? '—' : Number(v).toFixed(d));
const pill = (st) => `<span class="sp ${esc(st).replace(/\s/g, '-')}">${esc(st)}</span>`;
const ib = (v, cls = '') => (v == null ? '<span class="ib-none">—</span>' : `<span class="ib ${cls}"><i style="width:${Math.max(2, v * 100)}%"></i></span><b>${num(v)}</b>`);

function bar(label, v, base, note) {
  return `<div class="bar"><span>${label}</span><div class="track">${v == null ? '' : `<i style="width:${v * 100}%"></i>`}${base != null ? `<u style="left:${Math.min(99, base * 100)}%" title="chance: k / trials"></u>` : ''}</div><b>${num(v)}</b>${note ? `<small>${note}</small>` : ''}</div>`;
}

/* ---------- matched times chart ---------- */
const KIND_COLOR = { export: 'var(--c-iris)', live: 'var(--c-trial)', eval: 'var(--c-bench)' };
function timeline() {
  const rows = E.matched;
  const W = 760, H = 176, L = 46, R = 12, T = 20, B = 28;
  const end = new Date(E.generated).getTime();
  const start = end - E.window_days * 86400000;
  const ymax = Math.max(1000, ...rows.map((r) => r.ms)) * 1.08;
  const x = (t) => L + ((t - start) / (end - start)) * (W - L - R);
  const y = (ms) => T + (1 - ms / ymax) * (H - T - B);
  const days = [];
  for (let k = 0; k <= E.window_days; k++) {
    const d = new Date(start + k * 86400000);
    days.push(`<g class="tick"><line x1="${x(d.getTime())}" x2="${x(d.getTime())}" y1="${T}" y2="${H - B}"/><text x="${x(d.getTime())}" y="${H - 9}" text-anchor="${k === E.window_days ? 'end' : k === 0 ? 'start' : 'middle'}">${k === E.window_days ? 'now' : `${MON[d.getMonth()]} ${d.getDate()}`}</text></g>`);
  }
  const ys = [0, Math.round(ymax / 2 / 100) * 100, Math.round(ymax / 100) * 100].map((v) => `<g class="ytick"><line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 6}" y="${y(v) + 3}" text-anchor="end">${v}</text></g>`);
  const med = E.matched_summary.median_ms;
  // jitter points that share a timestamp so an export run reads as a column, not one dot
  const seen = {};
  const dots = rows.map((r, i) => {
    const t = new Date(r.ts).getTime();
    const k = r.ts.slice(0, 16);
    seen[k] = (seen[k] || 0) + 1;
    const jx = ((seen[k] % 9) - 4) * 2.2;
    return `<circle data-i="${i}" class="${r.patient === S.sel ? 'sel' : ''}" cx="${(x(t) + jx).toFixed(1)}" cy="${y(r.ms).toFixed(1)}" r="${r.patient === S.sel ? 5 : 3.2}" fill="${KIND_COLOR[r.kind] || 'var(--text-2)'}"/>`;
  });
  return `<svg id="tl" class="tl" viewBox="0 0 ${W} ${H}" role="img" aria-label="Match time per patient over the last ${E.window_days} days">
    ${ys.join('')}${days.join('')}
    ${med != null ? `<line class="med" x1="${L}" x2="${W - R}" y1="${y(med)}" y2="${y(med)}"/><text class="medl" x="${L + 6}" y="${y(med) - 4}">median ${Math.round(med)} ms</text>` : ''}
    <text class="ylab" x="${L - 6}" y="9" text-anchor="end">ms</text>
    ${dots.join('')}
  </svg>`;
}

function wireTimeline() {
  const svg = $('#tl');
  if (!svg) return;
  svg.addEventListener('mousemove', (e) => {
    const c = e.target.closest('circle');
    if (!c) { tip(null); return; }
    const r = E.matched[+c.dataset.i];
    const v = r.verdicts ? ` · <span class="vd-in"><i class="r">${r.verdicts.ready}</i><i class="p">${r.verdicts.provisional}</i><i class="b">${r.verdicts.blocked}</i></span>` : '';
    tip(`<b>${esc(r.patient)}</b> · ${esc(r.kind)}<br>${when(r.ts)} · <b>${fmt(r.ms)} ms</b>${r.shortlist ? ` · shortlist ${r.shortlist}` : ''}${v}${r.top ? `<br><small>top ${esc(r.top)}</small>` : ''}`, e.clientX, e.clientY);
  });
  svg.addEventListener('mouseleave', () => tip(null));
}

/* ---------- page ---------- */
export function render() {
  const g = E.golden, s = g.summary, ks = g.ks, K = ks[ks.length - 1], c = E.config, ms = E.matched_summary;
  const chance = (k) => k / c.n_trials;
  const me = g.per_patient.find((p) => p.patient === S.sel);
  const mySub = me?.subgroup;
  pageTitle('Evaluation', `<span><b>${s.n_queries}</b> queries · <b>${fmt(s.n_pairs)}</b> golden pairs</span><span>${esc(c.encoder)} · ${c.dim}-d · ${fmt(c.n_chunks)} chunks</span><span>mode <b>${esc(c.mode)}</b> · depth <b>${c.ranked_depth}</b></span><span>run <b>${when(E.generated)}</b></span>`);

  const layers = g.layers.map((l) => `<tr><td><span class="tagc ${l.kind === 'labelled' ? 'real' : 'derived'}">${l.id}</span></td><td>${esc(l.name)}<br><small>${esc(l.note)}</small></td><td class="num">${fmt(l.n_pairs)}</td></tr>`).join('');
  const hitSrc = Object.entries(g.hit_source).map(([k, v]) => `<span class="pill">${esc(k)} <b>${v}</b></span>`).join('') || '<small>no hits yet</small>';

  const subs = g.by_subgroup.map((r) => `<tr class="${r.subgroup === mySub ? 'sel' : ''}"><td>${esc(r.label)}${r.subgroup === mySub ? ' <small>· selected</small>' : ''}</td><td class="num">${r.n_patients}</td><td class="num">${r.n_queries}</td><td class="num">${fmt(r.n_pairs)}</td><td class="ibc">${ib(r[`recall@${K}`])}</td><td class="ibc">${ib(r[`hit@${K}`], 'alt')}</td><td class="num">${r.median_first_rank ?? '—'}</td></tr>`).join('');

  const misses = g.misses.slice(0, 10).map((m) => `<tr class="${m.patient === S.sel ? 'sel' : ''}"><td class="mono">${esc(m.patient)}</td><td><a href="https://clinicaltrials.gov/study/${esc(m.nct_id)}" target="_blank" rel="noopener" class="mono">${esc(m.nct_id)}</a><br><small>${esc(m.title.length > 92 ? m.title.slice(0, 90) + '…' : m.title)}</small></td><td class="mono">${esc(m.pool)}</td></tr>`).join('');

  const mine = me ? (me.n_golden ? `<b>${esc(me.patient)}</b> · ${esc(g.by_subgroup.find((x) => x.subgroup === me.subgroup)?.label || me.subgroup)} · ${me.n_golden} golden · <b>${me.n_hits}</b> in the top ${c.ranked_depth} · first at rank <b>${me.first_rank ?? '—'}</b>` : `<b>${esc(me.patient)}</b> · no actionable biomarker in the title layer, so no reference pairs: not scored`) : '';

  const sched = E.schedules.map((x) => `<tr><td><b>${esc(x.name)}</b><br><small>${esc(x.what)}</small></td><td>${esc(x.cadence)}${x.cron ? `<br><code>${esc(x.cron)}</code>` : ''}${x.also_on?.length ? `<br><small>also on change: ${x.also_on.map(esc).join(', ')}</small>` : ''}</td><td><code>${esc(x.target)}</code></td><td>${x.last_run ? `${when(x.last_run)}<br><small>${rel(x.last_run)}</small>` : '<small>never</small>'}</td><td>${x.next_run ? `${when(x.next_run)}<br><small>${rel(x.next_run)}</small>` : '<small>on trigger</small>'}</td><td>${pill(x.status)}</td></tr>`).join('');
  const runs = E.runs.slice().reverse().map((r) => `<tr><td class="mono">${when(r.ts)}</td><td>${esc(r.mode)}</td><td class="num">${r.n_queries}</td><td class="num">${fmt(r.n_pairs)}</td><td class="num">${num(r[`recall@${K}`] ?? r['recall@40'] ?? r['recall@12'])}</td><td class="num">${num(r[`hit@${K}`] ?? r['hit@40'] ?? r['hit@12'])}</td><td class="num">${num(r.mrr)}</td><td>${pill(r.status)}</td></tr>`).join('');

  const days = ms.by_day.map((d) => `<tr><td class="mono">${esc(d.day)}</td><td class="num">${d.n}</td><td class="num">${Math.round(d.median_ms)}</td><td class="num">${d.max_ms}</td></tr>`).join('');
  const kinds = Object.entries(ms.by_kind).map(([k, v]) => `<span><i style="background:${KIND_COLOR[k] || 'var(--text-2)'}"></i>${esc(k)} · ${v}</span>`).join('');

  $('#page').innerHTML = `
    <div class="ev-grid">
      <section class="panel"><div class="ph"><h3>Retrieval recall</h3><span class="right">golden set · ${esc(c.store)}</span></div>
        <div class="pb">
          <div class="kvs">
            <div><span class="lbl">Pool</span><b>${fmt(c.pool_chunks)} chunks</b></div>
            <div><span class="lbl">Shortlist</span><b>${c.shortlist} trials</b></div>
            <div><span class="lbl">Scored depth</span><b>top ${c.ranked_depth}</b></div>
            <div><span class="lbl">MRR</span><b>${num(s.mrr)}</b></div>
            <div><span class="lbl">First rank</span><b>${s.median_first_rank ?? '—'}<small> median</small></b></div>
          </div>
          <div class="barlist">
            ${ks.map((k) => bar(`Recall@${k} <small>capped at ${k}</small>`, s[`recall@${k}`], chance(k), null)).join('')}
            ${ks.map((k) => bar(`Hit@${k} <small>≥ 1 golden trial</small>`, s[`hit@${k}`], null, null)).join('')}
          </div>
          <div class="gate">gate <code>${esc(E.gate.metric)}</code> previous <b>${num(E.gate.previous)}</b> → current <b>${num(E.gate.current)}</b> · fail if drop > ${E.gate.threshold} ${pill(E.gate.status)}</div>
          ${c.note ? `<p class="note">${esc(c.note)}</p>` : ''}
        </div></section>

      <section class="panel"><div class="ph"><h3>Golden set</h3><span class="right">${g.no_reference.length} of ${g.per_patient.length} patients without a reference</span></div>
        <div class="pb flush"><table class="dt"><thead><tr><th>Layer</th><th>Pairs come from</th><th class="num">Pairs</th></tr></thead><tbody>${layers}</tbody></table></div>
        <div class="pb"><div class="lbl" style="margin-bottom:6px">Where the hits came from</div><div class="pills">${hitSrc}</div>
          ${g.violations.length ? `<p class="note warn">${g.violations.length} must-not trial(s) appeared in a result.</p>` : ''}
          <p class="mine">${mine}</p></div></section>

      <section class="panel wide"><div class="ph"><h3>By subgroup</h3><span class="right">recall and hit at depth ${K}</span></div>
        <div class="pb flush scroll"><table class="dt subs"><thead><tr><th>Subgroup</th><th class="num">Patients</th><th class="num">Scored</th><th class="num">Pairs</th><th>Recall@${K}</th><th>Hit@${K}</th><th class="num">First rank</th></tr></thead><tbody>${subs}</tbody></table></div></section>

      <section class="panel wide"><div class="ph"><h3>Misses</h3><span class="right">${fmt(g.n_misses)} golden trials not in the top ${c.ranked_depth} · showing ${Math.min(10, g.misses.length)}</span></div>
        <div class="pb flush scroll"><table class="dt"><thead><tr><th>Patient</th><th>Trial</th><th>Where</th></tr></thead><tbody>${misses || '<tr><td colspan="3"><small>none</small></td></tr>'}</tbody></table></div></section>

      <section class="panel wide"><div class="ph"><h3>Automated schedules</h3><span class="right">${esc(E.schedules.length)} jobs · <code>make cron</code> prints the crontab · Asia/Bangkok</span></div>
        <div class="pb flush scroll"><table class="dt sched"><thead><tr><th>Job</th><th>Cadence</th><th>Runs</th><th>Last run</th><th>Next run</th><th>Status</th></tr></thead><tbody>${sched}</tbody></table></div>
        <div class="ph sub"><h3>Run log · last ${E.window_days} days</h3></div>
        <div class="pb flush scroll"><table class="dt"><thead><tr><th>When</th><th>Mode</th><th class="num">Queries</th><th class="num">Pairs</th><th class="num">Recall</th><th class="num">Hit</th><th class="num">MRR</th><th>Gate</th></tr></thead><tbody>${runs || '<tr><td colspan="8"><small>no runs in the window</small></td></tr>'}</tbody></table></div></section>

      <section class="panel wide"><div class="ph"><h3>Matched times · last ${E.window_days} days</h3><span class="right">per patient, end to end: embed → IRIS → rules → models</span></div>
        <div class="pb">
          <div class="kvs">
            <div><span class="lbl">Matches</span><b>${fmt(ms.n)}</b></div>
            <div><span class="lbl">Patients</span><b>${fmt(ms.patients)}</b></div>
            <div><span class="lbl">Runs</span><b>${fmt(ms.runs)}</b></div>
            <div><span class="lbl">Median</span><b>${ms.median_ms != null ? Math.round(ms.median_ms) + ' ms' : '—'}</b></div>
            <div><span class="lbl">p95</span><b>${ms.p95_ms != null ? ms.p95_ms + ' ms' : '—'}</b></div>
            <div><span class="lbl">Max</span><b>${ms.max_ms != null ? ms.max_ms + ' ms' : '—'}</b></div>
          </div>
          ${E.matched.length ? timeline() : '<p class="note">No matches in the window. Run <code>make export</code> or click through the live app.</p>'}
          <div class="legend">${kinds}<span><i class="ring"></i>selected patient</span></div>
        </div>
        <div class="pb flush scroll"><table class="dt"><thead><tr><th>Day</th><th class="num">Matches</th><th class="num">Median ms</th><th class="num">Max ms</th></tr></thead><tbody>${days || '<tr><td colspan="4"><small>—</small></td></tr>'}</tbody></table></div></section>
    </div>`;
  wireTimeline();
}
