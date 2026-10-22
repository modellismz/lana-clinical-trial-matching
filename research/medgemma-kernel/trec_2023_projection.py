"""Literal historical clinical projection; no criteria rewriting or inferred facts."""
import hashlib
import json
import re
import unicodedata
import xml.etree.ElementTree as ET

from trec_trial_task import SYSTEM, PREFIX, CODES

FIELDS = ('brief_title', 'phase', 'interventions', 'conditions', 'brief_summary', 'eligibility')


def text(element):
    return '' if element is None else ''.join(element.itertext()).strip()


def trial_projection(raw_xml, expected_id):
    tree = ET.fromstring(raw_xml)
    assert tree.tag == 'clinical_study' and tree.findtext('id_info/nct_id') == expected_id
    eligibility = tree.find('eligibility'); fields = {}
    if eligibility is not None:
        # Unknown attributed/repeated structure must be investigated, never dropped.
        assert not any(node.attrib for node in eligibility.iter())
        for child in eligibility:
            assert child.tag not in fields
            fields[child.tag] = text(child)
    return dict(brief_title=text(tree.find('brief_title')), phase=text(tree.find('phase')),
        interventions=[dict(type=text(n.find('intervention_type')), name=text(n.find('intervention_name')))
            for n in tree.findall('intervention')],
        conditions=[text(n) for n in tree.findall('condition')],
        brief_summary=text(tree.find('brief_summary')), eligibility=fields)


def patient_projection(profile):
    assert set(profile) == {'template', 'fields'}
    assert len(profile['fields']) == len({f['name'] for f in profile['fields']})
    return dict(questionnaire_condition=profile['template'],
        fields=[dict(name=f['name'], value=f['value']) for f in profile['fields']])


def clinical_input(row):
    patient = row['patient']
    return dict(patient=dict(questionnaire_condition=patient['questionnaire_condition'],
        fields=[dict(name=f['name'], value=f['value']) for f in patient['fields']]),
        trial={k: row['trial'][k] for k in FIELDS})


def messages(row, proposal=None):
    payload = clinical_input(row)
    if proposal is not None:
        assert proposal in CODES
        payload['untrusted_proposal'] = dict(decision=proposal)
    return [dict(role='system', content=SYSTEM), dict(role='user', content=json.dumps(payload, ensure_ascii=False))]


def core_digest(trial, old=False):
    """Conservative lexical overlap screen, ignoring registry metadata/type lists.

    This does not establish semantic independence. Ignoring more fields can
    overblock, so it cannot be used to claim all trial differences are proven.
    """
    criteria = trial['inclusion_criteria']+'\n'+trial['exclusion_criteria'] if old else trial['eligibility'].get('criteria', '')
    def normal(value):
        value = unicodedata.normalize('NFKC', value).casefold()
        value = re.sub(r'\b(?:key\s+)?(?:inclusion|exclusion)\s+criteria\b\s*:?', ' ', value)
        return ' '.join(re.findall(r'[^\W_]+', value))
    values = [normal(trial[k]) for k in ['brief_title', 'brief_summary']] + [normal(criteria)]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()
