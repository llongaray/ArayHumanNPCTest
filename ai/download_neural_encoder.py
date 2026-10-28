"""Explicitly invoked authorized download. Fixed public repository and file allowlist."""
import hashlib
import json
from pathlib import Path
import shutil
import time

REPOSITORY='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
REVISION='e8f8c211226b894fcb81acc59f3b34ba3efd5f42'
ALLOWED={'model.safetensors','config.json','config_sentence_transformers.json','modules.json',
 'sentence_bert_config.json','tokenizer.json','tokenizer_config.json','special_tokens_map.json',
 'sentencepiece.bpe.model','unigram.json','1_Pooling/config.json','README.md','LICENSE','LICENSE.txt'}

def main():
    from huggingface_hub import HfApi,hf_hub_download
    root=Path(__file__).resolve().parent; environment=root/'neural_environment'
    manifest=environment/'encoder-download.json'
    if manifest.exists():raise ValueError('download_manifest_exists_use_recorded_revision')
    info=HfApi(token=False).model_info(REPOSITORY,revision=REVISION)
    revision=info.sha
    if len(revision)!=40 or any(c not in '0123456789abcdef' for c in revision):raise ValueError('model_revision')
    available={f.rfilename for f in info.siblings}; selected=sorted(ALLOWED & available)
    if not {'model.safetensors','modules.json','tokenizer.json','config.json','1_Pooling/config.json'}<=set(selected):raise ValueError('model_files_missing')
    target=root/'neural_models'/'paraphrase-multilingual-MiniLM-L12-v2'/revision
    record={'schema_version':1,'repository':REPOSITORY,'revision':revision,'path':str(target),
            'license':getattr(info.card_data,'license',None),'files':[],'completed':False}
    environment.mkdir(parents=True,exist_ok=True)
    manifest.write_text(json.dumps(record,indent=2),encoding='utf-8')
    started=time.monotonic()
    for name in selected:
        cached=hf_hub_download(REPOSITORY,name,revision=revision,cache_dir=environment/'.hub-cache',token=False)
        dest=target/name; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(cached,dest)
        h=hashlib.sha256()
        with dest.open('rb') as stream:
            for block in iter(lambda:stream.read(1048576),b''):h.update(block)
        record['files'].append({'name':name,'bytes':dest.stat().st_size,'sha256':h.hexdigest()})
        manifest.write_text(json.dumps(record,indent=2),encoding='utf-8')
        print('downloaded',name,dest.stat().st_size,flush=True)
    record.update(completed=True,elapsed_seconds=time.monotonic()-started)
    manifest.write_text(json.dumps(record,indent=2),encoding='utf-8')
    print('revision',revision,flush=True)

if __name__=='__main__':main()
