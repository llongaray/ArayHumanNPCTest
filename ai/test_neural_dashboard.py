"""Offline dashboard/CLI contracts. No listening socket or game service."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import pytest

from neural_trainer import store
from neural_trainer.lab import recipients,scenario,Laboratory,catalog
from neural_trainer.web import create_app

@pytest.fixture
def isolated_store(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'ARTIFACTS',tmp_path/'artifacts');monkeypatch.setattr(store,'RUNS',tmp_path/'artifacts'/'manual-runs')
    return tmp_path

def test_auto_run_ids_and_directories_never_collide(isolated_store):
    with ThreadPoolExecutor(max_workers=4) as pool:created=list(pool.map(lambda _:store.create_run(),range(20)))
    assert len({d['run_id'] for _,d in created})==20
    assert len({str(p) for p,_ in created})==20

def test_explicit_existing_output_is_preserved(isolated_store):
    p=store.ARTIFACTS/'chosen';store.create_run(p);(p/'sentinel').write_text('preserve')
    with pytest.raises(FileExistsError):store.create_run(p)
    assert (p/'sentinel').read_text()=='preserve'

def test_output_cannot_escape_artifacts(isolated_store):
    with pytest.raises(ValueError):store.create_run(isolated_store/'outside')

def test_atomic_states_and_partial_journal_reads(isolated_store):
    path,d=store.create_run();journal=store.Journal(path,d)
    journal.emit(status='training',epoch=1,train_loss=.3)
    journal.emit(status='completed',epoch=2)
    with (path/'metrics.jsonl').open('a') as f:f.write('{"partial":')
    assert store.read_json(path/'state.json')['epoch']==2
    assert len(store.history(path))==2
    assert store.runs()[0]['status']=='completed'

def test_dead_training_process_is_shown_interrupted(isolated_store):
    path,d=store.create_run();store.atomic_json(path/'state.json',dict(d,status='training',pid=99999999))
    assert store.runs()[0]['status']=='interrupted'

@pytest.mark.parametrize('text,expected',[
    ('Venha aqui',[]),('Carlos, me siga',['Carlos']),('Tânia: saúde?',['Tania']),
    ('Carlos e Tania, vamos',['Carlos','Tania']),('Vocês, aguardem',['Carlos','Tania']),
    ('Carlos e Fulano, venha',[]),('Carlose, venha',[]),('Carlos, <script>alert(1)</script>',['Carlos'])])
def test_lab_recipient_gate(text,expected):assert recipients(text)==expected

def test_lab_scenarios_isolate_uuid_world_and_candidates():
    a=scenario('Carlos, siga','Carlos','calm');b=scenario('Tania, siga','Tania','missing')
    assert a['uuid']!=b['uuid'] and a['world_id'].startswith('SYNTHETIC/')
    assert all(c['uuid']==a['uuid'] for c in a['candidates'])
    assert not any(c['action']=='PICKUP_ITEM' for c in b['candidates'])

def test_flask_routes_no_start_or_shell_and_local_only(isolated_store):
    app=create_app();c=app.test_client()
    assert c.get('/').status_code==200
    assert c.get('/api/runs').json==[]
    assert c.get('/api/runs',environ_base={'REMOTE_ADDR':'192.168.1.3'}).status_code==403
    assert c.get('/api/runs',headers={'Host':'evil.example'}).status_code==400
    assert c.post('/api/train').status_code in (403,404)
    assert c.post('/api/laboratory',json={'message':'Carlos, oi'}).status_code==403
    headers={'X-Neural-Token':app.config['LAB_TOKEN'],'Origin':'http://evil.example'}
    assert c.post('/api/laboratory',json={},headers=headers).status_code==403

def test_lab_no_recipient_does_not_load_weights():
    lab=Laboratory();r=lab.predict('venha aqui','not-a-checkpoint','calm')
    assert r['blocked']=='explicit_recipient_required' and lab.model is None

def test_flask_rejects_unknown_fields_and_paths():
    app=create_app();c=app.test_client();h={'X-Neural-Token':app.config['LAB_TOKEN']}
    assert c.post('/api/laboratory',json={'command':'del'},headers=h).status_code==400
    assert c.get('/api/runs/not-an-id').status_code==404
    assert c.get('/api/runs/../../windows').status_code==404

def test_lab_real_cpu_weights_and_guards_without_execution():
    entries=catalog()
    entry=next((e for e in entries if e['name']=='3c5b2/baseline'),None)
    if entry is None:pytest.skip('optional local checkpoint absent')
    lab=Laboratory();result=lab.predict('Carlos, como está sua saúde?',entry['id'],'emergency')
    p=result['predictions'][0]
    assert p['embedding']['dimension']==384 and abs(p['embedding']['norm']-1)<.001
    assert p['guarded']['decision']=='WAIT' and p['guarded']['goals']==[]
    assert p['execution']=='DISABLED_SYNTHETIC_ONLY'
    assert result['checkpoint_validated'] is False

def test_cli_rejects_invalid_training_parameters():
    from neural_trainer.cli import main
    with pytest.raises(SystemExit):main(['train','--epochs','0'])
    with pytest.raises(SystemExit):main(['train','--learning-rate','nan'])

def test_manual_training_never_loads_final_test(monkeypatch):
    # Exercise orchestration/interruption with no encoder/model or file-side test access.
    from neural_trainer import cli
    import train_neural_v2 as v2
    import neural_encoder,neural_inputs_v2
    calls=[]
    def split(name):
        calls.append(name)
        assert name in ('train','validation')
        return []
    monkeypatch.setattr(v2,'read_split',split)
    monkeypatch.setattr(neural_encoder,'LocalEncoder',lambda _:type('E',(),{'fingerprint':'f'*64})())
    monkeypatch.setattr(neural_inputs_v2,'encode_rows_v2',lambda r,e:())
    def interrupted(*a,**kw):raise KeyboardInterrupt()
    monkeypatch.setattr(v2,'experiment',interrupted)
    # Store redirects apply before an explicit directory is allocated.
    import tempfile
    with tempfile.TemporaryDirectory() as temp:
        monkeypatch.setattr(store,'ARTIFACTS',Path(temp));monkeypatch.setattr(store,'RUNS',Path(temp)/'runs')
        args=argparse.Namespace(output_dir=None,variant='baseline',epochs=1,batch_size=32,learning_rate=.002,seed=1729,encoder_path='unused')
        assert cli.train(args)==130
        assert store.runs()[0]['status']=='interrupted'
    assert calls==['train','validation']
