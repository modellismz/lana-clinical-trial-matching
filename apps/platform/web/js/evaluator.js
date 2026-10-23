// Browser port of lana/evaluator.py. Same rules, so the what-if panel agrees with the pipeline.
export const REF_DATE = new Date('2026-10-17T00:00:00Z');
const WINDOW = { lab: 28, fitness: 28, imaging: 42 };
export const BIOMARKERS = new Set(['kras', 'nras', 'braf', 'her2', 'msi']);
export const LABELS = {
  kras: 'KRAS', nras: 'NRAS', braf: 'BRAF', her2: 'HER2', msi: 'MSI / MMR', ecog: 'ECOG performance status',
  anc: 'ANC', platelets: 'Platelet count', hemoglobin: 'Hemoglobin', crcl: 'Creatinine clearance',
  creatinine: 'Serum creatinine', creatinine_uln: 'Serum creatinine', bilirubin: 'Bilirubin', bilirubin_uln: 'Bilirubin',
  transaminase_uln: 'AST / ALT', measurable: 'Baseline CT (RECIST)', brain_mets: 'Brain imaging', hiv: 'HIV screen',
  hbv: 'Hepatitis B screen', hcv: 'Hepatitis C screen', consent: 'Consent record', age: 'Age', stage_iv: 'Stage',
  prior_lines: 'Treatment history',
};
const ACTION = {
  not_done: 'Order the test',
  pending: 'Chase the pending result',
  failed: 'Repeat the test (first attempt failed)',
  insufficient: 'Obtain more sample, or use a liquid biopsy',
};

const days = (iso) => Math.round((REF_DATE - new Date(iso + 'T00:00:00Z')) / 86400000);
export const daysAgo = days;

function cmp(op, have, want) {
  if (op === 'ge') return have >= want;
  if (op === 'le') return have <= want;
  return have === want;
}

function satisfies(name, fact, test) {
  const { op, value: want } = test;
  const val = fact.value;
  if (op === 'variant') {
    if (name === 'braf') return val === 'mutant' && fact.variant === want;
    return val === 'mutant' && String(fact.variant || '').toUpperCase().startsWith(String(want).toUpperCase());
  }
  return cmp(op, val, want);
}

const evidence = (name, f) => ({ fact: name, value: f.value, variant: f.variant ?? null, status: f.status, source: f.source, date: f.date, detail: f.detail });

export function assess(c, facts) {
  const name = c.fact;
  const f = facts[name];
  const label = LABELS[name] || name;
  if (!f) return { status: 'unknown', reason: `${label} is not part of the record`, action: `Record ${label}`, evidence: null };
  if (f.status !== 'done') {
    return {
      status: 'unknown',
      reason: `${label}: ${f.status.replace('_', ' ')}`,
      action: BIOMARKERS.has(name) ? ACTION[f.status] || 'Collect the data' : `Record ${label}`,
      evidence: evidence(name, f),
    };
  }
  const win = WINDOW[c.kind];
  const observed = f.date;
  if (win && observed !== null && observed !== undefined && observed !== '') {
    let problem = null;
    const parsed = typeof observed === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(observed)
      ? new Date(observed + 'T00:00:00Z') : new Date(NaN);
    // Reject impossible calendar dates that JavaScript would otherwise normalize.
    if (!Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== observed || observed.startsWith('0000-')) {
      problem = 'observation date is invalid';
    } else if (parsed > REF_DATE) {
      problem = 'observation date is in the future';
    }
    if (problem) return {
      status: 'unknown',
      reason: `${label}: ${problem}; recency cannot be verified`,
      action: `Record a valid observation date for ${label}`,
      evidence: evidence(name, f),
    };
    const age = days(f.date);
    if (age > win) return { status: 'unknown', reason: `${label} is ${age} days old (window ${win})`, action: `Repeat ${label}`, evidence: evidence(name, f) };
  }
  if (f.value === null || f.value === undefined) return { status: 'unknown', reason: `${label}: no value`, action: `Record ${label}`, evidence: evidence(name, f) };
  const holds = satisfies(name, f, c.test);
  const ok = c.polarity === 'require' ? holds : !holds;
  return { status: ok ? 'met' : 'not_met', reason: null, action: null, evidence: evidence(name, f) };
}

export function summarize(rows) {
  const counts = { met: 0, not_met: 0, unknown: 0 };
  rows.forEach((r) => { counts[r.status] += 1; });
  const verdict = counts.not_met ? 'blocked' : counts.unknown ? 'provisional' : 'ready';
  return { counts, verdict };
}

/** Re-assess every criterion of a match with patched facts (what-if). */
export function reassess(match, facts) {
  const rows = match.criteria.map((c) => ({ ...c, ...assess(c, facts) }));
  return { rows, ...summarize(rows) };
}
