"""Version 2 authored scenarios. No original held-out phrases are imported.

Split-specific construction banks and disjoint compound-action pairs are assigned
before scenario augmentation. This is synthetic supervision, never game evidence.
"""
import copy
import hashlib
import json
from pathlib import Path
import random
import unicodedata

from neural_contract import ACTIONS,TARGETED,check_observation,safe_decision
from neural_data import observation

# Banks represent construction families, not random paraphrases split afterwards.
ACTION_BANKS=[
 ('pare agora|interrompa o caminho|cancele sua caminhada','fique parado aí|não avance mais|encerre o percurso','estacione onde está|chega de andar por ora|suspenda o deslocamento'),
 ('me siga|venha comigo|acompanhe minha caminhada','ande atrás de mim|mantenha minha companhia|siga os meus passos','quero você me acompanhando|cola em mim no trajeto|não me deixe ir sozinho'),
 ('olhe pra mim|vire o rosto para mim|fique me olhando','me encare um pouco|preste atenção na minha direção|volte os olhos para mim','quero seu olhar voltado pra mim|me dê atenção olhando aqui|fique de frente para quem está falando'),
 ('caminhe até a marca|vá andando ao destino|alcance o ponto a pé','sem correr, chegue à posição|percorra o trajeto caminhando|desloque-se em passo normal','chegue devagar ao lugar|use caminhada para alcançar a marca|percorra a rota sem acelerar'),
 ('corra até a marca|vá correndo ao destino|alcance o ponto em corrida','acelere até a posição|chegue depressa correndo|use corrida nesse trajeto','dispare até o local|apresse a chegada usando corrida|alcance rapidamente a posição marcada'),
 ('avance agachado|vá furtivamente ao ponto|caminhe sem fazer barulho','mova-se abaixado até a marca|chegue sorrateiramente|use postura furtiva no trajeto','se esgueire até lá|faça o percurso em silêncio e agachado|alcance o lugar sem se expor'),
 ('encare o alvo marcado|vire para o ponto|olhe para o objeto indicado','oriente o rosto para a marca|fique de frente pro alvo|gire em direção ao local','quero o olhar na posição indicada|volte sua atenção ao objeto marcado|posicione o rosto rumo à marca'),
 ('abra a porta|deixe a porta aberta|puxe a porta destravada para abrir','libere a passagem abrindo a porta|pode abrir essa porta|mova a folha da porta até abrir','preciso passar, abra a porta|faça a abertura da porta destravada|permita minha passagem pela porta aberta'),
 ('feche a porta|deixe a porta fechada|encoste a porta até fechar','bloqueie a passagem fechando a porta|não deixe a porta aberta|pode fechar essa porta','quero essa porta no estado fechado|faça o fechamento da porta|mantenha a entrada fechada pela porta'),
 ('abra a janela|deixe a janela aberta|levante a folha da janela','permita ventilação abrindo a janela|pode abrir a janela|libere a abertura da janela','quero essa janela no estado aberto|faça a abertura da folha da janela|levante o vidro da janela destravada'),
 ('atravesse a janela|passe pela janela aberta|cruze a janela segura','vá pro outro lado pela janela|use a janela como passagem|faça a travessia da janela','alcance o lado oposto cruzando a janela|saia por essa janela aberta|transponha a janela liberada'),
 ('pule a cerca baixa|salte a cerquinha|atravesse a pequena cerca','vá pro outro lado saltando a cerca|use a cerca baixa como passagem|transponha essa cerca pequena','cruze a barreira baixa|alcance o lado oposto pela cerca|faça a travessia da cerquinha'),
 ('pegue o item do chão|recolha o objeto no piso|apanhe o material caído','guarde o item caído no inventário|retire do chão o objeto|faça a coleta do material no piso','leve consigo o objeto visível no chão|colete o recurso caído|ponha no inventário o item do piso'),
 ('saque o recipiente|colete o conteúdo da caixa|retire os itens do baú acessível','leve o conteúdo do recipiente|recolha os objetos da caixa|esvazie para si o recipiente autorizado','quero os materiais dessa caixa coletados|faça a coleta no baú acessível|guarde os recursos do recipiente permitido'),
 ('transfira o item para a caixa|mova o objeto ao recipiente|deposite o material no baú','coloque o recurso no recipiente|passe o item para a caixa|troque o recipiente desse material','quero o objeto guardado naquele baú|faça a transferência ao recipiente|deixe o recurso na caixa de destino'),
 ('enfaixe seu ferimento|aplique uma bandagem em si|use a faixa na sua lesão','cuide da própria ferida com curativo|cubra a lesão com bandagem|trate seu corte com a faixa','quero sua ferida enfaixada|faça o curativo na lesão própria|proteja seu machucado usando a bandagem'),
]

# Each cell: ten manually labelled, different utterances per split.
SPEECH={
 'conversation':[
 'vamos conversar|quero ouvir sua história|conte algo sobre você|fala comigo um pouco|como foi sua vida antes disso|conte uma lembrança boa|vamos trocar uma ideia|me distraia com uma história|gostaria de conhecer você melhor|puxe um assunto',
 'bora bater papo|me fale dos seus planos|preciso de companhia numa conversa|conte como aprendeu seu ofício|quero saber mais sobre sua personalidade|vamos falar do passado|compartilhe uma lembrança|me conte o que pensa da nossa situação|tenho vontade de conversar contigo|me faça companhia com uma conversa',
 'topa uma prosa|me narre um episódio da sua vida|quero trocar experiências com você|fale dos sonhos que tinha|vamos prosear enquanto esperamos|conte uma coisa que te marcou|quero escutar sua opinião pessoal|converse comigo sobre esperança|me fale da sua profissão|me conte sobre alguém importante pra você'],
 'question':[
 'você tem uma bandagem?|o que há no seu inventário?|tem zumbi perto de você?|a porta está aberta?|qual sua profissão?|você está machucado?|qual é sua condição de saúde?|há algum item no chão?|essa janela está quebrada?|o caminho está livre?',
 'quantos recursos você carrega?|existe uma ameaça aí?|a caixa pode ser alcançada?|sua ferida sangra?|você vê alguma passagem segura?|quais objetos estão perto?|essa porta está trancada?|tem material para curativo?|qual foi o resultado da caminhada?|seu inventário está cheio?',
 'há sinais de perigo na sua posição?|o que você consegue observar daqui?|qual o estado dessa cerca?|você ainda tem espaço na mochila?|a janela permite passagem?|está tudo bem com sua saúde?|quanto peso você leva?|qual tarefa está em andamento?|você enxerga um recipiente acessível?|essa bandagem está no piso?'],
 'information':[
 'vi uma porta fechada|achei uma bandagem lá atrás|tem zumbi na rua|estou com a mochila cheia|vou ficar por perto|a janela que vi estava aberta|estou levando materiais|eu me machuquei na estrada|o baú está vazio|a última rota terminou',
 'acabei de encontrar uma caixa|há um obstáculo naquele caminho|minha mochila ficou pesada|observei uma cerca baixa|eu já guardei os pregos|o corredor ficou perigoso|vou esperar nesta sala|encontrei vidro na janela|a caminhada anterior falhou|estou anotando os recursos',
 'deixei um material sobre o piso|percebi movimento na rua|meu curativo acabou|a entrada foi bloqueada|estou registrando sua posição|eu fechei aquela porta|avistei um recipiente no galpão|o chão do outro lado tem vidro|minha tarefa terminou agora|tenho notícias sobre a passagem'],
 'silence':[
 'não responda|fique em silêncio|não diga nada agora|sem resposta por favor|apenas escute sem falar|não quero fala nem ação|dispenso sua resposta|só estou anotando, fique quieto|silêncio por enquanto|não é pra responder a isso',
 'guarde silêncio nesta conversa|não comente o que falei|só registre, sem me responder|pode continuar calado|nenhuma resposta é necessária|não abra a boca agora|prefiro que não fale|isto não pede reação|quero silêncio neste momento|apenas ouça em silêncio',
 'não precisa dizer coisa alguma|evite responder por ora|esta anotação dispensa comentários|fique quietinho enquanto anoto|não me dê retorno agora|quero que permaneça calado|escute isto sem retrucar|deixe esta mensagem sem resposta|nenhuma fala ou ação é pedida|não responda nem faça nada'],
 'clarify':[
 'faça aquilo|pegue alguma coisa|vá até lá|resolva esse negócio|use aquele objeto|cuide disso pra mim|mova o troço|prepare a coisa|arrume o que falta|faça o que estou pensando',
 'trate daquele assunto|pegue o negócio que eu quero|vá ao local que imaginei|use isso aí|resolva aquela situação|faça a tarefa que não expliquei|mexa naquela coisa|dê um jeito nisso|leve algo pra algum lugar|escolha o objeto que pensei',
 'faça o combinado que não falei|vá onde você sabe|recolha aquele trem|resolva a parada|use o que for naquele negócio|cuide daquilo ali|mova algo para algum canto|trate o problema não indicado|execute o plano que ficou na minha cabeça|pegue sei lá qual recurso'],
 'continue':[
 'continue sua tarefa atual|prossiga com o objetivo|mantenha a ação em andamento|não troque de tarefa|continue o percurso já iniciado|siga com o que estava fazendo|retome o objetivo vigente|mantenha esse trabalho|prossiga sem mudar o plano|dê continuidade à ação',
 'leve adiante a tarefa atual|não interrompa seu objetivo|permaneça nessa atividade|conclua o que já começou|pode seguir no mesmo trabalho|mantenha o plano em curso|continue exatamente essa ação|não altere o percurso atual|prossiga na atividade vigente|avance com o objetivo confirmado',
 'siga adiante na tarefa vigente|persista no trabalho iniciado|não substitua o objetivo atual|dê sequência ao que faz agora|vá em frente com a mesma ação|conserve sua tarefa em execução|mantenha o rumo do trabalho atual|continue trabalhando nisso|prossiga no plano já aprovado|leve a atividade atual até o fim']}

def norm(text):
    return ''.join(c for c in unicodedata.normalize('NFD',text.casefold()) if unicodedata.category(c)!='Mn').strip()

def create_case(split,family,text,intents,decision,actions,variant,index):
    rng=random.Random(3000+index); names=('Carlos','Tânia','João','Luísa','Beto','Márcia')
    actor=f'{index+1:08x}-1111-4111-8111-111111111111'; world='SYNTHETIC/v2/'+split
    addressed=names[index%6] if index%5 else names[index%6]+' e '+names[(index+1)%6]
    if index%7==0:text=norm(text)
    if index%11==0:text=text.replace('para','pra').replace('você','vc')
    if index%13==0:text=text.replace('agora','agroa').replace('caminhe','caminheh')
    message=addressed+', '+text
    obs=observation(message); obs.update(uuid=actor,world_id=world,session_id='v2-session-'+split,request_id='v2-'+str(index),observation_id='v2-obs-'+str(index))
    obs['routing'].update(world_id=world,recipients=[actor]+(['ffffffff-ffff-4fff-8fff-ffffffffffff'] if index%5==0 else []))
    obs['identity']['value'].update(name=names[index%6],occupation=('mecânico','enfermeira','carpinteiro')[index%3])
    obs['health']['value']['health']['value']=rng.choice([25,60,85,100])
    obs['threat']['value']['observed_zombies']=rng.choice([0,1,3,7])
    obs['inventory']['value']['items']=[{'full_type':x} for x in rng.sample(['Base.Bandage','Base.Nails','Base.Hammer'],rng.randrange(4))]
    # Grounded target labels; IDs and candidate order are deliberately non-semantic.
    color='azul' if index%2 else 'vermelha'
    for k,c in enumerate(obs['candidates']):
        c.update(uuid=actor,world_id=world,observation_id=obs['observation_id'],target_id=f'v2-{index}-{k}')
        c['description']='Alvo observado para '+c['action']+' com marca '+('azul' if k<13 else 'vermelha')
    rng.shuffle(obs['candidates'])
    goals=[]
    for a in actions:
        g={'action':a}
        if a in TARGETED:g['target_id']=next(c['target_id'] for c in obs['candidates'] if c['action']==a and c['description'].endswith(color))
        goals.append(g)
    if any(a in TARGETED for a in actions):obs['message']+=' Use os alvos com marca '+color+'.'
    if variant in ('manual','emergency'):
        obs['control'][variant+'_priority']=True;decision='WAIT';goals=[]
    elif variant=='missing' and actions:
        obs['candidates']=[c for c in obs['candidates'] if c['action']!=actions[0]]
        obs['capabilities']['value'][actions[0]]['available']=False;decision='REQUEST_CLARIFICATION';goals=[]
    elif variant=='unavailable' and actions:
        obs['capabilities']['value'][actions[0]]['available']=False;decision='REQUEST_CLARIFICATION';goals=[]
    if family.startswith('continue'):
        obs['current_goal']={'state':'WALKING','action':'FOLLOW_PLAYER','action_id':'existing-'+str(index)}
    row={'schema_version':2,'provenance':'authored_supervised_scenario_not_game_experience','phrase_family':family,
         'scenario_family':split+'/'+variant,'variant':variant,'observation':obs,'intents':intents,'decision':decision,'goals':goals}
    check_observation(obs,obs['captured_at_ms'])
    checked=safe_decision({'intents':intents,'decision':decision,'goals':goals,'confidence':1},obs,obs['captured_at_ms'])
    if checked['decision']!=decision or (decision=='EXECUTE_ACTION' and not checked['goals']):raise ValueError('label_guard_mismatch')
    return row

def records():
    out={s:[] for s in ('train','validation','test')}; index=0
    def add(s,f,t,i,d,a,v):
        nonlocal index
        out[s].append(create_case(s,f,t,i,d,a,v,index));index+=1
    for si,s in enumerate(out):
        for ai,bank in enumerate(ACTION_BANKS):
            for pi,text in enumerate(bank[si].split('|')):
                for v in ('normal','normal_alt','manual','emergency','missing'):
                    add(s,f'atomic/{s}/{ai}/{pi}',text,['INSTRUCTION','ACTION_REQUEST'],'EXECUTE_ACTION',[ACTIONS[ai]],v)
        for kind,banks in SPEECH.items():
            intents={'conversation':['CONVERSATION'],'question':['QUESTION'],'information':['INFORMATION'],
                     'silence':['NO_RESPONSE'],'clarify':['INSTRUCTION','ACTION_REQUEST'],'continue':['INSTRUCTION']}[kind]
            decision={'conversation':'REQUEST_DIALOGUE','question':'REQUEST_DIALOGUE','information':'NO_RESPONSE',
                      'silence':'NO_RESPONSE','clarify':'REQUEST_CLARIFICATION','continue':'CONTINUE_GOAL'}[kind]
            for pi,text in enumerate(banks[si].split('|')):
                for v in ('calm','injured','loaded','nearby'):
                    add(s,f'{kind}/{s}/{pi}',text,intents,decision,[],v)
    # Both directions of an unordered pair stay in the SAME partition.
    for a in range(len(ACTIONS)):
        for b in range(a+1,len(ACTIONS)):
            bucket=int(hashlib.sha256(f'pair-v2/{a}/{b}'.encode()).hexdigest()[:8],16)%10
            si=0 if bucket<6 else 1 if bucket<8 else 2;s=list(out)[si]
            for left,right in ((a,b),(b,a)):
                x=ACTION_BANKS[left][si].split('|')[0];y=ACTION_BANKS[right][si].split('|')[1]
                for form,text in enumerate((f'primeiro {x}; depois {y}',f'antes de {y}, {x}')):
                    add(s,f'compound/{a}/{b}',text,['INSTRUCTION','ACTION_REQUEST'],'EXECUTE_ACTION',[ACTIONS[left],ACTIONS[right]],'compound'+str(form))
    return out

def audit(data):
    phrases={};families={};scenarios={};counts={}
    for split,rows in data.items():
        for r in rows:
            for registry,key in ((families,r['phrase_family']),(scenarios,r['scenario_family']),
                                 (phrases,norm(r['observation']['message'].split(',',1)[1]))):
                if key in registry and registry[key]!=split:raise ValueError('v2_split_leakage')
                registry[key]=split
        counts[split]=len(rows)
    return {'counts':counts,'families':len(families),'scenario_families':len(scenarios),'normalized_unique_messages':len(phrases),
            'sha256':hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}

def main():
    root=Path(__file__).parent/'neural_supervised_data_v2'
    if root.exists():raise ValueError('preserve_existing_v2')
    data=records();checked=audit(data);root.mkdir()
    for split,rows in data.items():(root/(split+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    (root/'manifest.json').write_text(json.dumps({'schema_version':2,'audit':checked,'provenance':'authored_not_game_experience','test_status':'sealed_before_training'},indent=2),encoding='utf-8')
    print(json.dumps(checked))

if __name__=='__main__':main()
