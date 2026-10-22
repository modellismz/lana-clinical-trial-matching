#!/usr/bin/env python3
"""Resumable, entirely local 4B baseline/RAG/agent study; no inference API calls."""
import hashlib
import itertools
import json
import os
import time
import traceback
import bench
from local_evidence import messages as review_messages, typed_age

MODEL = 'google/medgemma-1.5-4b-it'
ARMS = ['rag_only', 'memory_audit']
FRONTIER = '/home/model/research/lana-benchmark-openai'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def immutable(path, value):
    if path.exists():
        assert bench.read(path) == value, 'Frozen artifact changed: ' + str(path)
    else:
        bench.save(path, value)


def status(phase, **extra):
    bench.save(bench.ROOT/'LOCAL_STUDY_STATUS.json', dict(
        phase=phase, pid=os.getpid(), utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), **extra))


def final_answer(text):
    """Strip only the documented MedGemma thought channel, never harvest draft JSON."""
    if text.lstrip().startswith('<unused94>'):
        if text.count('<unused95>') != 1:
            return ''
        return text.split('<unused95>', 1)[1].strip()
    return text


class Engine:
    def __init__(self):
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor, BitsAndBytesConfig
        self.torch = torch
        self.runtime = bench.read(bench.ROOT/'local_runtime_config.json')
        dtype = getattr(torch, self.runtime['compute_dtype'])
        self.revision = bench.read(bench.ROOT/'local_revision.json')['revision']
        self.processor = AutoProcessor.from_pretrained(MODEL, revision=self.revision)
        quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4',
                                  bnb_4bit_compute_dtype=dtype, bnb_4bit_use_double_quant=True)
        self.model = AutoModelForImageTextToText.from_pretrained(
            MODEL, revision=self.revision, quantization_config=quant,
            torch_dtype=dtype, device_map={'': 0}, low_cpu_mem_usage=True,
            attn_implementation='eager')
        self.model.eval()
        bench.save(bench.ROOT/'local_study_environment.json', dict(
            revision=self.revision, runtime=self.runtime, device=torch.cuda.get_device_name(),
            torch_version=torch.__version__, cpu_threads=torch.get_num_threads(),
            device_map={k: str(v) for k, v in self.model.hf_device_map.items()},
            generation_config=self.model.generation_config.to_dict()))

    def infer(self, split, arm, bid, rows, messages):
        target = bench.ROOT/'responses'/split/MODEL.replace('/', '__')/arm/(bid+'.json')
        request_hash = hashlib.sha256(json.dumps(messages).encode()).hexdigest()
        if target.exists():
            saved = bench.read(target)
            assert saved['request_sha256'] == request_hash and saved['revision'] == self.revision
            return saved['predictions']
        typed = [{'role': m['role'], 'content': [{'type': 'text', 'text': m['content']}]} for m in messages]
        inputs = self.processor.apply_chat_template(typed, add_generation_prompt=True, tokenize=True,
                    return_dict=True, return_tensors='pt').to(self.model.device)
        torch = self.torch
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()
        started = time.monotonic()
        from transformers import StoppingCriteria, StoppingCriteriaList, LogitsProcessor, LogitsProcessorList
        class FiniteLogits(LogitsProcessor):
            def __call__(self, input_ids, scores):
                if torch.isnan(scores).any() or torch.isposinf(scores).any() or not torch.isfinite(scores).any(dim=-1).all():
                    raise RuntimeError('Non-finite logits during generation; stopping without scoring')
                return scores
        input_length = inputs['input_ids'].shape[-1]
        class Progress(StoppingCriteria):
            def __call__(self, input_ids, scores, **kwargs):
                count = input_ids.shape[-1]-input_length
                if count % 64 == 0:
                    print(json.dumps(dict(progress=arm, split=split, batch=bid,
                                          generated_tokens=count, seconds=time.monotonic()-started)), flush=True)
                return False
        with torch.inference_mode():
            output = self.model.generate(**inputs, do_sample=False, max_new_tokens=bench.MAX_TOKENS,
                                         stopping_criteria=StoppingCriteriaList([Progress()]),
                                         logits_processor=LogitsProcessorList([FiniteLogits()]))
        torch.cuda.synchronize()
        tokens = output[0, inputs['input_ids'].shape[-1]:]
        text = self.processor.decode(tokens, skip_special_tokens=True)
        result = dict(model=MODEL, revision=self.revision, variant=arm, split=split, batch=bid,
                      seconds=time.monotonic()-started, charged_cost=0,
                      request_sha256=request_hash, input_tokens=inputs['input_ids'].shape[-1],
                      output_tokens=len(tokens), peak_vram_bytes=torch.cuda.max_memory_allocated(),
                      response_text=text, final_response_text=final_answer(text),
                      predictions=bench.parse(final_answer(text), rows))
        bench.save(target, result)
        print(json.dumps({k: result[k] for k in ['variant', 'split', 'batch', 'seconds', 'output_tokens', 'peak_vram_bytes']}), flush=True)
        return result['predictions']


def cached(split, arm):
    out = {}
    for bid, rows in bench.batches(split):
        path = bench.ROOT/'responses'/split/MODEL.replace('/', '__')/arm/(bid+'.json')
        assert path.exists(), f'Incomplete {split}/{arm}/{bid}'
        for p in bench.read(path)['predictions']:
            assert p['annotation_id'] not in out
            out[p['annotation_id']] = p
    expected = {r['annotation_id'] for _, rr in bench.batches(split) for r in rr}
    assert set(out) == expected
    return out


def materialize(split, arm, policy, baseline):
    revised = cached(split, arm)
    base = cached(split, baseline)
    result = {}
    for _, rows in bench.batches(split):
        for r in rows:
            ident = r['annotation_id']
            p = revised[ident] if policy[r['criterion_type']] else base[ident]
            # No silent malformed-response repair or answer-based retry.
            result[ident] = typed_age(r, p) if policy['typed_age'] else p
    return result


def select(baseline):
    rows = [r for _, rr in bench.batches('dev') for r in rr]
    gold = [r['expert_eligibility'] for r in rows]
    base = cached('dev', baseline)
    bm = bench.metrics(gold, [base[r['annotation_id']]['label'] for r in rows])
    selection = dict(baseline=baseline, baseline_dev=bm, arms={})
    for arm in ARMS:
        candidates = []
        for flags in itertools.product([False, True], repeat=3):
            policy = dict(zip(['inclusion', 'exclusion', 'typed_age'], flags))
            pp = materialize('dev', arm, policy, baseline)
            score = bench.metrics(gold, [pp[r['annotation_id']]['label'] for r in rows])
            safe = score['false_passes'] <= bm['false_passes'] and score['unknown_passes'] <= bm['unknown_passes']
            candidates.append(dict(policy=policy, score=score, safety_guard_passed=safe))
        winner = max((c for c in candidates if c['safety_guard_passed']),
                     key=lambda c: (c['score']['macro_f1'], c['score']['accuracy'], -sum(c['policy'].values())))
        selection['arms'][arm] = dict(selected=winner, candidates=candidates)
    immutable(bench.ROOT/'local_agent_selection.json', selection)
    freeze = bench.ROOT/'local_agent_selection_frozen.json'
    if not freeze.exists():
        bench.save(freeze, dict(sha256=digest(bench.ROOT/'local_agent_selection.json'),
                               utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())))
    assert bench.read(freeze)['sha256'] == digest(bench.ROOT/'local_agent_selection.json')
    return selection


def phase(engine, split, baseline):
    for i, (bid, rows) in enumerate(bench.batches(split)):
        status(split, batch_index=i, batch_count=len(bench.batches(split)), batch=bid)
        draft = engine.infer(split, baseline, bid, rows, bench.prompt(rows, baseline))
        engine.infer(split, 'rag_only', bid, rows, review_messages('rag_only', rows, []))
        engine.infer(split, 'memory_audit', bid, rows, review_messages('memory_audit', rows, draft))


def report(selection):
    import pathlib
    import report as helpers
    rows = [r for _, rr in bench.batches('test') for r in rr]
    gold = [r['expert_eligibility'] for r in rows]
    arms = {'medgemma_direct': cached('test', selection['baseline'])}
    for arm in ARMS:
        arms['medgemma_'+arm] = materialize('test', arm, selection['arms'][arm]['selected']['policy'], selection['baseline'])
    # Keep raw outputs visible even if development selects the baseline for a branch.
    raw = {a: bench.collect(MODEL, a, 'test', True) for a in ARMS}
    parent = pathlib.Path(FRONTIER)
    frozen = bench.read(parent/'direct_selection.json')
    assert digest(parent/'data/source.json') == digest(bench.ROOT/'data/source.json')
    assert all(bench.read(parent/'manifest.json')[k] == bench.read(bench.ROOT/'manifest.json')[k]
               for k in ['dev_patients', 'test_patients'])
    for model, choice in frozen.items():
        path = parent/'responses'/'test'/('openai-direct__'+model)/choice['variant']
        pp = {p['annotation_id']: p for f in path.glob('*.json') for p in bench.read(f)['predictions']}
        assert set(pp) == set(arms['medgemma_direct']), 'Incomplete comparator'
        arms[model] = pp
    scores = {a: bench.metrics(gold, [pp[r['annotation_id']]['label'] for r in rows]) for a, pp in arms.items()}
    ci = helpers.intervals(rows, arms)
    bench.save(bench.ROOT/'LOCAL_RESULTS.json', dict(scores=scores, raw_local_arms=raw,
               selection=selection, bootstrap=ci, protocol=bench.read(bench.ROOT/'local_study_protocol.json')))
    lines = ['# Local MedGemma 4B benchmark', '',
             '687 held-out criteria / 37 synthetic patients. Expert labels; patient-disjoint development. '+
             'Local engine: MedGemma 1.5 4B, NF4, '+bench.read(bench.ROOT/'local_runtime_config.json')['compute_dtype']+
             ' compute, RTX 2080 SUPER. No inference API calls for local arms.', '',
             '| System | Macro-F1 | Accuracy | False passes / 22 | Passes on Unknown / 188 |',
             '|---|---:|---:|---:|---:|']
    for a, s in scores.items():
        lines.append(f'| {a} | {s["macro_f1"]*100:.2f}% | {s["accuracy"]*100:.2f}% | {s["false_passes"]} | {s["unknown_passes"]} |')
    lines += ['', 'Paired macro-F1 differences (95% patient-cluster bootstrap CI; exploratory):', '']
    for p in ci['paired_macro_f1_difference_ci95']:
        a, b = p['model_a'], p['model_b']
        lo, hi = p['ci95']
        delta = scores[a]['macro_f1']-scores[b]['macro_f1']
        lines.append(f'- {a} minus {b}: {delta*100:+.2f} pp [{lo*100:+.2f}, {hi*100:+.2f}].')
    lines += ['', 'Baseline selects between two prompts on development. RAG-only and memory-audit '+
              'use the same two expert-labelled development references per criterion, excluding the target patient. '+
              'Memory-audit additionally sees the baseline draft and sourced age/sex/numeric evidence. '+
              'Each arm selects eight development-only branch/age policies with identical safety guards. '+
              'The selected policy may retain the baseline; inspect LOCAL_RESULTS.json for all candidates and raw-arm scores.', '',
              'Local API spend is zero; GPU/electricity costs are not zero and are not measured. '+
              'Raw response artifacts record latency, tokens, VRAM and the exact checkpoint revision. '+
              'The agent uses additional calls and labelled references; this is a system comparison, not equal compute.', '',
              'This local protocol was fixed after frontier summary scores were known, before local full-development selection '+
              'and local held-out inference. The shared public test set is not an untouched external replication. '+
              'No clinical outcome, enrolment, hospital retrieval, IRIS, Laya, RL, treatment benefit or private deployment is validated. '+
              'Public-data contamination and sparse rare classes remain limitations.']
    (bench.ROOT/'LOCAL_REPORT.md').write_text('\n'.join(lines)+'\n')
    status('complete', scores=scores)


def main():
    import fcntl
    import pathlib
    lock = (bench.ROOT/'local-study.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    # Never overlap with the initial GPU smoke. Its FP16 attempt may have failed:
    # the separate health preflight and runtime config govern study eligibility.
    smoke = bench.ROOT/'LOCAL_RUNNING.json'
    if smoke.exists():
        pid = bench.read(smoke)['pid']
        proc = pathlib.Path('/proc')/str(pid)
        while proc.exists():
            try:
                command = (proc/'cmdline').read_bytes()
                state = (proc/'stat').read_text().split(') ', 1)[1].split()[0]
            except FileNotFoundError:
                break
            if b'local_bench.py' not in command or state == 'Z':
                break
            status('waiting_for_smoke', smoke_pid=pid)
            time.sleep(5)
    runtime = bench.read(bench.ROOT/'local_runtime_config.json')
    health = bench.read(bench.ROOT/('local_health_'+runtime['compute_dtype']+'.json'))
    assert len(health['checks']) == 2 and all(c['finite_logits'] and c.get('output_tokens', 0) > 0 for c in health['checks'])
    # Hash all behavior affecting predictions/selection before full development.
    files = ['bench.py', 'local_bench.py', 'local_study.py', 'local_evidence.py', 'report.py', 'local_runtime_config.json']
    immutable(bench.ROOT/'local_study_protocol.json', dict(
        model=MODEL, checkpoint=bench.read(bench.ROOT/'local_revision.json'),
        code_sha256={f: digest(bench.ROOT/f) for f in files},
        source_sha256=digest(bench.ROOT/'data/source.json'),
        manifest_sha256=digest(bench.ROOT/'manifest.json'),
        baseline_candidates=bench.VARIANTS, arms=ARMS, policies_per_arm=8,
        generation=dict(max_new_tokens=bench.MAX_TOKENS, do_sample=False,
                        quantization='NF4 double quant; '+runtime['compute_dtype']+' compute; eager attention',
                        finite_logits_guard=True, native_thinking='Keep generated native thought channel; budget includes all tokens; score final channel after one <unused95> marker only.'),
        registration_context='Frontier summary scores and numerical preflight outputs already known; initial FP16 attempt aborted with non-finite logits; no local held-out inference or test tuning.',
        local_inference_api_calls=0))
    status('loading')
    engine = Engine()
    for variant in bench.VARIANTS:
        for i, (bid, rows) in enumerate(bench.batches('dev')):
            status('development_baseline', variant=variant, batch_index=i, batch_count=len(bench.batches('dev')))
            engine.infer('dev', variant, bid, rows, bench.prompt(rows, variant))
    candidates = [(v, bench.collect(MODEL, v, 'dev', True)) for v in bench.VARIANTS]
    best = max(candidates, key=lambda x: (x[1]['macro_f1'], x[1]['accuracy']))
    immutable(bench.ROOT/'local_selection.json', dict(variant=best[0], dev_scores=dict(candidates)))
    phase(engine, 'dev', best[0])
    selection = select(best[0])
    phase(engine, 'test', best[0])
    status('reporting')
    report(selection)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        status('stopped', error_type=type(exc).__name__, error=str(exc)[:800])
        traceback.print_exc()
        raise
