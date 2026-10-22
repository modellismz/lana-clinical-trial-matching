// Inline SVG of the tumour: primary side on the colon frame and every recorded metastatic site. Anterior view.
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

const SITE_LABEL = { liver: 'liver', lung: 'lung', lymph_node: 'lymph node', peritoneum: 'peritoneum', brain: 'brain', ovary: 'ovary', bone: 'bone', adrenal: 'adrenal', skin: 'skin', other: 'other' };
const RIGHT = ['cecum', 'asc', 'trans'];
const LEFT = ['desc', 'sig', 'rect'];

export function anatomySVG(p) {
  const mets = new Set(p.metastasis_sites);
  const side = p.side;
  const prim = (seg) => (side === 'left' ? LEFT : side === 'right' ? RIGHT : []).includes(seg) ? 'prim' : side ? 'colon' : 'colon unk';
  const met = (k) => (mets.has(k) ? 'met' : 'organ');
  const female = p.sex === 'female';
  return `<svg class="anat" viewBox="0 0 200 300" role="img" aria-label="Tumour map: ${esc(side ? side + '-sided primary' : 'primary side not recorded')}${mets.size ? ', metastases to ' + [...mets].map((m) => SITE_LABEL[m] || m).join(', ') : ''}">
  <defs><pattern id="hatch" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="2" height="4" fill="rgba(255,127,163,.55)"/></pattern></defs>
  <text x="10" y="14" class="rl">R</text><text x="183" y="14" class="rl">L</text>
  <!-- body -->
  <circle cx="100" cy="30" r="20" class="body"/>
  <path class="body" d="M86 50 v8 L58 68 q-10 6 -12 20 l-6 60 q-2 24 6 46 l6 50 h116 l6 -50 q8 -22 6 -46 l-6 -60 q-2 -14 -12 -20 L114 58 v-8"/>
  <!-- brain -->
  <path class="${met('brain')} brain" d="M86 26 q2 -12 14 -12 q12 0 14 12 q0 10 -8 12 q-6 2 -12 0 q-8 -2 -8 -12z"/>
  <!-- lungs -->
  <path class="${met('lung')}" d="M92 78 q-16 2 -20 24 q-2 18 6 28 q8 4 14 -4 z"/>
  <path class="${met('lung')}" d="M108 78 q16 2 20 24 q2 18 -6 28 q-8 4 -14 -4 z"/>
  <!-- spine / pelvis -->
  <path class="${met('bone')} bone" d="M100 62 v160 M70 236 q30 22 60 0 M66 224 q-8 14 6 26 M134 224 q8 14 -6 26"/>
  <!-- liver (patient right, viewer left) -->
  <path class="${met('liver')}" d="M56 136 q6 -14 34 -14 q22 0 36 10 q-2 10 -24 12 q-26 2 -38 10 q-10 -6 -8 -18z"/>
  <!-- peritoneum -->
  <rect x="50" y="150" width="100" height="100" rx="26" class="${met('peritoneum')} perit"/>
  <!-- colon frame -->
  <path class="${prim('cecum')} seg" d="M60 222 q-6 -2 -6 -10 q0 -8 6 -8"/>
  <path class="${prim('asc')} seg" d="M60 204 v-34"/>
  <path class="${prim('trans')} seg" d="M60 170 q40 14 80 0"/>
  <path class="${prim('desc')} seg" d="M140 170 v40"/>
  <path class="${prim('sig')} seg" d="M140 210 q4 18 -14 22 q-16 4 -20 14"/>
  <path class="${prim('rect')} seg" d="M106 246 q-4 10 -2 22"/>
  <!-- lymph nodes along the mesentery -->
  <g class="${met('lymph_node')} nodes"><circle cx="100" cy="190" r="3"/><circle cx="86" cy="200" r="3"/><circle cx="114" cy="200" r="3"/><circle cx="100" cy="210" r="3"/></g>
  ${female || mets.has('ovary') ? `<g class="${met('ovary')} ovary"><circle cx="82" cy="236" r="4"/><circle cx="118" cy="236" r="4"/></g>` : ''}
  <!-- labels for highlighted sites -->
  ${side ? `<text x="${side === 'left' ? 150 : 50}" y="196" class="lab prim" text-anchor="${side === 'left' ? 'start' : 'end'}">primary</text>` : '<text x="100" y="286" class="lab unk" text-anchor="middle">side not recorded</text>'}
  ${mets.has('liver') ? '<text x="46" y="128" class="lab met" text-anchor="end">liver</text>' : ''}
  ${mets.has('lung') ? '<text x="160" y="92" class="lab met">lung</text>' : ''}
  ${mets.has('brain') ? '<text x="128" y="22" class="lab met">brain</text>' : ''}
  ${mets.has('lymph_node') ? '<text x="100" y="230" class="lab met" text-anchor="middle">nodes</text>' : ''}
  ${mets.has('peritoneum') ? '<text x="100" y="262" class="lab met" text-anchor="middle">peritoneum</text>' : ''}
  ${mets.has('ovary') ? '<text x="126" y="240" class="lab met">ovary</text>' : ''}
  ${mets.has('bone') ? '<text x="150" y="258" class="lab met">bone</text>' : ''}
</svg>`;
}

export function anatomyCaption(p) {
  const mets = p.metastasis_sites.map((m) => SITE_LABEL[m] || m);
  const stage = (p.stage_raw || '').replace(/stage\s*/i, '').replace('4', 'IV');
  return `<div class="anat-cap">
    <div><span class="lbl">Type</span><b>colorectal adenocarcinoma <span class="tagc real">REAL</span></b></div>
    <div><span class="lbl">Stage</span><b>${esc(stage || '—')}</b></div>
    <div><span class="lbl">Primary</span><b class="${p.side ? 'prim' : ''}">${p.side ? esc(p.side) + ' colon' : 'side not recorded'}</b></div>
    <div><span class="lbl">Metastases</span><b class="${mets.length ? 'met' : ''}">${mets.length ? esc(mets.join(', ')) : 'none recorded'}</b></div>
  </div>`;
}

const GENE_LABEL = { kras: 'KRAS', nras: 'NRAS', braf: 'BRAF', pik3ca: 'PIK3CA', her2: 'HER2', msi: 'MSI' };
function positives(f) {
  return ['kras', 'nras', 'braf', 'pik3ca', 'her2', 'msi'].filter((g) => f[g].status === 'done' && (f[g].value === 'mutant' || f[g].value === 'non_v600_mutant' || f[g].value === 'amplified' || f[g].value === 'msi_high'))
    .map((g) => `${GENE_LABEL[g]} ${f[g].value === 'amplified' ? 'amp' : f[g].value === 'msi_high' ? 'high' : f[g].variant || 'mut'}`);
}

/** Compact caption for the always-visible rail map. */
export function anatomyCompact(p) {
  const mets = p.metastasis_sites.map((m) => SITE_LABEL[m] || m);
  const stage = (p.stage_raw || '').replace(/stage\s*/i, '').replace('4', 'IV');
  const pos = positives(p.facts);
  return `<div class="ra-cap">
    <div><span class="lbl">Patient</span><b>${esc(p.id)}</b></div>
    <div><span class="lbl">Type · stage</span><b>CRC adenocarcinoma · ${esc(stage || '—')}</b></div>
    <div><span class="lbl">Primary</span><b class="${p.side ? 'prim' : 'unk'}">${p.side ? esc(p.side) + ' colon' : 'side not recorded'}</b></div>
    <div><span class="lbl">Metastases · ${mets.length}</span><b class="${mets.length ? 'met' : 'unk'}">${mets.length ? esc(mets.join(', ')) : 'none recorded'}</b></div>
    <div><span class="lbl">Mutations · ${pos.length}</span><b class="${pos.length ? 'mut' : 'unk'}">${pos.length ? pos.map((x) => `<span class="chip pos">${esc(x)}</span>`).join(' ') : 'none detected'}</b></div>
  </div>`;
}
