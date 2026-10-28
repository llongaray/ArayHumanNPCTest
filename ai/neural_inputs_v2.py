"""Token-aware, valid-JSON compaction for the existing frozen MiniLM.

Numeric features retain the full observation; only textual summaries are reduced.
No arbitrary JSON/string cutting or invented values.
"""
import copy
import json
from neural_contract import unwrap,features
from neural_runtime import tensor_batch

def compact_value(value,tokenizer,budget):
    value=copy.deepcopy(value);partial=False
    while True:
        text=json.dumps({'partial':partial,'value':value},ensure_ascii=False,separators=(',',':'))
        if len(tokenizer(text,add_special_tokens=True,truncation=False)['input_ids'])<=budget:return value,partial
        partial=True
        if isinstance(value,list) and value:value.pop(0)
        elif isinstance(value,dict) and value:
            # Prefer reducing a collection over deleting all its members at once.
            key=next(reversed(value))
            if isinstance(value[key],list) and value[key]:value[key].pop()
            else:value.pop(key)
        else:return None,True

def tensor_batch_v2(observations,encoder):
    import torch
    reduced=copy.deepcopy(observations)
    limits={'identity':55,'profile':55,'health':38,'inventory':38,'threat':38,
            'action_results':38,'conversation_memory':38,'personal_memory':38}
    for obs in reduced:
        for key,limit in limits.items():
            value=unwrap(obs.get(key))
            if value is None:continue
            compact,partial=compact_value(value,encoder.model.tokenizer,limit)
            obs[key]={'status':'PARTIAL' if partial else obs[key]['status'],'value':compact}
    batch=list(tensor_batch(reduced,encoder))
    batch[4]=torch.tensor([features(o) for o in observations],dtype=torch.float32)
    return tuple(batch)

def encode_rows_v2(rows,encoder):
    import torch
    chunks=[tensor_batch_v2([r['observation'] for r in rows[i:i+32]],encoder) for i in range(0,len(rows),32)]
    return tuple(torch.cat([batch[j] for batch in chunks]).detach().clone() for j in range(7))
