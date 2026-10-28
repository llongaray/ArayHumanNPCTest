"""Policy contracts and safety guards, deliberately separate from learned inference."""
import copy
import math
import uuid
import json
import hashlib

INTENTS=('CONVERSATION','QUESTION','INSTRUCTION','ACTION_REQUEST','INFORMATION','NO_RESPONSE')
DECISIONS=('EXECUTE_ACTION','REQUEST_DIALOGUE','CONTINUE_GOAL','WAIT','NO_RESPONSE','REQUEST_CLARIFICATION')
ACTIONS=('STOP','FOLLOW_PLAYER','LOOK_AT_PLAYER','WALK','RUN','SNEAK','FACE_TARGET','OPEN_DOOR',
         'CLOSE_DOOR','OPEN_WINDOW','CLIMB_WINDOW','CLIMB_FENCE','PICKUP_ITEM','LOOT_CONTAINER','TRANSFER_ITEM','BANDAGE')
TARGETED=set(ACTIONS)-{'STOP','FOLLOW_PLAYER','LOOK_AT_PLAYER'}
FEATURES=('health','health_known','zombies','threat_known','inventory_items','inventory_known',
          'load_ratio','load_known','manual_priority','emergency_priority','failed_results','results_known',
          'profile_known','memory_known','candidate_fraction','partial_perception')
MAX_GOALS=2


def unwrap(value):
    return value.get('value') if isinstance(value,dict) and value.get('status') in ('KNOWN','PARTIAL') else None


def check_observation(obs,now):
    if not isinstance(obs,dict) or obs.get('schema_version')!=1: raise ValueError('observation_schema')
    if len(json.dumps(obs,ensure_ascii=False,allow_nan=False).encode('utf-8'))>32768: raise ValueError('observation_budget')
    for key in ('uuid','world_id','session_id','request_id','observation_id'):
        if not isinstance(obs.get(key),str) or not 0<len(obs[key])<=160: raise ValueError(key)
    if str(uuid.UUID(obs['uuid']))!=obs['uuid']: raise ValueError('uuid')
    if type(obs.get('captured_at_ms')) is not int or not 0<=now-obs['captured_at_ms']<=1500:
        raise ValueError('observation_expired')
    if type(obs.get('expires_at_ms')) is not int or not now<obs['expires_at_ms']<=obs['captured_at_ms']+1500:
        raise ValueError('observation_expired')
    route=obs.get('routing',{})
    ids=route.get('recipients',[])
    if route.get('schema_version')!=1 or route.get('world_id')!=obs['world_id'] or not isinstance(ids,list) or obs['uuid'] not in ids or len(ids)>8 or len(set(ids))!=len(ids):
        raise ValueError('recipient_binding')
    if not isinstance(obs.get('message'),str) or len(obs['message'].encode('utf-8'))>2000:
        raise ValueError('message_budget')
    if not any(c in obs['message'] for c in (':',',')): raise ValueError('recipient_required')
    for section in ('identity','profile','personal_memory'):
        value=unwrap(obs.get(section))
        if isinstance(value,dict):
            if value.get('uuid',obs['uuid'])!=obs['uuid'] or value.get('npc_id',obs['uuid'])!=obs['uuid'] or value.get('world_id',obs['world_id'])!=obs['world_id']:
                raise ValueError('private_state_binding')
    events=unwrap(obs.get('conversation_memory'))
    if isinstance(events,list):
        for event in events:
            if event.get('uuid')!=obs['uuid'] or event.get('world_id')!=obs['world_id']:raise ValueError('memory_binding')
    if not isinstance(obs.get('control'),dict): raise ValueError('control_unavailable')
    for key in ('manual_priority','emergency_priority'):
        if type(obs['control'].get(key)) is not bool: raise ValueError('control_unavailable')
    candidates=obs.get('candidates',[])
    if not isinstance(candidates,list) or len(candidates)>32: raise ValueError('candidate_budget')
    seen=set()
    for c in candidates:
        if not isinstance(c,dict) or c.get('action') not in TARGETED or c.get('uuid')!=obs['uuid'] or c.get('world_id')!=obs['world_id']:
            raise ValueError('candidate_binding')
        if c.get('observation_id')!=obs['observation_id'] or type(c.get('expires_at_ms')) is not int or c['expires_at_ms']<=now:
            raise ValueError('candidate_expired')
        if not isinstance(c.get('target_id'),str) or not 0<len(c['target_id'])<=160: raise ValueError('candidate_id')
        pair=(c['action'],c['target_id'])
        if pair in seen: raise ValueError('duplicate_candidate')
        seen.add(pair)
    return obs


def features(obs):
    health=unwrap(obs.get('health')) or {}; health=health.get('health',{})
    threat=unwrap(obs.get('threat')) or {}
    inv=unwrap(obs.get('inventory')) or {}
    results=unwrap(obs.get('action_results'))
    results=results if isinstance(results,list) else []
    def observed(v):
        return isinstance(v,dict) and v.get('known') is True and type(v.get('value')) in (float,int) and math.isfinite(v['value'])
    weight=inv.get('weight',{}); capacity=inv.get('capacity',{})
    load=observed(weight) and observed(capacity) and capacity['value']>0
    known=health.get('known') is True
    control=obs['control']
    return [max(0,min(1,health.get('value',0)/100)) if observed(health) else 0,int(known),
      min(1,max(0,threat.get('observed_zombies',0))/12),int(threat.get('known') is True),
      min(1,len(inv.get('items',[]))/128),int(obs.get('inventory',{}).get('status') in ('KNOWN','PARTIAL')),
      min(2,weight['value']/capacity['value']) if load else 0,int(load),
      int(control['manual_priority']),int(control['emergency_priority']),
      min(1,sum(r.get('state')=='FAILED' for r in results)/4),int(bool(results)),
      int(obs.get('profile',{}).get('status')=='KNOWN'),int(obs.get('personal_memory',{}).get('status')=='KNOWN'),
      len(obs.get('candidates',[]))/32,int(not (unwrap(obs.get('perception')) or {}).get('visibility',{}).get('complete',False))]


def capability_mask(obs):
    caps=unwrap(obs.get('capabilities')) or {}
    return [caps.get(a,{}).get('available') is True and caps.get(a,{}).get('support')!='UNSUPPORTED' for a in ACTIONS]


def safe_decision(prediction,obs,now,threshold=.80):
    check_observation(obs,now)
    base={k:obs[k] for k in ('uuid','world_id','session_id','request_id','observation_id','expires_at_ms')}
    base.update(schema_version=1,intents=[],decision='REQUEST_CLARIFICATION',confidence=0.0,goals=[],reason='low_confidence')
    score=prediction.get('confidence')
    if type(score) not in (float,int) or not math.isfinite(score) or not 0<=score<=1: return base
    base['confidence']=score
    if obs['control']['manual_priority'] or obs['control']['emergency_priority']:
        return dict(base,decision='WAIT',reason='priority_guard')
    if score<threshold: return base
    decision=prediction.get('decision'); intents=prediction.get('intents',[])
    if decision not in DECISIONS or not isinstance(intents,list) or any(x not in INTENTS for x in intents): return base
    base.update(decision=decision,intents=intents,reason='neural_prediction')
    goals=prediction.get('goals',[])
    if decision=='CONTINUE_GOAL':
        current=obs.get('current_goal')
        if not isinstance(current,dict) or current.get('state') not in ('RUNNING','WALKING','FOLLOWING'):
            return dict(base,decision='REQUEST_CLARIFICATION',reason='no_current_goal')
        return base
    if decision!='EXECUTE_ACTION': return base
    if not isinstance(goals,list) or not 1<=len(goals)<=MAX_GOALS: return dict(base,decision='REQUEST_CLARIFICATION',reason='goal_budget')
    mask=dict(zip(ACTIONS,capability_mask(obs)))
    validated=[]
    for index,goal in enumerate(goals):
        if not isinstance(goal,dict) or set(goal)-{'action','target_id'}: return dict(base,decision='REQUEST_CLARIFICATION',reason='goal_fields')
        action=goal.get('action'); target=goal.get('target_id')
        if not mask.get(action): return dict(base,decision='REQUEST_CLARIFICATION',reason='action_unavailable')
        if action in TARGETED:
            candidate=next((c for c in obs['candidates'] if c['action']==action and c['target_id']==target),None)
            if not candidate:
                return dict(base,decision='REQUEST_CLARIFICATION',reason='target_unavailable')
            if not isinstance(candidate.get('description'),str) or not candidate['description'].strip():
                return dict(base,decision='REQUEST_CLARIFICATION',reason='target_semantics_unknown')
        elif target is not None: return dict(base,decision='REQUEST_CLARIFICATION',reason='unexpected_target')
        validated.append({'order':index+1,'objective':action,'action':action,'parameters':{'target_id':target} if target else {}})
    return dict(base,goals=validated)


def prepare_dispatch(decision,obs,now):
    """Prepare first action only. Later objectives require a new observation/result."""
    raw={'decision':decision.get('decision'),'intents':decision.get('intents',[]),'confidence':decision.get('confidence'),
         'goals':[{'action':g['action'],**g.get('parameters',{})} for g in decision.get('goals',[])]}
    if any(decision.get(k)!=obs.get(k) for k in ('uuid','world_id','session_id','request_id','observation_id')):
        raise ValueError('decision_binding')
    validated=safe_decision(raw,obs,now)
    if validated['decision']=='CONTINUE_GOAL': return {'kind':'continue_existing','goal':copy.deepcopy(obs['current_goal'])}
    if validated['decision']=='REQUEST_DIALOGUE':
        return {'kind':'dialogue_prepared','uuid':obs['uuid'],'world_id':obs['world_id'],'verbal_only':True,'executable':False}
    if not validated['goals']: return {'kind':'no_execution','decision':validated['decision'],'reason':validated['reason']}
    first=validated['goals'][0]
    request={'schema_version':1,'uuid':obs['uuid'],'world_id':obs['world_id'],'origin':'neural','priority':0,
             'action_id':'neural:'+hashlib.sha256((obs['uuid']+obs['world_id']+obs['session_id']+obs['request_id']).encode()).hexdigest()[:32]+':1','expires_at_ms':obs['expires_at_ms'],
             'observation_id':obs['observation_id'],'action':first['action'],**first['parameters']}
    return {'kind':'action_prepared','request':request,'continuation_requires_fresh_observation':copy.deepcopy(validated['goals'][1:])}


def transition(before,decision,executed,result,after,terminal):
    if type(terminal) is not bool: raise ValueError('terminal')
    for record in (decision,executed,result,after):
        if any(record.get(k)!=before.get(k) for k in ('uuid','world_id','session_id')): raise ValueError('transition_binding')
    if decision.get('decision')=='EXECUTE_ACTION':
        if not executed.get('action_id') or executed.get('action_id')!=result.get('action_id'):raise ValueError('transition_action')
        if not decision.get('goals') or executed.get('requested_action',executed.get('action'))!=decision['goals'][0]['action']:raise ValueError('transition_action')
    if after['captured_at_ms']<before['captured_at_ms']:raise ValueError('transition_time')
    return copy.deepcopy({'schema_version':1,'observation':before,'decision':decision,'executed':executed,
                          'result':result,'next_observation':after,'terminal':terminal})
