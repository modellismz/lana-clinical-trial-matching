"""Fresh MedGemma Q/K/V/O LoRA for the separate whole-trial task."""
import json

import bench
import trec_trial_task as task
from source_verifier_engine import Engine as Parent


class Engine(Parent):
    def __init__(self, out):
        super().__init__(out)
        self.code_ids = [self.processor.tokenizer.encode(c, add_special_tokens=False) for c in task.CODES]
        assert all(len(x) == 1 for x in self.code_ids)
        self.code_ids = [x[0] for x in self.code_ids]
        self.prefix_ids = self.processor.tokenizer.encode(task.PREFIX, add_special_tokens=False)
        env = bench.read(out/'environment.json')
        env.update(task='TREC trial-level three-class', code_ids=self.code_ids,
            initialization='Fresh zero-B Q/K/V/O adapters; no previous adapted checkpoint loaded',
            inference='Source plus three deliberately untrusted proposals; four actual forwards')
        bench.save(out/'environment.json', env)

    def source_inputs(self, row, proposed=None):
        typed = [dict(role=m['role'], content=[dict(type='text', text=m['content'])])
                 for m in task.messages(row, proposed)]
        values = self.processor.apply_chat_template(typed, add_generation_prompt=True,
            tokenize=True, return_dict=True, return_tensors='pt').to(self.model.device)
        if 'token_type_ids' in values:
            assert not values['token_type_ids'].any()
            values.pop('token_type_ids')
        assert set(values) <= {'input_ids', 'attention_mask'}
        suffix = self.torch.tensor([self.prefix_ids], device=self.model.device, dtype=self.torch.long)
        values['input_ids'] = self.torch.cat([values['input_ids'], suffix], dim=-1)
        values['attention_mask'] = self.torch.ones_like(values['input_ids'])
        assert values['input_ids'].shape[-1] + 16 <= 2048, 'Never truncate source'
        return values

    def loss(self, row, proposed=None):
        torch = self.torch
        values = self.source_inputs(row, proposed)
        tokens = self.processor.tokenizer.encode(task.target(row['label']), add_special_tokens=False)
        target = torch.tensor(tokens, device=self.model.device, dtype=torch.long)
        ids = torch.cat([values['input_ids'], target[None, :]], dim=-1)
        assert ids.shape[-1] <= 2048
        logits = self.model(input_ids=ids, attention_mask=torch.ones_like(ids),
            use_cache=False, logits_to_keep=len(tokens)+1).logits
        from source_verifier_engine import decision_loss
        return decision_loss(logits, target)


def readout(record, fusion):
    scores = [v['scores'] for v in record['views']]
    assert len(scores) == 4 and all(len(s) == 3 for s in scores)
    if fusion == 'source':
        values = scores[0]
    elif fusion == 'mean_logits':
        values = [sum(s[k] for s in scores)/4 for k in range(3)]
    elif fusion == 'vote':
        votes = [max(range(3), key=lambda k: s[k]) for s in scores]
        values = [votes.count(k) for k in range(3)]
    else:
        raise ValueError(fusion)
    return max(range(3), key=lambda k: values[k])
