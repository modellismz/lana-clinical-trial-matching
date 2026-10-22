"""Local evidence and development-reference tools. No provider or network clients."""
import json
import re
import bench


def reference_memory(row):
    """Expert-labelled development examples only; exclude the target patient."""
    dev=set(bench.read(bench.ROOT/'manifest.json')['dev_patients'])
    words=lambda t:set(re.findall(r'[a-z0-9]+',t.lower()))-{'the','a','an','and','or','of','with','to','in'}
    q=words(row['criterion_text']);candidates=[]
    for r in bench.read(bench.ROOT/'data/source.json'):
        if r['patient_id'] not in dev or r['patient_id']==row['patient_id'] or r['criterion_type']!=row['criterion_type']:continue
        w=words(r['criterion_text']);score=len(q&w)/max(1,len(q|w))
        candidates.append((score,-r['annotation_id'],r))
    examples=[]
    for _,_,r in sorted(candidates,key=lambda x:(x[0],x[1]),reverse=True)[:2]:
        lines=r['note'].splitlines();ids=set(json.loads(r['expert_sentences']))|{0}
        snippets=' '.join(s for i,s in enumerate(lines) if i in ids)[:550]
        examples.append({'development_annotation_id':r['annotation_id'],'patient_id':r['patient_id'],
                         'criterion_type':r['criterion_type'],'criterion':r['criterion_text'][:450],
                         'patient_evidence_excerpt':snippets,'expert_label':r['expert_eligibility']})
    assert all(x['patient_id']!=row['patient_id'] for x in examples)
    return examples


def facts(note):
    lines = {int(i):s for i,s in re.findall(r'(?m)^(\d+)\.\s*(.*)$',note)}
    out = {'age':None,'sex':None,'numeric_source_sentences':[]}
    first = lines.get(0,'')
    m=re.search(r'\b(\d{1,3})[- ]year[- ]old\b',first,re.I)
    if m: out['age']={'value':int(m[1]),'unit':'years','sentence_id':0,'quote':m[0]}
    m=re.search(r'\b(female|male|woman|man)\b',first,re.I)
    if m: out['sex']={'value':m[0].lower(),'sentence_id':0,'quote':m[0]}
    for i,s in lines.items():
        if re.search(r'\d',s): out['numeric_source_sentences'].append({'sentence_id':i,'text':s})
    return out


def typed_age(row,pred):
    age=facts(row['note'])['age']
    if not age: return pred
    t=row['criterion_text'].lower().strip().rstrip('.;')
    suffix=r'(?:\s*(?:years?(?:\s*old)?|years?\s*of\s*age))?'
    match=re.fullmatch(r'(?:age[d]?\s*(?:between\s*)?)(\d+)\s*(?:to|through|[-–]|and)\s*(\d+)'+suffix,t)
    meets=None
    if match:
        meets=int(match[1])<=age['value']<=int(match[2])
    else:
        match=re.fullmatch(r'age\s*(>=|≥|>|<=|≤|<|at least|greater than or equal to|greater than|less than|at most)\s*(\d+)'+suffix,t)
        if match:
            op,n=match[1],int(match[2]); x=age['value']
            meets= x>=n if op in ['>=','≥','at least','greater than or equal to'] else x>n if op in ['>','greater than'] else x<=n if op in ['<=','≤','at most'] else x<n
    if meets is None: return pred
    label=('included' if meets else 'not included') if row['criterion_type']=='inclusion' else ('excluded' if meets else 'not excluded')
    return dict(pred,label=label,sentence_ids=[0],reason=f'Typed age check: {age["value"]} years against exact simple age criterion.',typed_rule='exact_age')


def messages(arm,rows,draft):
    system=bench.BASE
    if arm=='self_review':
        system+='\nReview the draft decisions carefully against the full patient note and criteria. Correct any mistakes. Return the complete decisions array in the same schema. Do not trust a draft merely because it sounds confident.'
    elif arm in ['evidence_audit','memory_audit']:
        system+='''\nYou are the evidence audit agent. Use the local evidence-tool output and independently check each draft. For each criterion: (1) decompose AND/OR and conditional clauses; (2) locate actual patient evidence and distinguish absent, contradicted and explicitly unresolved facts; (3) check exact age/sex, disease subtype, values/units and timing; (4) check inclusion/exclusion polarity; (5) return a corrected decision with existing source sentence IDs. Not applicable requires a condition that does not apply, not a missing clinical value. For exclusion criteria, preserve the benchmark convention stated above. A general diagnosis is not proof of a specific subtype or a quantitative threshold. Evidence-tool outputs are sourced facts, not gold answers. Do not invent tests, consent or medical history.'''
    else:
        system+='\nClassify the target criteria independently. Use the development reference examples only as annotation-style guidance. They describe different patients: none of their clinical facts apply to the target patient.'
    payload={'patient_note':rows[0]['note'],'trial_title':rows[0]['trial_title'],
             'criteria':[{'id':r['annotation_id'],'type':r['criterion_type'],'text':r['criterion_text']} for r in rows],
             'draft_decisions':[{k:p.get(k) for k in ['annotation_id','label','sentence_ids','reason']} for p in draft]}
    if arm=='rag_only':payload.pop('draft_decisions')
    if arm in ['evidence_audit','memory_audit']: payload['local_evidence_tool']=facts(rows[0]['note'])
    if arm in ['rag_only','memory_audit']:
        system+='\nDevelopment references are expert-labelled examples from different patients, not target answers or target facts. Use them to clarify the six-label annotation convention only.'
        payload['development_reference_tool']=[{'target_criterion_id':r['annotation_id'],'examples':reference_memory(r)} for r in rows]
    return [{'role':'system','content':system},{'role':'user','content':json.dumps(payload)}]
