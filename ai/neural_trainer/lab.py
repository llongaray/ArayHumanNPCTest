"""Read-only neural laboratory using real weights and synthetic versioned state."""
import hashlib
import json
from pathlib import Path
import re
import threading
import time
import unicodedata
from . import AI
from .store import ARTIFACTS,read_json,runs

def catalog():
    paths=[ARTIFACTS/'3c5b1-seed1729'/'manifest.json',
           ARTIFACTS/'3c5b2'/'baseline'/'manifest.json',ARTIFACTS/'3c5b2'/'balanced_sequence'/'manifest.json']
    paths.extend(Path(r['checkpoint_manifest']) for r in runs() if r.get('checkpoint_manifest'))
    result=[]
    for path in paths:
        path=path.resolve()
        if not path.is_relative_to(ARTIFACTS.resolve()):continue
        m=read_json(path)
        if not isinstance(m,dict) or not (path.parent/'weights.pt').is_file():continue
        metrics=m.get('validation') or m.get('metrics',{}).get('validation')
        from train_neural import passes
        from train_neural_v2 import gate_result
        failures=gate_result(metrics) if metrics and 'per_class' in metrics else ([] if metrics and passes(metrics) else ['original_gates'])
        validated=False
        if m.get('validated') is True:
            from neural_runtime import verify_manifest
            try:verify_manifest(path.parent);validated=True
            except (ValueError,OSError):pass
        result.append({'id':hashlib.sha256(str(path).encode()).hexdigest()[:24],'name':path.parent.relative_to(ARTIFACTS).as_posix(),
                       'manifest_path':str(path),'weights_sha256':m.get('weights_sha256'),'best_epoch':m.get('selected_epoch'),
                       'validation':metrics,'validated':validated,'approval':'VALIDATED' if validated else 'EXPERIMENTAL',
                       'validation_gate_failures':failures,'validation_passed':not failures,
                       'architecture':m.get('architecture'),'version':m.get('schema_version'),
                       'encoder_fingerprint':m.get('encoder_fingerprint') or read_json(ARTIFACTS/'3c5b2'/'result.json',{}).get('encoder_fingerprint'),
                       'input_adapter':'v1' if '3c5b1-seed1729' in str(path) else 'v2'})
    return result

def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFD',text.casefold()) if unicodedata.category(c)!='Mn')

def recipients(message):
    if not isinstance(message,str) or len(message.encode('utf-8'))>2000:raise ValueError('message_budget')
    prefix=re.split('[:,]',normalize(message),maxsplit=1)
    if len(prefix)!=2:return []
    head=prefix[0].strip()
    if head in ('voces','pessoal','todos'):return ['Carlos','Tania']
    if not re.fullmatch(r'(carlos|tania)(\s+e\s+(carlos|tania))*',head):return []
    return list(dict.fromkeys(n.title() for n in re.findall(r'carlos|tania',head)))

SCENARIOS={'calm':{'version':1,'label':'Área sintética calma'},'injured':{'version':1,'label':'Ferimento sintético'},
           'emergency':{'version':1,'label':'Prioridade emergencial sintética'},'missing':{'version':1,'label':'Coleta indisponível'}}

def scenario(message,name,kind):
    from neural_data import observation
    obs=observation(message);now=int(time.time()*1000);actor='11111111-1111-4111-8111-111111111111' if name=='Carlos' else '22222222-2222-4222-8222-222222222222'
    obs.update(uuid=actor,world_id='SYNTHETIC/LAB-v1',session_id='lab-session',request_id='lab-'+str(time.time_ns()),
               captured_at_ms=now,expires_at_ms=now+1000)
    obs['routing'].update(world_id=obs['world_id'],recipients=[actor]);obs['identity']['value']['name']=name
    for c in obs['candidates']:c.update(uuid=actor,world_id=obs['world_id'],expires_at_ms=now+1000)
    if kind=='injured':obs['health']['value']['health']['value']=35
    if kind=='emergency':obs['control']['emergency_priority']=True;obs['threat']['value']['observed_zombies']=4
    if kind=='missing':
        obs['candidates']=[c for c in obs['candidates'] if c['action']!='PICKUP_ITEM'];obs['capabilities']['value']['PICKUP_ITEM']['available']=False
    return obs

class Laboratory:
    def __init__(self):self.lock=threading.Lock();self.encoder=None;self.model=None;self.key=None
    def predict(self,message,checkpoint_id,kind):
        names=recipients(message)
        if not names:return {'synthetic':True,'recipients':[],'blocked':'explicit_recipient_required','predictions':[]}
        if kind not in SCENARIOS:raise ValueError('unknown_scenario')
        entry=next((m for m in catalog() if m['id']==checkpoint_id),None)
        if entry is None:raise ValueError('unknown_checkpoint')
        if not self.lock.acquire(blocking=False):raise RuntimeError('laboratory_busy')
        try:
            import torch
            from neural_runtime import digest,decode,tensor_batch
            from neural_inputs_v2 import tensor_batch_v2
            from neural_model import NPCPolicy
            from neural_encoder import LocalEncoder
            from neural_contract import safe_decision
            from .cli import ENCODER
            torch.set_num_threads(2);start=time.perf_counter()
            path=Path(entry['manifest_path']).parent/'weights.pt'
            actual=digest(path)
            if actual!=entry['weights_sha256']:raise ValueError('checkpoint_integrity')
            if self.encoder is None:self.encoder=LocalEncoder(ENCODER)
            if self.encoder.fingerprint!=entry['encoder_fingerprint']:raise ValueError('encoder_integrity')
            if self.key!=(str(path),actual):
                model=NPCPolicy();model.load_state_dict(torch.load(path,map_location='cpu',weights_only=True),strict=True);model.eval()
                self.model=model;self.key=(str(path),actual)
            predictions=[]
            for name in names:
                obs=scenario(message,name,kind);infer=time.perf_counter()
                with torch.inference_mode():
                    inputs=(tensor_batch_v2 if entry['input_adapter']=='v2' else tensor_batch)([obs],self.encoder)
                    raw=decode(self.model(*inputs),[obs])[0]
                try:guarded=safe_decision(raw,obs,int(time.time()*1000))
                except ValueError as exc:guarded={'decision':'NO_RESPONSE','goals':[],'reason':str(exc)}
                predictions.append({'recipient':name,'uuid':obs['uuid'],'world_id':obs['world_id'],'raw':raw,'guarded':guarded,
                                    'blocked_actions':[] if guarded['decision']=='EXECUTE_ACTION' else [dict(g,blocked_reason=guarded.get('reason')) for g in raw['goals']],
                                    'expected':{'decision':'WAIT','source':'scenario_priority_guard'} if kind=='emergency' else None,
                                    'observation':obs,'inference_ms':(time.perf_counter()-infer)*1000,
                                    'embedding':{'dimension':384,'preview':inputs[0][0,:12].tolist(),'norm':float(inputs[0][0].norm())},
                                    'execution':'DISABLED_SYNTHETIC_ONLY'})
            return {'synthetic':True,'scenario_version':1,'recipients':names,'checkpoint':entry['name'],
                    'checkpoint_validated':entry['validated'],'predictions':predictions,'total_ms':(time.perf_counter()-start)*1000}
        finally:self.lock.release()
