#!/usr/bin/env python3
"""Dependency-free, resumable, budget-limited criterion inference benchmark."""
import argparse
import collections
import concurrent.futures
import hashlib
import json
import math
import pathlib
import random
import re
import statistics
import threading
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
LABELS = ['included', 'not included', 'excluded', 'not excluded',
          'not enough information', 'not applicable']
MODELS = ['openai/gpt-5.6-sol', 'anthropic/claude-sonnet-5.5',
          'google/gemini-3.1-pro-preview']
VARIANTS = ['direct', 'evidence_first']
SEED = 20261018
MAX_TOKENS = 4096
LOCK = threading.Lock()


def read(path):
    return json.loads(path.read_text())


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False))
    tmp.replace(path)


def get(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.load(r)


def setup():
    source = ROOT / 'data/source.json'
    if not source.exists():
        rows = []
        for offset in range(0, 1015, 100):
            url = ('https://datasets-server.huggingface.co/rows?dataset='
                   'ncbi%2FTrialGPT-Criterion-Annotations&config=default&split=train'
                   f'&offset={offset}&length=100')
            part = get(url)
            rows.extend(x['row'] for x in part['rows'])
        assert len(rows) == 1015 and len({x['annotation_id'] for x in rows}) == 1015
        assert set(x['expert_eligibility'] for x in rows) == set(LABELS)
        save(source, rows)
    rows = read(source)
    patients = sorted({r['patient_id'] for r in rows})
    random.Random(SEED).shuffle(patients)
    dev, test = set(patients[:16]), set(patients[16:])
    assert not dev & test
    manifest = {
        'seed': SEED, 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'dev_patients': sorted(dev), 'test_patients': sorted(test),
        'labels': LABELS, 'models': MODELS, 'variants': VARIANTS,
        'max_tokens': MAX_TOKENS, 'reasoning_effort': 'low', 'batch_size': 8,
        'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }
    for name, ids in [('dev', dev), ('test', test)]:
        rr = [r for r in rows if r['patient_id'] in ids]
        manifest[name + '_rows'] = len(rr)
        manifest[name + '_labels'] = dict(collections.Counter(r['expert_eligibility'] for r in rr))
    manifest['shared_trials'] = sorted(
        {r['trial_id'] for r in rows if r['patient_id'] in dev} &
        {r['trial_id'] for r in rows if r['patient_id'] in test})
    target = ROOT / 'manifest.json'
    if target.exists():
        old = read(target)
        assert all(old[k] == v for k, v in manifest.items() if k != 'created_utc'), 'Manifest changed'
    else:
        save(target, manifest)
    if not (ROOT / 'catalog.json').exists():
        catalog = get('https://openrouter.ai/api/v1/models')['data']
        selected = {m['id']: m for m in catalog if m['id'] in MODELS}
        assert set(selected) == set(MODELS)
        save(ROOT / 'catalog.json', selected)
    print(json.dumps({k: v for k, v in manifest.items() if k not in ['dev_patients', 'test_patients']}, indent=2), flush=True)


BASE = '''You are evaluating individual clinical trial criteria against a numbered patient note for a research benchmark. This is not an enrolment decision.
Use only the supplied note. Do not use outside facts or invent patient findings.
Allowed labels and polarity:
- inclusion: included (criterion satisfied), not included (criterion contradicted), not enough information, or not applicable.
- exclusion: excluded (exclusion condition present), not excluded (condition absent or not documented under this benchmark's annotation convention), not enough information (an explicitly unresolved finding or required quantitative evidence cannot be established), or not applicable.
An exclusion label "excluded" means the patient fails that criterion. Do not invert this.
For inclusion, absence of evidence is not evidence of satisfaction. For compound conditions, honor AND, OR, negation, thresholds, dates, and prior-treatment requirements. Not applicable is reserved for conditions that do not apply to this patient, not missing information.
Return ONLY a JSON object with a "decisions" array. One item per supplied criterion, each with: "id" (integer annotation ID), "label" (one exact allowed label), "sentence_ids" (array of supporting numbered note sentences, empty if no evidence), "reason" (at most 20 words).
'''
EXTRA = '''Before each decision, identify the exact patient evidence and separate it from unreported facts. Check the criterion's type, logical operators, numeric thresholds and temporal requirements against that evidence. Cite the relevant sentence IDs; verify every cited ID exists and that your final label agrees with your stated evidence. A missing inclusion fact must stay unknown. For exclusions, preserve the benchmark's undocumented-condition convention above. Do not turn an uncertainty into a confirmed diagnosis. Perform these checks internally and keep the requested output concise.
'''


def prompt(rows, variant):
    assert variant in VARIANTS
    # Explicit allowlist: no gold, GPT outputs, training flags, or expert evidence.
    payload = {'patient_note': rows[0]['note'], 'trial_title': rows[0]['trial_title'],
               'criteria': [{'id': r['annotation_id'], 'type': r['criterion_type'],
                             'text': r['criterion_text']} for r in rows]}
    return [{'role': 'system', 'content': BASE + (EXTRA if variant == 'evidence_first' else '')},
            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]


def batches(split):
    manifest = read(ROOT / 'manifest.json')
    ids = set(manifest[split + '_patients'])
    groups = collections.defaultdict(list)
    for r in read(ROOT / 'data/source.json'):
        if r['patient_id'] in ids:
            groups[(r['patient_id'], r['trial_id'])].append(r)
    output = []
    for key, rr in sorted(groups.items()):
        rr.sort(key=lambda r: r['annotation_id'])
        for i in range(0, len(rr), 8):
            output.append((f'{key[0]}__{key[1]}__{i//8}', rr[i:i+8]))
    return output


def parse(content, rows):
    try:
        content = re.sub(r'^```(?:json)?\s*|\s*```$', '', content.strip())
        obj = json.loads(content)
        arr = obj['decisions']
        assert isinstance(arr, list)
    except (ValueError, KeyError, TypeError, AssertionError):
        arr = []
    counts = collections.Counter(str(x.get('id')) for x in arr if isinstance(x, dict))
    by_id = {str(x.get('id')): x for x in arr if isinstance(x, dict)}
    out = []
    for r in rows:
        ident = str(r['annotation_id'])
        d = by_id.get(ident, {})
        allowed = ({'included', 'not included'} if r['criterion_type'] == 'inclusion'
                   else {'excluded', 'not excluded'}) | {'not enough information', 'not applicable'}
        label = d.get('label')
        if not isinstance(label, str) or label not in allowed or counts[ident] != 1:
            label = '__invalid__'
        citations = d.get('sentence_ids', [])
        if not isinstance(citations, list) or any(type(x) is not int for x in citations):
            citations = []
        valid = {int(x) for x in re.findall(r'(?m)^(\d+)\.', r['note'])}
        out.append({'annotation_id': r['annotation_id'], 'patient_id': r['patient_id'],
                    'label': label, 'sentence_ids': citations,
                    'invalid_citations': len(set(citations) - valid),
                    'reason': str(d.get('reason', ''))})
    return out


class Budget:
    def __init__(self, cap):
        self.cap = cap
        self.pending = 0.0
        self.spent = 0.0
        self.stopped = False
        self.ledger = ROOT / 'calls.jsonl'
        if self.ledger.exists():
            for line in self.ledger.read_text().splitlines():
                d = json.loads(line)
                self.spent += d.get('charged_cost', 0.0)
                if d.get('cost_unknown'):
                    self.stopped = True

    def reserve(self, amount):
        with LOCK:
            if self.stopped or self.spent + self.pending + amount > self.cap:
                raise RuntimeError('Budget reservation exceeds cap or cost unknown; stopping')
            self.pending += amount

    def finish(self, reserved, record):
        with LOCK:
            self.pending -= reserved
            self.spent += record['charged_cost']
            self.stopped |= record.get('cost_unknown', False)
            with self.ledger.open('a') as f:
                f.write(json.dumps(record) + '\n')


def infer(model, variant, split, batch, rows, budget, effort='low', output_cap=MAX_TOKENS):
    safe_model = model.replace('/', '__')
    arm = variant if effort == 'low' else variant + '__' + effort
    path = ROOT / 'responses' / split / safe_model / arm / (batch + '.json')
    if path.exists():
        return
    messages = prompt(rows, variant)
    payload = {'model': model, 'messages': messages, 'max_tokens': output_cap,
               'reasoning': {'effort': effort}, 'provider': {'data_collection': 'deny'},
               'usage': {'include': True}}
    data = json.dumps(payload).encode()
    pricing = read(ROOT / 'catalog.json')[model]['pricing']
    # Conservative upper bound: one input token per UTF-8 byte + output cap.
    reservation = (len(data) + 512) * float(pricing['prompt']) + output_cap * float(pricing['completion'])
    key = pathlib.Path('/home/model/.config/lana/openrouter.key').read_text().strip()
    for attempt in range(3):
        budget.reserve(reservation)
        start = time.monotonic()
        req = urllib.request.Request('https://openrouter.ai/api/v1/chat/completions', data=data,
                                     headers={'Authorization': 'Bearer ' + key,
                                              'Content-Type': 'application/json',
                                              'X-Title': 'LANA public synthetic benchmark'})
        record = {'model': model, 'variant': arm, 'split': split, 'batch': batch,
                  'reasoning_effort': effort, 'output_cap': output_cap,
                  'attempt': attempt, 'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                  'request_sha256': hashlib.sha256(data).hexdigest()}
        try:
            with urllib.request.urlopen(req, timeout=240) as response:
                result = json.load(response)
            cost = result.get('usage', {}).get('cost')
            record.update(charged_cost=float(cost) if cost is not None else reservation,
                          cost_unknown=cost is None, seconds=time.monotonic()-start,
                          usage=result.get('usage'), generation_id=result.get('id'))
            if 'choices' not in result:
                raise ValueError('Successful HTTP response missing choices')
            content = result['choices'][0]['message'].get('content') or ''
            artifact = dict(record, response=result, predictions=parse(content, rows))
            save(path, artifact)
            budget.finish(reservation, record)
            print(json.dumps({'done': batch, 'model': model, 'variant': arm, 'split': split,
                              'cost': record['charged_cost'], 'spent_total': round(budget.spent, 4),
                              'seconds': round(record['seconds'], 1),
                              'valid': sum(x['label'] != '__invalid__' for x in artifact['predictions']),
                              'n': len(rows)}), flush=True)
            if record['cost_unknown']:
                raise RuntimeError('Missing API cost; reserved maximum charged and stopped')
            return
        except urllib.error.HTTPError as e:
            # Error text can include server details; never persist request headers.
            record.update(error='HTTP ' + str(e.code), charged_cost=0.0,
                          error_detail=e.read().decode(errors='replace').replace(key, '[REDACTED]')[:1200],
                          seconds=time.monotonic()-start)
            budget.finish(reservation, record)
            print(json.dumps({'error': record['error'], 'model': model,
                              'detail': record['error_detail']}), flush=True)
            if e.code in [429, 500, 502, 503, 504] and attempt < 2:
                time.sleep(2 ** (attempt+1))
                continue
            raise RuntimeError(f'{model}: HTTP {e.code}') from None
        except (TimeoutError, OSError) as e:
            # Timed-out requests may have been billed. Reserve their full maximum.
            record.update(error=type(e).__name__, charged_cost=reservation,
                          cost_unknown=True, seconds=time.monotonic()-start)
            budget.finish(reservation, record)
            raise RuntimeError('Transport outcome/cost unknown; stopped for reconciliation') from None
        except (ValueError, KeyError, TypeError) as e:
            record.update(error='Unusable API envelope: ' + type(e).__name__,
                          charged_cost=reservation, cost_unknown=True,
                          seconds=time.monotonic()-start)
            budget.finish(reservation, record)
            raise RuntimeError('Unusable API envelope; reserved maximum charged and stopped') from None


def run(args):
    budget = Budget(args.cap)
    choices = read(ROOT / 'selection.json') if args.split == 'test' else None
    jobs = []
    for model in MODELS:
        if args.model and args.model != model:
            continue
        variants = [choices[model]['variant']] if choices else VARIANTS
        if args.variant:
            variants = [v for v in variants if v == args.variant]
        bb = batches(args.split)
        if args.limit:
            bb = bb[:args.limit]
        for variant in variants:
            jobs.extend((model, variant, args.split, bid, rr, budget, args.effort, args.output_cap) for bid, rr in bb)
    # Round robin models/prompt arms prevents one model consuming the whole budget.
    jobs.sort(key=lambda x: (x[3], x[1], x[0]))
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        active = {}
        iterator = iter(jobs)
        for _ in range(args.workers):
            try:
                j = next(iterator)
            except StopIteration:
                break
            active[pool.submit(infer, *j)] = j
        while active:
            done, _ = concurrent.futures.wait(active, return_when=concurrent.futures.FIRST_COMPLETED)
            for task in done:
                del active[task]
                task.result()
                try:
                    j = next(iterator)
                except StopIteration:
                    continue
                active[pool.submit(infer, *j)] = j
    print('Run complete. Ledger spend upper bound:', round(budget.spent, 6), flush=True)


def metrics(gold, pred):
    assert len(gold) == len(pred)
    confusion = {g: {p: 0 for p in LABELS + ['__invalid__']} for g in LABELS}
    for g, p in zip(gold, pred):
        confusion[g][p] += 1
    classes = {}
    for lab in LABELS:
        tp = sum(g == p == lab for g, p in zip(gold, pred))
        actual, guessed = gold.count(lab), pred.count(lab)
        precision = tp / guessed if guessed else 0
        recall = tp / actual if actual else 0
        f1 = 2 * tp / (actual + guessed) if actual + guessed else 0
        classes[lab] = dict(support=actual, precision=precision, recall=recall, f1=f1)
    fail = {'not included', 'excluded'}
    passes = {'included', 'not excluded'}
    failures = sum(g in fail for g in gold)
    unknowns = gold.count('not enough information')
    return {'n': len(gold), 'accuracy': sum(g == p for g, p in zip(gold, pred))/len(gold),
            'macro_f1': sum(x['f1'] for x in classes.values())/6,
            'invalid_outputs': pred.count('__invalid__'),
            'definite_failures': failures,
            'false_passes': sum(g in fail and p in passes for g, p in zip(gold, pred)),
            'false_pass_rate': sum(g in fail and p in passes for g, p in zip(gold, pred))/failures if failures else None,
            'unknowns': unknowns,
            'unknown_passes': sum(g == 'not enough information' and p in passes for g, p in zip(gold, pred)),
            'per_class': classes, 'confusion': confusion}


def collect(model, variant, split, require_complete=False):
    paths = ROOT / 'responses' / split / model.replace('/', '__') / variant
    predictions = {}
    artifacts = []
    for p in sorted(paths.glob('*.json')):
        d = read(p)
        artifacts.append(d)
        for x in d['predictions']:
            assert x['annotation_id'] not in predictions
            predictions[x['annotation_id']] = x
    rows = [r for _, rr in batches(split) for r in rr]
    if require_complete:
        assert set(predictions) == {r['annotation_id'] for r in rows}, f'Incomplete arm {model}/{variant}/{split}'
    rows = [r for r in rows if r['annotation_id'] in predictions]
    if not rows:
        return None
    gold = [r['expert_eligibility'] for r in rows]
    pred = [predictions[r['annotation_id']]['label'] for r in rows]
    m = metrics(gold, pred)
    tp = ng = np = exact = invalid_cites = 0
    for r in rows:
        p = predictions[r['annotation_id']]
        gset = set(json.loads(r['expert_sentences']))
        pset = set(p['sentence_ids'])
        tp += len(gset & pset)
        ng += len(gset)
        np += len(pset)
        exact += gset == pset
        invalid_cites += p['invalid_citations']
    m['evidence'] = {'micro_precision': tp/np if np else 0, 'micro_recall': tp/ng if ng else 0,
                     'micro_f1': 2*tp/(np+ng) if np+ng else 0,
                     'exact_set_match': exact/len(rows), 'invalid_citations': invalid_cites}
    m['cost_usd'] = sum(x['charged_cost'] for x in artifacts)
    m['request_seconds_median'] = statistics.median(x['seconds'] for x in artifacts)
    m['requests'] = len(artifacts)
    m['complete'] = len(rows) == sum(len(rr) for _, rr in batches(split))
    return m


def select():
    result = {}
    for model in MODELS:
        candidates = [(v, collect(model, v, 'dev', True)) for v in VARIANTS]
        # Stable tie-breaking prefers direct (first registered candidate).
        best = max(candidates, key=lambda x: (x[1]['macro_f1'], x[1]['accuracy']))
        result[model] = {'variant': best[0], 'dev_scores': {v: s for v, s in candidates}}
    target = ROOT / 'selection.json'
    if target.exists():
        assert read(target) == result, 'Selection already frozen; refusing change'
    else:
        save(target, result)
    print(json.dumps({m: {'variant': s['variant'], 'macro_f1': s['dev_scores'][s['variant']]['macro_f1']} for m, s in result.items()}, indent=2))


def score(split):
    # Test scores are intentionally inaccessible before configuration selection.
    selection = read(ROOT / 'selection.json') if split == 'test' else None
    results = {}
    for model in MODELS:
        for variant in ([selection[model]['variant']] if selection else VARIANTS):
            m = collect(model, variant, split, require_complete=(split == 'test'))
            if m:
                results[model + ':' + variant] = m
    save(ROOT / f'{split}_scores.json', results)
    print(json.dumps({k: {x: v[x] for x in ['n', 'macro_f1', 'accuracy', 'false_passes', 'definite_failures', 'invalid_outputs', 'cost_usd', 'complete']} for k, v in results.items()}, indent=2))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['setup', 'run', 'score', 'select'])
    p.add_argument('--split', choices=['dev', 'test'], default='dev')
    p.add_argument('--model', choices=MODELS)
    p.add_argument('--variant', choices=VARIANTS)
    p.add_argument('--limit', type=int)
    p.add_argument('--workers', type=int, default=3)
    p.add_argument('--cap', type=float, default=30)
    p.add_argument('--effort', choices=['low', 'high'], default='low')
    p.add_argument('--output-cap', type=int, choices=[4096, 8192], default=4096)
    args = p.parse_args()
    if args.action == 'setup':
        setup()
    elif args.action == 'run':
        run(args)
    elif args.action == 'select':
        select()
    else:
        score(args.split)


if __name__ == '__main__':
    main()
