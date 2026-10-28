"""Explicit local-path CPU encoder; never resolves a remote model identifier."""
from pathlib import Path
import hashlib
import json

MODEL_ID='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'

class LocalEncoder:
    def __init__(self,path):
        path=Path(path).resolve()
        if not path.is_dir() or not (path/'modules.json').is_file(): raise ValueError('local_encoder_missing')
        from sentence_transformers import SentenceTransformer
        self.model=SentenceTransformer(str(path),device='cpu',local_files_only=True,trust_remote_code=False,model_kwargs={'use_safetensors':True})
        if self.model.get_sentence_embedding_dimension()!=384: raise ValueError('encoder_dimension')
        # Bind checkpoints to actual local contents, not an asserted model name alone.
        digest=hashlib.sha256()
        for file in sorted(path.rglob('*')):
            if file.is_file():
                digest.update(file.relative_to(path).as_posix().encode())
                with file.open('rb') as stream:
                    for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
        self.fingerprint=digest.hexdigest()
        self.cache={}

    def encode(self,texts):
        if len(texts)>128 or any(not isinstance(t,str) or len(t.encode('utf-8'))>2000 for t in texts): raise ValueError('encoder_budget')
        import torch
        missing=list(dict.fromkeys(t for t in texts if t not in self.cache))
        vectors={t:self.cache[t] for t in texts if t in self.cache}
        tokens=self.model.tokenizer(missing,truncation=False,add_special_tokens=True)['input_ids'] if missing else []
        if any(len(ids)>self.model.max_seq_length for ids in tokens):raise ValueError('encoder_token_budget')
        if missing:
            encoded=self.model.encode(missing,batch_size=16,convert_to_tensor=True,normalize_embeddings=True,show_progress_bar=False,device='cpu')
            for text,vector in zip(missing,encoded):
                vectors[text]=vector.detach().clone(); self.cache[text]=vectors[text]
            while len(self.cache)>2048:self.cache.pop(next(iter(self.cache)))
        return torch.stack([vectors[t] for t in texts])
