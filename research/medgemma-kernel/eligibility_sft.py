"""Disjoint pilot training bank and source-only eligibility/evidence format."""
import json
import re
import bench
from source_evidence_v2 import sentences,final_text


def allowed(kind):
    return ({'included','not included'} if kind=='inclusion' else {'excluded','not excluded'})|{'not enough information','not applicable'}


def messages(row):
    system='''Assess one clinical trial criterion against the original numbered patient note. Use supplied patient facts only; do not invent tests, values, treatment receipt or consent. Respect specific severity/subtype, negation, AND/OR, thresholds and time.
For inclusion use included when satisfied, not included when contradicted, or not enough information when evidence is missing. Specifically required current treatment is not satisfied if receipt is unreported.
For exclusion use excluded when the exclusion condition is present; not excluded when absent or not documented under this research convention; not enough information when a required value/test or explicitly unresolved finding prevents assessment.
Use not applicable only for an explicitly inapplicable whole-criterion prerequisite or solely internal research-data processing. Missing information alone does not prove inapplicability.
Return only JSON with exactly two fields: label (one allowed label for the supplied type) and sentence_ids (integer IDs of relevant original sentences; empty if none). No explanation or thought text. This is a research annotation, not an enrollment decision.'''
    payload=dict(patient_note=row['note'],trial_title=row['trial_title'],
                 criterion=dict(type=row['criterion_type'],text=row['criterion_text']),
                 question='What is the correct criterion label and its supporting source sentence IDs?')
    return [dict(role='system',content=system),dict(role='user',content=json.dumps(payload,ensure_ascii=False))]


def target(row):
    label=row['expert_eligibility'];assert label in allowed(row['criterion_type'])
    ids=json.loads(row['expert_sentences'])
    assert isinstance(ids,list) and all(type(i) is int for i in ids)
    assert set(ids)<=set(sentences(row['note']))
    assert len(ids)==len(set(ids))
    return '<unused95>'+json.dumps(dict(label=label,sentence_ids=ids),separators=(',',':'),ensure_ascii=False)+'<end_of_turn>'


def parse(row,raw,plain,capped):
    if capped:return dict(label='__invalid__',sentence_ids=[],error='Final generation capped')
    text=final_text(raw,plain)
    if text is None:return dict(label='__invalid__',sentence_ids=[],error='Unfinished thought')
    text=re.sub(r'^```(?:json)?\s*|\s*```$','',text)
    try:
        value=json.loads(text)
        assert isinstance(value,dict) and set(value)=={'label','sentence_ids'}
        assert value['label'] in allowed(row['criterion_type'])
        ids=value['sentence_ids']
        assert isinstance(ids,list) and all(type(i) is int for i in ids)
        assert len(ids)==len(set(ids)) and set(ids)<=set(sentences(row['note']))
        return value
    except (ValueError,TypeError,KeyError,AssertionError):
        return dict(label='__invalid__',sentence_ids=[],error='Invalid schema, polarity or source citation')


def training_bank(rows,protocol):
    by_id={r['annotation_id']:r for r in rows}
    held_ids=set(protocol['dev_ids']+protocol['test_ids'])
    held=[by_id[i] for i in held_ids]
    forbidden_trials={r['trial_id'] for r in held}
    candidates=[r for r in rows if r['annotation_id'] not in held_ids]
    bank=[r for r in candidates if r['trial_id'] not in forbidden_trials]
    for key in ['annotation_id','patient_id','note','trial_id']:
        assert not {r[key] for r in bank}&{r[key] for r in held}
    assert len(protocol['dev_ids'])==328 and len(protocol['test_ids'])==516
    for row in bank:target(row)
    return bank,dict(candidate_rows=len(candidates),retained_rows=len(bank),
                     removed_shared_trial_ids=sorted({r['trial_id'] for r in candidates}&forbidden_trials),
                     training_ids=[r['annotation_id'] for r in bank],
                     training_patients=sorted({r['patient_id'] for r in bank}),
                     original_development_ids=protocol['dev_ids'],original_confirmation_ids=protocol['test_ids'],
                     isolation='No training-bank annotation, patient, full note or trial overlap with either original evaluation split.',
                     prior_exposure='Training patients were previously inspected pilot patients, deliberately excluded from original primary evaluation. This is supervised task adaptation, not an agent-architecture-only comparison.')
