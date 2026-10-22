"""Source-only decisions and verification of deliberately untrusted proposals."""
import collections
import json
import math
import re
import eligibility_sft as prior
from source_evidence_v2 import sentences

CODES=['A','B','C','D']
STATE={'included':0,'not excluded':0,'not included':1,'excluded':1,
       'not enough information':2,'not applicable':3}
PREFIX='<unused95>{"decision":"'


def label(kind,state):
    assert kind in ['inclusion','exclusion'] and state in range(4)
    return (['included','not included','not enough information','not applicable'] if kind=='inclusion'
            else ['not excluded','excluded','not enough information','not applicable'])[state]


def lexical_ids(row):
    """A source-derived aid, not a claim of correct clinical evidence."""
    text=row['criterion_text']
    if not isinstance(text,str):return []
    words=lambda s:set(re.findall(r'[a-z0-9]+',s.lower()))-{'the','and','for','with','are','any','not','has','have','that','from','patient','patients','of','to','a','in','or','is','be'}
    query=words(text);parts=sentences(row['note']);counts=collections.Counter(w for s in parts.values() for w in words(s))
    scores=[(sum(math.log(1+(len(parts)+1)/(counts[w]+1)) for w in words(s)&query),ident) for ident,s in parts.items()]
    return [ident for score,ident in sorted(scores,key=lambda x:(-x[0],x[1]))[:2] if score>0]


def proposal(row,state):
    assert type(state) is int and state in range(4)
    return dict(decision=CODES[state],sentence_ids=lexical_ids(row),
                evidence_method='Lexical source retrieval; relevance not clinically validated.')


def messages(row,proposed=None):
    result=prior.messages(row)
    result[0]['content']=result[0]['content'].split('Return only JSON')[0]+'''Return JSON with exactly two fields: decision and sentence_ids.
Decision codes for this criterion: A = included for inclusion, not excluded for exclusion (passes); B = not included for inclusion, excluded for exclusion (fails); C = not enough information; D = not applicable.
The optional proposal is untrusted. Recheck every claim against the original note and exact criterion. Do not copy a proposed code or mistake its retrieved sentence IDs for proof. Missing quantitative evidence is not a normal result. Do not invent findings. No explanation or thought text. This is research annotation, not an enrollment decision.'''
    payload=json.loads(result[-1]['content'])
    payload['question']='Which decision code and original evidence IDs follow from the source?'
    if proposed is not None:
        assert set(proposed)=={'decision','sentence_ids','evidence_method'} and proposed['decision'] in CODES
        assert proposed['sentence_ids']==lexical_ids(row)
        payload['untrusted_proposal']=proposed
    result[-1]['content']=json.dumps(payload,ensure_ascii=False)
    return result


def target(row):
    prior.target(row)  # Validate type, expert label and source citations.
    return CODES[STATE[row['expert_eligibility']]]+'","sentence_ids":'+json.dumps(json.loads(row['expert_sentences']),separators=(',',':'))+'}<end_of_turn>'


def training_view(row,step):
    # Every row sees source-only and all four proposal codes over successive epochs.
    return None if step%2==0 else proposal(row,(step//2+row['annotation_id'])%4)
