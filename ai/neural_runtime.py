"""Offline/shadow runtime. No mailbox registration, Executor calls or Ollama calls."""
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path

from neural_contract import ACTIONS,INTENTS,DECISIONS,FEATURES,TARGETED,MAX_GOALS,unwrap,check_observation,features,capability_mask,safe_decision

def dependency_status():
    names=('torch','sentence_transformers','numpy')
    return {name:importlib.util.find_spec(name) is not None for name in names}

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):h.update(block)
    return h.hexdigest()

def verify_manifest(directory):
    directory=Path(directory)
    if not (directory/'manifest.json').is_file(): raise ValueError('checkpoint_missing')
    if (directory/'manifest.json').stat().st_size>65536: raise ValueError('manifest_budget')
    m=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    if m.get('schema_version')!=1 or m.get('architecture')!='aray_multitask_gru_v1': raise ValueError('checkpoint_schema')
    if m.get('intents')!=list(INTENTS) or m.get('decisions')!=list(DECISIONS) or m.get('actions')!=list(ACTIONS) or m.get('features')!=list(FEATURES): raise ValueError('checkpoint_labels')
    if m.get('validated') is not True: raise ValueError('checkpoint_not_validated')
    for split in ('validation','test'):
        metrics=m.get('metrics',{}).get(split,{})
        if any(type(metrics.get(k)) not in (int,float) or not math.isfinite(metrics[k]) for k in ('count','intent_exact','decision_accuracy','ordered_goal_exact','invalid_action_rate','multi_goal_exact','multi_goal_count','confidence_coverage')):
            raise ValueError('checkpoint_metrics')
        if metrics.get('count',0)<20 or metrics.get('intent_exact',0)<.80 or metrics.get('decision_accuracy',0)<.85 or metrics.get('ordered_goal_exact',0)<.80 or metrics.get('invalid_action_rate',1)!=0:
            raise ValueError('checkpoint_metrics')
        if metrics['multi_goal_count']<4 or metrics['multi_goal_exact']<.80 or metrics['confidence_coverage']<.50:raise ValueError('checkpoint_metrics')
    weights=directory/'weights.pt'
    if not weights.is_file() or weights.stat().st_size>20*1024*1024 or digest(weights)!=m.get('weights_sha256'): raise ValueError('checkpoint_integrity')
    if not isinstance(m.get('encoder_fingerprint'),str) or len(m['encoder_fingerprint'])!=64: raise ValueError('checkpoint_encoder')
    if m.get('embedding_dim')!=384 or m.get('hidden')!=128: raise ValueError('checkpoint_dimensions')
    return m

def tensor_batch(observations,encoder):
    """Encode real strings with a real encoder; numeric slots are observed scalar features."""
    import torch
    def summary(obs,key,limit=350):
        value=unwrap(obs.get(key))
        if value is None:return 'Dados indisponíveis'
        value=copy.deepcopy(value); partial=False
        while True:
            text=json.dumps({'partial':partial,'value':value},ensure_ascii=False,separators=(',',':'))
            if len(text.encode('utf-8'))<=limit:return text
            partial=True
            if isinstance(value,dict) and value:value.pop(next(reversed(value)))
            elif isinstance(value,list) and value:value.pop(0)
            else:return 'Resumo indisponível por orçamento'
    language=encoder.encode([o['message'] for o in observations])
    profile=encoder.encode([summary(o,'identity')+' '+summary(o,'profile') for o in observations])
    history=encoder.encode([summary(o,'action_results',150)+' '+summary(o,'conversation_memory',200)+' '+summary(o,'personal_memory',150) for o in observations])
    state=encoder.encode([summary(o,'health',180)+' '+summary(o,'inventory',180)+' '+summary(o,'threat',180) for o in observations])
    candidates=torch.zeros(len(observations),32,384+len(ACTIONS))
    for row,obs in enumerate(observations):
        cs=obs.get('candidates',[])
        if cs:
            encoded=encoder.encode([(c.get('description') or 'Descrição do alvo indisponível')[:400] for c in cs])
            candidates[row,:len(cs),:384]=encoded
            for j,c in enumerate(cs):candidates[row,j,384+ACTIONS.index(c['action'])]=1
    return (language,profile,history,state,torch.tensor([features(o) for o in observations],dtype=torch.float32),
            torch.tensor([capability_mask(o) for o in observations],dtype=torch.float32),candidates)

def decode(output,observations):
    """Select learned logits; action/target guards are policy-independent safety."""
    import torch
    predictions=[]
    for row,obs in enumerate(observations):
        ip=output['intents'][row].sigmoid(); dp=output['decision'][row].softmax(-1); cp=output['count'][row].softmax(-1)
        count=int(cp.argmax()); selected=int(dp.argmax())
        confidence=min(float(dp[selected]),float(cp[count]),float(torch.maximum(ip,1-ip).min()))
        goals=[]
        for slot in range(count):
            ap=output['actions'][row,slot].softmax(-1); action_index=int(ap.argmax())
            confidence=min(confidence,float(ap[action_index]))
            if action_index==len(ACTIONS): confidence=0; break
            action=ACTIONS[action_index]; goal={'action':action}
            if action in TARGETED:
                indices=[i for i,c in enumerate(obs.get('candidates',[])) if c['action']==action]
                if not indices: confidence=0; break
                logits=output['pointers'][row,slot,indices]; pp=logits.softmax(-1); pick=int(pp.argmax())
                confidence=min(confidence,float(pp[pick])); goal['target_id']=obs['candidates'][indices[pick]]['target_id']
                if not obs['candidates'][indices[pick]].get('description'):confidence=0
            goals.append(goal)
        predictions.append({'decision':DECISIONS[selected],'intents':[label for i,label in enumerate(INTENTS) if float(ip[i])>=.5],
                            'confidence':confidence,'goals':goals})
    return predictions

class NeuralPolicy:
    def __init__(self,directory=None,encoder_path=None,enabled=False):
        self.model=None; self.encoder=None; self.reason='activation_disabled'
        if not enabled:return
        try:
            manifest=verify_manifest(directory)
            if not all(dependency_status().values()):raise ValueError('dependencies_unavailable')
            from neural_encoder import LocalEncoder
            from neural_model import NPCPolicy
            import torch
            torch.set_num_threads(2)
            self.encoder=LocalEncoder(encoder_path)
            if self.encoder.fingerprint!=manifest['encoder_fingerprint']:raise ValueError('encoder_mismatch')
            model=NPCPolicy()
            model.load_state_dict(torch.load(Path(directory)/'weights.pt',map_location='cpu',weights_only=True),strict=True)
            model.eval(); self.model=model; self.reason=None
        except (ValueError,OSError,ImportError,RuntimeError,TypeError,AttributeError) as exc:
            self.model=None; self.encoder=None; self.reason=str(exc)[:100]

    def predict(self,obs,now):
        try:check_observation(obs,now)
        except (ValueError,KeyError,TypeError,AttributeError) as exc:
            return {'schema_version':1,'status':'UNAVAILABLE','reason':str(exc),'decision':'NO_RESPONSE','goals':[]}
        if self.model is None:return {'schema_version':1,'status':'UNAVAILABLE','reason':self.reason,'decision':'NO_RESPONSE','goals':[]}
        try:
            import torch
            with torch.inference_mode(): output=self.model(*tensor_batch([obs],self.encoder))
            return dict(safe_decision(decode(output,[obs])[0],obs,now),status='PREDICTED')
        except (ValueError,KeyError,TypeError,RuntimeError,AttributeError):
            return {'schema_version':1,'status':'UNAVAILABLE','reason':'inference_failed','decision':'NO_RESPONSE','goals':[]}

def compose_observation(neural,agent):
    """Read-only join of trusted snapshots; no synthetic target names or coordinates."""
    if any(neural.get(k)!=agent.get(k) for k in ('uuid','world_id')):raise ValueError('observation_binding')
    out=copy.deepcopy(neural)
    out['observation_id']=agent['observation_id']; out['control']=copy.deepcopy(agent.get('runtime',{}).get('control'))
    out['candidates']=copy.deepcopy([c for c in agent.get('candidates',[]) if c.get('action') in TARGETED][:32])
    current=agent.get('runtime',{}).get('execution')
    out['current_goal']=copy.deepcopy(current)
    out['expires_at_ms']=min(out['expires_at_ms'],agent['expires_at_ms'])
    return out
