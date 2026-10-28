# 3C.3.3 — fuga com interações físicas

Implementação experimental, sem teste no jogo. A suíte executa o Lua real do
mod e wrappers Lua da instalação, com a parte Java e as animações simuladas.
Não comprova compatibilidade real com NPCs.

## Auditoria local da B42.13.1

Instalação inspecionada: `E:/Games/Project.Zomboid.v42.13.1/game`.
Leitura dos arquivos Lua e inspeção somente de leitura das assinaturas/bytecode
de `projectzomboid.jar` com javap; nenhuma classe foi carregada como jogo.

| Transição | Evidência nativa | Implementação/status |
|---|---|---|
| WALK | TimedActions/WalkToTimedAction.lua e PathFindBehavior2 | Motor anterior preservado |
| OPEN_DOOR | ISWorldObjectContextMenu.restoreDoor usa IsoDoor.ToggleDoor(character) | Chamada nativa, confirmação de IsOpen e passagem revalidada; experimental em NPC |
| OPEN_WINDOW | shared/TimedActions/ISOpenCloseWindow.lua:perform chama character:openWindow | Mesmo método nativo; aguarda saída do estado Java; experimental |
| CLIMB_WINDOW | client/TimedActions/ISClimbThroughWindow.lua:perform chama climbThroughWindow | Mesmo método nativo; aguarda estado seguro e chegada ao tile; experimental |
| CLIMB_FENCE | client/TimedActions/ISClimbOverFence.lua:perform chama climbOverFence(direction) | Mesmo método nativo para cerca baixa, aguardando chegada; experimental |
| DEFENSIVE_SHOVE | IsoLivingCharacter.setDoShove; IsoPlayer.DoAttack/pressedAttack; SwipeStatePlayer e CombatManager | UNSUPPORTED: nenhum ataque executado |

`setNPC(true)` existe em IsoGameCharacter e é usado pela criação atual do mod.
O bytecode configura IsoAIModule e o campo isNpc. `IsoPlayer.pressedMovement`
e `pressedCancelAction` retornam false para esse campo antes de ler teclado ou
controle. As chamadas de janela/cerca de IsoGameCharacter reportam eventos ao
ActionContext; os métodos inspecionados não rejeitam isNpc. Isso sustenta a
tentativa experimental, não uma declaração de funcionamento em jogo.

O empurrão foi deliberadamente recusado: `DoAttack(float)` em IsoPlayer delega
a pressedAttack após autorização; a colisão de SwipeStatePlayer usa
CombatManager.attackCollisionCheck, arma/AttackVars e verificações de jogador
local. Não foi encontrado um contrato público que garanta um único zumbi vivo
como alvo, excluindo jogadores e outros NPCs. Não há chamada a ataques, dano,
setDoShove, troca de arma ou animação artificial.

Há ainda uma particularidade confirmada em OpenWindowState.execute: pânico
contextual acima de 5 pode disparar smashWindow. O adaptador exige contextPanic
conhecido e zero no início e imediatamente antes da chamada. Não altera esse
campo. Se o pânico aumentar dentro da animação, o comportamento continua sendo
do motor; vidro perigoso impede a travessia seguinte.

## Arquitetura e validações

Novo `42/media/lua/client/ArayHumanPhysical.lua`: descritores internos das
transições, validação local, bloqueio físico por UUID, orientação nativa,
observação de conclusão e cancelamento diferido.

EscapePlanner tenta primeiro o planejamento WALK anterior. Somente se falhar,
tenta uma busca limitada com interações e penalidade adicional por interação.
Ambas mantêm no máximo 96 nós por busca (configurável até 128), 256 ocupantes
examinados na busca e deslocamento total de até seis tiles. Não é busca global
nem promessa de caminho ótimo. O segundo passe pode dobrar o custo da busca
em uma tentativa sem rota livre. Inspeção de ocupação física limita cada tile
a 32 entidades. Trechos WALK consecutivos mantêm compactação quando possível.

Portas: somente IsoDoor simples, fechada, destrancada, sem barricada, sem
obstrução e não invencível. getDoubleDoorIndex/getGarageDoorIndex devem retornar
-1 (confirmado no bytecode). Portas compostas/garagens não são suportadas.
O objeto deve corresponder exatamente à aresta cardinal/orientação getNorth.
Abrir não autoriza atravessar: WALK revalida colisões depois da abertura.

Janelas: somente IsoWindow no térreo, entre tiles carregados com piso sólido,
sem ocupantes no destino nem vidro quebrado no chão dos dois lados. Abertura
exige janela destrancada, não permanentemente travada nem barricada.
Travessia exige canClimbThrough imediatamente antes da chamada. Janela
quebrada só é candidata se isGlassRemoved for true; não remove vidro, quebra
janela ou assume que roupa protege contra ferimentos.

Cerca: somente baixa, no térreo, encontrada por getHoppableTo, objeto ainda
existente. Na execução exige isSafeToClimbOver e isPlayerAbleToHopWallTo.
Não usa climbOverWall nem atravessa móveis ou paredes arbitrárias.

Cada interação exige estado IdleState confirmado, ausência de ataque/empurrão,
queda ou escalada, fila própria vazia, mesmo UUID/instância/mundo, observação
local completa e recente (até 1 s), origem atual e direção válida. Exige
distância mínima de ameaça de 1,25 tile para porta e 2 para janela/cerca;
no destino, pelo menos 2,5 tiles de todos os zumbis observados. O planejador
também aplica essas margens às transições. APIs ausentes ou desconhecidas
recusam a operação.

DEFENSIVE_SHOVE valida instância, perigo local, estado, alvo reencontrado vivo,
distância de até 1,25 tile e orientação, com inspeção máxima de 32 entidades.
Quando elegível, registra UNSUPPORTED e cooldown de 2 s; não executa empurrão.
Se o alvo/orientação não puder ser confirmado, retorna o motivo da recusa.

## Estados, interrupção e limites

Executor: ESCAPING_STEP → INTERACTING → ESCAPING_STEP/RUNNING/COMPLETED ou FAILED.
Adaptador: ORIENTING → NATIVE → resultado observado. A fila Lua não é usada
como sinal de término: os wrappers nativos removem a ação ao iniciar a animação
Java, fato também coberto pelo teste com os arquivos reais da instalação.

Antes da chamada nativa, ameaça nova, bloqueio, mudança de mundo/objeto ou
cancelamento impedem a operação. Durante a animação, o risco é reavaliado e
registrado, mas não há forceStop, mudança de estado ou teleporte. Cancelamento
invalida o executor e mantém o bloqueio até IdleState seguro ou morte; callbacks
antigos não retomam a rota. Comandos de caminhada/olhar e decisões novas são
recusados enquanto esse UUID estiver bloqueado. STOP/STAY podem solicitar
cancelamento. Outro NPC e a fila do jogador permanecem independentes.

Orientação: limite de 1,5 s. Operação física: timeout de 7 s, com espera pelo
estado seguro para liberar o bloqueio. Episódio de fuga: 6 s mais 2,5 s por
interação planejada, limitado a 12 s. O timeout não força a interrupção de
animação insegura; uma animação Java travada pode deixar esse UUID bloqueado,
com diagnóstico explícito. Monitoramento usa os 250 ms anteriores e a mesma
seleção de até dois NPCs por rodada; aposentadoria de cancelados também é
limitada a uma verificação a cada 250 ms, sem nova varredura de ameaças.

## Arquivos

Criados: ArayHumanPhysical.lua, ai/test_physical_escape.py e este relatório.
Alterados: ArayHumanEscapePlanner.lua, ArayHumanExecutor.lua,
ArayHumanWalking.lua, ArayHumanCommands.lua e ai/test_executor.py (carrega o
novo módulo no ambiente de regressão). Perception continua fornecendo os
mesmos snapshots e varredura local; não foi alterado nesta fase.

## Validação

233 testes aprovados: 203 anteriores e 30 novos (15 cenários em Lua 5.1/5.4).
Cobrem porta fechada, rota livre preferida, abertura e travessia de janela,
vidro perigoso/vidro removido, cerca baixa/alta, alvo e ameaça no outro lado,
mudança durante orientação, animação em andamento, cancelamento manual,
callback invalidado, timeout diferido, dois NPCs, APIs ausentes, observação de
UUID/mundo incorretos e controle/fila do jogador preservados. Wrappers Lua
reais de abertura/janela/cerca também foram executados com Java simulado.

Comando: `python -B -m pytest ai -q -p no:cacheprovider`, com Lupa disponível
no runtime temporário de testes anterior. Nenhum jogo ou serviço iniciado.

Pendências para validação manual: animações e estados efetivos do NPC, posição
fracionária junto a obstáculos, pânico durante abertura, colisão do volume do
personagem, arredores que mudam depois do planejamento e integração do motor
Java com NPCs. Não há suporte a andar superior, parede/cerca alta, janela
IsoThumpable/frame, portas compostas, combate ou empurrão seguro.

Não houve alterações em FBO, câmera, balões, JARs, saves, SQLite ou modelo,
ativação de decisões gerais/Ollama contínuo/RL, commit ou push. Aguardar
validação manual antes da 3C.4A.
