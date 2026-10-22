"""Official 4B frozen base, Q/K/V/O adapters and decision-dominant decoder loss."""
import hashlib
import json
import math
import time
import bench
import source_verifier_task as task
from lora_state_engine import Engine as BaseEngine,make_lora

CONTEXT=2048
RANK=16
ALPHA=32


def decision_loss(logits,target):
    import torch
    n=target.numel();assert logits.shape[1]==n+1 and n>1
    losses=torch.nn.functional.cross_entropy(logits[0,:-1,:].float(),target,reduction='none')
    assert torch.isfinite(losses).all()
    return losses[0]+.1*losses[1:].mean()


class Engine(BaseEngine):
    def __init__(self,out):
        super().__init__(out,rank=RANK,alpha=ALPHA)
        for name,module in list(self.model.named_modules()):
            if name.startswith('model.layers.') and name.endswith(('.self_attn.k_proj','.self_attn.o_proj')):
                parent_name,attribute=name.rsplit('.',1);adapter=make_lora(module,RANK,ALPHA)
                setattr(self.model.get_submodule(parent_name),attribute,adapter);self.adapters.append((name,adapter))
        self.parameters=[p for p in self.model.parameters() if p.requires_grad]
        assert len(self.adapters)==4*self.model.config.num_hidden_layers
        assert sum(p.numel() for p in self.parameters)<20_000_000
        self.code_ids=[self.processor.tokenizer.encode(code,add_special_tokens=False) for code in task.CODES]
        assert all(len(ids)==1 for ids in self.code_ids)
        self.code_ids=[ids[0] for ids in self.code_ids];assert len(set(self.code_ids))==4
        self.prefix_ids=self.processor.tokenizer.encode(task.PREFIX,add_special_tokens=False)
        env=bench.read(out/'environment.json')
        env.update(adapter_modules=len(self.adapters),trainable_parameters=sum(p.numel() for p in self.parameters),
                   objective='First decision-token full-vocabulary CE plus .1 mean evidence/format CE',
                   inference='Two source-bound decoder forwards: source decision then untrusted-proposal verification; no sampled reasoning.',
                   code_ids=self.code_ids,final_prefix=task.PREFIX,classifier_head_used=False)
        bench.save(out/'environment.json',env)

    def source_inputs(self,row,proposed=None):
        typed=[dict(role=m['role'],content=[dict(type='text',text=m['content'])]) for m in task.messages(row,proposed)]
        inputs=self.processor.apply_chat_template(typed,add_generation_prompt=True,tokenize=True,return_dict=True,return_tensors='pt').to(self.model.device)
        if 'token_type_ids' in inputs:assert not inputs['token_type_ids'].any();inputs.pop('token_type_ids')
        assert set(inputs)<={'input_ids','attention_mask'}
        suffix=self.torch.tensor([self.prefix_ids],device=self.model.device,dtype=inputs['input_ids'].dtype)
        inputs['input_ids']=self.torch.cat([inputs['input_ids'],suffix],dim=-1)
        inputs['attention_mask']=self.torch.ones_like(inputs['input_ids'])
        assert inputs['input_ids'].shape[-1]<CONTEXT,'Never truncate a source'
        return inputs

    def loss(self,row,proposed=None):
        inputs=self.source_inputs(row,proposed)
        ids=self.processor.tokenizer.encode(task.target(row),add_special_tokens=False)
        assert ids[0]==self.code_ids[task.STATE[row['expert_eligibility']]]
        target=self.torch.tensor(ids,device=self.model.device)
        joined=self.torch.cat([inputs['input_ids'],target[None,:]],dim=-1)
        assert joined.shape[-1]<=CONTEXT
        logits=self.model(input_ids=joined,attention_mask=self.torch.ones_like(joined),use_cache=False,logits_to_keep=len(ids)+1).logits
        return decision_loss(logits,target)

    def score(self,row,proposed=None):
        self.enable(True);self.model.eval();inputs=self.source_inputs(row,proposed);torch=self.torch
        torch.cuda.synchronize();start=time.monotonic()
        with torch.inference_mode():values=self.model(**inputs,use_cache=False,logits_to_keep=1).logits[0,-1,:].float()
        torch.cuda.synchronize();elapsed=time.monotonic()-start
        assert torch.isfinite(values).all()
        probabilities=torch.log_softmax(values,dim=-1);scores=values[self.code_ids]
        return dict(scores=scores.tolist(),allowed_probability_mass=float(probabilities[self.code_ids].exp().sum()),
                    unrestricted_top_token_id=int(values.argmax()),input_tokens=inputs['input_ids'].shape[-1],seconds=elapsed,
                    predicted_state=int(scores.argmax()))


def request(row,proposed,revision,checkpoint):
    return dict(prompt=task.messages(row,proposed),final_prefix=task.PREFIX,model_revision=revision,
                adapter_sha256=checkpoint,adapters_enabled=True,rank=RANK,alpha=ALPHA,modules='q/k/v/o',
                readout='Four fixed single-token codes, raw decoder logits; no generated reasoning or correctness retries.',
                context_budget=CONTEXT,source_truncated=False)


def infer(engine,row,path,checkpoint):
    assert not path.exists(),'Never replace an inference record'
    views=[];proposed=None
    for name in ['source','verifier']:
        payload=request(row,proposed,engine.revision,checkpoint);value=engine.score(row,proposed)
        views.append(dict(view=name,request=payload,request_sha256=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest(),**value))
        if name=='source':proposed=task.proposal(row,value['predicted_state'])
    record=dict(annotation_id=row['annotation_id'],views=views,seconds=sum(v['seconds'] for v in views))
    bench.save(path,record);return record


def validate(record,row,revision,checkpoint):
    assert record['annotation_id']==row['annotation_id'] and len(record['views'])==2
    proposed=None
    for name,view in zip(['source','verifier'],record['views']):
        payload=request(row,proposed,revision,checkpoint)
        assert view['view']==name and view['request']==payload
        assert view['request_sha256']==hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
        assert len(view['scores'])==4 and all(math.isfinite(x) for x in view['scores'])
        assert view['predicted_state']==max(range(4),key=lambda k:view['scores'][k])
        assert 0<=view['allowed_probability_mass']<=1.00001 and view['seconds']>=0
        if name=='source':proposed=task.proposal(row,view['predicted_state'])
    return record
