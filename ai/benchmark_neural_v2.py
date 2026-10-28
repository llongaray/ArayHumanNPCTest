"""Validation-only CPU benchmark for the experimental v2 input adapter."""
import json
from pathlib import Path
import time
from benchmark_neural import latency,confidence_summary

def main():
    import psutil
    import torch
    from neural_encoder import LocalEncoder
    from neural_model import NPCPolicy
    from neural_inputs_v2 import tensor_batch_v2
    from neural_runtime import decode,digest
    from train_neural_v2 import OUT,DATA,read_split
    torch.set_num_threads(2)
    result=json.loads((OUT/'result.json').read_text(encoding='utf-8'));frozen=result['selection']
    path=OUT/frozen['selected_experiment']/'weights.pt'
    if digest(path)!=frozen['weights_sha256']:raise ValueError('weights_changed')
    encoder_path=Path(__file__).parent/'neural_models'/'paraphrase-multilingual-MiniLM-L12-v2'/'e8f8c211226b894fcb81acc59f3b34ba3efd5f42'
    proc=psutil.Process();before=proc.memory_info().rss;t=time.perf_counter();encoder=LocalEncoder(encoder_path)
    if encoder.fingerprint!=frozen['encoder_fingerprint']:raise ValueError('encoder_changed')
    model=NPCPolicy();model.load_state_dict(torch.load(path,map_location='cpu',weights_only=True));model.eval();loaded=time.perf_counter()-t
    rows=read_split('validation');measurements={k:[] for k in ('head_cached_inputs','cold_cache','warm_cache')}
    with torch.inference_mode():
        inp=tensor_batch_v2([rows[0]['observation']],encoder)
        for _ in range(5):decode(model(*inp),[rows[0]['observation']])
        for row in rows[:30]:
            obs=row['observation'];inp=tensor_batch_v2([obs],encoder)
            t=time.perf_counter();decode(model(*inp),[obs]);measurements['head_cached_inputs'].append((time.perf_counter()-t)*1000)
            encoder.cache.clear();t=time.perf_counter();inp=tensor_batch_v2([obs],encoder);decode(model(*inp),[obs]);measurements['cold_cache'].append((time.perf_counter()-t)*1000)
            t=time.perf_counter();inp=tensor_batch_v2([obs],encoder);decode(model(*inp),[obs]);measurements['warm_cache'].append((time.perf_counter()-t)*1000)
    memory=proc.memory_info()
    report={'split':'validation_only','samples':30,'threads':2,'cpu':True,'test_forward_calls':0,'load_seconds':loaded,
            'latency':{k:latency(v) for k,v in measurements.items()},'rss_before':before,'rss_after':memory.rss,'peak_rss':getattr(memory,'peak_wset',None),
            'test_confidence_from_saved_predictions':confidence_summary(json.loads((OUT/'test-predictions.json').read_text(encoding='utf-8')))}
    (OUT/'benchmark.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
