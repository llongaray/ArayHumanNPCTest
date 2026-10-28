"""Offline validation-only benchmark. Never reevaluates the held-out test set."""
import argparse
import json
from pathlib import Path
import statistics
import time

def latency(values):
    ordered=sorted(values)
    return {'count':len(values),'mean_ms':statistics.mean(values),'median_ms':statistics.median(values),
            'p95_ms':ordered[min(len(ordered)-1,int(len(ordered)*.95))],'max_ms':max(values)}

def confidence_summary(records):
    bins=[]
    for low,high in ((0,.5),(.5,.8),(.8,.9),(.9,1.000001)):
        group=[r for r in records if low<=r['prediction']['confidence']<high]
        correct=sum(r['expected']['decision']==r['prediction']['decision'] for r in group)
        bins.append({'lower':low,'upper':min(high,1),'count':len(group),'decision_accuracy':correct/len(group) if group else None})
    scores=[r['prediction']['confidence'] for r in records]
    return {'mean':statistics.mean(scores),'min':min(scores),'max':max(scores),'bins':bins,
            'calibrated':False,'interpretation':'raw neural confidence; no probability-of-correctness guarantee'}

def main():
    p=argparse.ArgumentParser(); p.add_argument('--encoder-path',required=True); p.add_argument('--checkpoint',required=True)
    args=p.parse_args()
    import psutil
    import torch
    from neural_encoder import LocalEncoder
    from neural_model import NPCPolicy
    from neural_runtime import tensor_batch,decode,digest
    torch.set_num_threads(2)
    root=Path(args.checkpoint); manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    if digest(root/'weights.pt')!=manifest['weights_sha256']:raise ValueError('checkpoint_hash')
    process=psutil.Process(); before=process.memory_info().rss
    started=time.perf_counter(); encoder=LocalEncoder(args.encoder_path)
    if encoder.fingerprint!=manifest['encoder_fingerprint']:raise ValueError('encoder_hash')
    model=NPCPolicy(); model.load_state_dict(torch.load(root/'weights.pt',map_location='cpu',weights_only=True)); model.eval()
    load_seconds=time.perf_counter()-started
    rows=[json.loads(line) for line in (root/'validation.jsonl').read_text(encoding='utf-8').splitlines()]
    times={k:[] for k in ('head_cached_inputs','end_to_end_cold_text_cache','end_to_end_warm_text_cache')}
    with torch.inference_mode():
        inputs=tensor_batch([rows[0]['observation']],encoder)
        for _ in range(5):decode(model(*inputs),[rows[0]['observation']])
        for row in rows[:30]:
            obs=row['observation']; inputs=tensor_batch([obs],encoder)
            start=time.perf_counter(); decode(model(*inputs),[obs]); times['head_cached_inputs'].append((time.perf_counter()-start)*1000)
            encoder.cache.clear()
            start=time.perf_counter(); inputs=tensor_batch([obs],encoder); decode(model(*inputs),[obs]); times['end_to_end_cold_text_cache'].append((time.perf_counter()-start)*1000)
            start=time.perf_counter(); inputs=tensor_batch([obs],encoder); decode(model(*inputs),[obs]); times['end_to_end_warm_text_cache'].append((time.perf_counter()-start)*1000)
    memory=process.memory_info()
    report={'split':'validation_only','samples':30,'threads':2,'device':'cpu','load_seconds':load_seconds,
            'latency':{k:latency(v) for k,v in times.items()},'rss_before_load_bytes':before,'rss_after_bytes':memory.rss,
            'process_peak_working_set_bytes':getattr(memory,'peak_wset',None),'test_forward_calls':0,
            'confidence':{s:confidence_summary(json.loads((root/(s+'-predictions.json')).read_text(encoding='utf-8'))) for s in ('validation','test')}}
    (root/'benchmark.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
