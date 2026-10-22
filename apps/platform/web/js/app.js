// Boot: load shared data, render the shell, then hand the page body to the module named in <body data-page>.
import { $, S, j, esc, renderShell, selectPatient } from './common.js';

async function boot() {
  S.page = document.body.dataset.page;
  const q = new URLSearchParams(location.search);
  const [patients, bench] = await Promise.all([j('data/patients.json'), j('data/benchmarks.json')]);
  S.patients = patients; S.bench = bench;
  const mod = await import(`./pages/${S.page}.js`);
  await mod.init?.();
  S.render = mod.render;
  renderShell();
  const p = patients.some((x) => x.id === q.get('p')) ? q.get('p') : patients[0].id;
  await selectPatient(p, q.get('t'));
}

boot().catch((e) => {
  $('#page').innerHTML = `<pre style="padding:1rem;color:#f88">Could not load data: ${esc(e.message)}\nServe this folder over HTTP (make static) after running the pipeline.</pre>`;
  console.error(e);
});
