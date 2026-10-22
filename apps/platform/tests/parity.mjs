// The browser evaluator must agree with the Python evaluator on every exported criterion.
//   node tests/parity.mjs
import { readFileSync } from 'node:fs';
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
process.exit(bad ? 1 : 0);
