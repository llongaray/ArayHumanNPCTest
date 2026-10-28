"""Manual PowerShell-facing CLI. Browser has no training/command endpoints."""
import argparse
import copy
import json
import math
import os
from pathlib import Path
import traceback
from . import AI
from .store import create_run,Journal,atomic_json,runs,ARTIFACTS

ENCODER=AI/'neural_models'/'paraphrase-multilingual-MiniLM-L12-v2'/'e8f8c211226b894fcb81acc59f3b34ba3efd5f42'

def train(args):
    import torch
    from neural_encoder import LocalEncoder
    from neural_runtime import digest
    from neural_inputs_v2 import encode_rows_v2
    from train_neural_v2 import CONFIGS,GATES,DATA,read_split,experiment
    torch.set_num_threads(2);os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    path,identity=create_run(args.output_dir);journal=Journal(path,identity)
    config=copy.deepcopy(next(c for c in CONFIGS if c['name']==args.variant));config['epochs']=args.epochs
    try:
        journal.emit(status='waiting',stage='loading',architecture='aray_multitask_gru_v1',model_version=2,
                     dataset='supervised-v2/train+validation',total_epochs=args.epochs,variant=args.variant,
                     validated=False,test_evaluations=0)
        protocol={'schema_version':3,'run_id':identity['run_id'],'config':config,'epochs':args.epochs,'batch_size':args.batch_size,
                  'learning_rate':args.learning_rate,'seed':args.seed,'gates':GATES,'test_policy':'NEVER_READ_OR_EVALUATE_TEST',
                  'dataset_files':{s:digest(DATA/(s+'.jsonl')) for s in ('train','validation')},
                  'source_hashes':{n:digest(AI/n) for n in ('train_neural_v2.py','neural_model.py','neural_inputs_v2.py')},
                  'encoder_path':str(Path(args.encoder_path).resolve()),'game_integrated':False}
        atomic_json(path/'protocol.json',protocol)
        encoder=LocalEncoder(args.encoder_path)
        rows={s:read_split(s) for s in ('train','validation')}
        encoded={s:encode_rows_v2(r,encoder) for s,r in rows.items()}
        journal.emit(status='training',stage='optimization',encoder_fingerprint=encoder.fingerprint)
        def update(**values):journal.emit(status='training',stage='optimization',**values)
        result=experiment(config,encoded,rows,output_root=path,seed=args.seed,batch_size=args.batch_size,
                          learning_rate=args.learning_rate,observer=update)
        result.update(encoder_fingerprint=encoder.fingerprint,run_id=identity['run_id'],dataset='supervised-v2',
                      test_policy='not_evaluated_consumed_test',validated=False)
        atomic_json(path/args.variant/'manifest.json',result)
        atomic_json(path/'summary.json',result)
        journal.emit(status='completed',stage='finished',best_epoch=result['selected_epoch'],best_metrics=result['validation'],
                     best_checkpoint=str(path/args.variant/'weights.pt'),checkpoint_manifest=str(path/args.variant/'manifest.json'),
                     validation_gate_failures=__import__('train_neural_v2').gate_result(result['validation']),
                     validated=False,approval='EXPERIMENTAL_TEST_NOT_EVALUATED',eta_seconds=0)
        atomic_json(path/'hashes.json',{str(p.relative_to(path)):digest(p) for p in path.rglob('*') if p.is_file() and p.name!='hashes.json'})
        print(json.dumps({'run_id':identity['run_id'],'path':str(path),'status':'completed','validated':False,'test_evaluations':0},indent=2))
        return 0
    except KeyboardInterrupt:
        journal.emit(status='interrupted',stage='stopped',reason='Ctrl+C',eta_seconds=None);return 130
    except Exception as exc:
        (path/'error.log').write_text(traceback.format_exc(),encoding='utf-8')
        journal.emit(status='failed',stage='failed',error=str(exc),eta_seconds=None);raise

def main(argv=None):
    p=argparse.ArgumentParser(description='Treino neural offline e painel local; nenhuma ação no jogo.')
    sub=p.add_subparsers(dest='command',required=True)
    t=sub.add_parser('train');t.add_argument('--encoder-path',default=str(ENCODER));t.add_argument('--output-dir')
    t.add_argument('--epochs',type=int,default=150);t.add_argument('--batch-size',type=int,default=32)
    t.add_argument('--learning-rate',type=float,default=.002);t.add_argument('--seed',type=int,default=1729)
    t.add_argument('--variant',choices=('baseline','balanced_sequence'),default='baseline')
    d=sub.add_parser('dashboard');d.add_argument('--port',type=int,default=8766)
    sub.add_parser('status');sub.add_parser('checkpoints');sub.add_parser('compare')
    args=p.parse_args(argv)
    if args.command=='train':
        if not 1<=args.epochs<=10000 or not 1<=args.batch_size<=256 or not math.isfinite(args.learning_rate) or not 0<args.learning_rate<=1 or not 0<=args.seed<2**32:
            p.error('epochs 1..10000; batch 1..256; learning rate (0,1]; seed uint32')
        return train(args)
    if args.command=='dashboard':
        if not 1024<=args.port<=65535:p.error('port 1024..65535')
        from .web import create_app
        create_app().run(host='127.0.0.1',port=args.port,debug=False,use_reloader=False)
        return 0
    if args.command=='status':print(json.dumps(runs(),ensure_ascii=False,indent=2))
    else:
        from .lab import catalog
        print(json.dumps(catalog(),ensure_ascii=False,indent=2))
    return 0
