# lana platform · MVP

This is the imported public-data application guide. The separate MedGemma 4B experiment and its published metric replay are documented in [the repository benchmark](../../benchmarks/README.md); the UI's Model A/B are different models. The source includes an optional IRIS-backed pipeline, while the hosted demo uses exported snapshots. The pipeline was not rebuilt during this repository publication.

Real public colorectal cancer data, embedded and matched to real clinical trials. Every trial rule is marked **Met**, **Not met** or **Unknown**, and a test that was never done stays Unknown.

This is a hackathon prototype (Siriraj x MIT Hacking Medicine 2026, oncology track; the team placed third). Patients are real, de-identified public records. ECOG, labs, imaging and similar fields are not supplied by the selected public cohorts, so the demo uses **simulated and always tagged** values. Nothing here is medical advice, a medical device, or a determination of eligibility.

## Pages

Each step is its own page. The patient rail is on every page; the selected patient and trial travel in the URL (`?p=LN-XXXX&t=NCTXXXXXXXX`).

| Page | What you see | What is real |
|---|---|---|
| `index.html` Home · Patient map | All 8,435 patients as one force-directed web: one dot per patient, links to its most similar peers (RAS/RAF/HER2/PIK3CA/MSI result **and** test status, stage, metastasis sites, side, age, sex, TMB, cohort). Colour by biomarker subgroup, cohort, MSI testing or stage; data-availability bars per field | Every dot and every link is built from real cBioPortal facts (`pipeline/build_patient_map.py`). Layout is a spring simulation in the browser |
| `sources.html` Data input | One patient record from five sources, each value with its source and date | Genomics, MSI, staging, metastasis sites from cBioPortal (4 cohorts, 8,435 patients). Fitness, labs, imaging are simulated |
| `match.html` Trial match | Ranked trials, rule-by-rule evidence, what-if for each Unknown, and Thailand hotspots: the modelled patient pool per province for the patient's biomarker subgroup, with the trial's Thai sites | Model A trained on TREC 2021, tested on 2022. Model B trained on real cohorts. Province pools are **modelled (SIM)**: public province populations × published rates, formula shown on the page |
| `embed.html` Embedding | 1,073 trials in embedding space, the patient dropped in, the IRIS query and its top hits | bge-m3 embeddings (1,024-d), 32,701 chunks in InterSystems IRIS, searched with `VECTOR_COSINE` |
| `referral.html` Referral | The Review-ready Referral for the open trial, with limits stated | Built from the checks above |
| `evidence.html` Evidence | Data inventory, both models' held-out metrics, real versus simulated inputs | Metrics from `models/` |
| `evaluation.html` Evaluation | Abridged golden-set evaluation of the retrieval stage (recall@k, by subgroup, misses), the automated schedules with last and next run, and every match time from the last 7 days | Recall against AUTO (title names the biomarker), RULES (full mode) and HAND (`data/golden/`) labels. Times from the export run and the live API |

## Run it

Needs Python 3.11+, Docker, and about 6 GB of disk for the embedding model.

```bash
make setup           # venv + IRIS container (127.0.0.1:1974 / 52775)
make iris-unlock     # only if the first IRIS connection says "Password change required"
make data            # cBioPortal cohorts, ClinicalTrials.gov trials, TREC pairs  (~3 min)
make embed           # bge-m3 over 32,701 chunks, load into IRIS                  (~5 min)
make train           # Model A (TREC) and Model B (real cohorts)                  (~25 min)
make export          # run the engine on 36 demo patients -> web/data, then the Thailand hotspots, then the retrieval eval
make thailand        # only the Thailand province pools (SIM) -> web/data/thailand.json          (~2 s)
make patient-map     # only the home-page patient map -> web/data/patient_map.json (stdlib only)      (~3 s)
make eval            # golden-set retrieval eval -> web/data/evaluation.json; exit 1 on a recall@40 drop > 0.05
make eval-snapshot   # same from web/data only (scores the final top 12; no IRIS or model needed)
make cron            # crontab lines for the schedules in pipeline/eval_schedule.json
make serve           # http://localhost:8010   live API + site (first live click warms the model, ~20 s)
```

To only look at the app, the exported snapshot is committed: `make static` and open http://localhost:8011.

## Results (internal evaluation, not clinical validation)

| Model | Task | Data | Result |
|---|---|---|---|
| A · trial fit | Is the patient ELIGIBLE for the trial? | TREC 2021 train (75 topics), TREC 2022 test (50 unseen topics) | AUROC **0.74**, NDCG@10 **0.69**, P@10 0.58. Cosine-only baselines: AUROC 0.65 / 0.61, NDCG@10 0.63 / 0.60 |
| B · biomarker completion | Predict a missing biomarker from the known ones | 8,435 real patients, 5-fold CV | AUROC: MSI 0.99, BRAF 0.91, NRAS 0.79, KRAS 0.77, PIK3CA 0.71, HER2 0.68 (HER2, NRAS, PIK3CA stay close to their base rates) |
| Criteria compiler | Protocol lines turned into checkable tests | 1,073 real trials, 32,684 lines | 30% compiled; the rest, and every multi-cohort line, go to a reviewer |
| Evaluator | Browser and Python agree | 4,377 exported criteria | 0 mismatches (`node tests/parity.mjs`) |
| Retrieval · golden set | Is the trial that names the patient's biomarker in the result? | 23 demo patients with an actionable biomarker, 275 AUTO pairs (snapshot mode scores the final top 12) | hit@12 **0.43**, recall@12 0.08, MRR 0.14. HER2 and MSI-H patients: 0 hits. Full mode (`make eval`) scores the raw 40-trial shortlist |

Model A is scored inside a balanced sample (at most 15 pairs per label per topic), so its numbers describe ranking inside that pool, not search over the full registry.

The retrieval golden set is the only check on the shortlist gate: a trial that misses the 40-trial shortlist is never seen by the rules or either model. AUTO pairs are a sanity floor (the registry title names the patient's biomarker), not clinical labels; reviewer labels go in `data/golden/retrieval_golden.jsonl`. Every run appends to `data/eval_runs.jsonl`, and `make export` fails when recall@40 drops by more than 0.05 against the previous full run.

## How it works

```
cBioPortal (4 cohorts) ─► patient facts ─┐
simulated overlay (SIM) ─────────────────┤   patient text ─► bge-m3 ─► IRIS VECTOR_COSINE ─► shortlist
ClinicalTrials.gov ─► rule compiler ─────┘                                   │
                                                  rule evaluator (Met / Not met / Unknown)
                                                  Model A: does the patient fit the trial?  (TREC)
                                                  Model B: how likely is each Unknown to pass? (real cohorts)
                                                                              ▼
                                                              ranked Trial Matches + next best test
```

Design rules, enforced in code and tested in `tests/`:

1. **Not tested is not negative.** Only a completed test can make a rule Met or Not met. `not done`, `pending`, `failed` and `insufficient` all give Unknown.
2. **Vectors retrieve, rules decide.** Embeddings shortlist trials. Eligibility comes from explicit, readable rules.
3. **Models never override rules.** Model A ranks. Model B puts a probability next to an Unknown; it never resolves it.
4. **Recency.** Labs and ECOG older than 28 days are Unknown.
5. **Every value has a source.** `REAL:<study>` or `SIM`, with a date where it matters.

## Layout

```
pipeline/   data fetch, embedding, IRIS load, training, export, Thailand hotspots, patient map, retrieval eval + schedule
data/golden/ reviewer-labelled retrieval pairs (HAND layer), see its README
lana/       criteria compiler, evaluator, patient facts, completion model, IRIS access, engine
server/     optional FastAPI: /api/health, /api/match, serves web/
web/        static app (no build step): one HTML page per step, js/pages/*, exported data
models/     evaluation metrics for both models
tests/      unit tests, browser/Python evaluator parity, browser smoke test (Playwright)
```

## Tests

```bash
make test                         # unit tests: compiler + evaluator
node tests/parity.mjs             # browser evaluator == Python evaluator on every exported criterion
python tests/e2e_ui.py http://localhost:8010   # needs `pip install playwright` + Chrome; clicks through the app
```

## Honest limits

- No Thai patients. Cohorts are US (MSK, TCGA) and Chinese (SYSUCC).
- There is no public dataset of real colorectal patients with trial-eligibility labels. Model A is trained on TREC (all diseases, synthetic patient topics); the rule evaluator is checked by unit tests, not against clinician labels.
- The rule compiler turns about a third of protocol lines into tests. The rest are shown as "need a reviewer".
- Trial text is the current registry version, fetched on the day the pipeline ran.
- Model B is weak for HER2, NRAS and PIK3CA (near prevalence). MSI is predicted mainly from tumour mutation burden.
- Metrics are internal (cross-validation, or a held-out TREC year). There is no external validation.
