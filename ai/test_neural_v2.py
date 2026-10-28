"""Contract/alignment tests, not evidence of semantic model accuracy."""
import copy
import hashlib
import json
from pathlib import Path
import pytest

from neural_data_v2 import records,audit
from neural_contract import ACTIONS,TARGETED,safe_decision
from neural_inputs_v2 import compact_value
from neural_runtime import decode
from train_neural import targets
from train_neural_v2 import detailed_metrics,gate_result

@pytest.fixture(scope='module')
def corpus():return records()

def test_v2_split_audit_and_compound_pair_holdout(corpus):
    result=audit(corpus)
    assert result['counts']=={'train':792,'validation':556,'test':572}
    families={s:{r['phrase_family'] for r in rows} for s,rows in corpus.items()}
    assert not families['train']&families['test'] and not families['validation']&families['test']
    assert all(sum(len(r['goals'])==2 for r in rows)>=40 for rows in corpus.values())

def test_reversed_pair_stays_in_same_partition(corpus):
    seen={}
    for s,rows in corpus.items():
        for r in rows:
            if r['phrase_family'].startswith('compound/'):
                seen.setdefault(r['phrase_family'],set()).add(s)
    assert all(len(s)==1 for s in seen.values())

def test_audit_rejects_leaked_family(corpus):
    broken={s:list(rows) for s,rows in corpus.items()}
    broken['test'].append(corpus['train'][0])
    with pytest.raises(ValueError,match='leakage'):audit(broken)

def test_every_label_passes_same_guards_as_runtime(corpus):
    for rows in corpus.values():
        for row in rows:
            obs=row['observation'];pred={k:row[k] for k in ('decision','goals','intents')}
            result=safe_decision(dict(pred,confidence=1),obs,obs['captured_at_ms'])
            assert result['decision']==row['decision']
            if row['goals']:assert len(result['goals'])==len(row['goals'])

def test_each_rare_intent_has_support(corpus):
    for rows in corpus.values():
        for label in ('CONVERSATION','QUESTION','INFORMATION','NO_RESPONSE'):
            assert sum(label in r['intents'] for r in rows)>=40

def test_action_target_alignment_survives_candidate_reordering(corpus):
    import torch
    rows=[copy.deepcopy(r) for r in corpus['train'] if len(r['goals'])==2][:16]
    for r in rows:r['observation']['candidates'].reverse()
    _,decisions,counts,actions,pointers=targets(rows)
    n=len(rows)
    logits={'intents':torch.full((n,6),-20.),'decision':torch.full((n,6),-20.),'count':torch.full((n,3),-20.),
            'actions':torch.full((n,2,17),-20.),'pointers':torch.full((n,2,32),-20.)}
    for i,row in enumerate(rows):
        logits['decision'][i,decisions[i]]=20;logits['count'][i,counts[i]]=20
        for j in range(2):
            logits['actions'][i,j,actions[i,j]]=20
            if pointers[i,j]>=0:logits['pointers'][i,j,pointers[i,j]]=20
    predictions=decode(logits,[r['observation'] for r in rows])
    assert all(p['goals']==r['goals'] for p,r in zip(predictions,rows))

def test_compaction_preserves_valid_json_and_source():
    # Token counter stub for algorithmic budget tests only; no fake embedding.
    class Tokenizer:
        def __call__(self,text,**kwargs):return {'input_ids':list(text)}
    source={'items':['a'*60,'b'*60],'complete':True};before=copy.deepcopy(source)
    value,partial=compact_value(source,Tokenizer(),60)
    assert source==before and partial
    assert isinstance(json.loads(json.dumps(value)),dict)
    assert len(json.dumps({'partial':partial,'value':value},separators=(',',':')))<=60

def test_previous_checkpoint_corpus_and_metrics_unchanged():
    root=Path(__file__).parent
    hashes=json.loads((root/'neural_experiments_v2'/'previous-artifacts.json').read_text(encoding='utf-8'))
    previous=root/'neural_artifacts'/'3c5b1-seed1729'
    assert all(hashlib.sha256((previous/p).read_bytes()).hexdigest()==h for p,h in hashes.items())

def test_safety_priority_is_not_changed_by_v2(corpus):
    row=next(r for r in corpus['train'] if r['variant']=='emergency')
    obs=row['observation']
    result=safe_decision({'decision':'EXECUTE_ACTION','intents':['ACTION_REQUEST'],'goals':[{'action':'FOLLOW_PLAYER'}],'confidence':1},obs,obs['captured_at_ms'])
    assert result['decision']=='WAIT' and result['goals']==[]

def test_unsupported_action_remains_rejected(corpus):
    row=next(r for r in corpus['train'] if r['variant']=='normal');obs=row['observation']
    for a in ('PUSH_ZOMBIE','CLIMB_STAIRS'):
        result=safe_decision({'decision':'EXECUTE_ACTION','intents':['ACTION_REQUEST'],'goals':[{'action':a}],'confidence':1},obs,obs['captured_at_ms'])
        assert result['decision']!='EXECUTE_ACTION'

def test_new_gates_reject_collapsed_rare_class():
    from neural_contract import INTENTS,DECISIONS
    metrics={'count':200,'intent_exact':1.,'decision_accuracy':1.,'ordered_goal_exact':1.,'multi_goal_count':80,
             'multi_goal_exact':1.,'invalid_action_rate':0.,'confidence_coverage':1.,
             'per_class':{label:{'support':40,'recall':1.,'f1':1.} for label in INTENTS},
             'per_action':{a:{'support':20,'exact':1.} for a in ACTIONS}}
    metrics['per_class'].update({'decision/'+d:{'support':40,'recall':1.} for d in DECISIONS})
    assert gate_result(metrics)==[]
    metrics['per_class']['INFORMATION']['recall']=0
    assert 'INFORMATION/recall' in gate_result(metrics)

def test_real_minilm_compaction_keeps_numeric_observations(corpus):
    import torch
    from neural_encoder import LocalEncoder
    from neural_inputs_v2 import tensor_batch_v2
    from neural_contract import features
    path=Path(__file__).parent/'neural_models'/'paraphrase-multilingual-MiniLM-L12-v2'/'e8f8c211226b894fcb81acc59f3b34ba3efd5f42'
    if not path.is_dir():pytest.skip('optional local MiniLM unavailable')
    torch.set_num_threads(2);encoder=LocalEncoder(path)
    obs=copy.deepcopy(corpus['train'][0]['observation'])
    obs['inventory']['value']['items']=[{'full_type':'Base.Bandage'}]*12
    before=copy.deepcopy(obs)
    batch=tensor_batch_v2([obs],encoder)
    assert obs==before and batch[0].shape==(1,384)
    assert torch.allclose(batch[4],torch.tensor([features(obs)],dtype=torch.float32))
