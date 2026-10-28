"""Analyze saved predictions only: never run test inputs through a model again."""
from collections import Counter
import json
from pathlib import Path
from train_neural_v2 import OUT,read_split

def main():
    result=json.loads((OUT/'result.json').read_text(encoding='utf-8'));chosen=result['selection']['selected_experiment'];report={}
    for split in ('validation','test'):
        rows=read_split(split)
        path=OUT/chosen/'validation-predictions.json' if split=='validation' else OUT/'test-predictions.json'
        records=json.loads(path.read_text(encoding='utf-8'));errors=Counter();examples=[];slots={}
        for row,r in zip(rows,records):
            gold=r['expected'];pred=r['prediction']
            if not gold['goals']:continue
            if pred['decision']!='EXECUTE_ACTION':kind='wrong_decision'
            elif len(pred['goals'])!=len(gold['goals']):kind='wrong_goal_count'
            elif [g['action'] for g in pred['goals']]!=[g['action'] for g in gold['goals']]:kind='wrong_action_or_order'
            elif pred['goals']!=gold['goals']:kind='wrong_target'
            else:kind='exact'
            errors[kind]+=1
            for i,g in enumerate(gold['goals']):
                a=slots.setdefault(g['action'],{'support':0,'action_correct':0,'target_correct_given_action':0,'target_cases_given_action':0})
                a['support']+=1
                if i<len(pred['goals']) and pred['goals'][i]['action']==g['action']:
                    a['action_correct']+=1
                    if 'target_id' in g:
                        a['target_cases_given_action']+=1;a['target_correct_given_action']+=pred['goals'][i].get('target_id')==g['target_id']
            if kind!='exact' and not any(x['kind']==kind for x in examples):
                examples.append({'kind':kind,'message':row['observation']['message'],'expected':gold,'prediction':pred})
        report[split]={'goal_error_decomposition':dict(errors),'slot_accuracy_counts':slots,'error_examples':examples,
                       'decision_distribution':dict(Counter(r['decision'] for r in rows)),
                       'intent_distribution':dict(Counter(i for r in rows for i in r['intents']))}
    report['train_distribution']=dict(Counter(r['decision'] for r in read_split('train')))
    (OUT/'diagnostics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
