# 3C.4B.1 — investigação de empurrão e escadas

## Resultado e alcance

Base verificada: 319 testes. Resultado final: **347 testes aprovados**.

Esta entrega implementa diagnóstico de capacidades, recusas explícitas nas
interfaces e validações adicionais da avaliação de empurrão. **Não implementa
empurrão físico nem habilita navegação entre andares.** Os dois recursos continuam
UNSUPPORTED pelos motivos específicos abaixo. A existência de métodos nativos
foi confirmada; isso não constitui validação de uso seguro pelo mod.

Não houve teste no jogo, inicialização de serviços, instalação de dependências de
terceiros no mod, alteração da instalação do jogo ou commit/push. A fase 3C.3.5
cancelada não foi restaurada. A fuga existente e suas limitações permanecem.

## Pesquisa de fontes e licenças

Foram examinados os arquivos dos três repositórios em revisões fixadas. Nenhum
trecho de código desses projetos foi incorporado ao mod ou aos testes.

| Projeto | Revisão examinada | Licença encontrada e consequência |
|---|---|---|
| PZNS | `20a30212f98aa891aec9cb070bb96164be27c12a` | MIT, copyright shadowhunter100; eventual reutilização exige preservar o aviso. Não foi necessária reutilização. |
| ProjectHoomans | `2bc4810f352929222723614a6506853428cd3a73` | Não foi localizada licença geral no conteúdo examinado. A licença WordNet encontrada refere-se à dependência, não concede licença ao framework. Código não reutilizado. |
| KnoxSurvivors | `543b4eada2bbc564a908294873ec6ed34d94c1b2` | All Rights Reserved; reutilização e adaptação dependem de autorização do autor. Código não reutilizado. |

### PZNS

[PZNS_WeaponAttack.lua](https://github.com/Project-Zomboid-Community-Modding/PZNS/blob/20a30212f98aa891aec9cb070bb96164be27c12a/PZNS_Framework/media/lua/client/05_npc_actions/PZNS_WeaponAttack.lua)
usa `NPCSetAttack(true)` e uma cadeia própria de tratamento de golpes, incluindo
`PZNS_WeaponSwing`, `calculateNPCDamage` e `victim:Hit(...)`. Não foi encontrado
ali um empurrão nativo com alvo exclusivo e confirmação física que atendesse às
restrições desta fase. A chamada manual de Hit foi descartada.

[PZNS_RunTo.lua](https://github.com/Project-Zomboid-Community-Modding/PZNS/blob/20a30212f98aa891aec9cb070bb96164be27c12a/PZNS_Framework/media/lua/client/05_npc_actions/PZNS_RunTo.lua)
utiliza `PathFindBehavior2:pathToLocation`, passando Z do destino. Isso é referência
de encaminhamento ao motor, não prova de validação segura entre andares na B42.13.1.
[Licença MIT](https://github.com/Project-Zomboid-Community-Modding/PZNS/blob/20a30212f98aa891aec9cb070bb96164be27c12a/LICENSE).

### ProjectHoomans

O arquivo examinado está no diretório `42.20`:
[PNC_Combat_Unarmed.lua](https://github.com/psychopatz/ProjectHoomans/blob/2bc4810f352929222723614a6506853428cd3a73/Contents/mods/ProjectHoomans/42.20/media/lua/shared/PNC/Core/Combat/PNC_Combat_Unarmed.lua).
`PlayShove`/`ApplyZombieShove` trabalham com corpos de zumbi e um subsistema próprio
de reação; o fallback usa `setAttackedBy`, `setHitForce` e `setStaggerBack`.
[PNC_Combat_ZombieReaction_Shove.lua](https://github.com/psychopatz/ProjectHoomans/blob/2bc4810f352929222723614a6506853428cd3a73/Contents/mods/ProjectHoomans/42.20/media/lua/shared/PNC/Core/Combat/PNC_Combat_ZombieReaction/PNC_Combat_ZombieReaction_Shove.lua)
mantém estado de reação e parâmetros próprios de deslocamento. Esse mecanismo
não comprova empurrão de um IsoPlayer com setNPC(true) e não foi reproduzido.

A pesquisa de caminho em
[VanillaAndAnimalPathing.md](https://github.com/psychopatz/ProjectHoomans/blob/2bc4810f352929222723614a6506853428cd3a73/docs/Research/VanillaAndAnimalPathing.md)
discute rotas de zumbis/animais e delegação de travessias. Não é evidência suficiente
para habilitar nossa navegação vertical. A árvore e arquivos de licença foram
examinados; não se assumiu licença permissiva pela visibilidade pública.

### KnoxSurvivors

O [README da revisão](https://github.com/exe-create/KnoxSurvivors/blob/543b4eada2bbc564a908294873ec6ed34d94c1b2/README.md)
declara alvo 42.20–42.21. Foram examinados `KnoxCombatController.java`,
`KnoxTraversalPolicy.java`, `KnoxCombatGate.java`, `KnoxHumanCombatGate.java` e
a estrutura de transformadores Java. O controlador articula autorizações de
ataque, shove, pressedAttack e entrada em SwipeStatePlayer, com infraestrutura
própria de controle de combate. Isso não fornece uma solução Lua transplantável
e comprovada para nossa versão e isolamento de aliados.

[Código do controlador](https://github.com/exe-create/KnoxSurvivors/blob/543b4eada2bbc564a908294873ec6ed34d94c1b2/java/src/main/java/com/knoxsurvivors/npc/KnoxCombatController.java).
[Licença restritiva](https://github.com/exe-create/KnoxSurvivors/blob/543b4eada2bbc564a908294873ec6ed34d94c1b2/LICENSE.md).
Não foram carregados agentes, classes, JARs ou patches desse projeto.

## Evidência local B42.13.1

Inspeção somente para leitura com `javap -c -p` e leitura dos Lua instalados em
`E:/Games/Project.Zomboid.v42.13.1/game`.
SHA-256 do `projectzomboid.jar` examinado:
`9F626AD644311AB301F8ABCD22AC93476B59B194BFF3147573DF96E3EAC86C2E`.

| Classe/arquivo | Evidência confirmada | Limite da conclusão |
|---|---|---|
| IsoGameCharacter.NPCSetAttack(boolean) | Escreve humanControlVars.initiateAttack | Não recebe alvo nem restringe atingidos a zumbis |
| IsoGameCharacter.NPCSetMelee(boolean) | Escreve humanControlVars.melee | Não confirma shove, alvo ou resultado |
| IsoAIModule.postUpdate | Propaga initiateAttack ao IsoPlayer | Intenção não equivale a colisão ou sucesso |
| IsoLivingCharacter.setDoShove | Método disponível | Uma flag não constitui ação concluída |
| IsoPlayer | pressedAttack, DoAttack, setAuthorizeMeleeAction, setAuthorizeShoveStomp, autorizações hand-to-hand disponíveis | Autorização global da ação não é filtro exclusivo de alvo |
| CombatManager.calcHitListShove | Método privado percorre IsoCell.getObjectList, considera IsoGameCharacter e chama checkPVP | Não há filtro fornecido pelo nosso UUID/roster; aliados não são excluídos pelo contrato do mod |
| SwipeStatePlayer | Colisão da animação delega ao CombatManager | Não foi encontrado ponto Lua seguro para substituir somente a seleção de atingidos |
| ISWalkToTimedAction:start/update | Passa X/Y/Z a pathToLocation e consulta BehaviorResult | Resultado nativo ainda precisa de confirmação posicional real |
| zombie.pathfind.PathFindBehavior2 | pathToLocation/LocationF e requisições com startZ/targetZ existem | Aceitar Z não valida os candidatos e ameaças do mod |
| IsoMovingObject.doStairs | Usa escada atual/anterior e getApparentZ com X/Y fracionários; chamado pelo motor | Transição vertical nativa existe; não deve ser simulada nem chamada manualmente para corrigir Z |
| IsoGridSquare | HasStairs, HasStairTop, HasStairsBelow, isSameStaircase, isStairBlockedTo, getStairsDirection/Height, isStairsEdgeBlocked disponíveis | Flags isoladas não demonstram rota completa, patamar livre ou segurança do outro andar |

O ajuste nativo de Z em doStairs faz parte da física do jogo. Não há setter de Z
ou chamada manual a doStairs introduzida no mod. Não foi encontrado impedimento
genérico a NPCs no trecho de doStairs: **o bloqueio atual de escadas é da integração
e validação do mod, não uma alegação de ausência da física no jogo**.

Para navegação vertical faltam candidatos verificáveis por UUID/mundo que
representem escada e patamares carregados, validação das arestas entre Z,
percepção de ameaças nos andares envolvidos e revisão dos monitores que hoje
exigem o mesmo andar. Habilitar apenas o destino Z burlaria essas garantias.

## Alterações implementadas

1. `42/media/lua/client/ArayHumanPhysical.lua`:
   - `unsupportedReason(action)` centraliza os motivos e preserva o alias STAIRS.
   - `inspectCapabilities(uuid)` retorna UUID, mundo, horário, presença de APIs,
     posição fracionária/tile e flags locais de escada. Leitura O(1), sem varredura,
     novos ticks ou execução física; cada chamada produz tabelas independentes.
   - Ausência/erro nas APIs de escada produz `known=false`, nunca um falso zero.
   - Avaliação defensiva exige ator carregado, evidência fresca/completa, alvo
     IsoZombie vivo ainda no tile carregado, altura próxima, alcance de 1,25 tile,
     orientação e aresta transitável quando em tile diferente.
   - No máximo 32 registros de ameaça e 32 entidades examinadas; dados incompletos
     recusados. Cooldown de diagnóstico de 2000 ms por UUID e mundo.
   - Zumbi elegível continua retornando UNSUPPORTED; log inclui distância e
     `executed=false`. Não há ataque, dano, animação falsa ou resultado de sucesso.
2. `42/media/lua/client/ArayHumanExecutor.lua`:
   - Reconhece os nomes PUSH_ZOMBIE/CLIMB_STAIRS e devolve o motivo auditado após
     validar identidade, mundo e metadados, antes de cancelar qualquer ação.
   - Pedido recusado não interrompe fuga, caminhada ou animação nativa, nem
     registra comando manual prioritário. Nenhum novo callback físico foi criado.
3. `42/media/lua/client/ArayHumanNavigation.lua`:
   - Preflight usa os mesmos motivos; uma sequência com recurso indisponível
     é recusada inteira antes da primeira caminhada.
4. `ai/test_unsupported_resources.py`: 14 cenários executados em Lua 5.1 e 5.4
   por Lupa; 28 novos testes.
5. Este relatório.

Walking, Perception e EscapePlanner foram inspecionados e não alterados.
PUSH_ZOMBIE e CLIMB_STAIRS não entram em Physical.actions e não são anunciados
como candidatos executáveis. Ações existentes de portas/janelas/cercas permanecem.

Exemplo abreviado da consulta, com valores ilustrativos:

```json
{
  "uuid": "11111111-1111-1111-1111-111111111111",
  "world_id": "Sandbox/Exemplo",
  "PUSH_ZOMBIE": {
    "supported": false,
    "reason": "UNSUPPORTED_target_exclusive_native_shove"
  },
  "CLIMB_STAIRS": {
    "supported": false,
    "reason": "UNSUPPORTED_STAIRS_VERTICAL_VALIDATION",
    "has_stairs": {"known": true, "value": false}
  }
}
```

## Testes e validação manual

Comando de regressão: `python -B -m pytest ai -q -p no:cacheprovider`, com
PYTHONPATH apontando ao runtime Lupa temporário já utilizado pelas fases anteriores.

- Regressão anterior isolada após as alterações: **319 passed in 14.19s**.
- Suíte final completa: **347 passed in 15.17s**.
- Os 28 testes novos cobrem zumbi elegível sem execução, exclusão de jogador e
  aliado, alcance, orientação, parede, alvo morto/movido/outro Z, evidência inválida,
  limites de leitura, APIs ausentes/com erro, dois NPCs/cooldowns/mundo,
  preservação de caminhada, recusa de sequência, cancelamento durante animação,
  escada detectada sem mudança artificial de Z e controle do jogador preservado.

Os testes novos verificam **recusa segura**, não sucesso de shove ou travessia
vertical. APIs Java são simuladas no harness; Lua de produção é executado de
verdade. A inspeção estática confirma métodos e fluxos, mas não reproduz física,
colisão, animação e escolha de atingidos do motor em execução.

Não há novo empurrão ou subida de escada para anunciar como funcional em teste
manual. Antes de habilitar shove, será necessário comprovar filtro nativo que
exclua jogador/aliados inclusive durante a animação e observar colisão/resultado
real. Para escadas, será necessário completar a validação vertical acima e testar
subida/descida, patamares, bloqueios, mudança de mundo e cancelamento em Z
fracionário, sempre deixando a transição física sob responsabilidade do motor.

Não avançar à 3C.4C sem novas instruções.
