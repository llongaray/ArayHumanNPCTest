"""Reusable v2 training components and safe manual CLI (validation only).

No game integration. Consumed final tests are never evaluated by this entry point.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import random
import time

from neural_contract import ACTIONS,INTENTS,DECISIONS,TARGETED,safe_decision
from neural_runtime import digest,decode
from neural_data_v2 import audit
from train_neural import targets,evaluate,passes
from neural_inputs_v2 import encode_rows_v2 as encode_rows

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'neural_artifacts'/'3c5b2'
DATA=ROOT/'neural_supervised_data_v2'
CONFIGS=[{'name':'baseline','epochs':150,'weighted':False,'scheduled':False,'sequence_weight':1.,'pointer_weight':1.},
         {'name':'balanced_sequence','epochs':150,'weighted':True,'scheduled':True,'sequence_weight':2.,'pointer_weight':2.}]
GATES={'intent_exact':.8,'decision_accuracy':.85,'ordered_goal_exact':.8,'multi_goal_exact':.8,
       'invalid_action_rate':0.,'confidence_coverage':.5,'multi_goal_count':40,'per_intent_f1':.8,
       'per_intent_recall':.8,'per_intent_support':20,'per_decision_recall':.8,'per_action_exact':.8,'per_action_support':3}

def read_split(split):
    return [json.loads(x) for x in (DATA/(split+'.jsonl')).read_text(encoding='utf-8').splitlines()]

def detailed_metrics(rows,records,base):
    result=copy.deepcopy(base); classes={}; per_action={}; types={}
    for label in INTENTS:
        c=base['intent_confusion'][label];tp,fp,fn=c['tp'],c['fp'],c['fn']
        classes[label]={'support':tp+fn,'precision':tp/max(1,tp+fp),'recall':tp/max(1,tp+fn),'f1':2*tp/max(1,2*tp+fp+fn)}
    for label in DECISIONS:
        selected=[r for r in records if r['expected']['decision']==label]
        classes['decision/'+label]={'support':len(selected),'recall':sum(r['prediction']['decision']==label for r in selected)/max(1,len(selected))}
    for label in ACTIONS:
        selected=[r for r in records if any(g['action']==label for g in r['expected']['goals'])]
        per_action[label]={'support':len(selected),'exact':sum(r['prediction']['decision']=='EXECUTE_ACTION' and r['prediction']['goals']==r['expected']['goals'] for r in selected)/max(1,len(selected))}
    for kind in ('single','compound'):
        selected=[r for r in records if len(r['expected']['goals'])==(1 if kind=='single' else 2)]
        types[kind]={'support':len(selected),'exact':sum(r['prediction']['decision']=='EXECUTE_ACTION' and r['prediction']['goals']==r['expected']['goals'] for r in selected)/max(1,len(selected))}
    high=[r for r in records if r['prediction']['confidence']>=.8]
    result.update(per_class=classes,per_action=per_action,goal_types=types,
                  high_confidence_decisions=dict(Counter(r['prediction']['decision'] for r in high)),
                  high_confidence_decision_accuracy=sum(r['prediction']['decision']==r['expected']['decision'] for r in high)/max(1,len(high)))
    return result

def gate_result(metrics):
    failures=[]
    if not passes(metrics):failures.append('original_gates')
    if metrics['multi_goal_count']<GATES['multi_goal_count']:failures.append('compound_support')
    for label in INTENTS:
        m=metrics['per_class'][label]
        for key,gate in (('support','per_intent_support'),('recall','per_intent_recall'),('f1','per_intent_f1')):
            if m[key]<GATES[gate]:failures.append(label+'/'+key)
    for label in DECISIONS:
        if metrics['per_class']['decision/'+label]['recall']<GATES['per_decision_recall']:failures.append(label+'/recall')
    for label,m in metrics['per_action'].items():
        if m['support']<GATES['per_action_support'] or m['exact']<GATES['per_action_exact']:failures.append(label+'/exact')
    return failures

def eval_details(model,inputs,rows):
    records=[];metrics=evaluate(model,inputs,rows,records)
    return detailed_metrics(rows,records,metrics),records

def selection_score(m):
    # Fixed before experiments; each head/order and minority intent matters.
    return m['decision_accuracy']+m['intent_exact']+m['ordered_goal_exact']+m['multi_goal_exact']+sum(m['per_class'][x]['f1'] for x in INTENTS)/len(INTENTS)-m['invalid_action_rate']

def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def experiment(config,encoded,rows,*,output_root=None,seed=1729,batch_size=32,learning_rate=.002,observer=None):
    import torch
    from neural_model import NPCPolicy
    torch.manual_seed(seed);random.seed(seed)
    folder=(Path(output_root) if output_root is not None else OUT)/config['name'];folder.mkdir(exist_ok=False)
    model=NPCPolicy();y=targets(rows['train']); opt=torch.optim.AdamW(model.parameters(),lr=learning_rate,weight_decay=.01)
    counts=torch.bincount(y[1],minlength=len(DECISIONS)).float()
    weights=(len(rows['train'])/(len(DECISIONS)*counts)).clamp(max=5) if config['weighted'] else None
    positives=y[0].sum(0);pos_weight=((len(rows['train'])-positives)/positives).clamp(.2,10) if config['weighted'] else None
    bce=torch.nn.BCEWithLogitsLoss(pos_weight=pos_weight);ce=torch.nn.CrossEntropyLoss();dce=torch.nn.CrossEntropyLoss(weight=weights)
    rank=-float('inf');history=[];start=time.monotonic();best=None;selected=None
    validation_targets=targets(rows['validation'])
    def loss_for(out,labels,indices,split):
        loss=bce(out['intents'],labels[0])+dce(out['decision'],labels[1])+ce(out['count'],labels[2])
        pointers=[]
        for j in range(2):
            active=labels[2]>0
            if active.any():loss=loss+config['sequence_weight']*ce(out['actions'][active,j],labels[3][active,j])
            for bi,global_id in enumerate(indices.tolist()):
                pointer=int(labels[4][bi,j])
                if pointer<0:continue
                obs=rows[split][global_id]['observation'];action=ACTIONS[int(labels[3][bi,j])]
                valid=[k for k,c in enumerate(obs['candidates']) if c['action']==action]
                pointers.append(ce(out['pointers'][bi,j,valid].unsqueeze(0),torch.tensor([valid.index(pointer)])))
        if pointers:loss=loss+config['pointer_weight']*torch.stack(pointers).sum()/(len(pointers) if config['weighted'] else len(indices))
        return loss
    for epoch in range(config['epochs']):
        model.train();epoch_loss=0
        for ids in torch.randperm(len(rows['train'])).split(batch_size):
            inputs=tuple(x[ids] for x in encoded['train']);labels=tuple(x[ids] for x in y)
            teacher=labels[3] if not config['scheduled'] or epoch<20 or random.random()<.5 else None
            out=model(*inputs,teacher=teacher)
            loss=loss_for(out,labels,ids,'train')
            if not torch.isfinite(loss):raise ValueError('nonfinite_training_loss')
            epoch_loss+=float(loss.detach())*len(ids)
            opt.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1);opt.step()
        if observer is not None or epoch%10==0 or epoch==config['epochs']-1:
            m,_=eval_details(model,encoded['validation'],rows['validation']);score=selection_score(m)
            validation_loss=None
            if observer is not None:
                with torch.inference_mode():
                    val_loss=0
                    for ids in torch.arange(len(rows['validation'])).split(batch_size):
                        inp=tuple(x[ids] for x in encoded['validation']);labels=tuple(x[ids] for x in validation_targets)
                        val_loss+=float(loss_for(model(*inp),labels,ids,'validation'))*len(ids)
                    validation_loss=val_loss/len(rows['validation'])
                    if not __import__('math').isfinite(validation_loss):raise ValueError('nonfinite_validation_loss')
            history.append({'epoch':epoch+1,'score':score,'metrics':m,'train_loss':epoch_loss/len(rows['train']),'validation_loss':validation_loss})
            print(json.dumps({'experiment':config['name'],'epoch':epoch+1,'score':score,'decisions':m['decision_accuracy'],'goals':m['ordered_goal_exact']}),flush=True)
            if score>rank:
                rank=score;best=copy.deepcopy(model.state_dict());selected=epoch+1
                if observer is not None:
                    checkpoint=folder/f'checkpoint-epoch-{selected:05d}.pt'
                    torch.save(best,checkpoint)
            if observer is not None:
                observer(epoch=epoch+1,total_epochs=config['epochs'],metrics=m,train_loss=epoch_loss/len(rows['train']),
                         validation_loss=validation_loss,learning_rate=learning_rate,best_epoch=selected,best_score=rank,
                         best_checkpoint=str(folder/f'checkpoint-epoch-{selected:05d}.pt'),
                         eta_seconds=(time.monotonic()-start)/(epoch+1)*(config['epochs']-epoch-1),validation_gate_failures=gate_result(m))
    model.load_state_dict(best);model.eval()
    torch.save(best,folder/'weights.pt');metrics,records=eval_details(model,encoded['validation'],rows['validation'])
    # Audit teacher forcing gap ONLY on validation; no test is loaded here.
    with torch.inference_mode():
        oracle=decode(model(*encoded['validation'],teacher=targets(rows['validation'])[3]),[r['observation'] for r in rows['validation']])
    gap={'autoregressive_exact':metrics['ordered_goal_exact'],'teacher_forced_exact':sum(p['decision']=='EXECUTE_ACTION' and p['goals']==r['goals'] for p,r in zip(oracle,rows['validation']) if r['goals'])/max(1,sum(bool(r['goals']) for r in rows['validation']))}
    manifest={'schema_version':2,'architecture':'aray_multitask_gru_v1','trained':True,'validated':False,'config':config,
              'seed':seed,'batch_size':batch_size,'learning_rate':learning_rate,'selected_epoch':selected,'selection_score':rank,'weights_sha256':digest(folder/'weights.pt'),
              'validation':metrics,'teacher_forcing_diagnostic':gap,'seconds':time.monotonic()-start,'parameter_count':sum(p.numel() for p in model.parameters()),'test_evaluations':0,'game_integrated':False}
    save(folder/'manifest.json',manifest);save(folder/'validation-predictions.json',records);save(folder/'history.json',history)
    return manifest

def main():
    # Legacy entry point now uses isolated manual runs; never repeats the consumed test.
    import sys
    from neural_trainer.cli import main as trainer_main
    return trainer_main(['train',*sys.argv[1:]])

if __name__=='__main__':raise SystemExit(main())
