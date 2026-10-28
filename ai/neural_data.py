"""Hand-labelled PT-BR teaching cases, NOT observations or experiences from the game.

Phrases are assigned to splits before scenario augmentation; identical phrases never
cross splits. No inference code imports these labels to interpret a player message.
"""
import copy
import hashlib
import json
import unicodedata
from pathlib import Path
from neural_contract import ACTIONS, TARGETED

# Each row: annotation, training formulations, held-out validation, held-out test.
PHRASES=(
 ('FOLLOW_PLAYER',('me siga','venha comigo','acompanhe meus passos'),('caminhe atrás de mim','mantenha-se comigo'),('não me deixe andando sozinho','quero sua companhia durante o trajeto')),
 ('STOP',('pare','não me siga mais','interrompa o deslocamento'),('fique onde está','cesse a caminhada'),('pode encerrar esse percurso','prefiro que permaneça no lugar')),
 ('LOOK_AT_PLAYER',('olhe para mim','vire-se na minha direção','me encare um instante'),('preste atenção em mim','dirija seu olhar para cá'),('quero que você fique de frente para mim','volte o rosto para onde estou')),
 ('FACE_TARGET',('fique de frente para o alvo indicado','vire para o ponto marcado','oriente o rosto ao alvo validado'),('encare o local selecionado','volte o corpo ao ponto indicado'),('aponte seu olhar para aquela posição observada','gire para ficar voltado ao destino marcado')),
 ('WALK',('caminhe até o destino indicado','vá andando ao ponto marcado','siga a pé até aquele local'),('desloque-se sem correr até o ponto','alcance a marca caminhando'),('percorra a rota até o destino em passo normal','chegue ao lugar indicado devagar')),
 ('RUN',('corra até o ponto marcado','vá correndo ao destino','alcance o local em corrida'),('acelere o passo até a marca','chegue correndo naquele ponto'),('use corrida para chegar ao destino indicado','apresse-se pela rota até a posição marcada')),
 ('SNEAK',('vá agachado ao ponto marcado','avance furtivamente até o destino','mova-se escondido até o local'),('alcance a marca sem fazer barulho','chegue ao destino abaixado'),('aproxime-se da posição indicada de maneira furtiva','percorra esse trajeto com postura baixa')),
 ('OPEN_DOOR',('abra a porta indicada','deixe essa porta aberta','pode abrir a porta'),('destranque a passagem abrindo a porta destravada','preciso dessa porta aberta'),('gire a maçaneta da porta destravada e abra','permita a passagem pela abertura dessa porta')),
 ('CLOSE_DOOR',('feche essa porta','deixe a porta fechada','pode fechar a porta'),('encerre a passagem fechando a porta','não deixe a porta aberta'),('quero essa abertura coberta pela porta','encoste a porta até fechar')),
 ('OPEN_WINDOW',('abra a janela indicada','deixe a janela aberta','pode abrir essa janela'),('levante a folha da janela','preciso dessa janela aberta'),('permita a ventilação abrindo a janela marcada','abra a folha da janela destravada')),
 ('CLIMB_WINDOW',('atravesse a janela aberta','passe pela janela indicada','cruze a janela segura'),('vá para o outro lado pela janela','use a janela aberta como passagem'),('alcance o lado oposto cruzando a janela','faça a travessia por essa janela validada')),
 ('CLIMB_FENCE',('pule a cerca baixa indicada','atravesse essa cerca baixa','salte a cerquinha'),('vá ao outro lado pela cerca baixa','transponha a pequena cerca'),('cruze a barreira baixa validada','alcance o outro lado saltando essa cerca pequena')),
 ('PICKUP_ITEM',('pegue a bandagem do chão','recolha aquela bandagem','apanhe o curativo no piso'),('traga a bandagem caída para seu inventário','retire o curativo do chão'),('guarde consigo a faixa que está no piso','colete aquela bandagem visível no chão')),
 ('PICKUP_ITEM@NAILS',('pegue os pregos do chão','recolha aqueles pregos','apanhe os pregos no piso'),('guarde os pregos caídos no seu inventário','retire os pregos do chão'),('faça a coleta dos pregos visíveis','leve consigo os pregos que estão no piso')),
 ('LOOT_CONTAINER',('colete os itens do recipiente acessível','recolha o conteúdo dessa caixa','saque esse recipiente autorizado'),('retire os objetos do recipiente indicado','pegue o conteúdo da caixa acessível'),('faça a coleta no recipiente validado','leve para seu inventário o conteúdo permitido dessa caixa')),
 ('TRANSFER_ITEM',('transfira a bandagem para o recipiente indicado','mova esse item ao recipiente autorizado','passe o item para o destino validado'),('coloque a bandagem na caixa indicada','faça a transferência desse objeto'),('troque o recipiente da bandagem usando o destino autorizado','deposite o objeto no recipiente acessível marcado')),
 ('BANDAGE',('faça uma bandagem no seu ferimento','use o curativo para se enfaixar','aplique uma faixa na sua lesão'),('cuide da lesão com a bandagem disponível','enfaixe a ferida'),('trate seu ferimento com o material real que carrega','cubra a lesão usando uma bandagem do inventário')),
 ('PICKUP_ITEM>FOLLOW_PLAYER',('pegue a bandagem e depois me siga','recolha o curativo antes de vir comigo','primeiro colete a bandagem, depois me acompanhe'),('traga a faixa para seu inventário e só então caminhe comigo','antes de me acompanhar, recolha a bandagem'),('quando terminar de apanhar o curativo, venha comigo','a coleta da bandagem vem primeiro; acompanhar-me vem depois')),
 ('FOLLOW_PLAYER>PICKUP_ITEM',('me siga e depois pegue a bandagem','venha comigo antes de recolher o curativo','primeiro me acompanhe, depois colete a bandagem'),('acompanhe meus passos e só então recolha a faixa','antes de coletar a bandagem, venha comigo'),('a coleta do curativo deve esperar até você me acompanhar','primeiro venha ao meu lado; em seguida guarde a faixa caída')),
 ('REQUEST_DIALOGUE',('vamos conversar um pouco','como você está?','conte sobre sua profissão'),('o que você tem no inventário?','há ameaças observadas perto de você?'),('você consegue descrever o que realmente percebeu?','gostaria de ouvir sobre sua história')),
 ('NO_RESPONSE',('não precisa responder, apenas estou anotando','sem resposta por enquanto','só registrei a informação, não responda'),('não diga nada agora','pode ficar em silêncio nesta conversa'),('esta observação dispensa uma resposta sua','não quero fala nem ação neste momento')),
 ('REQUEST_CLARIFICATION',('faça aquilo','pegue alguma coisa ali','resolva isso para mim'),('vá para aquele negócio','use aquilo que eu pensei'),('trate daquele assunto sem eu indicar qual','mexeu no objeto que eu queria?')),
 ('CONTINUE_GOAL',('continue o objetivo que já está fazendo','mantenha a tarefa atual','prossiga com a ação em andamento'),('não troque seu objetivo atual','dê continuidade ao percurso já iniciado'),('quero que você prossiga exatamente na tarefa vigente','siga adiante com o objetivo já confirmado')),
 ('INFORMATION',('eu encontrei uma rua bloqueada','estou levando materiais comigo','sua última ação terminou'),('vi uma porta fechada no caminho','vou permanecer por perto'),('acabei de observar o resultado da caminhada','estou registrando que esse trajeto falhou')),
)

def observation(text):
    world='SYNTHETIC/teaching'; actor='11111111-1111-4111-8111-111111111111'; now=100000
    known=lambda value:{'status':'KNOWN','value':value}
    caps={a:{'available':True,'support':'experimental'} for a in ACTIONS}
    caps.update({a:{'available':False,'support':'UNSUPPORTED'} for a in ('PUSH_ZOMBIE','CLIMB_STAIRS')})
    descriptions={'PICKUP_ITEM':'Bandagem Base.Bandage no chão carregado','BANDAGE':'Ferimento próprio e bandagem real no inventário',
                  'LOOT_CONTAINER':'Caixa acessível e autorizada','TRANSFER_ITEM':'Bandagem para recipiente autorizado'}
    candidates=[{'uuid':actor,'world_id':world,'action':a,'target_id':'synthetic:'+a,'description':descriptions.get(a,'Destino observado para '+a),
      'observation_id':'synthetic-observation','expires_at_ms':now+1000} for a in ACTIONS if a in TARGETED]
    candidates += [dict(c,target_id=c['target_id']+':other',description='Pregos Base.Nails no chão carregado' if c['action']=='PICKUP_ITEM' else 'Outro alvo observado para '+c['action']) for c in list(candidates)]
    return {'schema_version':1,'uuid':actor,'world_id':world,'session_id':'synthetic-session','request_id':'synthetic-request',
      'observation_id':'synthetic-observation','captured_at_ms':now,'expires_at_ms':now+1000,'message':text,
      'routing':{'schema_version':1,'world_id':world,'recipients':[actor]},'control':{'manual_priority':False,'emergency_priority':False},
      'identity':known({'name':'Carlos','occupation':'mecânico','personality':'cauteloso'}),'profile':{'status':'UNAVAILABLE'},
      'health':known({'health':{'known':True,'value':85}}),'threat':known({'known':True,'observed_zombies':0}),
      'inventory':known({'items':[{'full_type':'Base.Bandage'}],'complete':True}),
      'capabilities':known(caps),'perception':known({'visibility':{'known':True,'complete':True}}),
      'action_results':known([]),'conversation_memory':known([]),'personal_memory':{'status':'UNAVAILABLE'},'candidates':candidates}

def records():
    out={k:[] for k in ('train','validation','test')}
    for label,train,val,test in PHRASES:
        for split,phrases in zip(out,(train,val,test)):
            name={'train':'Carlos','validation':'Tania','test':'João'}[split]
            for p,phrase in enumerate(phrases):
                text=name+', '+phrase; obs=observation(text)
                obs['identity']['value']['name']=name
                parts=[a.split('@')[0] for a in label.split('>')]
                goals=[{'action':a,**({'target_id':'synthetic:'+a+(':other' if '@NAILS' in label and a=='PICKUP_ITEM' else '')} if a in TARGETED else {})} for a in parts] if parts[0] in ACTIONS else []
                decision='EXECUTE_ACTION' if goals else ('REQUEST_DIALOGUE' if label=='INFORMATION' else label)
                intents=['INSTRUCTION','ACTION_REQUEST'] if goals or label=='REQUEST_CLARIFICATION' else (
                  ['INFORMATION'] if label in ('INFORMATION','CONTINUE_GOAL') else ['NO_RESPONSE'] if label=='NO_RESPONSE' else ['CONVERSATION','QUESTION'])
                if label=='REQUEST_DIALOGUE':intents=['CONVERSATION','QUESTION'] if '?' in phrase else ['CONVERSATION']
                if label=='REQUEST_CLARIFICATION' and '?' in phrase:intents=['QUESTION']
                if label=='CONTINUE_GOAL':obs['current_goal']={'state':'WALKING','action':'FOLLOW_PLAYER','action_id':'existing-goal'}
                base={'schema_version':1,'provenance':'authored_supervised_scenario_not_game_experience',
                      'phrase_family':split+':'+label+':'+str(p),'observation':obs,'intents':intents,'decision':decision,'goals':goals}
                out[split].append(base)
                if goals:
                    for variant in ('emergency','manual','unavailable'):
                        case=copy.deepcopy(base); case['variant']=variant
                        if variant in ('emergency','manual'):
                            case['observation']['control'][variant+'_priority']=True; case['decision']='WAIT'
                        else:
                            case['observation']['capabilities']['value'][goals[0]['action']]['available']=False
                            case['decision']='REQUEST_CLARIFICATION'
                        case['goals']=[]; out[split].append(case)
    return out

def normalized(text):
    # Names are excluded only from leakage checks, never from actual model inputs.
    text=text.split(',',1)[-1]
    return ''.join(c for c in unicodedata.normalize('NFD',text.casefold()) if unicodedata.category(c)!='Mn').strip()

def audit(data):
    families={}; phrases={}
    for split,rows in data.items():
        for row in rows:
            key=row['phrase_family']; text=normalized(row['observation']['message'])
            if key in families and families[key]!=split or text in phrases and phrases[text]!=split: raise ValueError('split_leakage')
            families[key]=split; phrases[text]=split
            if row['provenance']!='authored_supervised_scenario_not_game_experience': raise ValueError('provenance')
    digest=hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    return {'counts':{s:len(rows) for s,rows in data.items()},'phrase_families':len(families),'dataset_sha256':digest}

def load_data(root=None):
    root=Path(root) if root else Path(__file__).parent/'neural_supervised_data'
    data={}
    for split in ('train','validation','test'):
        file=root/(split+'.jsonl')
        if file.stat().st_size>8*1024*1024:raise ValueError('dataset_budget')
        rows=[json.loads(line) for line in file.read_text(encoding='utf-8').splitlines() if line]
        if not 1<=len(rows)<=2000:raise ValueError('dataset_count')
        data[split]=rows
    checked=audit(data)
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('dataset_sha256')!=checked['dataset_sha256']:raise ValueError('dataset_integrity')
    return data

if __name__=='__main__':
    print(json.dumps(audit(records()),ensure_ascii=False,indent=2))
