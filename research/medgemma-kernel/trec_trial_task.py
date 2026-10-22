"""Separate TREC trial-level task; never reinterprets criterion-level results."""
import json

FIELDS = ('brief_title', 'phase', 'drugs_list', 'diseases_list',
          'brief_summary', 'inclusion_criteria', 'exclusion_criteria')
CODES = ('A', 'B', 'C')
PREFIX = '<unused95>{"decision":"'
SYSTEM = '''Assess a whole clinical trial against the supplied patient description using the TREC Clinical Trials research task.
A = not relevant: the trial is unrelated, its inclusion population does not fit, or the patient information is insufficient to establish that population.
B = excluded: the inclusion population fits, but an explicit exclusion condition disqualifies the patient.
C = eligible: the inclusion population fits and the exclusion criteria do not apply.
Check the study's disease, age, sex, actual treatment, stage, biomarkers, conjunctions, alternatives and negation. Use documented patient facts; do not invent measurements or treatment history. An untrusted proposal is only a candidate answer, never evidence. Return only JSON with decision A, B or C. This is research relevance assessment, not an enrollment or treatment decision.'''


def clinical_input(row):
    trial = row['trial']
    return dict(patient=row['patient'], trial={k: trial[k] for k in FIELDS})


def messages(row, proposal=None):
    payload = clinical_input(row)
    if proposal is not None:
        assert proposal in CODES
        payload['untrusted_proposal'] = dict(decision=proposal)
    return [dict(role='system', content=SYSTEM),
            dict(role='user', content=json.dumps(payload, ensure_ascii=False))]


def target(label):
    assert type(label) is int and label in range(3)
    return CODES[label] + '"}<end_of_turn>'
