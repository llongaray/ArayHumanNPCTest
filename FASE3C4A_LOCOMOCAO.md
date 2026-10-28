# 3C.4A — navegação e locomoção

## Base e escopo

As alterações parciais da 3C.3.5 cancelada foram retiradas de Executor e
EscapePlanner usando os trechos conhecidos da edição interrompida. Antes da
implementação, a base 3C.3.3 voltou a passar nos 233 testes. Não foi usado reset
do repositório nem removido trabalho preexistente.

Esta fase adiciona controle explícito de locomoção e observações. Não escolhe
modos automaticamente, não consulta Ollama e não atribui recompensas. O
monitor local de emergência e as interações da 3C.3.3 continuam existentes.

## Auditoria das APIs instaladas

Fontes: `E:/Games/Project.Zomboid.v42.13.1/game/media/lua` e assinaturas/bytecode
do `projectzomboid.jar`, inspecionados com javap em leitura. Nenhum jogo ou
serviço foi iniciado, nem o JAR modificado.

| Capacidade | APIs reais utilizadas/evidência |
|---|---|
| Caminhar | `ISWalkToTimedAction` de client/TimedActions/WalkToTimedAction.lua; `getPathFindBehavior2():pathToLocation/update/cancel`, `setPath2(nil)` |
| Correr | `NPCSetRunning/NPCGetRunning`, `setPathfindRunning/isPathfindRunning`, `setRunning/isRunning`; sprint permanece desativado durante o modo |
| Agachar e mover furtivamente | `setSneaking/isSneaking`; SNEAK solicita a postura nativa durante o percurso, sem prometer invisibilidade |
| Parar | Cancelamento da ação própria e pathfinding próprio; flags nativas de corrida desligadas; postura anterior preservada |
| Virar | `faceLocationF`, `isFacingLocation`, `shouldBeTurning`; usa X/Y reais do jogador atual ou centro de tile validado |
| Obstáculos | Integração com ArayHumanPhysical e EscapePlanner existentes: ToggleDoor, openWindow, climbThroughWindow e climbOverFence |
| Observações | X/Y/Z reais; `isCollidedThisFrame`; `getBodyDamage():getHealth`; percepção local limitada existente |

O bytecode de IsoAIModule aplica `humanControlVars.running` com setRunning;
NPCSetRunning escreve esse campo. Portanto, só setRunning não seria suficiente
para persistir a intenção no ramo NPC. Os getters são verificados após aplicar
o modo. setPathfindRunning configura a flag nativa de pathfinding, sem impor
velocidade numérica. O motor continua responsável pela velocidade efetiva,
atributos, carga, ferimentos e animações.

`setNPC(true)` e os desvios de entrada de IsoPlayer foram confirmados na
auditoria anterior e novamente inspecionados na instalação: NPCs retornam
false em pressedMovement/pressedCancelAction antes da leitura do jogador.
Não há simulação de teclas, mudança de coordenadas ou setMoveSpeed artificial.
Isso confirma a existência e o uso pretendido das APIs, não compatibilidade
real nem velocidade atingida sem teste manual no jogo.

## Interface reutilizável

Entrada principal: `ArayHuman.Locomotion.submit(request)` delega ao executor.

```json
{
  "uuid": "11111111-1111-4111-8111-111111111111",
  "world_id": "Sandbox/SEU_MUNDO",
  "action": "MOVE_TO",
  "target_id": "tile:4:0:0",
  "movement_mode": "RUN",
  "action_id": "nav-0001",
  "source": "policy"
}
```

Exemplo ilustrativo: UUID, mundo e target_id devem vir dos dados reais atuais.
`action` aceita MOVE_TO, STOP e FACE_TARGET. MOVE_TO aceita WALK, RUN ou SNEAK;
STOP e FACE_TARGET são ações, sem movement_mode. FACE_TARGET aceita tile
validado ou `target_id="PLAYER"`, resolvido pelo sobrevivente vivo atual e
atualizado se ele mudar durante a rotação.

Alternativamente, `validateDestination(uuid,target_id)` retorna um descritor
com UUID, mundo, target_id e horário de validação. Pode ser enviado em
`destination`, sem target_id separado. O executor sempre revalida no snapshot
atual; o descritor não autoriza coordenadas arbitrárias e expira em 1,5 s.

`source` é policy por padrão. Adaptações futuras de RL/Ollama devem usar policy:
ordens manuais e fuga emergencial têm prioridade. `source="manual"` é uma
entrada local de comando humano, não uma credencial nem um campo a aceitar
diretamente de saída de modelo. O protocolo Python/Ollama existente não foi
ampliado nesta fase; decisões externas continuam passando pela validação da
3C.2/3C.3. A interface é preparação para um adaptador futuro.

`expires_at_ms` é opcional, com duração máxima de 30 s. action_id identifica a
solicitação; o executor também fornece execution_id próprio. Há rejeição de
duplicados durante a validade, com registro limitado a 1024 entradas e limpeza
na troca de mundo. Chamadores devem gerar IDs únicos.

Consultas:

- `getState(uuid)`: action_id, execution_id, modo, alvo, estado, resultado e
  observations; cópias independentes.
- `getResult(uuid,action_id)`: resultado terminado, incluindo cancelamentos;
  últimas 16 solicitações por UUID em memória, descartadas na troca de mundo.
- `Executor.getState(uuid)` e `Walking.getState(uuid)`: detalhes já existentes
  continuam disponíveis.

## Segurança e integração

Executor revalida UUID real, instância viva/carregada, mundo, validade e tipo da
ação. Destinos devem existir entre os tiles permitidos do snapshot atual,
estar no mesmo andar, livres e dentro do raio de execução de 10 tiles.
Deslocamento previsto além de 12 tiles do jogador mantém WAITING_PERMISSION;
os hooks de aprovação existentes continuam verificando a ação correta.

Trocar modo ou destino usa nova solicitação: valida primeiro, cancela somente
a ação do UUID correspondente, restaura flags anteriores e solicita um novo
pathfinding nativo. Não escreve coordenadas por frame. A geração e a posse
da ação impedem stop/perform/callback antigos de afetar a substituta.

Flags de corrida/postura/sprint são salvas por caminhada e restauradas na
conclusão, erro ou cancelamento. APIs de modo ausentes recusam pedidos
explícitos. Chamadas antigas sem modo preservam a compatibilidade do adaptador
anterior quando essas APIs não podem ser confirmadas. A restauração é
diagnosticada; se um setter nativo deixar de responder, é uma tentativa
controlada e não uma garantia de recuperação desse setter.

ArayHumanPhysical bloqueia mudanças incompatíveis durante animações. STOP
solicita cancelamento diferido e fica em WAITING_PHYSICAL_STOP até o estado
seguro; não força a saída da animação. A restauração de flags também espera se
o NPC estiver escalando ou caído. FACE_TARGET cancela a caminhada própria e
fica TURNING até observar orientação confirmada, expirar ou falhar.

O monitor de fuga pode interromper os novos deslocamentos por UUID. Não houve
alteração da política de episódios da 3C.3.3: continuam três tentativas por
bloco, recuperação após 30 s e até dois blocos adicionais. Chegadas ainda
consomem esse contador. A limitação relatada no teste real continua conhecida;
a correção da 3C.3.5 cancelada não está incluída nesta entrega. Fugas continuam
usando o modo padrão WALK, sem nova escolha automática de RUN/SNEAK.

## Resultados observáveis

Observations registra distância XY fracionária acumulada, duração de relógio,
velocidade amostrada, posição, distância inicial/restante ao alvo e progresso
(pode ser negativo em um desvio). Não considera iniciar pathfinding como
chegada. Amostragem mínima de 250 ms e fechamento na conclusão/cancelamento.

Colisões são amostras de isCollidedThisFrame, não uma contagem completa de
impactos. Dano é soma das quedas de saúde observadas; não identifica atacante
e pode perder dano seguido de cura entre amostras. APIs ausentes usam
`known=false`, sem transformar desconhecido em zero. Falhas de pathfinding,
destino bloqueado, ausência de progresso e timeout continuam em result.

Ameaça antes/depois usa `Perception.observeThreats`, uma leitura local que não
consome o histórico de aproximação e queda de saúde usado pelo monitor de
emergência. A varredura mantém os limites existentes: até 169 tiles, 96
entidades e conexões limitadas. Coleta ocorre na entrada/saída, não a cada
frame; policy faz ainda uma leitura de segurança antes de iniciar. Troca de
mundo ou instância indisponível produz ameaça final desconhecida.

Logs `[ARAY-LOCOMOTION]` incluem UUID, action_id, modo, estado, resultado,
distância e duração. Resultados são mantidos em memória, sem gravação SQLite.
Nenhuma recompensa ou decisão de treinamento foi calculada.

## Arquivos e testes

Criados: `42/media/lua/client/ArayHumanLocomotion.lua`,
`ai/test_locomotion.py` e este relatório.

Alterados: ArayHumanWalking.lua, ArayHumanExecutor.lua,
ArayHumanPerception.lua e ai/test_executor.py (carregamento do módulo na suíte).
EscapePlanner foi restaurado à base após a fase cancelada e é reutilizado;
Physical e Commands não receberam novas alterações nesta fase.

Suíte completa: **277 testes aprovados**, incluindo os 233 anteriores e 44
novos casos parametrizados em Lua 5.1/5.4. Executa os módulos Lua reais e a
ação WalkToTimedAction.lua da instalação, com APIs Java simuladas.

Cobertura nova: modos e restauração, RUN→SNEAK em percurso, troca de destino,
callbacks antigos, dois NPCs, STOP, FACE_TARGET com sobrevivente substituído,
posição fracionária, dano/colisão/progresso, dados desconhecidos, APIs ausentes,
destino bloqueado dinamicamente, tokens, UUID/mundo/ações inválidos, replay,
limite de 12 tiles, aprovação, prioridade manual/emergencial, timeout,
animação física pendente, preservação de evidências da percepção e resultados
copiados/retidos. A suíte anterior cobre portas/janelas/cercas e a fuga local.

Execução: `python -B -m pytest ai -q -p no:cacheprovider`, com o runtime Lupa
temporário já disponível. Jogo, serviços e inferência não foram iniciados.

Limites: não há garantia de velocidade, animação ou furtividade real no motor
Java sem validação manual; não há nova navegação vertical, UI de seleção de
modos, planejador geral de obstáculos ou tratamento novo para fuga esgotada.
As restrições físicas da 3C.3.3 (térreo, portas simples, vidro seguro e empurrão
UNSUPPORTED) continuam válidas. Não houve mudança em FBO, câmera, balões,
JARs, saves, SQLite ou modelo, nem RL, treino, autonomia contínua, commit/push.

Aguardar instruções antes da 3C.4B.
