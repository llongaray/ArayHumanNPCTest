# Fase 3C.3 — Executor por UUID, sem autonomia automática

## Arquivos desta fase

Criados:

- `42/media/lua/client/ArayHumanExecutor.lua`: validação, estados, permissões,
  execução explícita e fuga confirmada localmente.
- `42/media/lua/client/ArayHumanWalking.lua`: adaptador nativo com caminhada,
  observação e cancelamento independentes por UUID.
- `ai/test_executor.py`: módulos Lua de produção e ação nativa B42 sob motor simulado.

Modificados:

- `ArayHumanTest.lua`: remove o `walkTest` global e delega ao adaptador; mantém
  as funções do F7. A criação não zera mais a caminhada de outros NPCs.
- `ArayHumanCommands.lua`: ordens manuais por UUID, seguimento limitado por tempo
  e callbacks vinculados à caminhada correta.
- `ArayHumanContext.lua`: callbacks e cursor de destino retêm o UUID do NPC para
  o qual o menu foi aberto, mesmo após mudança de foco.
- `ArayHumanPerception.lua`: lê a ordem por UUID quando a API correspondente existe;
  conserva o fallback de ordem global não atribuída para compatibilidade.

Nenhum código Python de decisão, persistência, renderização FBO, câmera ou
posição de balões foi alterado nesta fase. A documentação das fases anteriores
representa o estado existente no encerramento de cada fase.

## Uso explícito

```lua
local e = ArayHuman.Executor
e.beginSession(sessionId, sessionStartedAtMs)
local ok, actionIdOrError = e.submit(decisionResponse, optionalGoal)
local state = e.getState(uuid)
e.cancel(uuid, "cancelled_by_local_caller")
```

`decisionResponse` é o envelope 3C.2, contendo `kind`, `ok`, `world_id`, `npc_id`,
`session_id`, `session_started_at_ms`, `sequence`, `id`, `issued_at_ms`,
`expires_at_ms` e `decision`. O marcador `executable=false` da fase 3C.2 não é
um gatilho de execução. Somente uma chamada local explícita a `submit()` inicia
a interpretação validada da decisão. Não há leitor automático de respostas,
emissor Lua de requisições, chamada Ollama ou agendador de decisões.

A sessão deve ser estabelecida localmente. Mudar a sessão cancela ações anteriores;
reiniciar a mesma sessão não apaga o controle de sequência. Mundo, UUID, instância
carregada, vida, sessão, sequência, duplicatas e expiração são verificados.
O snapshot usado na execução é recolhido localmente, não fornecido pelo modelo.

MOVE_TO/WANDER_NEARBY aceitam somente um parâmetro `candidate_id` (contrato 3C.2)
ou `target_id` (alias local). Os dois nomes representam o mesmo identificador
`tile:x:y:z`; não se aceitam ambos nem coordenadas adicionais. O ID é procurado
entre os tiles avaliados do snapshot atual; suas coordenadas não são executadas
diretamente por simples análise da string. São revalidados carregamento, piso,
ocupação, andar e distância real antes do pedido ao pathfinding.

LOOK_AT_PLAYER usa o sobrevivente vivo atual. SAY usa
`ArayHuman.SpeechBubble.show(character, text, false)`; nenhum código do balão foi
alterado. IDLE/STOP encerram a ação desse UUID. FOLLOW_PLAYER escolhe um candidato
até dois tiles do jogador e só reconsidera após um intervalo, conclusão ou
interrupção; não solicita uma caminhada nova a cada frame.

## Máquina de estados

| Estado | Comportamento |
| --- | --- |
| `VALIDATING` | Estado transitório ao admitir uma intenção validada. |
| `WAITING_PERMISSION` | Destino além do limite, sem caminhada enfileirada. |
| `RUNNING` | Uma caminhada nativa em andamento. |
| `FOLLOWING` | Seguindo, sem caminhada ativa no momento, aguardando próximo intervalo. |
| `COMPLETED` | Sucesso, IDLE/STOP/SAY/LOOK concluídos ou perigo reduzido. |
| `CANCELLED` | Comando manual, substituição, ameaça, mundo/sessão alterados ou instância perdida. |
| `FAILED` | Destino indisponível, falha nativa, ausência de progresso, timeout ou expiração. |

`getState()` retorna cópia dos dados públicos: UUID, objetivo, ação, ID, geração,
destino, estado, início, timeout, resultado, mundo, sessão, sequência e, quando
aplicável, emergência, justificativa e autorização registrada. Não expõe referências
mutáveis do personagem, fila ou ação nativa.

## Movimento e cancelamento

O adaptador carrega `TimedActions/WalkToTimedAction`, arquivo encontrado na
instalação 42.13.1 que define `ISWalkToTimedAction`, e a fila `ISTimedActionQueue`.
Uma ação nativa solicita `PathFindBehavior2:pathToLocation()` uma vez. O motor
nativo calcula o caminho e faz o movimento; o executor apenas acompanha e cancela.

Cada caminhada possui personagem, UUID, ID e registro próprios. A geração do
executor e a identidade do registro do adaptador protegem callbacks. Antes de
cancelar, o registro antigo é invalidado; depois são interrompidos a ação e o
pathfinding daquele personagem e removida apenas a entrada pertencente ao adaptador.
Os métodos `start`, `update`, `stop` e `perform` da instância nativa também são
protegidos, pois `stop` nativo pode limpar a fila do personagem. Uma chamada
atrasada da ação antiga não pode cancelar o novo caminho ou completar a nova ação.

Filas com ação alheia ao adaptador na admissão são recusadas com
`foreign_action_busy`. Não se limpa a fila do jogador e não se usa a referência
do NPC em foco para resolver callbacks já iniciados.

Chamadas antigas continuam válidas: `walkTo(square, source)`, `walkActive()`,
`cancelWalk(silent)`, `order(cmd)`, `getOrderName()` e `getOrderLabel()` usam o foco.
As variantes por UUID são `walkTo(square, source, uuid, options)`, `walkActive(uuid)`,
`cancelWalk(silent, uuid)`, `order(cmd, uuid)` e `getOrderName(uuid)`.

Comandos manuais têm prioridade e criam um bloqueio por UUID, inclusive quando
não existe caminhada enfileirada. `Executor.releaseManual(uuid)` é uma função
local explícita: encerra a ordem manual e libera esse bloqueio. Decisões emitidas
antes ou no instante do comando manual permanecem recusadas após a liberação.
Comandos manuais explícitos do F7/menu mantêm o comportamento existente; a regra
de autorização abaixo se aplica aos deslocamentos iniciados pelo executor.

## Limite e autorização

Antes de cada caminhada do executor, o centro do destino é comparado à posição
atual do jogador. Padrão: 12 tiles de distância planar. Acima disso, o retorno é
`false, "permission_required"`, com estado `WAITING_PERMISSION` e sem ação nativa.

- ASK: a futura interface pode chamar `approve(uuid, actionId)` após aprovação.
- NOTIFY: pode chamar `recordNotice(uuid, actionId, text)` após avisar o jogador.

Essas funções são hooks locais de confiança, não parâmetros que o Ollama possa
fornecer. NOTIFY exige texto não vazio, registra evidência e timestamp no estado
e no log. Sem essa chamada não há autorização automática. Não existe interface
de aprovação nesta fase. A autorização vale para a ação/destino pendente; a chamada
revalida expiração, mundo/sessão, ameaça e disponibilidade do destino.

## Emergência local

`Executor.escape(uuid)` é outra chamada local explícita. Nenhuma flag do modelo
ativa emergência; envelopes contendo `emergency` são recusados. Comando manual
ativo continua prioritário e deve ser liberado explicitamente antes da fuga.

Para admitir uma fuga é necessário confirmar, nos ocupantes locais, um zumbi
vivo observado próximo, no andar do NPC, com conexão não bloqueada segundo
`IsoGridSquare:isBlockedTo()`. Apenas texto, distância declarada pelo modelo ou
visibilidade da câmera não constituem prova. Percepção de entidades truncada
não é suficiente para autorizar a exceção.

O executor avalia corredores retos cardinais presentes no snapshot: cada tile
deve continuar carregado, livre e com piso; cada ligação adjacente deve ser
confirmadamente não bloqueada. A separação das ameaças observadas não pode
diminuir ao longo do corredor. O destino deve ficar a pelo menos cinco tiles
das ameaças observadas e melhorar a separação inicial em pelo menos dois tiles.
Sem candidato adequado, retorna `safe_escape_unavailable` e não inventa caminho.

Uma fuga pode substituir caminhada comum, atravessar o limite de 12 tiles e
solicitar uma única caminhada nativa. Fica limitada a seis tiles de deslocamento
e seis segundos por padrão. É interrompida quando o perigo diminui, o destino
fica bloqueado, o NPC sai do corredor avaliado, a sessão/mundo muda ou a validade
termina. A justificativa registrada é produzida localmente.

## Frequências e APIs

- Caminhadas MOVE/WANDER: uma solicitação nativa por ação admitida.
- Monitor do executor: 250 ms; snapshot local com idade máxima de 1500 ms.
- Seguimento do executor: intervalo de 1000 ms, distância desejada de dois tiles.
- Seguimento manual: avaliação a cada 750 ms.
- Timeout comum: 30000 ms; ausência de progresso: 5000 ms.
- Uma ação também termina ao vencer o envelope 3C.2, mesmo antes do timeout comum.

APIs principais: `getCell():getGridSquare()`, `getCurrentSquare()`, `getModData()`,
`getX/Y/Z()`, `isDead()`, `faceLocation()`, `getMovingObjects()`, `instanceof`,
`isBlockedTo()`, `ISWalkToTimedAction:new()/setOnComplete()`, `ISTimedActionQueue`,
`getPathFindBehavior2():cancel()`, `setPath2(nil)`, `getTimestampMs()` e `OnTick`.
Percepção e teste de ocupação usam os módulos já existentes. Não se trocam
instância do jogador, câmera, entrada WASD, renderização ou posição de balões.

## Testes e limitações

Execução: `python -B -m pytest ai -q -p no:cacheprovider`, com Lupa no runtime
temporário. Resultado: **155 testes aprovados**, incluindo os 109 anteriores e
46 execuções novas (23 cenários em Lua 5.1 e Lua 5.4).

Os testes carregam o executor, adaptador, comandos, contexto e percepção reais,
além de `WalkToTimedAction.lua` da instalação B42. O motor Java, filas e mundo
são simulados. Se a instalação estiver em outro caminho, definir `ARAY_GAME_DIR`;
sem o arquivo nativo os testes desta fase são marcados como indisponíveis.

Cobertura: dois NPCs, cancelamento individual, substituição de destino, callbacks
nativos atrasados, bloqueio e ocupação após snapshot, morte, instância/chunk
indisponíveis, mundo/sessão, ASK/NOTIFY, expiração de autorização, fuga confirmada,
falta de corredor, limite de duração e desvio, falha de pathfinding, timeout e
ausência de progresso, seguimento com novo sobrevivente, comandos manuais/F7,
menu com mudança de foco, cópias do estado e fila alheia preservada. Armadilhas
verificam ausência de chamadas a câmera, criação de jogador, inferência e arquivos;
a fila do jogador permanece intocada. Sem chamadas explícitas não há execução.

Limitações: a percepção espacial 3C.1 não comprova visão/audição; os seis segundos
e os limites usam tempo real, inclusive durante pausa. Não há combate, abertura
de portas ou execução de tarefas de inventário. Fuga usa somente corredores retos
conservadores, podendo recusar saídas válidas com curvas. O pathfinding nativo
escolhe a trajetória real: a checagem de corredor/obstáculos reduz risco e cancela
desvios, mas não substitui validação no motor Java. A integração de filas,
animações, FBO e WASD ainda precisa de teste manual pelo usuário no jogo.

Não foi iniciado o jogo ou serviço real, nem alterado JAR, save, SQLite real ou
modelo Ollama. Nenhum commit/push foi realizado. Não há persistência dos estados
do executor nesta fase, nem autonomia ou agendamento automático de decisões.
