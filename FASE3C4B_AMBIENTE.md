# 3C.4B — interação avançada com o ambiente

Implementação sobre a base 3C.4A, sem teste no jogo. APIs e bytecode foram
inspecionados somente para leitura na instalação B42.13.1. As funcionalidades
físicas continuam experimentais para IsoPlayer com setNPC(true).

## Auditoria e capacidades

Instalação: `E:/Games/Project.Zomboid.v42.13.1/game`.

| Ação | API nativa e confirmação | Entrega |
|---|---|---|
| OPEN_DOOR | IsoDoor.ToggleDoor(character), IsOpen; uso real em ISWorldObjectContextMenu.restoreDoor | Porta simples, destrancada, sem barricada/obstrução; confirma aberta |
| CLOSE_DOOR | Mesma ToggleDoor, sem setters de travamento; confirma IsOpen=false | Porta simples, ambos os lados livres; já fechada é operação idempotente |
| Passar por porta | Caminhada existente com ISWalkToTimedAction/PathFindBehavior2 | Etapa WALK separada, depois de OPEN_DOOR confirmado |
| OPEN_WINDOW | IsoGameCharacter.openWindow, usado por ISOpenCloseWindow.lua | Reutilizado; aguarda estado nativo e IsOpen=true |
| CLIMB_WINDOW | climbThroughWindow e canClimbThrough, usados por ISClimbThroughWindow.lua | Reutilizado; exige animação terminada e presença real no tile de destino |
| CLIMB_FENCE | climbOverFence, isSafeToClimbOver e isPlayerAbleToHopWallTo; ISClimbOverFence.lua | Cerca baixa compatível; presença real no destino após animação |
| STAIRS / destino em outro Z | PathFindBehavior2.pathToLocation aceita Z; IsoGridSquare possui APIs de escadas | UNSUPPORTED_STAIRS_NPC nesta interface |

ArayHumanPhysical continua sendo o único adaptador que abre/fecha portas ou
inicia animações de janela/cerca. Navigation não replica essas chamadas: cada
etapa passa pelo Executor e pelos módulos da 3C.3.3/3C.4A.

Portas são localizadas por getDoorTo e orientação getNorth, com objeto e índice
confirmados. Foram inspecionados os métodos getDoorTo/getWindowTo: procuram
os objetos nas arestas correspondentes dos dois tiles. Portas compostas e
garagens continuam recusadas pelo índice nativo. OPEN/CLOSE usam o estado
desejado, sem alternar uma porta que já esteja nesse estado. Nenhum método de
destravamento artificial é usado. Abrir a porta não afirma que a passagem
está livre: a telemetria mede passage_clear e o WALK seguinte é revalidado.

Janelas exigem origem/destino carregados, piso sólido, ausência de vidro no
chão, sem barricada e vidro seguro. Janela quebrada só permite travessia se
isGlassRemoved=true. As ações em janelas e cercas permanecem restritas ao
térreo; altura maior ou piso de chegada incompatível é recusado. Abertura
recusa contextPanic desconhecido/positivo; o comportamento nativo ainda pode
quebrar a janela se o pânico aumentar dentro da animação. A travessia seguinte
revalida vidro e canClimbThrough, sem assumir proteção por roupas.

As verificações de ameaça usam a percepção local dos dois lados da aresta.
Navegação normal exige varredura completa e recente e cede à ameaça imediata.
Mantém margens de pelo menos 1,25 tile na origem para porta e 2 para
janela/cerca, e 2,5 no destino. A fuga existente mantém sua finalidade de
emergência e suas validações; não passa a depender desta fila de navegação.

## Escadas e Z

APIs inspecionadas: HasStairs, HasStairsNorth/West, HasStairTop,
HasStairsBelow, isSameStaircase, isStairBlockedTo, getStairsDirection,
getStairsHeightMin/Max, isAboveTopOfStairs e pathToLocation(int,int,int).
O bytecode de pathToLocation encaminha o Z solicitado ao destino nativo; o de
isAboveTopOfStairs consulta o piso e os tipos de escada do nível inferior.
ISInventoryTransferAction.lua também usa HasStairs/isSameStaircase.

Isso comprova mecanismos de escada no motor, não uma ligação interandar
segura para o adaptador atual. A percepção de destinos, a validação de
travessias e a política de risco ainda são do mesmo nível. Não foi acrescentada
uma chamada 3D sem validar a cadeia de escada, piso e chegada. STAIRS e planos
com destino de caminhada em outro Z retornam UNSUPPORTED_STAIRS_NPC.
Não se afirma que o jogo não suporte escadas; o suporte seguro para este
controlador ficou pendente, sem teleporte nem modificação de Z.

## Interface e navegação composta

`ArayHuman.Physical.getCandidates(uuid, approach_target_id?)` examina somente
as quatro arestas do tile atual ou de um tile de aproximação já permitido no
snapshot local. Retorna identificadores opacos, objeto/tile/índice, origem,
destino e ações candidatas. São capacidades, não autorização para execução
imediata: por exemplo, CLIMB_WINDOW continua exigindo abertura antes de iniciar.

Os tokens são privados por UUID/mundo e ligados à instância real do objeto.
Há no máximo 64 referências por UUID. Objeto trocado/removido, tile
descarregado, mundo diferente ou token de outro NPC é recusado. Não se recebe
objeto Java, coordenada arbitrária nem código executável de uma decisão.

Primitivas usam a interface da 3C.4A:

```lua
ArayHuman.Locomotion.submit({
    uuid = uuidReal,
    world_id = snapshotAtual.world_id,
    action_id = "door-001",
    action = "CLOSE_DOOR",
    target_id = candidato.target_id,
    source = "policy"
})
```

Planos finitos usam o novo módulo:

```lua
ArayHuman.Navigation.submit({
    uuid = uuidReal,
    world_id = snapshotAtual.world_id,
    action_id = "route-001",
    source = "policy",
    steps = {
        {action = "WALK", target_id = tileAproximacao},
        {action = "OPEN_WINDOW", target_id = janelaId},
        {action = "CLIMB_WINDOW", target_id = janelaId},
        {action = "RUN", target_id = tileSaida}
    }
})
```

WALK/RUN/SNEAK são atalhos para MOVE_TO com movement_mode; também se aceita
a forma MOVE_TO explícita. Os IDs vêm do snapshot e da descoberta física reais.
Preflight verifica formatos/proveniência; execução revalida a cena atual em
cada etapa. Para fechar uma porta depois de atravessá-la, o token deve ter
como origem o lado em que o NPC estará, descoberto pelo tile de aproximação.

Limites: até 12 etapas, 8 planos ativos, 120 s por plano e 30 s por solicitação
filha. O atualizador processa até dois planos por rodada de 250 ms, sem laço
de tentativas dentro de uma rodada. Rejeição/falha encerra o plano; não existe
replanejamento, recompensa ou repetição automática. Após a última etapa,
nenhuma ação nova é iniciada. Todos os alvos de caminhada devem estar entre
os candidatos locais conhecidos no preflight e novamente na execução.

Mantém o limite de 12 tiles do jogador e as validações da 3C.4A. Travessias
físicas que excederiam esse limite são recusadas com permission_required;
nenhuma interface nova de autorização foi criada. source=policy deve ser
usado por adaptadores futuros; source=manual é reservado ao comando humano
local. O protocolo Python/Ollama não foi ampliado nesta fase.

## Estados, interrupções e concorrência

Plano: READY → RUNNING → próxima etapa READY ou COMPLETED/FAILED/CANCELLED.
WAITING_PHYSICAL impede iniciar uma ação incompatível enquanto termina uma
animação anterior. O resultado da etapa anterior precisa estar confirmado
antes do próximo despacho; completar a fila Lua não basta para uma travessia.

Ordens manuais, cancelamento do Executor e novas solicitações aceitas cancelam
o plano correspondente, inclusive entre etapas ou antes do primeiro despacho.
O despacho de uma etapa interna é identificado para não cancelar seu próprio
plano. Um plano só cancela o filho que ainda pertence ao seu action_id;
comandos substitutos e outros NPCs não são cancelados.

Além da geração/posse já existentes, há exclusividade do objeto físico durante
a interação: outro NPC não pode alternar a mesma porta/janela simultaneamente.
Ocupação nos dois lados também pode recusar uma operação por segurança.

Ao surgir ameaça durante orientação, a operação é recusada. Dentro da animação
Java, o cancelamento fica pendente até IdleState seguro ou morte, sem forceStop
da animação. O plano não continua após esse cancelamento. A fuga local pode
agir quando a trava física for liberada. Uma animação Java que nunca retorne
ao estado seguro pode manter a trava: timeout não força uma saída insegura.

## Telemetria

Cada ação física informa action_id, ação, objeto/índice/posição, posição inicial
e final reais, duração, estado aberto antes/depois, passage_clear, resultado,
queda de saúde observada e ameaça antes/depois. Logs ARAY-PHYSICAL e
ARAY-LOCOMOTION registram início, resultado e falha por UUID.

O plano agrega distância/duração/dano amostrados e guarda os resultados
estruturados de cada filho, além de requested_steps e motivo de encerramento.
Etapas rejeitadas antes de executar têm executed=false e dano desconhecido,
sem inventar zero ou sucesso. A coleta de ameaça reutiliza observeThreats,
sem consumir evidências do monitor de emergência.

Consultas: Navigation.getState(uuid), Navigation.getResult(uuid,action_id),
Locomotion.getResult(uuid,child_action_id) e Physical.getResult(uuid,action_id).
Há até 16 resultados por UUID em cada histórico, com cópias e invalidação
por mundo. Physical conserva a observação do término nativo mesmo quando o
plano já foi cancelado; seu callback não pode reativar a sequência antiga.
São dados em memória, sem SQLite e sem recompensas de RL.

## Arquivos e validação

Criados: ArayHumanNavigation.lua, ai/test_navigation.py e este relatório.
Alterados: ArayHumanPhysical.lua, ArayHumanExecutor.lua,
ArayHumanLocomotion.lua (posições inicial/final nas observações) e
ai/test_executor.py (carrega o módulo novo na suíte).
Walking, Perception, EscapePlanner e comandos existentes são reutilizados.

Suíte completa: **319 testes aprovados** — 277 anteriores e 42 novos casos
em Lua 5.1/5.4. Comando: `python -B -m pytest ai -q -p no:cacheprovider`,
usando o runtime Lupa temporário anterior. Módulos e ações Lua reais são
executados com Java/movimento/animações simulados; não é teste do motor em jogo.

Cobertura: portas abertas/fechadas/trancadas, fechamento recusado pelo nativo,
idempotência, três sequências compostas, janela aberta/fechada/vidro, cerca
baixa/alta/piso sem apoio, Z/escadas recusados, ameaça do outro lado e durante
animação, confirmação de chegada, callbacks antigos, cancelamento entre etapas
e em animação, comando substituto, dois NPCs, exclusividade de objeto, tokens
por UUID, objeto trocado, chunks e mundo indisponíveis, troca de mundo durante
animação, APIs ausentes, timeout, replay e preservação do jogador.

Sem jogo/serviços, RL, treinamento, decisões contínuas ou combate. Sem mudanças
em FBO, câmera, balões, JARs, saves, SQLite, modelo ou commit/push. A política de
tentativas de fuga da base permanece; a 3C.3.5 cancelada não foi retomada.
Validação manual ainda é necessária para colisões, animações e comportamento
real de NPCs na instalação. Aguardar instruções antes da 3C.4C.
