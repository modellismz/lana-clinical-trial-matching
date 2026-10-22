# Golden set for the retrieval stage

`retrieval_golden.jsonl`: one line per reviewer-labelled pair. These are the **HAND** labels on the
Evaluation page. The file is empty until a clinician or trial coordinator fills it; nothing here is
generated.

```json
{"patient": "LN-06A2", "nct_id": "NCT06252649", "label": "must_shortlist", "by": "initials", "on": "2026-10-20", "note": "KRAS G12C, first line, Siriraj site"}
{"patient": "LN-06A2", "nct_id": "NCT01479608", "label": "must_not", "by": "initials", "on": "2026-10-20", "note": "liver transplant trial, not a drug trial"}
```

- `patient` is the pseudo-id shown in the app (`web/data/patients.json`).
- `label` is `must_shortlist` (retrieval must put it in the 40-trial shortlist) or `must_not`.
- Keep a held-out slice: lines with `"split": "holdout"` are scored but never used to tune the query text.

The other two layers are derived automatically and tagged as such on the page:

- **AUTO**: trials whose registry title names the patient's actionable biomarker (KRAS G12C, BRAF V600E,
  MSI-H / dMMR, HER2, RAS wild-type). A sanity floor, not a clinical judgement.
- **RULES** (full mode only): trials the rule evaluator passes when run over the whole registry, not just
  the shortlist (no criterion Not met, at least one biomarker criterion Met, coverage ≥ 0.4).
