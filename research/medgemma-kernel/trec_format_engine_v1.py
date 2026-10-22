"""Same complete canonical input, half-strength noneligible risk penalty."""
from trec_canonical_risk_engine import Engine as Parent
from trec_risk_objective import components
import trec_trial_task as targets

COEFFICIENT=.5


def weighted_loss(base,risk):return base+COEFFICIENT*risk


class Engine(Parent):
    def risk_loss(self,row,proposed=None):
        torch=self.torch;values=self.source_inputs(row,proposed)
        target=torch.tensor(self.processor.tokenizer.encode(targets.target(row['label']),add_special_tokens=False),
            device=self.model.device,dtype=torch.long)
        ids=torch.cat([values['input_ids'],target[None,:]],dim=-1);assert ids.shape[-1]<=2304
        logits=self.model(input_ids=ids,attention_mask=torch.ones_like(ids),use_cache=False,logits_to_keep=target.numel()+1).logits
        base,risk=components(logits,target,self.code_ids,row['label'])
        return weighted_loss(base,risk),dict(base_loss=float(base.detach()),risk_penalty=float(risk.detach()),risk_coefficient=COEFFICIENT)
