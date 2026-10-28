# 3C.4E — catálogo e observações para agentes

## Entrega e escopo

Camada Lua explícita, versão 1, sem loop de decisões, inferência, treinamento ou
recompensas. Ela consulta os observadores existentes e encaminha solicitações ao
Executor/Navigation. Não há um segundo executor nem mecanismos físicos novos.

Arquivos criados:

- `42/media/lua/client/ArayHumanCapabilities.lua`: catálogo, fronteira de entrada,
  prioridades, despacho, cancelamento e histórico limitado de resultados.
- `42/media/lua/client/ArayHumanAgentState.lua`: observação agregada e candidatos
  vinculados ao UUID, mundo, instância e identificador de observação.
- `ai/test_agent_catalog.py`: contratos e integração em Lua real 5.1 e 5.4, com
  APIs Java simuladas e ações Lua vanilla usadas pelo ambiente de testes anterior.
- Este relatório.

Arquivo modificado: `42/media/lua/client/ArayHumanExecutor.lua`.
Adiciona consulta somente de leitura de prioridades, timestamp da ameaça já
observada pelo monitor e entrada local para SAY/FOLLOW_PLAYER reutilizando o
balão e a função interna de acompanhamento. O caminho `submit(decision_response)`
continua validando sessão e sequência como antes. LOOK_AT_PLAYER da camada nova
usa FACE_TARGET/PLAYER, que já confirma a orientação nativa.

Não foram editados Python de produção, chat, persistência, renderização, câmera,
balões, JARs, executáveis, saves, bancos existentes ou configuração de modelo.
Jogo e serviços não foram iniciados. Não houve commit ou push.

## Auditoria dos contratos reutilizados

| Módulo | Contrato utilizado e limites preservados |
|---|---|
| Perception | getSnapshot/updateSnapshot, posição fracionária, jogador vivo atual, entidades locais, tiles candidatos e informações de completude. getSnapshot pode retornar vazio ou antigo; a agregação atualiza quando necessário. |
| Survival | getSnapshot/updateSnapshot/getEvents, wrappers known/status, saúde, condições simultâneas, ferimentos, necessidades e política. Nenhum setter é utilizado. |
| Locomotion | Resultados por action_id, métricas reais de deslocamento/colisão/dano, modos nativos e confirmação da orientação. |
| Walking | Ação de caminhada e PathFindBehavior2 existentes; callback/generation por UUID. A camada central não muda coordenadas nem conduz quadros de movimento. |
| Physical | getCandidates, tokens privados por objeto, resolveCandidate, animações, locks e resultados. Cancelamentos podem permanecer pendentes até retirada nativa segura. |
| Navigation | Planos finitos de até 12 etapas e confirmação da etapa anterior. Cada etapa usa o Executor existente. |
| Inventory | Observação limitada, tokens de itens/recipientes, propriedade, alcance, capacidade, transferências e bandagem com itens reais. Experimental e restrito a singleplayer. |
| Executor | requestLocomotion, estados, cancelamento, limite de 12 tiles, prioridade manual e fuga local. A política não pode aprovar ASK/NOTIFY nem declarar emergência. |
| ai/decision_handler.py | Contrato anterior decision_request/decision_response, UUID/mundo/sessão/sequência/expiração; modelo por mundo, JSON validado, timeout HTTP de 15 s. Não modificado nem conectado automaticamente à nova entrada. |

APIs nativas seguem nos adaptadores auditados anteriormente: getters de posição,
estado e metadata de IsoPlayer; Stats.get/CharacterStat, BodyDamage e partes do
corpo; flags NPCSetRunning/setPathfindRunning/setRunning/setSneaking/setSprinting;
faceLocationF/isFacingLocation/shouldBeTurning; PathFindBehavior2 e caminhada
nativa; ToggleDoor, openWindow, climbThroughWindow, climbOverFence;
ISGrabItemAction, ISTransferAction.transferItem e ISApplyBandage.
Esta fase não acrescenta chamada nativa de mutação fora desses adaptadores.

## Catálogo

`ArayHuman.Capabilities.getCatalog(uuid)` retorna versão, UUID/mundo, política e
um mapa `actions`. Cada entrada informa:

- `support`: experimental ou UNSUPPORTED.
- `available`: elegível neste contexto para submeter à validação final.
- `availability_status`: eligible_for_validation ou unavailable, com `reason`.
- `evidence`: auditoria local de APIs B42 e testes Lua simulados.
- `manual_validation`: pending; `revalidation_required`: true.
- Ação de backend, modo, necessidade de alvo.

Nenhuma ação foi promovida a compatibilidade comprovada no jogo nesta fase.
Implementação/API auditada e disponibilidade atual são dimensões separadas.
Uma ação elegível ainda pode falhar por mudança de alvo, obstáculo, ameaça,
alcance, API opcional, fila nativa ou permissão. O catálogo não promete caminho
livre nem visibilidade/linha de visão.

| Ação pública | Encaminhamento |
|---|---|
| WALK, RUN, SNEAK | MOVE_TO e respectivo movement_mode |
| STOP, FACE_TARGET | Executor local existente |
| LOOK_AT_PLAYER | FACE_TARGET com PLAYER resolvido localmente |
| FOLLOW_PLAYER | Função follow do Executor, prazo finito, intervalo existente de 1 s |
| SAY | Balão existente; resultado speech_dispatched confirma despacho, não que alguém ouviu |
| OPEN_DOOR, CLOSE_DOOR, OPEN_WINDOW, CLIMB_WINDOW, CLIMB_FENCE | Physical através do Executor |
| PICKUP_ITEM, LOOT_CONTAINER, TRANSFER_ITEM, BANDAGE | Inventory através do Executor |
| NAVIGATE | Navigation: sequência finita de ações com alvo |
| PUSH_ZOMBIE | Bloqueada: UNSUPPORTED_target_exclusive_native_shove |
| CLIMB_STAIRS | Bloqueada: UNSUPPORTED_STAIRS_VERTICAL_VALIDATION |

IDLE/MOVE_TO/WANDER_NEARBY continuam no protocolo anterior do DecisionHandler;
não são novas ações públicas desta versão. EAT/DRINK/REST não são executáveis.
Não há tradução automática de respostas Ollama: um adaptador futuro terá de
preservar a validação anterior e criar explicitamente a solicitação versionada.

## Observação unificada

`ArayHuman.AgentState.getSnapshot(uuid)` retorna uma cópia serializável com:

- schema_version, uuid, world_id, captured_at_ms, observation_id e expires_at_ms.
- Identidade local (UUID/nome, quando conhecido), posição/direção e estado ativo.
- Percepção compacta, jogador atual, NPCs/zumbis observados e limites da leitura.
- Saúde, condições/ferimentos, estados simultâneos, necessidades e política.
- Inventário, peso/capacidade, completude e indicação de itens omitidos por limite.
- Execução/Navigation/interação em andamento e prioridades atuais.
- Candidatos com UUID/mundo, action, target_id e validade.
- Até 8 eventos Survival e 4 resultados resumidos da nova interface.
- profile.schema_version=1; profissão, traços, habilidades, XP e pontos
  indisponíveis: 3C.4D.1 não foi implementada.

Identidade/persona do SQLite continua sob o serviço existente. Esta camada não
abre bancos nem inventa personalidade, profissão ou histórico de personagens.
Resultados de comandos antigos fora desta interface não são fabricados; seu
estado atual pode aparecer em runtime, e o histórico novo cobre seus pedidos.

Valores reais de fome/sede/fadiga continuam observados. `rl_objective=false`
permanece para os três. A desativação física continua UNSUPPORTED; endurance é
preservada. Nenhum zeramento periódico foi criado.

Dados desconhecidos usam known=false; indisponibilidade inclui status/reason
onde o observador os fornece. Zero e false conhecidos permanecem valores reais.
Campos opcionais ausentes não significam zero. Capturas dos submódulos podem
ter timestamps diferentes: não é uma transação atômica do motor.

## Entrada explícita para agentes

APIs:

```lua
ArayHuman.Capabilities.request(request)          -- boolean, resultado ou motivo
ArayHuman.Capabilities.getResult(uuid, action_id)
ArayHuman.Capabilities.getRecentResults(uuid)
ArayHuman.Capabilities.cancel(uuid, action_id, origin)
ArayHuman.AgentState.invalidate(uuid)
ArayHuman.AgentState.clearAll()
```

Exemplo didático de pedido; os IDs de observação/alvo devem ser copiados de uma
observação real recente, e os timestamps substituídos pelos valores vigentes:

```json
{
  "schema_version": 1,
  "uuid": "11111111-1111-4111-8111-111111111111",
  "world_id": "Sandbox/MundoExemplo",
  "action_id": "rl:42",
  "origin": "rl",
  "priority": 2,
  "expires_at_ms": 1793171815000,
  "observation_id": "observation:7",
  "action": "RUN",
  "target_id": "tile:1:0:0"
}
```

Para SAY, usar `text` de 1 a 300 bytes não vazios, sem alvo. STOP,
LOOK_AT_PLAYER e FOLLOW_PLAYER também não recebem alvo. Para NAVIGATE:

```json
{
  "schema_version": 1,
  "uuid": "11111111-1111-4111-8111-111111111111",
  "world_id": "Sandbox/MundoExemplo",
  "action_id": "rl:43",
  "origin": "rl",
  "priority": 2,
  "expires_at_ms": 1793171815000,
  "observation_id": "observation:7",
  "action": "NAVIGATE",
  "steps": [
    {"action": "OPEN_WINDOW", "target_id": "edge:1"},
    {"action": "CLIMB_WINDOW", "target_id": "edge:1"},
    {"action": "RUN", "target_id": "tile:2:1:0"}
  ]
}
```

Regras de admissão:

- UUID canônico, roster/metadata e isNPC reais, instância viva e square carregado;
  exclusão explícita do jogador controlado; mundo deve coincidir.
- schema_version=1; action_id de 1–96 bytes alfanuméricos/ponto/dois-pontos/hífen/
  sublinhado; origins somente ollama, rl ou neural. Todas viram source=policy.
- Prioridade inteira 0–3; pedido menor não substitui pedido ativo maior desta
  interface. Prioridade manual/emergencial sempre prevalece. Valores iguais
  podem substituir ações de política, usando cancelamento/generation existentes.
- Prazo inteiro futuro, máximo 30 s, inclusive planos. Não existe fila autônoma.
- Alvos só da observação emitida ao mesmo UUID/mundo/instância, ainda vigente.
  Renovar uma observação não renova silenciosamente um pedido velho.
- Etapas: array contíguo, máximo 12; cada ação/alvo deve estar autorizado na
  observação. Apenas pares action/target_id; sem condicionais ou laços.
- Entrada somente de dados simples, até 512 nós/profundidade 6; sem metatables,
  ciclos, funções, userdata, números não finitos, campos extras ou coordenadas.
- Revalidação final pelo Executor/Physical/Inventory/Navigation permanece ativa.
- cancel só alcança o action_id e origem registrados, se ainda forem donos da
  execução; nunca cancela comando manual, fuga ou uma execução substituta.

origin é proveniência, não autenticação de transporte. Mesmo uma origem forjada
como ollama/rl/neural conserva os mesmos limites de política. O módulo não
executa, interpreta ou carrega strings como código. Texto SAY pode conter texto
livre, mas somente é enviado ao mecanismo existente de balão.

Pedidos recusados antes do despacho retornam false e motivo; não alocam ação.
Falhas do backend depois do despacho retornam false e registro estruturado.
WAITING_PERMISSION é preservado se o Executor criar esse estado; a camada não
concede permissão. Pedidos rejeitados não constituem telemetria de ação executada.

## Resultados

Registros completos incluem pedido original, requested_action, dispatched_action,
executed_action quando uma execução foi alocada, movement_mode, origem, estado,
result/failure_reason, before/after, duração, dano, progresso, recursos e backend.
executed_action identifica a ação do backend, não garante seu sucesso físico.
COMPLETED e métricas observadas são necessários para avaliar o resultado.

Exemplo abreviado ilustrativo de uma caminhada concluída:

```json
{
  "schema_version": 1,
  "uuid": "11111111-1111-4111-8111-111111111111",
  "world_id": "Sandbox/MundoExemplo",
  "action_id": "rl:42",
  "requested_action": "RUN",
  "dispatched_action": "MOVE_TO",
  "executed_action": "MOVE_TO",
  "movement_mode": "RUN",
  "state": "COMPLETED",
  "duration_ms": {"known": true, "status": "known", "value": 1000},
  "damage_received": {"known": true, "value": 0},
  "progress": {
    "distance_travelled": {"known": true, "status": "known", "value": 1},
    "progress": {"known": true, "status": "known", "value": 1},
    "collisions": {"known": true, "value": 0}
  },
  "resources_used": {"known": false, "status": "unknown", "reason": "not_observed"},
  "before": {"position": {"known": true, "x": 0.5, "y": 0.5, "z": 0}},
  "after": {"position": {"x": 1.5, "y": 0.5, "z": 0}},
  "unknown_fields": ["reward", "profession", "traits", "skills", "xp", "points"]
}
```

`after` usa a amostra final congelada pelo backend; uma consulta tardia não
atribui posição/dano de um comando posterior à ação anterior. As necessidades
associadas mantêm o timestamp do Survival. `completed_at_ms` é o momento em que
a interface observou o término; duração vem da métrica nativa, não desse polling.
Se um campo não foi medido, continua desconhecido.

Cancelamento de interação/itens pode retornar CANCEL_PENDING. A interface espera
a retirada do lock nativo pertencente àquela ação, preserva o resultado físico
efetivo e não conclui cancelamento antecipadamente. `physical_result` e resultados
de Inventory mantêm os efeitos reais, inclusive quando a animação acaba depois
do cancelamento lógico. Planos apresentam resultados compactos por etapa.
Recursos não instrumentados não são anunciados como quantidade zero.

## Desempenho e limites

- Consultas explícitas; nenhum novo OnTick, decisão automática ou inferência.
- Cache espacial/inventário por UUID: inicialmente 1000 ms, com invalidação por
  mundo, instância, morte, jogador atual, tempo regressivo ou pedido novo.
- Runtime/prioridades/resultados são consultados sem refazer varredura espacial
  a cada leitura do cache. A seleção ordena apenas tiles já observados.
- Até 128 NPCs na camada; 16 pedidos por UUID, 12 etapas/30 s por pedido.
  Registros terminais antigos são retirados ao atingir o limite; não terminais
  não são descartados para admitir pedidos ilimitados. O backend também mantém
  suas proteções de replay. IDs devem ser únicos durante a sessão do produtor.
- Até 96 candidatos: no máximo 32 destinos espaciais próximos, 48 candidatos de
  inventário e interações cardinais disponíveis. MOVE no catálogo de candidatos
  representa WALK/RUN/SNEAK e FACE_TARGET para aquele tile.
- Até 32 itens listados, 16 NPCs e 16 zumbis no resumo, 8 eventos e 4 resultados.
  Ferimentos continuam sujeitos ao limite de 32 partes do Survival.
- Leituras locais preservam limites originais de Perception (raio 10, 400 tiles,
  128 entidades/objetos) e Inventory (5 squares, 128 itens, 64 objetos, 256 tokens).
  Nenhuma varredura global, consulta Ollama ou gravação SQLite.
- Cópias têm limite de 16384 nós, profundidade 12 e 128 entradas por tabela;
  truncamento marca serialization_truncated. Listas resumidas indicam limites/
  scan/truncamento. Dados omitidos não representam ausência de entidade.

O custo de reconstrução é limitado às leituras dos observadores e ordenação dos
tiles locais já obtidos; consultas ao cache fazem cópias limitadas e consultam
estados. Pedidos continuam pagando a revalidação dos adaptadores existentes.
Latência e FPS reais não foram medidos: testes simulados não comprovam desempenho
no motor. Não chamar os getters indiscriminadamente para todos os NPCs por frame.

## Verificação e limitações para validação manual

Suíte: `python -B -m pytest ai -q -p no:cacheprovider`, usando o runtime Lupa
isolado já disponível. Testes novos rodam Lua 5.1 e 5.4 e cobrem todas as ações,
tokens expirados, dados parciais, APIs ausentes, fontes inválidas, funções/userdata/
ciclos, prioridades, sequência de janela, animação cancelada, métricas reais,
consulta tardia, dois NPCs, morte, mundo/jogador trocado e limites de cache/memória.

Regressão completa: **607 testes aprovados**, sendo os 475 anteriores e 132 novos
casos parametrizados em Lua 5.1/5.4. Tempo observado da suíte: cerca de 24 s.

Limitações preservadas: APIs físicas/inventário experimentais sem teste no jogo;
portas compostas e obstáculos não auditados recusados; janelas/cercas restritas
pelas validações atuais de piso/vidro/ameaça; escadas e empurrão continuam bloqueados.
Candidatos não certificam caminho transitável completo. Planos só podem usar
alvos já emitidos; novos itens ou alvos descobertos depois exigem outra observação
e pedido. O limite e a recuperação da fuga anteriores permanecem como estavam;
a 3C.3.5 cancelada não foi presumida implementada.

A camada não amplia o contrato Python/Ollama de decisões, nem autentica um futuro
transporte remoto. Antes de integrar agentes contínuos, ainda serão necessários
adaptadores de transporte, validação manual no jogo e avaliação de desempenho.
Nenhuma recompensa ou treinamento foi implementado. Aguardar 3C.4E.1.
