// 01 Data input: one patient record, each value with its source. Mutations and simulated gap-fill called out.
import { $, esc, chip, kv, valueText, dateBit, isPositive, patient, pageTitle, LABELS } from '../common.js';
import { anatomySVG, anatomyCaption } from '../anatomy.js';

const GENES = ['kras', 'nras', 'braf', 'pik3ca', 'her2', 'msi'];

export function render() {
  const p = patient();
  const f = p.facts;
  const c = p.counts;
  pageTitle('Data input', `<span><b>${p.id}</b> · ${esc(p.source_id)}</span><span>${esc(p.study_short)} · ${esc(p.panel)}</span><span><b>${c.real}</b> REAL · <b>${c.sim}</b> SIM · <b>${c.missing}</b> not done</span>`);

  const bio = GENES.map((g) => [LABELS[g] || g.toUpperCase(), chip(g, f[g])]);
  const labs = ['ecog', 'anc', 'platelets', 'hemoglobin', 'creatinine', 'bilirubin', 'ast', 'alt'].map((g) => {
    const x = f[g];
    return [LABELS[g] || g.toUpperCase(), x.status === 'done' ? `${esc(valueText(g, x))} ${dateBit(x)}` : '<span class="chip nd">not on record</span>'];
  });
  const screens = ['hiv', 'hbv', 'hcv'].map((g) => [LABELS[g], f[g].status === 'done' ? esc(f[g].value) : '<span class="chip nd">not done</span>']);
  const anat = (label, html) => html;
  const panels = [
    { kind: 'REAL', title: 'Genomics & pathology', src: 'cBioPortal', ds: p.study_label, url: p.study_url, body: kv([...bio, ['Panel', `${esc(p.panel)}`], ['Sample', `<code>${esc(p.sample_id)}</code>`], ['TMB', f.tmb.value != null ? `${Number(f.tmb.value).toFixed(1)} mut/Mb` : '—']]) },
    { kind: 'REAL', title: 'Clinical & staging', src: 'cBioPortal', ds: p.study_label, url: p.study_url, body: kv([['Age', f.age.value ?? '<span class="chip nd">not in dataset</span>'], ['Sex', esc(f.sex.value || '—')], ['Type', anat('type', 'colorectal adenocarcinoma')], ['Stage', anat('stage', esc(valueText('stage_iv', f.stage_iv)))], ['Primary', anat('primary', esc(p.side ? p.side + '-sided' : 'side not recorded'))], ['Metastases', anat('mets', p.metastasis_sites.length ? esc(p.metastasis_sites.map((s) => s.replace('_', ' ')).join(', ')) : 'none recorded')], ['Ancestry', esc(p.race || '—')]]) },
    { kind: 'SIM', title: 'Imaging & treatment', src: 'simulated overlay', ds: '', url: null, body: kv([['Baseline CT', f.measurable.status === 'done' ? `${esc(valueText('measurable', f.measurable))} ${dateBit(f.measurable, 42)}` : '<span class="chip nd">no baseline CT</span>'], ['Brain imaging', f.brain_mets.status === 'done' ? `${esc(valueText('brain_mets', f.brain_mets))} ${f.brain_mets.source.startsWith('REAL') ? '' : dateBit(f.brain_mets, 42)}` : '<span class="chip nd">not done</span>'], ['Prior lines', esc(valueText('prior_lines', f.prior_lines))]]) },
    { kind: 'SIM', title: 'Fitness & laboratory', src: 'simulated overlay', ds: '28-day window', url: null, body: kv(labs) },
    { kind: 'SIM', title: 'Safety screens & consent', src: 'simulated overlay', ds: '', url: null, body: kv([...screens, ['Consent', f.consent.status === 'done' ? 'recorded' : '<span class="chip nd">not recorded</span>']]) },
  ];

  // mutations: every positive molecular finding, plus what was never tested (a gap SIM does not fill)
  const pos = GENES.filter((g) => f[g].status === 'done' && isPositive(g, f[g]));
  const wt = GENES.filter((g) => f[g].status === 'done' && !isPositive(g, f[g]));
  const nd = GENES.filter((g) => f[g].status !== 'done');
  const mutHtml = `
    <div class="muts">${pos.length ? pos.map((g) => `<div class="mut"><b>${esc(LABELS[g] || g.toUpperCase())}</b><span>${esc(valueText(g, f[g]))}</span><small>${esc(f[g].source.replace('REAL:', ''))}</small></div>`).join('') : `<div class="mut none"><b>no driver alteration detected</b><span>${esc(wt.map((g) => (LABELS[g] || g.toUpperCase())).join(' · '))} wild-type / negative</span></div>`}
      ${f.tmb.value != null ? `<div class="mut tmb"><b>TMB</b><span>${Number(f.tmb.value).toFixed(1)} mut/Mb</span><small>${esc(f.tmb.source.replace('REAL:', ''))}</small></div>` : ''}</div>
    ${pos.length ? `<div class="mut-wt"><span class="lbl">wild-type / negative</span> ${wt.map((g) => `<span class="chip neg">${esc(LABELS[g] || g.toUpperCase())}</span>`).join(' ') || '—'}</div>` : ''}
    <div class="mut-wt"><span class="lbl">not tested · stays unknown</span> ${nd.map((g) => `<span class="chip ${{ failed: 'fl', insufficient: 'in', pending: 'pe' }[f[g].status] || 'nd'}">${esc(LABELS[g] || g.toUpperCase())} · ${esc(f[g].status.replace('_', ' '))}</span>`).join(' ') || '<span class="muted">none</span>'}</div>`;

  // simulated gap-fill: every SIM value the rules can use
  const sim = Object.entries(f).filter(([, x]) => x.source === 'SIM');
  const simDone = sim.filter(([, x]) => x.status === 'done');
  const simMissing = sim.filter(([, x]) => x.status !== 'done');
  const simHtml = `
    <div class="simcloud">${simDone.map(([k, x]) => `<span class="simv" title="${esc(LABELS[k] || k)} · simulated">${esc(LABELS[k] || k)} <b>${esc(valueText(k, x))}</b>${dateBit(x)}</span>`).join('')}</div>
    ${simMissing.length ? `<div class="mut-wt"><span class="lbl">simulated as not done</span> ${simMissing.map(([k, x]) => `<span class="chip nd">${esc(LABELS[k] || k)} · ${esc(x.status.replace('_', ' '))}</span>`).join(' ')}</div>` : ''}`;

  const segs = p.summary_segments.map((s) => {
    const mut = /mutation|amplified|MSI-high/i.test(s.t) ? ' mut' : '';
    return `<span class="sg ${s.src === 'REAL' ? 'real' : s.src === 'SIM' ? 'sim' : ''}${mut}">${esc(s.t)}</span>`;
  }).join('');

  $('#page').innerHTML = `
    <div class="kpis">
      <div class="kpi"><span class="lbl">Patient</span><b>${p.id}</b></div>
      <div class="kpi"><span class="lbl">Source record</span><b>${esc(p.source_id)}</b></div>
      <div class="kpi"><span class="lbl">Cohort</span><b>${esc(p.study_short)}</b></div>
      <div class="kpi"><span class="lbl">Age · sex · side</span><b class="wrap">${p.age ?? '—'} · ${esc(p.sex?.[0]?.toUpperCase() || '—')} · ${esc(p.side || '—')}</b></div>
      <div class="kpi"><span class="lbl">Stage · mets</span><b class="wrap">${esc(p.stage_raw || '—')} · ${p.metastasis_sites.length}</b></div>
      <div class="kpi"><span class="lbl">Mutations · untested</span><b><span style="color:var(--c-real)">${pos.length}</span><span class="sep">·</span>${nd.length}</b></div>
      <div class="kpi"><span class="lbl">Real · sim · not done</span><b><span style="color:var(--c-real)">${c.real}</span><span class="sep">·</span>${c.sim}<span class="sep">·</span>${c.missing}</b></div>
      <div class="kpi"><span class="lbl">Shortlist verdicts</span><b><span class="m">${p.verdicts.ready}</span><span class="sep">·</span><span class="u">${p.verdicts.provisional}</span><span class="sep">·</span><span class="n">${p.verdicts.blocked}</span></b></div>
    </div>
    <div class="src-grid">
      <section class="panel tumor"><div class="ph"><span class="tagc real">REAL</span><h3>Tumour map</h3><span class="right">anterior · cBioPortal</span></div>
        <div class="pb"><div class="tumor-body">${anatomySVG(p)}${anatomyCaption(p)}</div></div></section>
      <section class="panel hi-mut"><div class="ph"><span class="tagc real">REAL</span><h3>Mutations</h3><span class="right">${pos.length} positive · ${wt.length} wild-type · ${nd.length} not tested</span></div><div class="pb">${mutHtml}</div></section>
      <section class="panel hi-sim"><div class="ph"><span class="tagc sim">SIM</span><h3>Simulated gap-fill</h3><span class="right">${simDone.length} values · ${simMissing.length} not done · no public colorectal dataset has these</span></div><div class="pb">${simHtml}</div></section>
      ${panels.map((k) => `
        <section class="panel src src-card" data-kind="${k.kind}">
          <div class="ph"><span class="tagc ${k.kind === 'REAL' ? 'real' : 'sim'}">${k.kind}</span><h3>${k.title}</h3>
            <span class="origin">${k.url ? `<a href="${esc(k.url)}" target="_blank" rel="noopener">${esc(k.src)}</a>` : esc(k.src)}${k.ds ? ' · ' + esc(k.ds) : ''}</span></div>
          <div class="pb"><dl>${k.body}</dl></div>
        </section>`).join('')}
      <section class="panel">
        <div class="ph"><h3>Record text</h3><span class="right">input to bge-m3 · 1,024 d</span></div>
        <div class="pb"><p class="rec">${segs}</p>
          <div class="legend"><span class="sg real">REAL</span><span class="sg sim">SIM</span><span class="sg real mut">mutation</span></div></div>
      </section>
    </div>`;
}
