# 3C.4E.1 — perfil nativo e criação de NPCs

## Resultado

Implementados catálogo nativo, leitura de perfil, validação de builds, criação
opcional com bônus nativos e adaptador explícito para propostas Ollama. Nenhum
botão F7, loop de autonomia, treinamento ou recompensa foi acrescentado.

Aplicação é **experimental em singleplayer**: fontes Lua e bytecode Java da
instalação B42.13.1 foram inspecionados, e os testes executam o Lua de produção
com APIs Java simuladas. Compatibilidade no jogo ainda depende de teste manual.

## Arquivos

Criados:

- `42/media/lua/client/ArayHumanCharacterBuild.lua`.
- `ai/character_build_handler.py`.
- `ai/test_character_build.py`.
- `ai/test_character_build_handler.py`.
- Este relatório.

Modificados:

- `ArayHumanTest.lua`: hook opcional `config.characterBuild` no spawn existente.
  Sem esse campo, mantém o fluxo anterior. Validação acontece antes do construtor;
  aplicação/verificação antes de configureNpc/setNPC(true). Falha remove somente
  a instância recém-criada e usa a restauração de controle já existente.
- `ArayHumanLifecycle.lua`: identifica reconstruções como `restoring=true` quando
  há posição salva; não transmite builds nem repete bônus na restauração.
- `ArayHumanAgentState.lua`: substitui o perfil reservado por leitura nativa
  quando o módulo estiver disponível. Mantém versão 1 do perfil e campos
  desconhecidos/indisponíveis quando faltarem APIs ou dados.

Nenhum código Python de produção anterior, schema, banco existente, seleção de
modelo, JAR, executável, save, FBO, implementação de câmera ou balões foi alterado.
Jogo/serviços não foram iniciados; não houve commit ou push.

## Auditoria local B42.13.1

Fontes examinadas na instalação `E:/Games/Project.Zomboid.v42.13.1/game`:

- `media/lua/client/OptionScreens/CharacterCreationProfession.lua`: seleção,
  profissão no descritor, traços concedidos, exclusões, PointToSpend e
  negativeTraitOffset. As duas funções de pontos são executadas nos testes de
  comparação com a implementação do mod.
- `CharacterCreationMain.lua`, `CoopCharacterCreation.lua` e fluxo initWorld:
  nomes e descritor são preparados na UI; traços vão para LuaTraits do mundo.
  O mod não usa ou altera essa lista global do jogador.
- `media/scripts/generated/characters/character_professions.txt` e
  `character_traits.txt`: IDs, custos, grants e bônus reais desta instalação.
- Bytecode somente para leitura: SurvivorDesc, CharacterProfessionDefinition,
  CharacterTraitDefinition, CharacterTraits, PerkFactory/Perk, IsoGameCharacter,
  IsoGameCharacter.XP, IsoPlayer e IsoWorld.

APIs utilizadas:

| Finalidade | API |
|---|---|
| Catálogo | CharacterProfessionDefinition.getProfessions; CharacterTraitDefinition.getTraits |
| IDs e restrições | getType/getName, getCost, isFree, getGrantedTraits, getMutuallyExclusiveTraits |
| Bônus declarados | getXpBoosts e transformIntoKahluaTable |
| Orçamento | SandboxVars.CharacterFreePoints; getSandboxOptions().getOptionByName("NegativeTraitsPenalty").getValue |
| Descritor novo | setProfessionSkills e setCharacterProfession |
| Aplicação | IsoGameCharacter.applyTraits(ArrayList), applyProfessionRecipes, applyCharacterTraitsRecipes |
| Perfil | getDescriptor/getCharacterProfession; getCharacterTraits/getKnownTraits/get |
| Níveis e XP | PerkFactory.PerkList; Perk.getId/getTotalXpForLevel; getPerkLevel; getXp/getXP/getPerkBoost/getTotalXp/getLevel |

`getKnownTraits()` é filtrado pelo getter booleano do traço: traço conhecido não
é presumido ativo. APIs ausentes produzem desconhecido ou recusa segura.

O bytecode de **IsoWorld** chama applyTraits na criação vanilla. Em
**IsoGameCharacter.applyTraits**, o motor combina bônus de profissão/traços,
inclui base 5 em Fitness/Strength, limita os níveis a 0–10, ajusta XP ao nível e
limita o mapa de bônus de XP a 3. O mod chama esse mecanismo; não chama LevelPerk,
setPerkLevelDebug, AddXP, setXPToLevel ou setters de atributos para fabricar bônus.
Esses ajustes internos ao método vanilla não são substituídos por código Lua.

## Regras e exemplos reais

Saldo = custo/saldo-base da profissão + CharacterFreePoints − custos dos traços
escolhidos − penalidade por quantidade de traços negativos.

O valor da profissão é **somado**, como no vanilla. Traços concedidos pela
profissão/traços são incluídos e verificados sem cobrar novamente sua seleção.
Não se permite escolher manualmente um traço gratuito/de profissão ou de custo
zero, duplicar IDs ou combinar exclusões. Grants inválidos/cíclicos são recusados.

NegativeTraitsPenalty:

- 1: sem desconto adicional.
- 2: desconta floor(número de negativos / 3).
- 3: desconta floor(número de negativos / 2).
- 4: desconta max(0, número de negativos − 1).

Como no vanilla, a contagem considera os negativos da seleção efetiva, incluindo
os grants que façam parte dela. Opções desconhecidas não recebem defaults fictícios.

Exemplos lidos dos scripts locais, com CharacterFreePoints=0 e penalty=1:

| Profissão / traços | Saldo | Interpretação |
|---|---:|---|
| unemployed, sem traços | +8 | Válida, pontos sobrando/subótima quanto ao orçamento |
| unemployed + brave(4) + dextrous(2) + outdoorsman(2) | 0 | Válida, orçamento usado |
| unemployed + strong(10) | −2 | Inválida; recusada |
| carpenter, sem traços | +1 | Válida, sobra 1 ponto nesta B42 |
| strong + weak | — | Recusada por incompatibilidade |

Saldo zero não recebe avaliação de qualidade estratégica. Catálogo é lido das
definições carregadas; números dos exemplos não são constantes do algoritmo.
IDs públicos são getName() dos tipos nativos; colisões de nomes são recusadas.

## APIs Lua e criação explícita

```lua
local B = ArayHuman.CharacterBuild
local catalog = B.getCatalog()
local playerProfile = B.getPlayerProfile() -- somente leitura
local evaluation = B.validateProposal({
    schema_version = 1,
    profession_id = "unemployed",
    trait_ids = {"brave", "dextrous", "outdoorsman"}
})
local context = B.getProposalContext("Carpinteiro de apoio")
local npcProfile = B.getProfile(uuid)
local export = B.exportRecord(uuid) -- retorna dados; não grava arquivos/bancos
```

O produtor local autorizado pode passar a proposta validada em
`ArayHuman.spawnCarlos({uuid=uuidReal, characterBuild=proposal, ...})`. Usa o
spawn existente e identidade/mundo existentes. Não existe spawn automático a
partir de uma resposta do modelo. O usuário deverá disparar esse caminho por
integração explícita; nenhum controle novo foi colocado no F7.

Internamente:

1. prepareDescriptor valida UUID/mundo/autoridade singleplayer/catálogo/orçamento.
   Rejeita UUID existente e descritor do jogador ou de NPC registrado.
2. Configura o descritor novo com profissão e mapa de bônus nativos e emite token
   privado de uso único, limitado ao descritor, UUID, mundo e prazo.
3. Após IsoPlayer.new, applyCreated consome o token, revalida as regras/catálogo,
   verifica posse do descritor, personagem vivo ainda sem flag NPC e níveis zero.
4. Chama applyTraits e receitas nativas uma única vez; registra marcador APPLYING.
5. Confirma cada traço, níveis, XP total do nível e bônus de XP esperado. Falha
   não tenta corrigir via setters nem reaplica parcialmente: descarta a instância.
6. O spawn existente só então configura setNPC(true), UUID, nome e roster.

Restauração ou reutilização de uma instância não chama applyCreated novamente.
Marcadores FAILED/VERIFICATION_FAILED também impedem reaplicação na mesma
instância. Um token expirado, de outro mundo/descritor, ou já usado é recusado.

## Contrato Ollama

`ai/character_build_handler.py` fornece `propose(request, client, model)` e
`propose_for_world(request, ollama_state)`. Este último reutiliza o cliente HTTP
existente e lê a seleção de modelo por mundo; não escolhe nem salva outro modelo.

Entrada versionada, com kind=character_build_request, id, npc_id UUID real,
world_id, session_id, issued_at_ms, expires_at_ms e context. Context é o resultado
de getProposalContext(role), com perfil somente de jogo e catálogo local completo.
O serializador do futuro transporte deve representar arrays vazios como `[]`
e mapas como `{}`; não converter arrays vazios de traits/grants/excludes em mapas.

O contexto no prompt contém somente profissão, traços, níveis, XP, pontos
observados, papel e campos permitidos do catálogo. Nomes de jogador, contas,
posição, caminhos, campos extras e metadata externa não entram no prompt.
Estruturas aninhadas do perfil são validadas, não copiadas indiscriminadamente.

Resposta do modelo, e somente ela:

```json
{
  "schema_version": 1,
  "profession_id": "unemployed",
  "trait_ids": ["brave", "dextrous", "outdoorsman"]
}
```

Envelope retornado pelo adaptador, abreviado:

```json
{
  "kind": "character_build_response",
  "schema_version": 1,
  "ok": true,
  "executable": false,
  "validation": {
    "valid": true,
    "balance": 0,
    "budget_status": "fully_used",
    "strategic_quality": {"known": false, "reason": "not_evaluated"},
    "rewards": {"implemented": false},
    "learning": {
      "schema_version": 1,
      "reward": {"available": false},
      "penalty": {"available": false}
    }
  }
}
```

O envelope completo mantém IDs de pedido/NPC/mundo/sessão e expiração. JSON
incompleto, duplicação de chaves, NaN, IDs inexistentes, custos/skills/código
adicionais, incompatibilidades, duplicados e saldo negativo são recusados.
Custos são calculados a partir do catálogo, nunca da saída do modelo. A validação
Lua contra as definições nativas continua sendo a autoridade final.

Temperatura 0, até 768 tokens de saída, contexto 8192 e timeout HTTP de até 15 s,
reduzido pelo prazo restante. Pedido tem TTL máximo 30 s e limite 192 KiB;
o prompt usa catálogo compacto, preserva desconhecidos como null e recusa mais
de 24000 bytes em vez de truncar IDs/restrições silenciosamente. Esse limite de
bytes não é uma contagem exata de tokens do modelo selecionado.
catálogo deve ter captura recente e mundo correspondente. Resposta atrasada é
recusada. Falha/timeout retorna erro estruturado com executable=false.

**Sem operação nova na mailbox e sem loop de inferência.** O adaptador é uma
chamada explícita bloqueante para execução fora da thread da mailbox; não foi
inserido no caminho sequencial de persist/ping/chat. A ponte automática de
propostas para o jogo, autenticação/replay de transporte e UI ficam para fase
posterior. Sessão no envelope é correlação, não autorização para criar atores.

## Perfil e persistência

AgentState expõe profissão, traços ativos, cada habilidade com nível/XP/bônus,
XP global/nível quando disponíveis e initial_build quando aplicado pelo módulo.
O perfil é atualizado por consulta, com cache de 1000 ms, independente por
UUID/instância/mundo, e invalidação na morte/troca de jogador/mundo.

Não existe ponto disponível de criação confiável em um personagem já vivo.
No jogador/legados, points permanece desconhecido. Em NPCs criados pelo módulo,
points é o **saldo inicial registrado**, explicitamente não uma moeda gastável
durante progressão. XP global ou getXp().getLevel também não são anunciados como
pontos de profissão/traços disponíveis.

O marcador `modData.ARAY_CharacterBuild` contém versão, UUID/mundo, proposta,
validade, saldo, regras, traços efetivos, níveis esperados, timestamp e status.
exportRecord retorna esse registro inicial mais uma observação de progressão
real. Não escreve SQLite nem arquivos.

Auditoria do esquema atual: occupation/skills_json em npcs representam a
identidade narrativa; npc_state armazena posição/revisão. Não são uma gravação
completa dos níveis/XP nativos. O Lifecycle pode reconstruir outro IsoPlayer a
partir desses dados: **não se declara preservação de progressão entre essas
reconstruções nesta fase**. Não reaplicar bônus evita acumulação, mas não substitui
um mecanismo de restauração nativa completa.

Proposta futura, sem executar migração: entidade versionada de perfil nativo,
vinculada a mundo/UUID e revisão, com initial_build_json imutável e
progression_json observado separado. Atualizar pelo serviço de persistência
existente, com revisão transacional e migração explícita; não misturar com lore
ou substituir skills_json narrativo. Antes de habilitar restauração, definir e
auditar como serializar/carregar o estado nativo completo, sem reaplicar bônus.

## Limites e verificações

Catálogo: até 64 profissões, 256 traços, 128 habilidades; no máximo 32 traços
escolhidos e 128 traços efetivos. Excesso/dados incompletos são recusados.
Até 64 tokens preparados por mundo, TTL 30 s; até 128 perfis em cache. Não há
consulta pesada por frame nem novo OnTick. Obtenção do catálogo/proposta é explícita.

Testes: Lua real 5.1/5.4, funções de orçamento vanilla, custos da instalação,
hook de spawn de produção com construtor simulado, verificação de bônus/XP,
saldo positivo/zero/negativo, grants/incompatibilidades, falhas parciais,
recarregamento sem bônus duplicados, dois NPCs, jogador somente de leitura,
regras alteradas durante criação e Ollama simulado. Regressão completa dos 607
testes anteriores. Comando: `python -B -m pytest ai -q -p no:cacheprovider`, com
o runtime Lupa isolado já utilizado nas fases anteriores.

Resultado final: **725 testes aprovados** (607 anteriores + 118 novos).

JAR manteve SHA-256
`9F626AD644311AB301F8ABCD22AC93476B59B194BFF3147573DF96E3EAC86C2E`.

Validação manual futura: criação singleplayer com uma build real, confirmação
dos níveis/XP/receitas e controle do jogador, múltiplos UUIDs e comportamento ao
salvar/carregar. Não foram ativados combate, RL/RN, recompensas, penalidades de
morte, autonomia contínua ou inferência periódica. PUSH_ZOMBIE e CLIMB_STAIRS
continuam bloqueados. Necessidades e sua política anterior foram preservadas.

Aguardar instruções antes da 3C.5.
