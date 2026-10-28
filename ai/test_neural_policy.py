"""Policy guards/dataset/runtime tests. Real torch tests explicitly skip if absent."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

from neural_data import records,audit,load_data,observation
from neural_contract import check_observation,safe_decision,prepare_dispatch,transition,ACTIONS,INTENTS,DECISIONS,FEATURES
from neural_runtime import NeuralPolicy,verify_manifest,dependency_status,digest,compose_observation
from train_neural import train


@pytest.fixture
def obs():return observation('Carlos, pegue a bandagem e depois me siga')


def prediction(action='PICKUP_ITEM',target='synthetic:PICKUP_ITEM'):
    return {'intents':['INSTRUCTION','ACTION_REQUEST'],'decision':'EXECUTE_ACTION','confidence':.95,
            'goals':[{'action':action,**({'target_id':target} if target else {})},{'action':'FOLLOW_PLAYER'}]}


def test_dataset_real_catalog_labels_splits_and_order():
    data=load_data(); expected=records(); assert audit(data)==audit(expected)
    assert audit(data)['counts']=={'train':243,'validation':162,'test':162}
    decisions=set(); intents=set(); pairs=set(); actions=set()
    for rows in data.values():
        for row in rows:
            check_observation(row['observation'],100000)
            assert row['provenance']=='authored_supervised_scenario_not_game_experience'
            decisions.add(row['decision']); intents.update(row['intents'])
            actions.update(g['action'] for g in row['goals'])
            if len(row['goals'])==2:pairs.add(tuple(g['action'] for g in row['goals']))
            guarded=safe_decision(dict(decision=row['decision'],intents=row['intents'],goals=row['goals'],confidence=1),row['observation'],100000)
            assert guarded['decision']==row['decision']
    assert decisions==set(DECISIONS) and intents==set(INTENTS)
    assert actions==set(ACTIONS)
    assert ('PICKUP_ITEM','FOLLOW_PLAYER') in pairs and ('FOLLOW_PLAYER','PICKUP_ITEM') in pairs


def test_duplicate_phrase_across_split_rejected():
    data=records(); data['test'].append(copy.deepcopy(data['train'][0]))
    with pytest.raises(ValueError,match='split_leakage'):audit(data)


def test_multi_objective_grounded_order_and_first_action_only(obs):
    result=safe_decision(prediction(),obs,100000)
    assert [g['action'] for g in result['goals']]==['PICKUP_ITEM','FOLLOW_PLAYER']
    request=prepare_dispatch(result,obs,100000)
    assert request['request']['origin']=='neural' and request['request']['priority']==0
    assert request['request']['target_id']=='synthetic:PICKUP_ITEM'
    assert request['continuation_requires_fresh_observation'][0]['action']=='FOLLOW_PLAYER'
    assert 'x' not in request['request'] and 'source' not in request['request']


@pytest.mark.parametrize('fault',['invented_target','unsupported','unavailable','coordinates','code','too_many_goals','unexpected_target'])
def test_invalid_neural_goals_cannot_be_executed(obs,fault):
    raw=prediction()
    if fault=='invented_target':raw['goals'][0]['target_id']='invented'
    elif fault=='unsupported':raw['goals'][0]['action']='PUSH_ZOMBIE'
    elif fault=='unavailable':obs['capabilities']['value']['PICKUP_ITEM']['available']=False
    elif fault=='coordinates':raw['goals'][0]['x']=99
    elif fault=='code':raw['goals'][0]['lua']='spawn()'
    elif fault=='too_many_goals':raw['goals']*=2
    else:raw['goals'][1]['target_id']='invented'
    result=safe_decision(raw,obs,100000)
    assert result['decision']=='REQUEST_CLARIFICATION' and result['goals']==[]


@pytest.mark.parametrize('score',[.1,.79,float('nan'),float('inf'),True,-1,2])
def test_low_or_invalid_confidence_never_dispatches(obs,score):
    raw=prediction(); raw['confidence']=score
    result=safe_decision(raw,obs,100000)
    assert not result['goals'] and prepare_dispatch(result,obs,100000)['kind']=='no_execution'


@pytest.mark.parametrize('priority',['manual_priority','emergency_priority'])
def test_priorities_override_high_confidence_without_execution(obs,priority):
    obs['control'][priority]=True
    result=safe_decision(prediction(),obs,100000)
    assert result['decision']=='WAIT' and result['reason']=='priority_guard' and not result['goals']


@pytest.mark.parametrize('field',['uuid','world_id','session_id','request_id','observation_id'])
def test_decision_cannot_cross_npc_world_or_session(obs,field):
    decision=safe_decision(prediction(),obs,100000); changed=copy.deepcopy(obs)
    changed[field]='22222222-2222-4222-8222-222222222222' if field=='uuid' else 'other'
    with pytest.raises(ValueError):prepare_dispatch(decision,changed,100000)


@pytest.mark.parametrize('fault',['expired','route','no_address','candidate_world','candidate_expired','control_unknown'])
def test_observation_fail_closed_before_model_loading(obs,fault):
    if fault=='expired':obs['expires_at_ms']=99999
    elif fault=='route':obs['routing']['recipients']=[]
    elif fault=='no_address':obs['message']='pegue a bandagem'
    elif fault=='candidate_world':obs['candidates'][0]['world_id']='other'
    elif fault=='candidate_expired':obs['candidates'][0]['expires_at_ms']=99999
    else:obs['control']['emergency_priority']=None
    result=NeuralPolicy().predict(obs,100000)
    assert result['status']=='UNAVAILABLE' and result['decision']=='NO_RESPONSE' and not result['goals']


def test_no_checkpoint_no_fake_inference_or_metrics(obs,tmp_path,monkeypatch):
    service=NeuralPolicy(); assert service.predict(obs,100000)['reason']=='activation_disabled'
    enabled=NeuralPolicy(tmp_path,tmp_path,enabled=True)
    assert enabled.predict(obs,100000)['reason']=='checkpoint_missing'
    monkeypatch.setattr('train_neural.dependency_status',lambda:{'torch':False})
    result=train(tmp_path,tmp_path/'output')
    assert result=={'status':'UNAVAILABLE','reason':'dependencies_unavailable','trained':False,'validated':False,'metrics':None}
    assert not (tmp_path/'output').exists()


def manifest(directory):
    (directory/'weights.pt').write_bytes(b'test integrity sentinel, not a neural checkpoint')
    good={'count':154,'intent_exact':.9,'decision_accuracy':.9,'ordered_goal_exact':.9,'invalid_action_rate':0,
          'multi_goal_count':4,'multi_goal_exact':1,'confidence_coverage':.8}
    return {'schema_version':1,'architecture':'aray_multitask_gru_v1','validated':True,
            'intents':list(INTENTS),'decisions':list(DECISIONS),'actions':list(ACTIONS),'features':list(FEATURES),
            'embedding_dim':384,'hidden':128,'encoder_fingerprint':'0'*64,'weights_sha256':digest(directory/'weights.pt'),
            'metrics':{'validation':good,'test':copy.deepcopy(good)}}


@pytest.mark.parametrize('fault',['unvalidated','labels','integrity','metrics','nonfinite','encoder','dimensions'])
def test_checkpoint_manifest_guard_before_tensor_deserialization(tmp_path,fault):
    m=manifest(tmp_path)
    if fault=='unvalidated':m['validated']=False
    elif fault=='labels':m['actions'].append('PUSH_ZOMBIE')
    elif fault=='integrity':m['weights_sha256']='f'*64
    elif fault=='metrics':m['metrics']['test']['decision_accuracy']=.1
    elif fault=='nonfinite':m['metrics']['test']['intent_exact']=float('nan')
    elif fault=='encoder':m['encoder_fingerprint']='wrong'
    else:m['embedding_dim']=12
    (tmp_path/'manifest.json').write_text(json.dumps(m),encoding='utf-8')
    with pytest.raises(ValueError):verify_manifest(tmp_path)


def test_continue_is_not_a_new_walk_and_dialogue_not_an_action(obs):
    obs['current_goal']={'state':'WALKING','action_id':'existing'}
    for choice in ('CONTINUE_GOAL','REQUEST_DIALOGUE','WAIT','NO_RESPONSE','REQUEST_CLARIFICATION'):
        decision=safe_decision({'decision':choice,'intents':['INFORMATION'],'confidence':.99},obs,100000)
        result=prepare_dispatch(decision,obs,100000)
        assert result['kind']!='action_prepared'


def test_transition_no_rewards_and_uuid_isolation(obs):
    decision=safe_decision(prediction(),obs,100000)
    base={k:obs[k] for k in ('uuid','world_id','session_id')}
    executed=dict(base,action_id='a',action='PICKUP_ITEM'); result=dict(base,action_id='a',result='COMPLETED')
    record=transition(obs,decision,executed,result,obs,False)
    assert set(record)=={'schema_version','observation','decision','executed','result','next_observation','terminal'}
    result['uuid']='other'
    with pytest.raises(ValueError):transition(obs,decision,executed,result,obs,False)


def test_compose_trusted_snapshots_never_invents_target_description(obs):
    agent={'uuid':obs['uuid'],'world_id':obs['world_id'],'observation_id':obs['observation_id'],
           'runtime':{'control':obs['control']},'expires_at_ms':obs['expires_at_ms'],
           'candidates':[{k:v for k,v in obs['candidates'][0].items() if k!='description'}]}
    out=compose_observation(obs,agent)
    assert 'description' not in out['candidates'][0] and out['uuid']==obs['uuid']


def test_target_without_observed_semantics_is_not_invented(obs):
    next(c for c in obs['candidates'] if c['action']=='PICKUP_ITEM').pop('description')
    result=safe_decision(prediction(),obs,100000)
    assert result['decision']=='REQUEST_CLARIFICATION' and result['reason']=='target_semantics_unknown'


@pytest.mark.parametrize('section',['identity','personal_memory','conversation_memory'])
def test_other_npc_private_data_rejected(obs,section):
    foreign={'uuid':'22222222-2222-4222-8222-222222222222','world_id':obs['world_id'],'text':'private'}
    obs[section]={'status':'KNOWN','value':[foreign] if section=='conversation_memory' else foreign}
    assert NeuralPolicy().predict(obs,100000)['reason'] in ('private_state_binding','memory_binding')


def test_transition_mismatched_action_rejected(obs):
    decision=safe_decision(prediction(),obs,100000)
    base={k:obs[k] for k in ('uuid','world_id','session_id')}
    with pytest.raises(ValueError,match='transition_action'):
        transition(obs,decision,dict(base,action_id='a',action='PICKUP_ITEM'),dict(base,action_id='b'),obs,False)


@pytest.mark.skipif(importlib.util.find_spec('torch') is None,reason='PyTorch CPU absent; installation not authorized')
def test_real_torch_gradient_and_ordered_decoder():
    # Tensor mechanics only, not a semantic accuracy benchmark or pretrained embeddings.
    import torch
    from neural_model import NPCPolicy
    torch.manual_seed(71); model=NPCPolicy(); model.eval()
    args=[torch.randn(2,384) for _ in range(4)]+[torch.zeros(2,len(FEATURES)),torch.ones(2,len(ACTIONS)),torch.randn(2,32,384+len(ACTIONS))]
    teacher=torch.tensor([[0,1],[1,0]])
    output=model(*args,teacher=teacher)
    assert output['intents'].shape==(2,len(INTENTS)) and output['actions'].shape==(2,2,len(ACTIONS)+1)
    assert output['pointers'].shape==(2,2,32)
    loss=output['decision'].square().mean()+output['actions'].square().mean()
    loss.backward()
    assert model.fusion[0].weight.grad.abs().sum()>0 and model.decoder.weight_hh.grad.abs().sum()>0
    old=model.fusion[0].weight.detach().clone(); torch.optim.SGD(model.parameters(),lr=.01).step()
    assert not torch.equal(old,model.fusion[0].weight.detach())
