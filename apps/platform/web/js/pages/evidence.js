// 05 Evidence: data inventory, both models' held-out metrics, real versus simulated inputs.
import { $, esc, fmt, S, pageTitle } from '../common.js';

function bar(label, v, base, note) {
  return `<div class="bar"><span>${label}</span><div class="track"><i style="width:${v * 100}%"></i>${base != null ? `<u style="left:${base * 100}%" title="chance"></u>` : ''}</div><b>${v.toFixed(2)}</b>${note ? `<small>${note}</small>` : ''}</div>`;
}

export function render() {
  const b = S.bench;
  const t = b.trial_fit;
  const cb = t.baselines;
  pageTitle('Evidence', `<span><b>${fmt(b.n_trials)}</b> trials</span><span><b>${fmt(b.n_criteria)}</b> lines</span><span><b>${fmt(b.n_chunks)}</b> vectors</span><span>compiled <b>${fmt(b.n_assessable)}</b> (${Math.round(b.n_assessable / b.n_criteria * 100)}%)</span>`);
  const inv = b.inventory.map((d) => `<tr><td><span class="tagc ${d.kind === 'REAL' ? 'real' : 'sim'}">${d.kind}</span></td><td>${d.url ? `<a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.name)}</a>` : esc(d.name)}</td><td class="num">${d.n != null ? fmt(d.n) : '—'}</td><td>${esc(d.what)}</td><td class="mono">${esc(d.via)}</td></tr>`).join('');
  const comp = Object.entries(b.completion.targets).map(([k, v]) => bar(`${k.toUpperCase()} <small>${v.positive_class} · ${(v.prevalence * 100).toFixed(1)}%</small>`, v.auroc, 0.5, `AP ${v.average_precision.toFixed(2)} · n ${fmt(v.n)}`)).join('');
  $('#page').innerHTML = `
    <div class="ev-grid">
      <section class="panel wide"><div class="ph"><h3>Data inventory</h3></div>
        <div class="pb flush scroll"><table class="dt inv"><thead><tr><th></th><th>Source</th><th class="num">Rows</th><th>Used for</th><th>Via</th></tr></thead><tbody>${inv}</tbody></table></div></section>
      <section class="panel"><div class="ph"><h3>Model A · trial fit</h3><span class="right">TREC 2021 → 2022</span></div>
        <div class="pb">
          <div class="kvs">
            <div><span class="lbl">Train pairs · topics</span><b>${fmt(t.n_train_pairs)} · ${t.n_train_topics}</b></div>
            <div><span class="lbl">Test pairs · topics</span><b>${fmt(t.n_test_pairs)} · ${t.n_test_topics}</b></div>
            <div><span class="lbl">NDCG@10</span><b>${t.ranking['ndcg@10']}</b></div>
            <div><span class="lbl">P@10</span><b>${t.ranking.p_at_10_eligible ?? t.ranking['p@10_eligible']}</b></div>
          </div>
          <div class="barlist">
            ${bar('Model A · 8 features', t.auroc_eligible, 0.5, `AUROC eligible · NDCG@10 ${t.ranking['ndcg@10']}`)}
            ${bar('Cosine · trial summary', cb['cosine(topic, trial head)'].auroc_eligible, 0.5, `NDCG@10 ${cb['cosine(topic, trial head)']['ndcg@10']}`)}
            ${bar('Cosine · inclusion text', cb['cosine(topic, inclusion text)'].auroc_eligible, 0.5, `NDCG@10 ${cb['cosine(topic, inclusion text)']['ndcg@10']}`)}
          </div>
        </div></section>
      <section class="panel"><div class="ph"><h3>Model B · biomarker completion</h3><span class="right">${b.completion.folds}-fold CV · AUROC</span></div>
        <div class="pb">
          <div class="kvs"><div><span class="lbl">Data</span><b style="font-size:11px;white-space:normal">${esc(b.completion.data)}</b></div></div>
          <div class="barlist">${comp}</div>
        </div></section>
      <section class="panel wide"><div class="ph"><h3>Inputs · real vs simulated</h3></div>
        <div class="pb"><div class="mx">${[['Age, sex, stage, sidedness', 'REAL'], ['KRAS · NRAS · BRAF · HER2 · PIK3CA', 'REAL'], ['MSI / MMR incl. failed, not done', 'REAL'], ['Metastasis sites', 'REAL'], ['Trial protocols and sites', 'REAL'], ['Matching labels (TREC)', 'REAL'], ['ECOG, labs, dates', 'SIM'], ['Baseline CT, brain imaging', 'SIM'], ['Prior lines, infection screens, consent', 'SIM'], ['Thailand province pools', 'SIM']].map(([k, v]) => `<div class="${v.toLowerCase()}"><span>${k}</span><b>${v}</b></div>`).join('')}</div></div></section>
    </div>`;
}
