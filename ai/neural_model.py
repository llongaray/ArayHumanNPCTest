"""Real trainable PyTorch network. Import only after explicit CPU dependencies exist."""
import torch
from torch import nn
from neural_contract import INTENTS, DECISIONS, ACTIONS, FEATURES, MAX_GOALS

class NPCPolicy(nn.Module):
    def __init__(self,embedding_dim=384,hidden=128):
        super().__init__()
        self.embedding_dim,self.hidden=embedding_dim,hidden
        self.fusion=nn.Sequential(nn.Linear(embedding_dim*4+len(FEATURES)+len(ACTIONS),hidden),nn.ReLU(),nn.Dropout(.1))
        self.intents=nn.Linear(hidden,len(INTENTS)); self.decision=nn.Linear(hidden,len(DECISIONS))
        self.count=nn.Linear(hidden,MAX_GOALS+1)
        self.action_embedding=nn.Embedding(len(ACTIONS)+1,32)
        self.decoder=nn.GRUCell(32,hidden)
        self.action=nn.Linear(hidden,len(ACTIONS)+1)
        self.candidate_key=nn.Linear(embedding_dim+len(ACTIONS),hidden)
        self.query=nn.Linear(hidden,hidden)

    def forward(self,language,profile,history,state,numeric,capabilities,candidates,teacher=None):
        h=self.fusion(torch.cat((language,profile,history,state,numeric,capabilities),dim=-1))
        first=h; previous=torch.full((h.shape[0],),len(ACTIONS),dtype=torch.long,device=h.device)
        actions=[]; pointers=[]
        keys=self.candidate_key(candidates)
        for step in range(MAX_GOALS):
            h=self.decoder(self.action_embedding(previous),h)
            logits=self.action(h); actions.append(logits)
            pointers.append(torch.einsum('bh,bnh->bn',self.query(h),keys)/(self.hidden**.5))
            previous=teacher[:,step] if teacher is not None else logits.argmax(-1)
        return {'intents':self.intents(first),'decision':self.decision(first),'count':self.count(first),
                'actions':torch.stack(actions,dim=1),'pointers':torch.stack(pointers,dim=1)}
