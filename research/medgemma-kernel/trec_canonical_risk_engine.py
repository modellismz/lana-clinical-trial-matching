"""Canonical clinical inputs with unchanged risk loss and2304token guard."""
import trec_2023_projection as task
import trec_trial_task as targets
from trec_trial_engine import Engine as Parent
from trec_risk_objective import components

CONTEXT=2304


class Engine(Parent):
    def source_inputs(self,row,proposed=None):
        torch=self.torch
        typed=[dict(role=m['role'],content=[dict(type='text',text=m['content'])]) for m in task.messages(row,proposed)]
        values=self.processor.apply_chat_template(typed,add_generation_prompt=True,
            tokenize=True,return_dict=True,return_tensors='pt').to(self.model.device)
        if 'token_type_ids' in values:
            assert not values['token_type_ids'].any();values.pop('token_type_ids')
        assert set(values)<={'input_ids','attention_mask'}
        suffix=torch.tensor([self.prefix_ids],device=self.model.device,dtype=torch.long)
        values['input_ids']=torch.cat([values['input_ids'],suffix],dim=-1)
        values['attention_mask']=torch.ones_like(values['input_ids'])
        assert values['input_ids'].shape[-1]+16<=CONTEXT,'Never truncate clinical source'
        return values

    def risk_loss(self,row,proposed=None):
        torch=self.torch;values=self.source_inputs(row,proposed)
        target=torch.tensor(self.processor.tokenizer.encode(targets.target(row['label']),add_special_tokens=False),
            device=self.model.device,dtype=torch.long)
        ids=torch.cat([values['input_ids'],target[None,:]],dim=-1)
        assert ids.shape[-1]<=CONTEXT
        logits=self.model(input_ids=ids,attention_mask=torch.ones_like(ids),use_cache=False,
            logits_to_keep=target.numel()+1).logits
        base,risk=components(logits,target,self.code_ids,row['label'])
        return base+risk,dict(base_loss=float(base.detach()),risk_penalty=float(risk.detach()))
