"""Explicit offline supervised training CLI. Never installs or downloads anything."""
import argparse
import copy
import json
from pathlib import Path
import random
import time

from neural_contract import ACTIONS,INTENTS,DECISIONS,FEATURES,MAX_GOALS,TARGETED,check_observation,safe_decision
from neural_data import load_data,audit
from neural_runtime import dependency_status,digest,decode,tensor_batch

def targets(rows):
    import torch
    intents=torch.zeros(len(rows),len(INTENTS)); decision=[]; counts=[]
    actions=torch.full((len(rows),MAX_GOALS),len(ACTIONS),dtype=torch.long)
    pointers=torch.full((len(rows),MAX_GOALS),-100,dtype=torch.long)
    for i,row in enumerate(rows):
        for intent in row['intents']:intents[i,INTENTS.index(intent)]=1
        decision.append(DECISIONS.index(row['decision'])); counts.append(len(row['goals']))
        for j,g in enumerate(row['goals']):
            actions[i,j]=ACTIONS.index(g['action'])
            if g['action'] in TARGETED:
                pointers[i,j]=next(k for k,c in enumerate(row['observation']['candidates']) if c['action']==g['action'] and c['target_id']==g['target_id'])
    return intents,torch.tensor(decision),torch.tensor(counts),actions,pointers

def encode_rows(rows,encoder):
    import torch
    chunks=[tensor_batch([r['observation'] for r in rows[i:i+32]],encoder) for i in range(0,len(rows),32)]
    return tuple(torch.cat([batch[j] for batch in chunks]).detach().clone() for j in range(7))

def evaluate(model,inputs,rows,details=None):
    import torch
    model.eval()
    with torch.inference_mode(): output=model(*inputs)
    predictions=decode(output,[r['observation'] for r in rows])
    if details is not None:
        details.extend({'index':i,'expected':{'intents':r['intents'],'decision':r['decision'],'goals':r['goals']},'prediction':p} for i,(r,p) in enumerate(zip(rows,predictions)))
    n=len(rows); exact=decisions=goal_correct=goal_total=multi_correct=multi_total=invalid=accepted=0
    confusion={i:{'tp':0,'fp':0,'fn':0,'tn':0} for i in INTENTS}
    decision_confusion=[[0]*len(DECISIONS) for _ in DECISIONS]
    for row,pred in zip(rows,predictions):
        exact+=set(row['intents'])==set(pred['intents']); decisions+=row['decision']==pred['decision']
        decision_confusion[DECISIONS.index(row['decision'])][DECISIONS.index(pred['decision'])]+=1
        for intent in INTENTS:
            actual=intent in row['intents']; guessed=intent in pred['intents']
            confusion[intent]['tp' if actual and guessed else 'fn' if actual else 'fp' if guessed else 'tn']+=1
        if row['goals']:
            goal_total+=1; matched=pred['decision']=='EXECUTE_ACTION' and pred['goals']==row['goals']
            goal_correct+=matched
            if len(row['goals'])>1:multi_total+=1; multi_correct+=matched
        guarded=safe_decision(pred,row['observation'],row['observation']['captured_at_ms'],threshold=0)
        if pred['decision']=='EXECUTE_ACTION' and (guarded['decision']!='EXECUTE_ACTION' or not guarded['goals']):invalid+=1
        accepted+=pred['confidence']>=.80
    return {'count':n,'intent_exact':exact/n,'decision_accuracy':decisions/n,
            'ordered_goal_count':goal_total,'ordered_goal_exact':goal_correct/max(1,goal_total),
            'multi_goal_count':multi_total,'multi_goal_exact':multi_correct/max(1,multi_total),
            'invalid_action_rate':invalid/n,'confidence_coverage':accepted/n,
            'intent_confusion':confusion,'decision_confusion':decision_confusion}

def passes(metrics):
    return metrics['count']>=20 and metrics['intent_exact']>=.80 and metrics['decision_accuracy']>=.85 and metrics['ordered_goal_exact']>=.80 and metrics['multi_goal_count']>=4 and metrics['multi_goal_exact']>=.80 and metrics['invalid_action_rate']==0 and metrics['confidence_coverage']>=.50

def train(encoder_path,output_dir,epochs=100):
    total_started=time.monotonic()
    if not all(dependency_status().values()):return {'status':'UNAVAILABLE','reason':'dependencies_unavailable','trained':False,'validated':False,'metrics':None}
    import torch
    from neural_encoder import LocalEncoder
    from neural_model import NPCPolicy
    if type(epochs) is not int or not 1<=epochs<=1000:raise ValueError('epochs_budget')
    root=Path(__file__).resolve().parent/'neural_artifacts'; output_dir=Path(output_dir).resolve()
    if not output_dir.is_relative_to(root) or output_dir==root or output_dir.exists():raise ValueError('new_workspace_output_required')
    torch.set_num_threads(2); torch.manual_seed(1729); random.seed(1729)
    data=load_data(); data_audit=audit(data)
    for rows in data.values():
        for row in rows:check_observation(row['observation'],row['observation']['captured_at_ms'])
    encoder=LocalEncoder(encoder_path)
    encoded={s:encode_rows(data[s],encoder) for s in ('train','validation')}
    y=targets(data['train']); model=NPCPolicy(); optimizer=torch.optim.AdamW(model.parameters(),lr=.002,weight_decay=.01)
    bce=torch.nn.BCEWithLogitsLoss(); ce=torch.nn.CrossEntropyLoss()
    best=None; rank=-1; started=time.monotonic(); selected_epoch=None; history=[]
    for epoch in range(epochs):
        model.train(); order=torch.randperm(len(data['train']))
        for indices in order.split(32):
            inputs=tuple(t[indices] for t in encoded['train']); labels=tuple(t[indices] for t in y)
            out=model(*inputs,teacher=labels[3])
            loss=bce(out['intents'],labels[0])+ce(out['decision'],labels[1])+ce(out['count'],labels[2])
            for j in range(MAX_GOALS):
                active=labels[2]>0
                if active.any():loss=loss+ce(out['actions'][active,j],labels[3][active,j])
                for row_index,global_index in enumerate(indices.tolist()):
                    pointer=int(labels[4][row_index,j])
                    if pointer>=0:
                        obs=data['train'][global_index]['observation']; action=ACTIONS[int(labels[3][row_index,j])]
                        valid=[k for k,c in enumerate(obs['candidates']) if c['action']==action]
                        logits=out['pointers'][row_index,j,valid].unsqueeze(0)
                        loss=loss+ce(logits,torch.tensor([valid.index(pointer)]))/len(indices)
            optimizer.zero_grad(); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(),1); optimizer.step()
        if epoch%5==0 or epoch==epochs-1:
            metrics=evaluate(model,encoded['validation'],data['validation'])
            value=metrics['decision_accuracy']+metrics['intent_exact']+metrics['ordered_goal_exact']
            history.append({'epoch':epoch+1,'selection_score':value,'metrics':metrics})
            print(json.dumps({'epoch':epoch+1,'validation_score':value}),flush=True)
            if value>rank:rank=value; best=copy.deepcopy(model.state_dict()); selected_epoch=epoch+1
    model.load_state_dict(best); model.eval()
    training_seconds=time.monotonic()-started
    output_dir.mkdir(parents=True,exist_ok=False)
    torch.save(model.state_dict(),output_dir/'weights.pt')
    selected_hash=digest(output_dir/'weights.pt')
    # Test is encoded and evaluated only after the validation-selected weights are frozen.
    encoded['test']=encode_rows(data['test'],encoder)
    metrics={}
    for split in ('validation','test'):
        details=[]; metrics[split]=evaluate(model,encoded[split],data[split],details)
        (output_dir/(split+'-predictions.json')).write_text(json.dumps(details,ensure_ascii=False,indent=2),encoding='utf-8')
    validated=all(passes(m) for m in metrics.values())
    if digest(output_dir/'weights.pt')!=selected_hash:raise RuntimeError('selected_checkpoint_changed')
    for split,rows in data.items():
        (output_dir/(split+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    manifest={'schema_version':1,'architecture':'aray_multitask_gru_v1','embedding_dim':384,'hidden':128,
       'intents':list(INTENTS),'decisions':list(DECISIONS),'actions':list(ACTIONS),'features':list(FEATURES),
       'trained':True,'validated':validated,'encoder_fingerprint':encoder.fingerprint,
       'weights_sha256':digest(output_dir/'weights.pt'),'data':data_audit,'metrics':metrics,
       'epochs':epochs,'seed':1729,'elapsed_seconds':time.monotonic()-total_started,'training_seconds':training_seconds,
       'selected_epoch':selected_epoch,'test_evaluations':1,'selection_uses_test':False,'game_validated':False}
    (output_dir/'validation-history.json').write_text(json.dumps(history,indent=2),encoding='utf-8')
    (output_dir/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'status':'TRAINED','trained':True,'validated':validated,'game_integrated':False,'metrics':metrics,'output':str(output_dir)}

def main():
    p=argparse.ArgumentParser(); p.add_argument('--encoder-path',required=True); p.add_argument('--output-dir',required=True); p.add_argument('--epochs',type=int,default=100)
    args=p.parse_args()
    result=train(args.encoder_path,args.output_dir,args.epochs); print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result.get('trained') else 2

if __name__=='__main__':raise SystemExit(main())
