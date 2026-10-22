// 02 Trial match: ranked trials, rule-by-rule evidence, what-if, and Thailand population hotspots.
import { $, $$, esc, pct, fmt, j, S, patient, openMatch, liveMatch, whatifOptions, saveWhatif, srcTag, valueText, daysAgo, REF_ISO, LABELS, pageTitle, popKeyFor, setOpen, url, tip } from '../common.js';
import { ThaiMap, km } from '../thailand.js';

let TH = null;
let tmap = null;
let hotKey = null;       // subgroup override chosen in the panel; null = follow the patient
let selProv = null;

export async function init() {
  TH = await j('data/thailand.json');
}

export function render() {
  const m = S.match;
  const p = patient();
  const v = p.verdicts;
  pageTitle('Trial match', `<span><b>${p.id}</b></span><span>shortlist <b>${m.matches.length}</b> / ${fmt(S.bench.n_trials)}</span><span><b style="color:var(--met)">${v.ready}</b> ready · <b style="color:var(--unk)">${v.provisional}</b> provisional · <b style="color:var(--not)">${v.blocked}</b> blocked</span><span>IRIS <b>${m.iris_ms ?? '—'}</b> ms</span>`);
  if (!$('#mrows')) skeleton();
  hotKey = null; selProv = null;
  renderRows();
  renderNext();
  renderHot();
}

function skeleton() {
  $('#page').innerHTML = `
    <div class="pred-grid">
      <div class="list">
        <div class="topm" id="topm"></div>
        <div class="lh"><span></span><span>Trial</span><span title="Model A">Fit · A</span><span title="Met / Unknown / Not met">Rules</span><span title="Model B">Pass B</span><span>Verdict</span></div>
        <div id="mrows"></div>
      </div>
      <aside class="side">
        <section class="panel hot">
          <div class="ph"><h3>Thailand</h3><span class="tagc sim">SIM</span><span class="right"><select id="hot-pop" aria-label="Population subgroup"></select></span></div>
          <div class="pb flush"><canvas id="thmap" aria-label="Modelled patient pool by province"></canvas>
            <div class="scale"><span>low</span><i></i><span>high</span><span class="site"><u></u>site</span></div>
            <div class="scroll"><table class="dt" id="hot-table"></table></div>
            <ul class="sites" id="hot-sites"></ul>
            <div class="method" id="hot-method"></div></div>
        </section>
        <section class="panel nt"><div class="ph"><h3>Next tests</h3><span class="right" id="nt-n"></span></div><div class="pb"><ul id="nt-list"></ul></div></section>
      </aside>
    </div>`;
  $('#mrows').onclick = (e) => {
    const h = e.target.closest('.mhead');
    if (h) { setOpen(S.open === h.dataset.nct ? null : h.dataset.nct); renderRows(); renderHot(); }
  };
  $('#topm').onclick = (e) => {
    const c = e.target.closest('[data-nct]');
    if (!c) return;
    setOpen(c.dataset.nct); renderRows(); renderHot();
    $(`.mhead[data-nct="${c.dataset.nct}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };
  $('#mrows').onchange = (e) => {
    const s = e.target.closest('select[data-fact]');
    if (!s) return;
    const o = whatifOptions(s.dataset.fact)[+s.value];
    if (o) S.whatif[s.dataset.fact] = { status: 'done', source: 'WHAT-IF', date: REF_ISO, detail: 'what-if', ...o.patch }; else delete S.whatif[s.dataset.fact];
    saveWhatif();
    renderRows();
  };
  document.addEventListener('click', (e) => { if (e.target.id === 'reset-wi') { S.whatif = {}; saveWhatif(); renderRows(); } });
  $('#hot-pop').innerHTML = Object.entries(TH.subgroups).map(([k, sg]) => `<option value="${k}">${esc(sg.label)}</option>`).join('');
  $('#hot-pop').onchange = (e) => { hotKey = e.target.value; renderHot(); };
  tmap = new ThaiMap($('#thmap'), TH, (h) => {
    if (!h) return tip(null);
    const e = h.province.est[hotKey || popKeyFor(patient().facts)];
    tip(`<b>${esc(h.province.name)}</b><small>${esc(h.province.region)} · pop ${fmt(h.province.pop)}<br><em>${fmt(e.n)}</em> (${fmt(e.lo)}–${fmt(e.hi)}) · ${e.per_100k}/100k · conf ${e.conf}</small>`, h.x, h.y);
  }, (key) => { selProv = selProv === key ? null : key; renderHot(); });
  $('#hot-table').onclick = (e) => { const r = e.target.closest('tr[data-prov]'); if (r) { selProv = selProv === r.dataset.prov ? null : r.dataset.prov; renderHot(); } };
}

/* ---------- ranked list ---------- */
/* best: every rule Met. strong: provisional with no Not met, ≤2 Unknown, ≥3 Met and P(pass) ≥ 0.7. */
function tier(x, lm) {
  if (lm.verdict === 'ready') return 'best';
  if (lm.verdict === 'provisional' && lm.counts.not_met === 0 && lm.counts.unknown <= 2 && lm.counts.met >= 3 && (lm.whatif || x.pass.p >= 0.7)) return 'strong';
  return lm.verdict === 'blocked' ? 'out' : 'none';
}

function renderRows() {
  $('#mrows').innerHTML = S.match.matches.map((x, i) => matchRow(x, i)).join('');
  renderTop();
}

function renderTop() {
  const rows = S.match.matches.map((x, i) => ({ x, i, lm: liveMatch(x) })).map((r) => ({ ...r, t: tier(r.x, r.lm) }));
  const rank = { best: 0, strong: 1 };
  const top = rows.filter((r) => r.t in rank).sort((a, b) => rank[a.t] - rank[b.t] || a.i - b.i).slice(0, 3);
  const nBest = rows.filter((r) => r.t === 'best').length;
  const nStrong = rows.filter((r) => r.t === 'strong').length;
  $('#topm').innerHTML = `<div class="topm-h"><span class="lbl">Top matches</span><span class="right"><b class="m">${nBest}</b> ready · <b class="u">${nStrong}</b> strong · ${rows.length - nBest - nStrong} other</span></div>
    <div class="topm-cards">${top.length ? top.map(({ x, i, lm, t }) => `
      <button class="tcard t-${t} ${S.open === x.nct_id ? 'open' : ''}" data-nct="${x.nct_id}">
        <span class="tc-top"><span class="tag">${t === 'best' ? '★ ready' : 'strong'}${lm.whatif ? ' · what-if' : ''}</span><span class="rk">#${i + 1}</span></span>
        <b>${esc(x.title)}</b>
        <i>${x.nct_id} · ${x.phase.map((q) => q.replace('PHASE', 'Ph ')).join('/') || 'NA'}${x.thai_sites.length ? ' · <em class="thai">TH</em>' : ''}</i>
        <span class="tc-m"><span><small>fit A</small><span class="v">${x.fit.toFixed(2)}</span></span><span><small>pass B</small><span class="v">${lm.whatif ? '—' : pct(x.pass.p)}</span></span><span><small>met · unk · not</small><span class="v"><em class="m">${lm.counts.met}</em> · <em class="u">${lm.counts.unknown}</em> · <em class="n">${lm.counts.not_met}</em></span></span></span>
      </button>`).join('') : '<span class="muted" style="padding:6px 0">no ready or strong match · see what-if on the open row</span>'}</div>`;
}

function strip(rows) {
  const order = { met: 0, unknown: 1, not_met: 2 };
  return `<span class="strip" aria-hidden="true">${[...rows].sort((a, b) => order[a.status] - order[b.status]).map((r) => `<i class="${r.status}"></i>`).join('')}</span>`;
}

function matchRow(x, i) {
  const lm = liveMatch(x);
  const open = S.open === x.nct_id;
  const checked = x.criteria.reduce((a, c) => a + (c.merged || 1), 0);
  const passTxt = lm.whatif ? '<small>what-if</small>' : x.verdict === 'blocked' ? '—' : pct(x.pass.p);
  const t = tier(x, lm);
  return `<article class="mrow ${lm.verdict} t-${t} ${open ? 'open' : ''}">
    <button class="mhead" data-nct="${x.nct_id}" aria-expanded="${open}">
      <span class="rk">${t === 'best' ? '★' : i + 1}</span>
      <span class="mt"><b>${esc(x.title)}</b><i>${x.nct_id} · ${x.phase.map((p) => p.replace('PHASE', 'Ph ')).join('/') || 'NA'} · ${esc(x.sponsor || '')} · ${x.n_sites} sites · rules ${checked}/${checked + x.needs_review}${x.thai_sites.length ? ' <em class="thai">TH</em>' : ''}</i></span>
      <span class="meter"><i style="width:${x.fit * 100}%"></i><em>${x.fit.toFixed(2)}</em></span>
      ${strip(lm.rows)}
      <span class="pass">${passTxt}</span>
      <span class="vchip ${lm.verdict} ${t === 'strong' ? 'strong' : ''}" title="${t === 'strong' ? 'strong: no Not met, ≤2 Unknown, ≥3 Met, P(pass) ≥ 0.7' : lm.verdict}">${lm.whatif ? 'what-if · ' : ''}${lm.verdict}</span>
    </button>
    ${open ? matchBody(x, lm) : ''}
  </article>`;
}

function matchBody(x, lm) {
  const unknownFacts = [...new Set([...lm.rows.filter((r) => r.status === 'unknown').map((r) => r.fact), ...Object.keys(S.whatif)])].filter((f) => whatifOptions(f).length);
  const rows = lm.rows.map((r) => {
    const ev = r.evidence;
    const evHtml = ev ? `${esc(valueText(r.fact, { value: ev.value, variant: ev.variant }))} ${srcTag(ev.source)} ${ev.date ? `<small class="when">${daysAgo(ev.date)} d</small>` : ''}` : '<span class="muted">no data</span>';
    const note = r.status === 'unknown' ? `<span class="why">${esc(r.reason)}</span><span class="act">${esc(r.action)}</span>` : r.merged > 1 ? `<small class="muted">×${r.merged} in protocol</small>` : '';
    return `<tr class="st-${r.status}"><td class="ico" title="${r.status}"><i></i></td><td class="rule"><b>${esc(r.label)}</b><small>${r.polarity === 'exclude' ? 'exclusion · ' : ''}${esc(r.text.slice(0, 150))}</small></td><td class="evd">${evHtml}</td><td class="act-c">${note}</td></tr>`;
  }).join('');
  const modelled = x.pass.modelled.map((q) => `<li><span>${esc(LABELS[q.fact] || q.fact)}</span><i style="--p:${q.p_satisfied * 100}%"></i><b>${pct(q.p_satisfied)}</b></li>`).join('');
  const controls = unknownFacts.map((f) => `<label><span>${esc(LABELS[f] || f)}</span><select data-fact="${f}"><option value="-1">unknown</option>${whatifOptions(f).map((o, i) => `<option value="${i}" ${S.whatif[f] && Object.entries(o.patch).every(([k, v]) => S.whatif[f][k] === v) ? 'selected' : ''}>${esc(o.label)}</option>`).join('')}</select></label>`).join('');
  return `<div class="mbody">
    <div class="cc">
      <div class="counts"><span class="m"><b>${lm.counts.met}</b> Met</span><span class="u"><b>${lm.counts.unknown}</b> Unknown</span><span class="n"><b>${lm.counts.not_met}</b> Not met</span><span class="r" title="Protocol lines not compiled to a rule"><b>${x.needs_review}</b> reviewer</span></div>
      <table class="crit"><tbody>${rows}</tbody></table>
    </div>
    <div class="cs">
      <section class="card"><h4>What-if${Object.keys(S.whatif).length ? '<button class="btn ghost sm right" id="reset-wi">Reset</button>' : ''}</h4>
        ${controls ? `<div class="wi">${controls}</div>` : '<span class="muted">—</span>'}
      </section>
      <section class="card"><h4>Model B · P(pass)<span class="right">${x.verdict === 'blocked' ? 'blocked' : pct(x.pass.p)}</span></h4>
        ${modelled ? `<ul class="mod">${modelled}${x.pass.operational_unknown ? `<li class="tot"><span class="muted">not modelled</span><span></span><b>${x.pass.operational_unknown}</b></li>` : ''}</ul>` : '<span class="muted">—</span>'}
      </section>
      <section class="card"><h4>Retrieval<span class="right">cos ${x.retrieval.best_sim.toFixed(3)} · ${x.retrieval.n_hits} chunks</span></h4><q>${esc(x.retrieval.best_text)}…</q></section>
      <div class="acts"><a class="btn" href="${url('referral.html')}">Referral →</a><a class="btn ghost" href="${esc(x.url)}" target="_blank" rel="noopener">Registry ↗</a></div>
    </div></div>`;
}

/* ---------- next tests ---------- */
function renderNext() {
  const t = S.match.next_best_tests;
  $('#nt-n').textContent = `${t.length}`;
  $('#nt-list').innerHTML = t.length
    ? t.map((q) => `<li class="${q.group}"><b>${esc(q.label)}</b><span>${esc(q.action)}</span><i>${q.group} · ${q.trials.length} trial${q.trials.length === 1 ? '' : 's'}</i></li>`).join('')
    : '<li class="none">—</li>';
}

/* ---------- Thailand hotspots ---------- */
function renderHot() {
  const key = hotKey || popKeyFor(patient().facts);
  $('#hot-pop').value = key;
  const x = openMatch();
  const sites = Object.values(TH.sites);
  const hl = new Set(x ? x.thai_sites.map((s) => s.facility) : []);
  const ref = sites.filter((s) => s.lat != null && (hl.size ? hl.has(s.facility) : true));
  const provs = [...TH.provinces].sort((a, b) => b.est[key].n - a.est[key].n);
  const total = provs.reduce((a, p) => a + p.est[key].n, 0);
  const top = provs.slice(0, 8);
  if (selProv && !top.some((p) => p.key === selProv)) top.push(provs.find((p) => p.key === selProv));
  tmap.set({ key, sites, highlight: hl, selected: selProv });
  const near = (p) => {
    if (!ref.length) return '—';
    const d = Math.min(...ref.map((s) => km([p.centroid[1], p.centroid[0]], [s.lat, s.lon])));
    return d < 1 ? '<1' : fmt(Math.round(d));
  };
  $('#hot-table').innerHTML = `
    <thead><tr><th>Province</th><th class="num">Pool</th><th class="num">/100k</th><th>Conf</th><th class="num" title="km from the province centroid to the nearest listed Thai site; the open trial's sites first">km</th></tr></thead>
    <tbody>${top.map((p) => { const e = p.est[key]; return `<tr class="rowbtn ${p.key === selProv ? 'sel' : ''}" data-prov="${p.key}"><td>${esc(p.name)}<br><small>${esc(p.region)}</small></td><td class="num"><b>${fmt(e.n)}</b><br><small>${fmt(e.lo)}–${fmt(e.hi)}</small></td><td class="num">${e.per_100k.toFixed(2)}</td><td><span class="conf"><i style="width:${e.conf * 100}%"></i></span>${e.conf.toFixed(2)}</td><td class="num">${near(p)}</td></tr>`; }).join('')}
    <tr><td><b>Thailand</b><br><small>77 provinces</small></td><td class="num"><b>${fmt(total)}</b><br><small>${fmt(provs.reduce((a, p) => a + p.est[key].lo, 0))}–${fmt(provs.reduce((a, p) => a + p.est[key].hi, 0))}</small></td><td class="num"></td><td></td><td class="num"></td></tr></tbody>`;
  $('#hot-sites').innerHTML = sites.length
    ? sites.map((s) => `<li class="${hl.has(s.facility) ? 'hl' : ''}"><span><b>${esc(s.facility)}</b><br><small>${esc(s.city || '')}${s.province ? ' · ' + esc(TH.provinces.find((p) => p.key === s.province)?.name || s.province) : ''}${s.located ? '' : ' · province centroid'}</small></span><small>${hl.has(s.facility) ? 'this trial · ' : ''}${s.trials.length} trial${s.trials.length === 1 ? '' : 's'}</small></li>`).join('')
    : '<li><small>no Thai site in this shortlist</small></li>';
  const M = TH.method;
  $('#hot-method').innerHTML = `<b>${esc(TH.subgroups[key].label)}</b> · pool = pop × ${M.crude_incidence_per_100k}/100k × regional factor × ${M.metastatic_share} × ${M.treatment_years} y × prev ${TH.subgroups[key].prevalence} · ±35% · ${TH.generated}`;
}
