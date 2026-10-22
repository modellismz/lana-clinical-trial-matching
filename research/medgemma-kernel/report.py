#!/usr/bin/env python3
"""Held-out report. Refuses to rank incomplete frontier arms."""
import collections
import csv
import hashlib
import html
import itertools
import json
import pathlib
import random
import statistics
import bench


def predictions(model, variant, split='test'):
    root = bench.ROOT / 'responses' / split / model.replace('/', '__') / variant
    return {x['annotation_id']: x for p in root.glob('*.json')
            for x in bench.read(p)['predictions']}


def f1(gold, pred):
    gc, pc = collections.Counter(gold), collections.Counter(pred)
    tp = collections.Counter(g for g, p in zip(gold, pred) if g == p)
    return sum(2*tp[l]/(gc[l]+pc[l]) if gc[l]+pc[l] else 0 for l in bench.LABELS)/6


def percentile(values, q):
    values = sorted(values)
    idx = (len(values)-1)*q
    lo, hi = int(idx), min(int(idx)+1, len(values)-1)
    return values[lo] + (values[hi]-values[lo])*(idx-lo)


def intervals(rows, arms):
    groups = collections.defaultdict(list)
    for r in rows:
        groups[r['patient_id']].append(r)
    patients = sorted(groups)
    rng = random.Random(bench.SEED)
    samples = {a: [] for a in arms}
    pairs = {a: [] for a in itertools.combinations(arms, 2)}
    for _ in range(2000):
        sampled = [r for p in rng.choices(patients, k=len(patients)) for r in groups[p]]
        g = [r['expert_eligibility'] for r in sampled]
        values = {}
        for name, preds in arms.items():
            values[name] = f1(g, [preds[r['annotation_id']]['label'] for r in sampled])
            samples[name].append(values[name])
        for a, b in pairs:
            pairs[(a, b)].append(values[a]-values[b])
    return {'resamples': 2000, 'seed': bench.SEED, 'unit': 'patient cluster',
            'macro_f1_ci95': {a: [percentile(v, .025), percentile(v, .975)] for a, v in samples.items()},
            'paired_macro_f1_difference_ci95': [
                {'model_a': a, 'model_b': b, 'ci95': [percentile(v, .025), percentile(v, .975)]}
                for (a, b), v in pairs.items()]}


def main():
    selection = bench.read(bench.ROOT / 'selection.json')
    manifest = bench.read(bench.ROOT / 'manifest.json')
    rows = [r for _, rr in bench.batches('test') for r in rr]
    devrows = [r for _, rr in bench.batches('dev') for r in rr]
    majority = collections.Counter(r['expert_eligibility'] for r in devrows).most_common(1)[0][0]
    scores = {'development_majority': bench.metrics(
        [r['expert_eligibility'] for r in rows], [majority]*len(rows))}
    arms = {}
    for model in bench.MODELS:
        variant = selection[model]['variant']
        scores[model] = bench.collect(model, variant, 'test', True)
        scores[model]['variant'] = variant
        arms[model] = predictions(model, variant)
    local_id = 'google/medgemma-1.5-4b-it'
    local_sel = bench.ROOT / 'local_selection.json'
    if local_sel.exists():
        variant = bench.read(local_sel)['variant']
        local = bench.collect(local_id, variant, 'test')
        if local and local['complete']:
            scores[local_id] = local
            scores[local_id]['variant'] = variant
            arms[local_id] = predictions(local_id, variant)
    high_scores, high_status = {}, {}
    for model in bench.MODELS:
        variant = selection[model]['variant'] + '__high'
        sc = bench.collect(model, variant, 'test')
        high_status[model] = {'completed_criteria': sc['n'] if sc else 0,
                              'expected_criteria': len(rows), 'complete': bool(sc and sc['complete'])}
        if sc and sc['complete']:
            high_scores[model] = dict(sc, variant=variant)
    ci = intervals(rows, arms)
    bench.save(bench.ROOT / 'results.json', {'manifest': manifest, 'scores': scores,
                                           'high_effort_scores': high_scores,
                                           'high_effort_status': high_status, 'bootstrap': ci})
    out = bench.ROOT / 'scores.csv'
    columns = ['model', 'variant', 'n', 'macro_f1', 'accuracy', 'false_passes',
               'definite_failures', 'unknown_passes', 'unknowns', 'invalid_outputs', 'cost_usd']
    with out.open('w') as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        for model, s in scores.items():
            w.writerow({'model': model, **{k: s.get(k) for k in columns if k != 'model'}})
    with (bench.ROOT / 'experiments.tsv').open('w') as f:
        columns = ['phase', 'model', 'variant', 'macro_f1', 'accuracy', 'cost_usd', 'status']
        w = csv.DictWriter(f, fieldnames=columns, delimiter='\t')
        w.writeheader()
        for model, selected in selection.items():
            for variant, s in selected['dev_scores'].items():
                w.writerow(dict(phase='development', model=model, variant=variant,
                                macro_f1=s['macro_f1'], accuracy=s['accuracy'], cost_usd=s['cost_usd'],
                                status='selected' if variant == selected['variant'] else 'not_selected'))
        for model, s in scores.items():
            w.writerow(dict(phase='held_out', model=model, variant=s.get('variant', majority),
                            macro_f1=s['macro_f1'], accuracy=s['accuracy'], cost_usd=s.get('cost_usd', 0),
                            status='reported'))
    errors = []
    with (bench.ROOT / 'test_predictions.jsonl').open('w') as f:
        for model, preds in arms.items():
            for r in rows:
                p = preds[r['annotation_id']]
                record = {'model': model, 'annotation_id': r['annotation_id'],
                          'patient_id': r['patient_id'], 'trial_id': r['trial_id'],
                          'criterion_type': r['criterion_type'], 'gold': r['expert_eligibility'],
                          'prediction': p['label'], 'sentence_ids': p['sentence_ids'],
                          'expert_sentences': r['expert_sentences'], 'reason': p['reason']}
                f.write(json.dumps(record)+'\n')
                if record['gold'] != record['prediction']:
                    errors.append(dict(record, criterion=r['criterion_text'], note=r['note']))
    bench.save(bench.ROOT / 'error_analysis.json', errors)
    calls = [json.loads(x) for x in (bench.ROOT / 'calls.jsonl').read_text().splitlines()]
    total = sum(c['charged_cost'] for c in calls)
    sorted_models = sorted(arms, key=lambda m: scores[m]['macro_f1'], reverse=True)
    lines = ['# LANA comparator benchmark — measured results', '',
             f'Completed hosted evaluation on **{len(rows)} held-out criteria from {len(manifest["test_patients"])} synthetic patients**. '
             f'Development used {len(devrows)} criteria from {len(manifest["dev_patients"])} separate patients. '
             'No patient or trial overlaps this split.', '',
             '**These are frontier comparator results. The complete LANA pipeline has not been evaluated.**', '',
             '| Model | Selected prompt | Macro-F1 (95% patient-bootstrap CI) | Accuracy | False pass / definite fail | Pass / Unknown |',
             '|---|---|---:|---:|---:|---:|']
    for m in sorted_models + ['development_majority']:
        s = scores[m]
        interval = ci['macro_f1_ci95'].get(m)
        interval_text = f' ({interval[0]*100:.1f}–{interval[1]*100:.1f})' if interval else ''
        lines.append(f'| {m} | {s.get("variant", majority)} | {s["macro_f1"]*100:.1f}%{interval_text} | '
                     f'{s["accuracy"]*100:.1f}% | {s["false_passes"]}/{s["definite_failures"]} | '
                     f'{s["unknown_passes"]}/{s["unknowns"]} |')
    lines += ['', '## Higher-reasoning secondary stress test', '',
              'All three development-selected prompts also run at reasoning=high and an 8,192 output-token cap, '
              'subject to available account credit and the same US$30 aggregate spending cap. '
              'Higher-budget results are separate from the primary lower-budget comparison.', '',
              '| Model | Completed test criteria | Macro-F1 | Accuracy | Status |',
              '|---|---:|---:|---:|---|']
    for model, status in high_status.items():
        s = high_scores.get(model)
        mf = f'{s["macro_f1"]*100:.1f}%' if s else 'not scored'
        ac = f'{s["accuracy"]*100:.1f}%' if s else 'not scored'
        state = 'complete' if s else 'incomplete — do not rank'
        lines.append(f'| {model} | {status["completed_criteria"]}/{status["expected_criteria"]} | {mf} | {ac} | {state} |')
    lines += ['', '## What was actually run', '',
              'Each frontier received the same notes, criteria, six-label definitions and JSON schema. '
              'Two fixed prompt candidates were evaluated on development only; each model’s winner was frozen before its test calls. '
              'Criteria were batched (at most eight) within a patient–trial pair. Reasoning effort was low; output cap was 4,096 tokens. '
              'This is criterion classification with the correct trial already supplied: it does not measure retrieval, enrolment, outcome prediction, RL, IRIS integration or patient benefit.', '',
              f'API ledger total for development + test + logged retries: **US${total:.4f}**, within US$30 cap. '
              'This excludes account top-up fees and local compute. API tokens and returned providers are retained in response artifacts.', '',
              '## Paired comparisons', '',
              'Intervals below are A minus B in macro-F1 percentage points, using 2,000 paired patient-cluster bootstrap samples. '
              'They are exploratory intervals without multiple-comparison correction. A higher point score alone does not establish superiority.', '']
    for pair in ci['paired_macro_f1_difference_ci95']:
        a, b = pair['model_a'], pair['model_b']
        delta = (scores[a]['macro_f1']-scores[b]['macro_f1'])*100
        lo, hi = pair['ci95']
        lines.append(f'- {a} minus {b}: {delta:+.2f} pp; 95% CI [{lo*100:+.2f}, {hi*100:+.2f}] pp.')
    lines += ['', '## Per-class results', '',
              '| Model | Label | Support | Precision | Recall | F1 |', '|---|---|---:|---:|---:|---:|']
    for m in sorted_models:
        for lab, v in scores[m]['per_class'].items():
            lines.append(f'| {m} | {lab} | {v["support"]} | {v["precision"]:.3f} | {v["recall"]:.3f} | {v["f1"]:.3f} |')
    lines += ['', '## Development search', '',
              '| Model | Candidate | Macro-F1 | Accuracy | Selected |', '|---|---|---:|---:|---|']
    for m, s in selection.items():
        for v, sc in s['dev_scores'].items():
            lines.append(f'| {m} | {v} | {sc["macro_f1"]:.4f} | {sc["accuracy"]:.4f} | {v == s["variant"]} |')
    lines += ['', '## Limitations and interpretation', '',
              '- Public synthetic mixed-disease data; not a colorectal-specific or hospital deployment validation. Models may have seen this published benchmark during pretraining.',
              '- Native benchmark conventions allow undocumented exclusion conditions to be marked `not excluded`. This must not become a clinical policy without clinician review. Unknown is not a confirmed clinical failure.',
              '- Only 22 definite-failure criteria are present in the test set. False-pass results are sparse criterion diagnostics, not a reliable patient harm rate or trial-level safety estimate.',
              '- Frontier models have different tokenizer, hidden reasoning, precision and serving systems. Equal request caps do not imply equal compute. Provider routing can change.',
              '- Macro-F1 keeps all six labels, including rare classes. Bootstrap uncertainty is large for rare classes.',
              '- Full raw responses, failures and prompts are retained. No wrong-answer retries or test-based tuning were performed.',
              '- MedGemma requires authorized gated Hugging Face access. If absent from the table, it did not run. No claim that LANA beats a frontier model is supported by this report.', '',
              '## Reproduction and provenance', '',
              f'- Source SHA-256: `{manifest["source_sha256"]}`.',
              '- Dataset: https://huggingface.co/datasets/ncbi/TrialGPT-Criterion-Annotations',
              '- Catalog snapshot: `catalog.json`; split and inference controls: `manifest.json`.',
              '- Calls and cost: `calls.jsonl`; criterion predictions: `test_predictions.jsonl`; all errors: `error_analysis.json`.',
              '- `results.json` includes full confusion matrices, evidence scores, per-class metrics and confidence intervals.',
              '- `bench.py setup`; `bench.py run --split dev --workers 6`; `bench.py select`; `bench.py run --split test --workers 6`; `report.py`.',
              '- No upstream autoresearch training or RL was performed. This is a bounded inference development search.', '']
    text = '\n'.join(lines)
    (bench.ROOT / 'REPORT.md').write_text(text)
    # Self-contained readable HTML table + inspectable full narrative.
    table = '<table><thead><tr><th>Model</th><th>Macro-F1</th><th>Accuracy</th><th>False passes</th></tr></thead><tbody>'
    for m in sorted_models:
        s = scores[m]
        table += f'<tr><td>{html.escape(m)}</td><td>{s["macro_f1"]*100:.1f}%</td><td>{s["accuracy"]*100:.1f}%</td><td>{s["false_passes"]}/{s["definite_failures"]}</td></tr>'
    table += '</tbody></table>'
    document = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LANA benchmark</title><style>body{font:16px/1.6 system-ui,sans-serif;max-width:1100px;margin:48px auto;padding:0 24px;color:#172b40;background:#f8fafc}h1{font-size:34px}table{border-collapse:collapse;width:100%;background:white}th,td{text-align:left;padding:14px;border-bottom:1px solid #cbd5e1}th{background:#e2e8f0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 ui-monospace,monospace;background:white;padding:24px;border:1px solid #e2e8f0}.notice{border-left:5px solid #a16207;padding:16px;background:#fef9c3}</style><h1>LANA · Frontier comparator benchmark</h1><p class="notice">Measured frontier baselines. Full LANA superiority is untested.</p>'''
    document += f'<p>{len(rows)} held-out criterion decisions · {len(manifest["test_patients"])} patients · API spend ${total:.4f}</p>'
    document += table + '<h2>Methods, uncertainty and full results</h2><pre>' + html.escape(text) + '</pre></html>'
    (bench.ROOT / 'REPORT.html').write_text(document)
    print(json.dumps({'total_api_cost_usd': total, 'scores': {m: {k: scores[m][k] for k in ['macro_f1', 'accuracy', 'false_passes', 'definite_failures']} for m in sorted_models}, 'bootstrap': ci}, indent=2))


if __name__ == '__main__':
    main()
