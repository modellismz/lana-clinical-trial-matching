"""Human-supervised decision loss with an extra false-eligible margin."""


def components(logits, target, code_ids, grade, margin=1.):
    import torch
    assert type(grade) is int and grade in range(3)
    assert len(code_ids) == len(set(code_ids)) == 3 and margin == 1.
    assert target.ndim == 1 and target.numel() > 1
    assert target[0].item() == code_ids[grade]
    assert logits.shape[:2] == (1, target.numel()+1)
    values = logits[0, :-1, :].float()
    assert torch.isfinite(values).all()
    losses = torch.nn.functional.cross_entropy(values, target, reduction='none')
    base = losses[0]+.1*losses[1:].mean()
    decision = values[0, code_ids]
    # Eligible human targets retain the ordinary supervised loss unchanged.
    risk = torch.nn.functional.softplus(decision[2]-decision[grade]+margin) if grade != 2 else decision.sum()*0.
    assert torch.isfinite(base) and torch.isfinite(risk)
    return base, risk
