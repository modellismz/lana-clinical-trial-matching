"""Source-bound evidence and deliberately narrow, auditable numeric tools.

No model-proposed value is accepted as a clinical measurement. Numeric tools
only handle whole, standalone criteria; unsupported syntax stays with the LLM.
"""
import json
import re
from decimal import Decimal

NUM = r'\d+(?:,\d{3})*(?:\.\d+)?'
FIELD = r'age|weight|ecog(?: performance status)?|platelet(?: count|s)?|hemoglobin|haemoglobin|creatinine|bilirubin|alt|ast|wbc|anc'
UNIT = r'years?|months?|kg|lbs?|g/dl|mg/dl|/mm3|/ul|/µl|u/l'
OP = r'>=|<=|≥|≤|>|<|at least|at most|greater than or equal to|less than or equal to|greater than|less than'


def sentences(note):
    found = re.findall(r'(?m)^(\d+)\.\s*([^\n]*)$', note)
    ids = [int(i) for i, _ in found]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate source sentence IDs')
    return {int(i): s for i, s in found}


def final_text(raw, plain):
    thought, final = raw.rfind('<unused94>'), raw.rfind('<unused95>')
    if thought >= 0 and final <= thought:
        return None
    value = raw[final + len('<unused95>'):] if final >= 0 else plain
    return re.sub(r'<(?:end_of_turn|eos|pad)>', '', value).strip()


def bind_evidence(row, raw, plain):
    text = final_text(raw, plain)
    if text is None:
        raise ValueError('No completed final channel')
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text)
    obj = json.loads(text)
    if not isinstance(obj, dict) or set(obj) != {'sentence_ids'}:
        raise ValueError('Expected sentence_ids only')
    ids = obj['sentence_ids']
    if not isinstance(ids, list) or any(type(i) is not int for i in ids):
        raise ValueError('Sentence IDs must be integers')
    source = sentences(row['note'])
    if len(ids) != len(set(ids)) or not set(ids) <= set(source):
        raise ValueError('Duplicate or invented citation')
    return [dict(sentence_id=i, quote=source[i]) for i in ids]


def canonical_field(value):
    value = value.lower()
    if value.startswith('ecog'): return 'ecog'
    if value.startswith('platelet'): return 'platelets'
    return {'haemoglobin': 'hemoglobin'}.get(value, value)


def normal(value, unit, field):
    number = Decimal(value.replace(',', ''))
    unit = unit.lower()
    if field == 'age' and unit in ['year', 'years', 'month', 'months']:
        return number / (12 if unit.startswith('month') else 1), 'years'
    if field == 'weight' and unit in ['kg', 'lb', 'lbs']:
        return number * (Decimal('0.45359237') if unit.startswith('lb') else 1), 'kg'
    if field == 'ecog' and unit == '': return number, 'score'
    if field in ['platelets', 'wbc', 'anc'] and unit in ['/mm3', '/ul', '/µl']:
        return number, '/µl'
    expected = {'hemoglobin': 'g/dl', 'creatinine': 'mg/dl', 'bilirubin': 'mg/dl', 'alt': 'u/l', 'ast': 'u/l'}
    if expected.get(field) == unit: return number, unit
    return None


def compile_numeric(criterion):
    text = criterion.strip().rstrip('.;').strip()
    # Full matches prevent a simple tool deciding only one part of an AND/OR,
    # subgroup, historical, relative-ULN or time-qualified requirement.
    pattern = rf'({FIELD})\s*({OP})\s*({NUM})\s*({UNIT})?'
    match = re.fullmatch(pattern, text, re.I)
    if match:
        field, op, value, unit = match.groups()
        field = canonical_field(field)
        numeric = normal(value, unit or '', field)
        if numeric is None: return None
        aliases = {'≥': '>=', '≤': '<=', 'at least': '>=', 'at most': '<=',
                   'greater than or equal to': '>=', 'less than or equal to': '<=',
                   'greater than': '>', 'less than': '<'}
        return dict(field=field, op=aliases.get(op.lower(), op), value=str(numeric[0]), unit=numeric[1])
    match = re.fullmatch(rf'(age|ecog(?: performance status)?)\s*(?:between\s*)?({NUM})\s*(?:-|–|to|and)\s*({NUM})\s*(years?)?', text, re.I)
    if match:
        field, low, high, unit = match.groups(); field = canonical_field(field)
        if field == 'ecog' and unit: return None
        if Decimal(low) > Decimal(high): return None
        return dict(field=field, op='range', low=low, high=high, unit='years' if field == 'age' else 'score')
    return None


def observations(note, field):
    result = []
    for ident, quote in sentences(note).items():
        if field == 'age':
            if ident != 0: continue
            for match in re.finditer(rf'\b({NUM})[- ](year|month)[- ]old\b', quote, re.I):
                prefix=quote[max(0,match.start()-32):match.start()]
                if re.search(r'\b(mother|father|sister|brother|daughter|son|wife|husband|grandmother|grandfather)\b',prefix,re.I):
                    continue
                value=normal(match[1],match[2],field)
                result.append(dict(sentence_id=ident,quote=quote,matched_text=match[0],field=field,value=str(value[0]),unit=value[1]))
            continue
        # No attempt to pick a current value from historical, negated,
        # hypothetical or otherwise qualified measurements in this version.
        if re.search(r'\b(prior|previous|previously|history|historical|formerly|before|after|not|no|denies|planned|plan|will|would|if|ago|baseline)\b', quote, re.I):
            continue
        if re.search(r'\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b', quote):
            continue
        if field == 'ecog':
            pattern = rf'^(?:The patient\x27s\s+|Patient\x27s\s+)?ECOG(?: performance status)?\s*[:=]?\s*({NUM})()\b'
        else:
            name = {'platelets': r'platelet(?: count|s)?', 'hemoglobin': r'h(?:ae|e)moglobin'}.get(field, re.escape(field))
            pattern = rf'^(?:The patient\x27s\s+|Patient\x27s\s+)?{name}\s*(?:is|was|of|:|=)?\s*({NUM})\s*({UNIT})(?![A-Za-z0-9/µ])'
        for match in re.finditer(pattern, quote, re.I):
            value = normal(match[1], match[2], field)
            if value is not None:
                result.append(dict(sentence_id=ident, quote=quote, matched_text=match[0],
                                   field=field, value=str(value[0]), unit=value[1]))
    return result


def numeric_decision(row):
    condition = compile_numeric(row['criterion_text'])
    if condition is None: return None
    values = observations(row['note'], condition['field'])
    # Even repeated equal measurements may refer to different visits. Do not
    # choose a date or discard competing measurements without resolving time.
    if len(values) != 1:
        # Parser non-coverage is not proof that clinical information is absent.
        # Let the evidence/decision route read the complete original note.
        return None
    value = Decimal(values[0]['value'])
    if values[0]['unit'] != condition['unit']:
        return dict(prediction='not enough information', rule=condition, evidence=values,
                    reason='Incompatible units; conversion unsupported.')
    op = condition['op']
    if op == 'range': met = Decimal(condition['low']) <= value <= Decimal(condition['high'])
    else:
        threshold = Decimal(condition['value'])
        met = {'>': value > threshold, '>=': value >= threshold,
               '<': value < threshold, '<=': value <= threshold}[op]
    labels = {'inclusion': ('not included', 'included'), 'exclusion': ('not excluded', 'excluded')}
    return dict(prediction=labels[row['criterion_type']][int(met)], rule=condition,
                evidence=values, reason='Exact standalone numeric condition evaluated on a unique source measurement.')


def extraction_messages(row):
    return [dict(role='system', content='Select the numbered patient sentences relevant to the exact trial criterion, including contradictions, dates, severity and treatment history. Return only JSON: {"sentence_ids":[0,2]}. Use existing IDs only; return [] if no evidence. Do not decide eligibility or invent findings.'),
            dict(role='user', content=json.dumps(dict(patient_note=row['note'], trial_title=row['trial_title'], criterion=row['criterion_text']), ensure_ascii=False))]


def decision_messages(row, evidence):
    system = '''Assess this trial criterion using the complete original note. The source-bound excerpts are navigation aids and may be incomplete. Check every required qualifier, AND/OR, negation, subtype, severity, numeric unit, dates and current versus prior treatment. A related diagnosis is not proof of a specific subtype. Never infer unreported body weight, laboratory results or completed tests from age or diagnosis.
End with exactly one line: Screening state: pass, fail, unknown, or not applicable.
pass: inclusion requirement satisfied, or exclusion condition absent/not documented under this research annotation convention.
fail: inclusion requirement contradicted, or exclusion condition present.
unknown: missing inclusion evidence or unresolved/required quantitative evidence; an unreported current treatment required for inclusion is not satisfied and is fail under this research convention.
not applicable: an explicitly inapplicable whole-criterion prerequisite, or solely internal research processing rather than participant eligibility. Missing information alone does not establish inapplicability.
Explain briefly with actual sentence IDs before the final line. These are research annotations, not enrollment decisions.'''
    payload = dict(patient_note=row['note'], trial_title=row['trial_title'],
                   criterion=dict(type=row['criterion_type'], text=row['criterion_text']),
                   evidence_sentence_ids=[x['sentence_id'] for x in evidence])
    return [dict(role='system', content=system), dict(role='user', content=json.dumps(payload, ensure_ascii=False))]
