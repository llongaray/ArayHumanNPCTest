# Fase 3C.1 — Percepção local por UUID

O módulo `42/media/lua/client/ArayHumanPerception.lua` observa o ambiente sem
executar ações, gerar NPCs, consultar Ollama ou gravar snapshots no SQLite.
`ArayHumanTest.lua` recebeu somente o acesso de leitura `getNpcByUuid(uuid)` ao
roster existente. Nenhuma troca de foco é realizada por esse acesso.

## API

```lua
local p = ArayHuman.Perception
local snapshot = p.updateSnapshot(uuid) -- coleta imediatamente; devolve cópia
local cached = p.getSnapshot(uuid)      -- cópia do cache ou nil; não varre ambiente
p.clearSnapshot(uuid)
p.clearAll()

p.config.intervalMs = 1000
p.config.radius = 10
p.config.maxEntities = 128
p.config.maxObjects = 128
p.config.maxTiles = 400
```

Limites defensivos: intervalo de 100 a 60000 ms, raio de 1 a 20 tiles,
entidades/objetos de 1 a 1024 e tiles de 1 a 1500. Configuração numérica inválida
usa o padrão. O orçamento de entidades inclui todos os ocupantes examinados,
inclusive o próprio NPC, o jogador e referências repetidas em diferentes tiles.

`OnTick` captura o roster no início de cada ciclo e distribui uma coleta por
tick. Um ciclo em andamento termina antes do próximo, evitando abandonar os
últimos NPCs em FPS baixo. Assim, 1000 ms é um intervalo nominal, não uma
garantia por NPC quando há mais NPCs que ticks disponíveis. Chamadas explícitas
a `updateSnapshot` não têm limitação temporal, mas respeitam os orçamentos.

## Dados e semântica

Cada snapshot contém UUID, mundo, timestamp, estado ativo e motivo de inatividade,
posição, direção, sobrevivente atual, distância planar e indicador de mesmo andar,
movimento, ordem, saúde, necessidades, NPCs/zumbis próximos, tiles, obstáculos,
portas e contadores de cobertura.

Campos opcionais usam `{ known = false }` ou `{ known = true, value = ... }`.
Zero e falso são valores conhecidos. Posições usam `known` e coordenadas.
Arrays vazios com `scan.complete = false` não comprovam ausência de entidades.
Não há serialização ou escrita de JSON no módulo; a representação é uma tabela Lua.

As entidades são candidatas espaciais no mesmo andar. Não são confirmadas por
linha de visão, audição ou visibilidade da câmera. Tiles fora de chunks carregados
não recebem classificação; incrementam `unavailable_tiles`. A classificação de
transitabilidade combina piso sólido e `isFree(false)`: não garante rota livre,
passagem entre tiles, ausência de paredes ou portas destrancadas. Obstáculos
indicam apenas tile sem piso sólido ou que não está livre. Portas expõem posição
do objeto e abertura conhecida quando disponível.

A ordem existente é global e não tem proprietário UUID. `order.known` permanece
falso, com motivo `legacy_global_order_not_attributed`; somente para o foco atual
é incluído `reported_global_name`, explicitamente não atribuído. Não se corrigiu
o sistema de ordens nesta fase.

NPC morto, com vida desconhecida, instância ausente ou square indisponível gera
snapshot inativo sem varredura. Leitura do cache invalida snapshot ativo após
perda da instância/square, morte ou troca do jogador; mudança de mundo invalida
todo o cache. A posição do jogador é recolhida novamente em cada coleta.
`clearAll()` limpa o estado imediatamente; o próximo tick pode repopulá-lo.

## APIs consultadas

- Mundo: `getWorld():getWorld()`, `getCore():getGameMode()`, `getCell()` e
  `getGridSquare()`.
- Identidade/posição: `getModData()`, `getCurrentSquare()`, `getX/Y/Z()`,
  `getDir()`, `isDead()`.
- Entorno: `getMovingObjects()`, `getObjects()`, `size()/get()`, `instanceof`,
  `TreatAsSolidFloor()`, `isFree(false)`, `IsoDoor:IsOpen()` e
  `IsoThumpable:isDoor()`.
- Movimento: `isWalking()`, `getCurrentActionContextStateName()` e
  `ISTimedActionQueue.hasActionType(character, "ISWalkToTimedAction")`.
- Saúde: `getBodyDamage():getHealth()`. Necessidades: `getStats():get()` com
  `CharacterStat.HUNGER`, `THIRST` e `FATIGUE`. Estes acessos foram conferidos nos
  scripts da instalação 42.13.1 e permanecem opcionais, protegidos contra falhas.
- Integração: `ArayHuman.getLocalPlayer()`, `getNpcByUuid()`, `rosterSnapshot()`,
  `getNpc()` e `getOrderName()`. Agendamento: `getTimestampMs()` e `Events.OnTick`.

Nenhuma referência Java é exposta no snapshot público. Cópias defensivas impedem
que consumidores alterem o cache ou os snapshots de outros NPCs.

## Custo e testes

Com raio 10, existem 317 offsets de tiles candidatos. Cada coleta examina no
máximo 317 desses offsets, 128 ocupantes e 128 objetos por padrão, mais consultas
constantes do NPC e do jogador. O custo é limitado por esses orçamentos; não há
varredura de listas globais de entidades. A enumeração do roster custa O(N) por
ciclo; a seleção dos offsets é ordenada e reconstruída somente quando muda o raio.
Não foi medido tempo em milissegundos no jogo.

`ai/test_perception.py` executa o módulo Lua de produção em Lua 5.1 e no runtime
padrão do Lupa, com mundo, jogadores, entidades, portas e filas simulados.
Cobertura: isolamento e cópias, troca/morte do sobrevivente, NPC morto, instância
e chunk ausentes, troca de mundo, identidade divergente, raio, três orçamentos,
APIs opcionais, valores zero/falso, obstáculos, cache, frequência e distribuição
sem inanição. APIs de ação, inferência, arquivos, câmera, visibilidade e varreduras
globais possuem contadores de acesso proibido, verificados em todos os testes.

Para executar, disponibilizar `lupa` no ambiente de teste e usar:

```text
python -B -m pytest ai -q -p no:cacheprovider
```

O runtime de teste foi instalado somente em diretório temporário. O jogo não foi
iniciado. A validação visual e a exposição efetiva dos métodos Java no motor
permanecem dependentes de verificação manual pelo usuário.

Resultado da execução nesta entrega: **68 testes passaram**, incluindo 18 casos
de percepção (9 cenários executados em dois runtimes Lua). Nenhuma API proibida
foi chamada nos testes de percepção.
