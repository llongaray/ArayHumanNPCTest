# 3C.4D — inventário e sobrevivência simplificada

## Resultado

Implementadas ações explícitas PICKUP_ITEM, LOOT_CONTAINER, TRANSFER_ITEM e BANDAGE,
com validação local, propriedade por UUID, cancelamento e confirmação dos efeitos.
São experimentais em singleplayer: APIs e Lua vanilla foram auditados, mas não
houve execução no jogo. Multiplayer é recusado.

**Fome, sede e fadiga não foram desligadas artificialmente.** Não foi encontrado
um controle nativo individual seguro que desative apenas essas necessidades e
preserve saúde, endurance e jogador. A exceção prevista na regra principal foi
aplicada: desativação física continua UNSUPPORTED, claramente identificada no
Survival. Seus objetivos/recompensas futuros ficam excluídos do contrato para RL.

Regressão completa: **475 testes aprovados**, incluindo os 413 anteriores.

## Auditoria de necessidades

Instalação examinada, somente para leitura:
`E:/Games/Project.Zomboid.v42.13.1/game`.
SHA-256 do JAR:
`9F626AD644311AB301F8ABCD22AC93476B59B194BFF3147573DF96E3EAC86C2E`.

Foram inspecionados IsoGameCharacter, IsoPlayer, IsoAIModule, Stats, CharacterStat,
CheatType, PlayerCheats, LuaHookManager e Event com javap, além dos Lua vanilla.

| Opção investigada | Evidência e decisão |
|---|---|
| setNPC(true) | Marca a instância como NPC; não fornece contrato individual de desligamento de HUNGER/THIRST/FATIGUE |
| Stats.set/reset | Alteram valores atuais; não desabilitam seu crescimento. Não usados para zerar/manter necessidades |
| getHungerMultiplier/getThirstMultiplier/getFatigueMod | Getters, sem setter individual auditado para desligamento estável |
| GodMode/health cheat | Afetam saúde e/ou outras condições; GodMode também reseta Stats no motor. Descartados |
| UnlimitedEndurance | Altera resistência de esforço, que precisa ser preservada. Descartado |
| CalculateStats hook | O retorno do hook interrompe o cálculo antes de updateEndurance, updateThirst, stress, wake state, morale e fitness. Não é filtro isolado das três necessidades |
| Sandbox/global options | Afetariam também o jogador/mundo. Não alteradas |
| AutoDrink | setAutoDrink é consultado no ramo servidor; não resolve o ramo singleplayer auditado. A opção Core é global e não foi alterada |

Uma descoberta importante: LuaHookManager.TriggerHook usa Event.trigger, que
retorna false sem callbacks e true após despachar callbacks, independentemente
do retorno Lua de um filtro individual. Portanto não se instalou um hook global
CalculateStats/AutoDrink que aparentasse filtrar NPCs mas alterasse o jogador.
O uso vanilla de Hook.AutoDrink em ISInventoryPaneContextMenu também foi examinado.

O módulo não chama Eat, DrinkFluid, autoDrink, REST ou setters de Stats. A
auto-hidratação já existente no motor não foi desativada: autoDrink pode continuar
dependendo da configuração nativa e de fontes de água presentes. A entrega não
promete bloquear essa simulação interna; não acrescenta consumo automático.

### Contrato Survival atualizado

`snapshot.needs_policy` e `Survival.getNeedsPolicy()` informam, para hunger,
thirst e fatigue:

```json
{
  "requested_disabled": true,
  "rl_objective": false,
  "effective_disabled": {
    "known": false,
    "status": "unsupported",
    "reason": "UNSUPPORTED_isolated_native_need_switch"
  }
}
```

Os valores brutos e rótulos observados permanecem honestos; HUNGRY e THIRSTY
recebem planning_eligible=false. EXHAUSTED explicita que somente endurance deve
ser usada como base de planejamento, excluindo fadiga. Endurance permanece
observável e inalterada. O contrato marca recompensas de alimentação, água e
descanso como false; não há cálculo de recompensa nesta fase.

Saúde, ferimentos, sangramento, infecção, dor, pânico e morte continuam sendo
observados. EAT, DRINK e REST permanecem não executáveis. BANDAGE passa a indicar
a capacidade real do Inventory quando suas dependências nativas estão disponíveis.

## Inventário e ações nativas

Criado `42/media/lua/client/ArayHumanInventory.lua`.

| Ação | Mecanismo verificado e utilizado | Confirmação |
|---|---|---|
| PICKUP_ITEM | ISGrabItemAction:new(character, worldItem, time), ação vanilla completa | Mesma instância InventoryItem está no NPC, saiu do chão e perdeu worldItem |
| LOOT_CONTAINER | Ação temporizada própria baseada em ISBaseTimedAction; delega o movimento real ao helper vanilla ISTransferAction:transferItem | Item saiu do recipiente fonte e está no inventário do NPC |
| TRANSFER_ITEM | Mesmo adaptador e helper, do inventário do NPC para recipiente de mundo validado | Mesmo item no destino e ausente na fonte |
| BANDAGE | ISApplyBandage:new(npc, npc, item, bodyPart, true), implementação vanilla de complete/perform | Parte realmente bandaged e item removido do inventário |

A ação UI padrão ISInventoryTransferAction foi auditada, mas não usada como
adaptador: seu isValid consulta ISInventoryPaneContextMenu.getContainers, que
percorre os painéis getPlayerInventory/getPlayerLoot pelo playerNum. O adaptador
mantém a fila nativa e a animação Loot, delegando apenas a transação ao helper
vanilla, com fonte/destino já verificados. Não copia sua seleção de UI.

ISApplyBandage.complete usa os mecanismos de tratamento do jogo, incluindo
SetBandaged e remoção do item. O mod não chama SetBandaged diretamente, não
escreve saúde e não reproduz cura com setters. São observados os efeitos da ação
original; o tratamento não exige nem promete aumento imediato da saúde.

Também foram verificados: InventoryItem.getID/getContainer/getWorldItem,
getActualWeight/isCanBandage/getBandagePower; ItemContainer.hasRoomFor,
isItemAllowed/isRemoveItemAllowed/isExistYet; IsoObject.getContainerCount,
getContainerByIndex/getObjectIndex; IsoThumpable.isLockedToCharacter;
IsoWorldInventoryObject.getWorldPosX/Y/Z; BodyPart.HasInjury/getIndex/bandaged;
IsoGameCharacter.hasTimedActions/getCharacterActions; BaseAction.forceStop e
LuaTimedActionNew.complete/perform.

## Escopo e validações

- Instância real do roster, UUID, mundo, vida, tile carregado e exclusão do
  sobrevivente controlado são verificados novamente antes das mutações.
- Descoberta limitada ao inventário principal e ao tile atual/quatro vizinhos
  cardinais, alcance de 1,5 tile. Itens no chão usam posição fracionária nativa;
  posição desconhecida é recusada. Paredes e níveis diferentes impedem acesso.
- Recipientes aceitos: móveis comuns IsoObject/IsoThumpable, tipos crate,
  counter, shelves, locker e wardrobe. Objeto, índice, lista do tile, parent,
  sourceGrid e ligação do container ao objeto precisam continuar válidos.
- Trancamento e permissões nativas de remoção/aceitação são respeitados. Não
  são abertos recipientes trancados artificialmente.
- Inventários de jogadores/outros NPCs, cadáveres, veículos, recipientes dentro
  de bolsas e aparelhos especiais não são alvos desta versão.
- Itens equipados, nas mãos, anexados ou favoritos não são enviados/consumidos.
  Bolsas como objetos transferíveis, rádios e lanternas/velas acesas são excluídos
  por seus efeitos adicionais de criação/substituição na lógica vanilla.
- Entrada exige hasRoomFor/isItemAllowed e peso previsto dentro de getMaxWeight;
  saída exige isRemoveItemAllowed. Capacidade é conferida novamente no impacto.
- BANDAGE é tratamento próprio: ferimento existente, sem bandagem atual, item
  real utilizável, limpo e não infectado no inventário do próprio NPC.
- Ameaça atual precisa estar completa/fresca; perigo imediato impede execução.
  O teste é repetido antes do perform/complete mutante. Durante a ação, novas
  verificações espaciais ficam limitadas a 250 ms, preservando o monitor existente.

LOOT_CONTAINER transfere um InventoryItem por pedido, não esvazia automaticamente
um recipiente. TRANSFER_ITEM nesta fase é NPC → recipiente comum do mundo;
transferências entre personagens, bolsas internas e descarte no chão não foram
habilitados. Quantidade 1 representa um objeto nativo; não há divisão de pilhas,
geração de recursos ou alteração de quantidade por setters.

## Contrato estruturado

```lua
local snapshot = ArayHuman.Inventory.getSnapshot(uuid)
local capabilities = ArayHuman.Inventory.getCapabilities()
local active = ArayHuman.Inventory.getState(uuid)
local result = ArayHuman.Inventory.getResult(uuid, action_id)
```

Snapshot contém UUID/mundo/timestamp, available, items, peso/capacidade,
recipientes observados, scan, capabilities e candidates. item_id é composto por
UUID e ID nativo, enquanto native_item_id preserva o número original. Esses IDs
de leitura não autorizam ação: apenas target_id resolve uma capacidade privada.

Cada candidato tem action, target_id, UUID/mundo, item, quantidade, índice da parte
quando aplicável, fonte e validade. O registro privado retém as referências reais;
troca de mundo, identidade, objeto, fonte, destino, ID ou expiração invalida a ação.
Validade padrão: 10 s; relógio e revalidações do executor também continuam valendo
para o pedido. Limites padrão: 128 itens examinados, 64 objetos, 256 candidatos,
32 partes para oferecer bandagem e 4 recipientes por objeto.

Exemplo de pedido local explícito, usando um candidato realmente retornado:

```lua
ArayHuman.Executor.requestLocomotion({
    uuid = uuid,
    world_id = snapshot.world_id,
    action = candidate.action,
    target_id = candidate.target_id,
    action_id = "inventory:manual:001",
    source = "manual"
})
```

Não há coordenadas, item inventado ou destino arbitrário nesse contrato.
IDs de ação duplicados continuam recusados pelo executor. Capabilities marca as
ações disponíveis como experimental_native_singleplayer e manual_validation=pending.

Os mesmos pedidos podem ser etapas de Navigation. Cada etapa espera o resultado
confirmado anterior. Para usar uma bandagem recém-coletada, obter novo snapshot
após a coleta e então solicitar BANDAGE: antes da coleta ela ainda não pertence
ao inventário do NPC e não autoriza um alvo de tratamento.

## Cancelamento, prioridades e resultados

Uma trava por UUID impede sobreposição com caminhada/interação física; uma trava
por item impede dois NPCs do mod de coletarem ou consumirem a mesma instância.
start/update/isValid/perform/complete/transferItem/stop são protegidos na instância
da ação, preservando as classes vanilla globais e o jogador.

Cancelamento invalida mutações antes de solicitar forceStop nativo. Não força
estado/animação por setters. A trava permanece até o estado ser seguro e a ação
sair de getCharacterActions. Se essa confirmação ficar indisponível, getState
expõe CANCEL_PENDING/native_stack_unavailable e preserva a trava. Não assume
conclusão por apenas IdleState ou por uma callback de fila.

Callbacks antigos não substituem gerações novas. Comando manual de cancelamento
interrompe somente o UUID correspondente. STOP aguarda retirada nativa segura.
Emergência solicita cancelamento do inventário antes de planejar fuga; não
consome tentativas de fuga enquanto aguarda a retirada. Os demais orçamentos e
comportamentos de fuga permanecem os mesmos.

Resultados estruturados em Inventory.getResult incluem item/ID, quantidade,
peso antes/depois, duração, saúde antes/depois, bandagem confirmada, tentativa de
mutação e erro nativo. Bandagem consumida informa quantity_consumed. Há até 16
resultados por UUID, copiados na leitura, e logs ARAY-INVENTORY por ação.
Executor/Locomotion recebem o resultado durante execução normal; após cancelamento,
consultar também Inventory.getResult para a observação final sem sobrescrever
o novo comando do NPC. Survival é atualizado após um resultado válido.

Uma falha nativa depois de retirar o item da fonte pode ser parcial. O resultado
registra falha/observações reais; não tenta rollback criando item, repetir a
transferência ou declarar sucesso. Da mesma forma, cancelar depois de uma mutação
já concluída não restaura magicamente o recurso. Isso requer conciliação pelo
consumidor do resultado, sem repetição automática nesta fase.

## Arquivos

- Criado `42/media/lua/client/ArayHumanInventory.lua`.
- Modificados `ArayHumanSurvival.lua`, `ArayHumanPhysical.lua`,
  `ArayHumanExecutor.lua` e `ArayHumanNavigation.lua`, na mesma pasta client.
- Criado `ai/test_inventory_actions.py`; modificado `ai/test_executor.py` para
  carregar a nova dependência no harness existente.
- Criado este relatório.

Locomotion, Walking, Perception, F7, chat, persistência, modelo, renderização,
câmera e balões não tiveram seus arquivos alterados nesta fase. PUSH_ZOMBIE e
CLIMB_STAIRS conservam UNSUPPORTED e os diagnósticos atuais. A whitelist de decisões
Ollama não foi ampliada; os pedidos novos são locais e explícitos.

## Testes e limitações para validação manual

Comando: `python -B -m pytest ai -q -p no:cacheprovider`, com Lupa temporário já
disponível. **475 passed in 19.08s**: 413 anteriores e 62 novos, em Lua 5.1/5.4.

O harness executa ISGrabItemAction.lua, ISTransferAction.lua e ISApplyBandage.lua
originais da instalação, junto do código do mod; as classes Java e filas são
simuladas. Testes cobrem inventário vazio/cheio, peso, coleta, transferência,
ferimento/bandagem real no modelo simulado, duas ordens possíveis de complete/
perform, consumo único, itens sujos/infectados, dois NPCs, disputa do mesmo item,
cancelamento, callbacks antigos, retirada nativa, mundo/chunk, trancas, paredes,
IDs/validade, API ausente/falha parcial, emergência e sequência finita.

Também verificam que nenhum método do inventário do jogador é usado para obter
itens, que não se chama Eat/Drink/Rest e que necessidades/endurance não recebem
setters. O teste de necessidades valida a recusa honesta do desligamento físico
e o bloqueio de objetivos; não simula uma desativação nativa inexistente.

Falta validar no jogo: execução de Loot/Bandage por IsoPlayer.setNPC(true), ordem
real de complete/perform, retirada de animação/fila após cancelamento e confirmação
de inventário/ferimento. O tratamento não é anunciado como compatibilidade já
comprovada em execução real. Inventários grandes, bolsas internas e multiplayer
permanecem limitações explícitas.

Nenhum jogo/serviço iniciado, Java/JAR/executável/save/SQLite existente alterado,
commit/push, RN/RL, treinamento ou autonomia contínua. Aguardar instruções antes
da 3C.4D.1.
