// 04 Referral: the review-ready packet for the open trial.
import { $, esc, S, patient, openMatch, liveMatch, pageTitle, url, srcTag, valueText, daysAgo } from '../common.js';

export function render() {
  const m = S.match;
  const x = openMatch();
  const p = patient();
  pageTitle('Referral', `<span><b>${p.id}</b></span><span>trial <b>${x ? x.nct_id : '—'}</b> · <a href="${url('match.html')}">change</a></span>`);
  if (!x) { $('#page').innerHTML = '<p class="muted">No trial in the shortlist.</p>'; return; }
  const lm = liveMatch(x);
  const simRows = lm.rows.filter((r) => r.evidence && !String(r.evidence.source).startsWith('REAL'));
  const simUsed = simRows.length;
  const lines = lm.rows.map((r) => `${r.status === 'met' ? '[Met]    ' : r.status === 'not_met' ? '[Not met]' : '[Unknown]'} ${r.label}${r.status === 'unknown' ? ' -> ' + r.action : ''}`);
  const text = `REVIEW-READY REFERRAL (draft)\nPatient ${p.id} (${p.study_short} public record ${p.source_id})\nTrial ${x.nct_id}: ${x.title}\nVerdict: ${lm.verdict}${lm.whatif ? ' (what-if)' : ''}; ${lm.counts.met} Met, ${lm.counts.unknown} Unknown, ${lm.counts.not_met} Not met; ${x.needs_review} protocol lines need a reviewer\n\n${lines.join('\n')}\n\nLimits: ${simUsed} evidence items are simulated. A referral does not establish eligibility; the trial team screens and decides.`;
  const order = { not_met: 0, unknown: 1, met: 2 };
  const ruleRows = [...lm.rows].sort((a, b) => order[a.status] - order[b.status]).map((r) => {
    const ev = r.evidence;
    const isSim = ev && !String(ev.source).startsWith('REAL');
    const e = ev ? `${esc(valueText(r.fact, { value: ev.value, variant: ev.variant }))} <span class="tagc ${isSim ? 'sim' : 'real'}">${isSim ? 'SIM' : 'REAL'}</span>${ev.date ? ` · ${daysAgo(ev.date)} d` : ''}` : '—';
    return `<tr class="${r.status} ${isSim ? 'simrow' : ''}"><td class="s">${r.status.replace('_', ' ')}</td><td>${esc(r.label)}${r.status === 'unknown' ? `<br><small style="text-transform:none;letter-spacing:0">${esc(r.action)}</small>` : ''}</td><td class="e">${e}</td></tr>`;
  }).join('');
  $('#page').innerHTML = `
    <article class="doc">
      <header><div><small>Review-ready referral · draft${lm.whatif ? ' · what-if' : ''}</small><h3>${esc(x.title)}</h3>
          <p>${x.nct_id} · ${esc(x.sponsor || '')} · ${x.phase.map((q) => q.replace('PHASE', 'Ph ')).join('/') || 'NA'} · ${x.thai_sites.length ? 'TH site: ' + esc(x.thai_sites.map((t) => t.facility).join(', ')) : 'no Thai site listed'}</p></div>
        <div class="seal ${lm.verdict}"><b>${lm.verdict}</b><small>${lm.counts.met} Met · ${lm.counts.unknown} Unknown · ${lm.counts.not_met} Not met</small></div></header>
      <div class="doc-grid">
        <section><h4>Patient</h4><p><b>${p.id}</b> · <code>${esc(p.source_id)}</code></p><p class="sub">${esc(p.summary)}</p><p class="sub"><a href="${esc(p.study_url)}" target="_blank" rel="noopener">${esc(p.study_label)}</a></p></section>
        <section><h4>Next actions</h4>${[...new Set(lm.rows.filter((r) => r.status === 'unknown').map((r) => r.action))].slice(0, 6).map((a) => `<p class="todo">${esc(a)}</p>`).join('') || '<p class="sub">None · book screening visit</p>'}</section>
        <section><h4>Limits</h4><ul class="lim"><li>${simUsed} simulated evidence item${simUsed === 1 ? '' : 's'}${simUsed ? `: ${esc([...new Set(simRows.map((r) => r.label))].join(', '))}` : ''}</li><li>${x.needs_review} protocol line${x.needs_review === 1 ? '' : 's'} not compiled · reviewer</li><li>Not an eligibility determination</li></ul></section>
      </div>
      <h4>Rules</h4>
      <table class="rules"><tbody>${ruleRows}</tbody></table>
      <button class="btn" id="copy-ref">Copy as text</button><small id="copied"></small>
    </article>`;
  $('#copy-ref').onclick = async () => {
    try { await navigator.clipboard.writeText(text); $('#copied').textContent = 'copied'; } catch { $('#copied').textContent = 'clipboard unavailable'; }
  };
}
