// The browser evaluator must agree with the Python evaluator on every exported criterion.
//   node tests/parity.mjs
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { assess } from '../web/js/evaluator.js';

const dir = new URL('../web/data/', import.meta.url);
const patients = JSON.parse(readFileSync(new URL('patients.json', dir)));
let n = 0, bad = 0;
for (const p of patients) {
  const m = JSON.parse(readFileSync(new URL(`matches/${p.id}.json`, dir)));
  for (const x of m.matches) {
    for (const c of x.criteria) {
      const js = assess(c, p.facts);
      n += 1;
      if (js.status !== c.status) {
        bad += 1;
        if (bad < 6) console.log('MISMATCH', p.id, x.nct_id, c.fact, 'python', c.status, 'js', js.status, c.reason);
      }
    }
  }
}
console.log(`${n} criteria checked, ${bad} mismatches`);
if (bad) process.exit(1);

// Shared synthetic edge cases also run in Python; exported snapshots alone do not cover bad dates.
const cases = JSON.parse(readFileSync(new URL('recency_cases.json', import.meta.url)));
for (const c of cases) {
  const criterion = { fact: 'anc', kind: c.kind, test: { op: 'ge', value: 1.5 }, polarity: c.polarity || 'require' };
  const fact = { value: c.value ?? 3.0, status: c.status || 'done', source: 'REAL:test' };
  if (!c.omit_date) fact.date = c.date;
  const result = assess(criterion, { anc: fact });
  assert.equal(result.status, c.expected, c.name);
  assert.equal(result.evidence.source, 'REAL:test', c.name);
  assert.equal(result.evidence.date, fact.date, c.name);
  if (c.expected === 'unknown') assert.ok(result.reason && result.action, c.name);
}
console.log(`${cases.length} shared recency cases passed`);
