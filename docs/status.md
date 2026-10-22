# Implementation status and roadmap

The product, local-model research and hospital deployment design have different levels of evidence.

| Area | Status | What is available |
|---|---|---|
| Static product UI | Implemented prototype | Seven linked pages; exported public-data snapshots |
| Criterion compiler / evaluator | Implemented prototype | Supported rules; missingness/recency handling; uncompiled lines shown for review |
| IRIS trial retrieval | Prototype source included | Database loader, vector queries and optional local pipeline; no fresh IRIS deployment was performed for this release |
| Retrieval/ranking and biomarker models | Prototype metrics included | Existing TREC-year split/CV results; distinct from the MedGemma experiment |
| Adapted local MedGemma 4B | Separate measured experiment | 665-pair frozen confirmation, prediction-level metric replay and hash-matched kernel source |
| 4B model connected to product | Planned | The current UI's Model A/B are different models |
| Hospital EHR/FHIR connectors | Proposed | No live hospital integration or partnership claimed |
| vLLM / Laya / Langfuse service integration | Proposed | Architecture only; no validated incremental benefit or compatibility claim |
| Live clinical referral / enrolment | Proposed | UI draft exists; no real-world workflow outcome study |
| Outcome follow-up / offline RL | Proposed | No outcome-linked RL result or patient-benefit estimate |

## Next milestones

1. Serve the frozen local classifier behind a versioned, bounded interface and evaluate it in the product workflow.
2. Improve retrieval coverage and compiler coverage against reviewed cases; report misses rather than only ranking among retrieved candidates.
3. Obtain authorised, clinician-adjudicated colorectal cases for site/time/patient-separated validation.
4. Pilot evidence review and referral workflow with a participating hospital and Trial Site.
5. Establish outcome definitions and logging before testing feedback-based ranking or offline RL.

Each milestone needs its own acceptance criteria. A successful public-data benchmark is not completion of the hospital deployment or clinical-validation milestones.
