"""Per-run immutable identity, atomic snapshots and append-only metric journal."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import time
import uuid
from . import AI

ARTIFACTS=AI/'neural_artifacts'
RUNS=ARTIFACTS/'manual-runs'

def atomic_json(path,value):
    path=Path(path);tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with tmp.open('x',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,allow_nan=False);stream.flush();os.fsync(stream.fileno())
        for attempt in range(8):
            try:os.replace(tmp,path);break
            except PermissionError:
                if attempt==7:raise
                time.sleep(.01*(attempt+1))
    finally:
        if tmp.exists():tmp.unlink()

def read_json(path,default=None):
    try:
        if Path(path).stat().st_size>8*1024*1024:return default
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError):return default

def create_run(output_dir=None):
    RUNS.mkdir(parents=True,exist_ok=True)
    if output_dir:
        path=Path(output_dir).resolve()
        if not path.is_relative_to(ARTIFACTS.resolve()) or path==ARTIFACTS.resolve():raise ValueError('output_dir_must_be_inside_ai_neural_artifacts')
        # No implicit deletion, resume or overwriting of an existing directory.
        path.mkdir(parents=True,exist_ok=False)
    else:
        for _ in range(10):
            path=RUNS/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex)
            try:path.mkdir(exist_ok=False);break
            except FileExistsError:continue
        else:raise ValueError('run_id_collision')
    run_id=uuid.uuid4().hex
    descriptor={'run_id':run_id,'path':str(path),'created_at':time.time(),'pid':os.getpid()}
    atomic_json(path/'run.json',descriptor)
    # Registry permits an explicit directory under artifacts without scanning the map/disk.
    atomic_json(RUNS/(run_id+'.json'),descriptor)
    return path,descriptor

class Journal:
    def __init__(self,path,descriptor):
        self.path=path;self.state=dict(descriptor,status='waiting',schema_version=1,epoch=0);self.started=time.monotonic()
        import psutil
        self.process=psutil.Process();self.state['process_created_at']=self.process.create_time();self.process.cpu_percent()
    def emit(self,**values):
        self.state.update(values);self.state['elapsed_seconds']=time.monotonic()-self.started
        self.state['updated_at']=time.time();self.state['cpu_percent']=self.process.cpu_percent();self.state['ram_bytes']=self.process.memory_info().rss
        self.state['cpu_percent_definition']='process; may exceed 100% across cores'
        event=dict(self.state)
        with (self.path/'metrics.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(event,ensure_ascii=False,allow_nan=False)+'\n');stream.flush()
        atomic_json(self.path/'state.json',self.state)

def history(path,limit=1500):
    # Ignore an incomplete trailing write; no reader lock blocks the trainer.
    try:
        with (Path(path)/'metrics.jsonl').open('rb') as stream:
            stream.seek(0,2);size=stream.tell();stream.seek(max(0,size-4*1024*1024));raw=stream.read()
        lines=raw.split(b'\n')
        if size>4*1024*1024:lines=lines[1:]
        out=[]
        for line in lines[:-1]:
            try:out.append(json.loads(line))
            except ValueError:continue
        return out[-limit:]
    except OSError:return []

def runs():
    out=[]
    if RUNS.is_dir():
        for file in sorted(RUNS.glob('*.json'),reverse=True)[:500]:
            d=read_json(file)
            if not isinstance(d,dict):continue
            p=Path(d.get('path','')).resolve()
            if not p.is_relative_to(ARTIFACTS.resolve()):continue
            state=read_json(p/'state.json',dict(d,status='waiting'))
            if state.get('status') in ('waiting','training'):
                import psutil
                try:
                    proc=psutil.Process(state['pid'])
                    alive=abs(proc.create_time()-state.get('process_created_at',0))<.01 and proc.is_running()
                except (psutil.Error,KeyError):alive=False
                if not alive:state=dict(state,status='interrupted',reason='process_not_running')
            state['path']=str(p);out.append(state)
    return sorted(out,key=lambda r:r.get('created_at',0),reverse=True)

def run_by_id(run_id):
    if not isinstance(run_id,str) or not re.fullmatch('[a-f0-9]{32}',run_id):raise ValueError('invalid_run_id')
    return next((r for r in runs() if r['run_id']==run_id),None)
