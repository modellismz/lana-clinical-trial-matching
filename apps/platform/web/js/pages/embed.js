// 03 Embedding: 1,073 trials in bge-m3 space, the patient's query and the IRIS retrieval.
import { $, $$, esc, fmt, j, S, patient, pageTitle, setOpen, tip } from '../common.js';
import { EmbedMap, CLUSTER_COLORS } from '../map.js';

let MAP = null;
let emap = null;

export async function init() {
  MAP = await j('data/trials.json');
}

export function render() {
  const m = S.match;
  pageTitle('Embedding', `<span><b>${patient().id}</b></span><span>bge-m3 · <b>1,024</b> d</span><span>IRIS Lana.Chunk · <b>${fmt(S.bench.n_chunks)}</b> vectors</span><span>top <b>700</b> → shortlist <b>${m.matches.length}</b></span>`);
  if (!$('#map')) skeleton();
  const hits = [...m.matches].sort((a, b) => b.retrieval.best_sim - a.retrieval.best_sim).slice(0, 8);
  const fp = m.query_vector_head;
  const maxv = Math.max(...fp.map(Math.abs), 0.001);
  emap.setPatient(MAP.patients[S.sel], m.matches.map((x) => x.nct_id));
  emap.setFocus(S.open);
  $('#fp').innerHTML = `<span class="lbl">query vector · dims 1–8 of 1,024</span><div class="bars">${fp.map((v) => `<i style="height:${Math.max(4, Math.abs(v) / maxv * 30)}px;${v < 0 ? 'opacity:.55;' : ''}" title="${v.toFixed(4)}"></i>`).join('')}</div>`;
  $('#hits').innerHTML = hits.map((h) => `
    <li><div class="hl"><b>${h.retrieval.best_sim.toFixed(3)}</b><i style="width:${(h.retrieval.best_sim - 0.3) / 0.6 * 100}%"></i></div>
      <a href="match.html?p=${S.sel}&t=${h.nct_id}" data-nct="${h.nct_id}"><strong>${esc(h.title)}</strong></a>
      <q>${esc(h.retrieval.best_text)}…</q><small>${h.nct_id} · ${h.retrieval.best_kind === 'head' ? 'summary' : h.retrieval.best_kind} · ${h.retrieval.n_hits} chunks</small></li>`).join('');
  $('#live').innerHTML = S.api
    ? `<button class="btn sm" id="run-live">Run live on IRIS</button><span id="live-note">snapshot · ${m.iris_ms ?? '—'} ms</span>`
    : `<span>snapshot · ${m.iris_ms ?? '—'} ms · API offline</span>`;
  $('#run-live')?.addEventListener('click', runLive);
}

function skeleton() {
  $('#page').innerHTML = `
    <div class="embed-grid">
      <section class="panel"><div class="ph"><h3>Trials · UMAP of bge-m3</h3><span class="right">${fmt(MAP.trials.length)} trials · ${MAP.clusters.length} clusters</span></div>
        <div class="pb flush"><canvas id="map" aria-label="Trials in embedding space"></canvas><div class="clusters" id="clusters"></div></div></section>
      <section class="panel"><div class="ph"><span class="tagc iris">IRIS</span><h3>Retrieval</h3><span class="right">Lana.Chunk</span></div>
        <div class="pb">
          <pre class="sql"><i>SELECT TOP</i> 700 Trial, Kind, Txt,
  <i>VECTOR_COSINE</i>(Vec, <i>TO_VECTOR</i>(?, FLOAT, 1024)) <i>AS</i> Sim
<i>FROM</i> Lana.Chunk <i>ORDER BY</i> Sim <i>DESC</i></pre>
          <div class="fp" id="fp" style="margin-top:10px"></div>
        </div>
        <ol class="hits" id="hits"></ol>
        <div class="liverow" id="live"></div>
      </section>
    </div>`;
  emap = new EmbedMap($('#map'), MAP, (h) => {
    if (!h) return tip(null);
    const t = h.trial;
    tip(`<b>${esc(t.t)}</b><small>${t.id} · phase ${esc(t.ph)} · ${esc(t.sp || '')}<br>${t.ns} sites${t.th ? ' · <em>Thai site</em>' : ''}</small>`, h.x, h.y);
  });
  $('#clusters').innerHTML = MAP.clusters.map((c) => `<button data-c="${c.id}" style="--cc:${CLUSTER_COLORS[c.id]}"><i></i>${esc(c.terms.slice(0, 3).join(' · '))}<small>${c.n}</small></button>`).join('') + '<span class="thai"><i></i>Thai site</span>';
  $('#clusters').addEventListener('click', (e) => {
    const b = e.target.closest('[data-c]');
    if (!b) return;
    const on = b.getAttribute('aria-pressed') === 'true';
    $$('#clusters button').forEach((x) => x.setAttribute('aria-pressed', 'false'));
    if (!on) { b.setAttribute('aria-pressed', 'true'); emap.setCluster(+b.dataset.c); } else emap.setCluster(null);
  });
  $('#hits').addEventListener('click', (e) => { const a = e.target.closest('[data-nct]'); if (a) setOpen(a.dataset.nct); });
}

async function runLive() {
  const note = $('#live-note');
  note.textContent = 'running…';
  try {
    const t = performance.now();
    const r = await fetch('/api/match', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ patient_id: S.sel }) });
    if (!r.ok) throw new Error(r.status);
    S.match = await r.json();
    S.match.iris_ms = Math.round(performance.now() - t);
    render();
  } catch { note.textContent = 'live API unavailable'; }
}
