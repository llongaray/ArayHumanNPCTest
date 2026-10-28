# 3C.4B.2 — viabilidade de PUSH_ZOMBIE com zona de segurança

## Resultado

**PUSH_ZOMBIE permanece UNSUPPORTED.** Não foi comprovada uma zona que exclua
jogador e aliados durante toda a colisão nativa. Também foi identificado um
requisito de autoridade local no caminho de colisão de SwipeStatePlayer que não
é atendido apenas por `IsoPlayer.setNPC(true)`.

A regra de distância atual do jogador foi acrescentada à avaliação defensiva,
mas **não autoriza ataque**, mesmo quando satisfeita. Não há empurrão experimental
habilitado, animação iniciada, dano, deslocamento ou sucesso simulado.

Base: 347 testes. Suíte completa final: **375 passed in 15.05s**, incluindo
28 casos novos, executados em Lua 5.1/5.4 pelo harness existente.

## Instalação examinada e método

Leitura dos módulos do mod e inspeção de assinaturas/bytecode com `javap -c -p`
na instalação `E:/Games/Project.Zomboid.v42.13.1/game`.

SHA-256 do JAR examinado:
`9F626AD644311AB301F8ABCD22AC93476B59B194BFF3147573DF96E3EAC86C2E`.

Classes: `zombie.characters.IsoGameCharacter`, `IsoLivingCharacter`, `IsoPlayer`,
`IsoAIModule`, `zombie.CombatManager` e `zombie.ai.states.SwipeStatePlayer`.
O JAR foi somente lido. Nenhum código Java foi carregado no jogo ou modificado.

## Evidência do fluxo nativo

1. `NPCSetAttack(boolean)` escreve `humanControlVars.initiateAttack`;
   `NPCSetMelee(boolean)` escreve `humanControlVars.melee`. `IsoAIModule`
   propaga controles ao IsoPlayer. Nenhuma dessas chamadas recebe alvo exclusivo.
2. `setDoShove(boolean)` escolhe uma modalidade do ataque; não restringe quem
   pode ser atingido nem confirma colisão. Em `SwipeStatePlayer.doAttack`, a
   modalidade shove usa bareHands, mas isso não fornece exclusão por UUID.
3. `SwipeStatePlayer.enter` calcula AttackVars e inicializa `PARAM_ATTACKED=false`.
   O evento de animação `OnAnimEvent_AttackCollisionCheck` consulta esse parâmetro
   e chama `CombatManager.attackCollisionCheck` **somente se
   `IsoPlayer.isLocalPlayer(character)` for verdadeiro**.
4. `IsoPlayer.isLocalPlayer()` procura a instância em `IsoPlayer.players[]`, até
   `numPlayers`, e retorna falso em servidor. `setNPC(true)` não equivale a esse
   registro. O NPC do mod é criado separadamente e não é registrado como jogador
   local controlado. Não se tentou colocá-lo no array, trocar jogador/câmera ou
   chamar CombatManager diretamente para contornar esse requisito.
5. Em `CombatManager.attackCollisionCheck`, o estado de shove/AttackVars é
   atualizado e o método chama `calculateHitInfoList(character)` no ponto de
   colisão. Essa chamada ocorre depois do início da animação.
6. **Há cache:** a sobrecarga privada de `calculateHitInfoList` retorna quando a
   lista já está preenchida. Quando vazia e permitida pela autoridade, pode chamar
   `calcHitListShove` e selecionar personagens presentes naquele instante.
   Existem chamadas anteriores de cálculo em `pressedAttack`, realce de alvos e
   retículo. Logo, a conclusão correta é **pode selecionar no ponto de colisão**,
   não "sempre recalcula" nem "congela obrigatoriamente o alvo inicial".
7. `calcHitListShove` percorre objetos da célula e considera IsoGameCharacter;
   o descarte preliminar usa distância ao quadrado maior que 9. Esse limite de
   3 tiles é uma pré-filtragem, **não** a definição completa do golpe. A seleção
   usa posição geométrica do alvo, direção, ângulos da arma, postura,
   `isMeleeAttackRange`, linha de visão e obstáculos. Não recebe nosso alvo/UUID
   como uma lista exclusiva de permitidos. Limites de multi-hit também dependem
   de arma/modalidade e configuração, portanto não se presumiu um único atingido.
8. `checkPVP` pode excluir IsoPlayers em certas configurações — por exemplo,
   singleplayer com coop PvP desativado. Isso deve ser reconhecido, mas não é um
   filtro permanente do roster, nem habilita colisão para um atacante não local.
   Não foi alterada configuração de PvP para tentar viabilizar esta ação.

As assinaturas e o fluxo podem ser reproduzidos com:

```powershell
javap -classpath E:/Games/Project.Zomboid.v42.13.1/game/projectzomboid.jar -c -p zombie.ai.states.SwipeStatePlayer
javap -classpath E:/Games/Project.Zomboid.v42.13.1/game/projectzomboid.jar -c -p zombie.CombatManager
javap -classpath E:/Games/Project.Zomboid.v42.13.1/game/projectzomboid.jar -c -p zombie.characters.IsoPlayer
```

## Por que a zona inicial não resolve

Distância de 1,25 tile ao zumbi e mais de 2 tiles ao jogador são condições
necessárias solicitadas, não uma prova da geometria completa da colisão.
Um círculo de 2 tiles ou um cone baseado apenas na orientação atual não reproduz
a seleção nativa descrita acima, nem inclui necessariamente o movimento até o
evento de impacto.

Mesmo uma observação completa e recém-capturada descreve o presente. Jogador e
aliados podem entrar na área durante a animação; posição/orientação do atacante
também podem mudar. Não foi comprovado um envelope de movimento e duração que
garanta exclusão até o último impacto, nem um veto Lua por vítima, atômico à
seleção e aplicação nativas.

`OnWeaponSwingHitPoint` é disparado dentro de attackCollisionCheck por
`LuaEventManager.triggerEvent`, com retorno void. Não é um contrato de veto por
atingido. Uma verificação em OnTick tampouco é atômica com a colisão. Cancelar
posteriormente ou limpar uma flag não desfaz impacto já aplicado; forçar saída
de estado não foi adotado como proteção de animação.

Manipular diretamente listas internas de atingidos, trocar autoridade local,
invocar a colisão manualmente ou interferir em jogadores/aliados para congelar
o cenário não foi implementado. A investigação não estabelece que toda solução
futura seja impossível: estabelece que **esta integração Lua não possui uma
garantia verificada sob as regras desta fase**.

## Alterações

- `42/media/lua/client/ArayHumanPhysical.lua`: após reencontrar um zumbi vivo,
  carregado, alcançável, orientado e a até 1,25 tile, consulta novamente o
  sobrevivente atual. Jogador morto, ausente ou sem tile carregado retorna
  `shove_player_unavailable`; distância XY menor ou igual a 2 retorna
  `shove_player_too_close`. O limite é estrito e usa posição fracionária atual.
- A distância XY é conservadora mesmo com níveis Z diferentes; não há exceção
  que autorize ataque por andar. A consulta é diagnóstica e não certifica todos
  os jogadores de multiplayer ou o volume do golpe.
- Caso a distância permita continuar a avaliação, o resultado permanece
  `UNSUPPORTED_target_exclusive_native_shove`. Logs incluem distância do alvo,
  distância do jogador, `collision_zone=unknown`,
  `exclusion_during_animation=unproven` e `executed=false`.
- `inspectCapabilities(uuid).PUSH_ZOMBIE.safety_zone` explicita limites,
  geometria desconhecida, exclusão durante animação não comprovada, seleção
  possível no impacto, reutilização de lista preenchida e requisito de jogador
  local. Presença de APIs não habilita a ação.
- `ai/test_shove_safety_zone.py`: novos testes isolados.
- Este relatório.

Executor e Navigation continuam recusando PUSH_ZOMBIE antes de cancelar ações
existentes. Não há nova ação física, callback, evento ou monitor por frame.
Os limites de leitura e cooldown por UUID/mundo da fase anterior permanecem.
Não existe um caminho "revalidar e executar" nesta entrega: a avaliação sempre
para antes de qualquer chamada de ataque porque a prova de segurança falhou.

## Testes e limites da validação

Comando: `python -B -m pytest ai -q -p no:cacheprovider`, usando o runtime Lupa
temporário já disponível no ambiente.

Resultado dos novos testes: **28 passed in 0.73s**.
Regressão completa, incluindo os 347 anteriores: **375 passed in 15.05s**.

Casos novos: jogador a 1,999/2/2,001 tiles; alvo a 1,25/1,251; múltiplos zumbis;
aliados à frente/atrás/lateralmente; jogador entrando após captura; troca de
sobrevivente; percepção incompleta, antiga, futura e de UUID/mundo errado;
movimento de aliado após recusa; cancelamento sem reativação; animação externa
não interrompida; diagnóstico que permanece bloqueado mesmo com APIs presentes.
A regressão também cobre isolamento de dois NPCs e cancelamento por UUID.

São testes de recusas e preservação de estado, não de dano, colisão ou shove
bem-sucedido. No cenário de movimento após recusa nenhuma animação de shove
é iniciada. O teste de animação em andamento simula um estado externo; comprova
que a avaliação não o cancela nem inicia outro ataque. Não demonstra segurança
de um shove nativo em execução, que continua desabilitado.

Sem jogo/serviços iniciados, alterações em JAR/Java, simulação de empurrão,
commit/push ou avanço à 3C.4C. Aguardar novas instruções.
