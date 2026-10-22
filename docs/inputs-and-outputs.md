# Inputs and outputs

LANA preserves missingness and source provenance. An ordered test is not a completed result; an untested biomarker is not a negative biomarker. All clinical facts need their subject, source, date, units and availability state where relevant.

## Patient-wise inputs

| Input | Examples / handling |
|---|---|
| Age | Age at assessment; retain the reference date |
| Gender / documented sex | Preserve source wording; trial-specific sex-related criteria need an explicit reviewed interpretation |
| Underlying diseases | Comorbidities and relevant medication history |
| ECOG | Value and assessment date; unresolved or stale observations remain visible |
| Bloodwork | CBC, ANC, platelets, haemoglobin, liver/renal tests; units, reference ranges and collection dates |
| Geography | Hospital/location and travel constraints; disclose only through authorised workflows |

## Tumour-wise inputs

| Input | Examples / handling |
|---|---|
| Clinical / pathological TNM | `cT4N2M1`; keep clinical and pathological stages separate |
| Metastatic sites | Documented organ sites and assessment dates |
| Brain metastases | Positive, negative, pending or unknown; retain treatment/activity details when required |
| Biomarkers | KRAS, BRAF, EGFR, NRAS, HER2, MSI/MMR and protocol-specific markers; exact variants, assays and test status |
| Surgery | Procedure/date and R0/R1 margin status; do not infer a margin from the procedure alone |
| Treatment history | Drug/regimen, setting, line, dates, response, recurrence/progression and prior failed treatments |

The demo cohort does not contain all these fields as real observations. Simulated overlays are labelled **SIM**, and unavailable fields remain explicit. Ambiguous regimen abbreviations need source clarification rather than automatic correction.

## Trial inputs

- Versioned inclusion and exclusion criteria, including cohort-specific logic.
- Title, condition, phase, intervention and Sponsor.
- Trial sites, recruitment status, snapshot date and protocol version.
- Reviewed executable rules, with uncompiled criteria retained for review.

## Outputs

| Output | Meaning |
|---|---|
| Candidate shortlist | Trials retrieved for further assessment; retrieval can miss relevant trials |
| Criterion assessments | Met / Not met / Unknown with supporting evidence and rule version |
| Missing-data queue | Untested, stale, contradictory or ambiguous evidence requiring review |
| Review-ready referral draft | Patient/trial summary, assessed rules and remaining protocol coverage limits |
| Governed feasibility | Proposed approved aggregate counts for Sponsors/CROs; no default patient-record access |
| Outcome log | Planned site-confirmed referral/screening/enrolment events for subsequent evaluation |

Similarity and prototype pass scores are not validated probabilities of eligibility, enrolment or treatment benefit.
