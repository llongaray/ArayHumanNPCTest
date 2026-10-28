# Fase 3C.3.2 — fuga e trajetória nativa

## Causa verificada no código

O executor cancelava `escape_corridor_deviation` quando o tile sob a posição
fracionária não constava da sequência cardinal exata do planejador. Não havia
verificação de perigo ou colisão nesse cancelamento. O motor nativo pode suavizar
a caminhada, inclusive usando tiles laterais seguros.

`validateLeg` passava o tile atual e o próximo waypoint diretamente a
`Perception.edgePassable`. Essa API interna aceita apenas vizinhos cardinais:
tiles diagonais ou mais distantes retornavam false ANTES de consultar
`isBlockedTo`. O executor interpretava todos esses casos como parede real.
Os logs recebidos são compatíveis com essas duas falhas; não permitem determinar
qual obstáculo existia no cenário real. Três falhas ainda travavam a fuga até
três segundos de segurança, impossível enquanto o zumbi permanecesse perto.

## Correção

- EscapePlanner valida o segmento desde X/Y reais por travessia de grade
  (supercover), com até 24 transições e segmento máximo de 7 tiles. Cada
  transição usa tiles carregados, squareFree e isBlockedTo nos dois sentidos.
  Cantos exatos exigem as duas passagens cardinais livres; desconhecido bloqueia.
- Compacta a rota: o destino mais distante comprovadamente alcançável em linha
  segura vira alvo nativo. Conserva pontos de curva quando a geometria ou a
  distância dos zumbis impedir o atalho. Não substitui PathFindBehavior2.
- Remove a exigência de pertencer à lista exata de tiles. Revalida o trecho
  desde a posição fracionária atual a cada monitoramento. Desvio seguro continua;
  trecho com colisão ou aproximação perigosa cancela apenas o UUID proprietário.
- Falhas cancelam a geração antiga; após cooldown de 1 segundo, sob ameaça
  imediata confirmada, o planejador parte da posição atual. Destinos tentados
  continuam excluídos durante o episódio, impedindo repetir a mesma rota completa.
- Três tentativas por bloco; após 30 segundos permite recuperação, no máximo
  duas por episódio (até nove tentativas). Excluídos são preservados. Após esse
  teto, permanece explicitamente esgotado até novo episódio: segurança completa
  durante pelo menos 3 segundos redefine os limites. Não há repetição infinita.
- Walking expõe posição real, velocidade medida em tiles/segundo de relógio,
  deslocamento amostrado, distância restante, idade do último progresso, presença
  da ação própria na fila e resultado nativo. Amostra mínima de 250 ms; logs de
  progresso por UUID a cada segundo. Início de pathfinding não significa sucesso.
- Mantém timeout de emergência de 6 segundos e ausência de progresso de 1,5
  segundo, monitor de 250 ms com até dois NPCs por rodada, limite de seis tiles
  da fuga, exceção emergencial dos 12 tiles e validação local da ameaça.

## Diagnóstico

`route_edge_blocked` informa posição fracionária, origem/destino da aresta,
direção, API e resultado. `isBlockedTo` registra forward/reverse. A API fornece
bloqueio agregado: `collision_or_closed_edge` não afirma se era porta, parede
ou outro objeto. squareFree identifica ocupação/solidez agregada; não inventa
identidade do obstáculo. Tiles ausentes são registrados como unloaded.

## Arquivos e APIs

Alterados: ArayHumanEscapePlanner.lua, ArayHumanExecutor.lua,
ArayHumanWalking.lua, ArayHumanPerception.lua e ai/test_executor.py.
Criados: ai/test_escape_recovery.py e este relatório.

APIs reutilizadas: getCell/getGridSquare, getX/getY/getZ/getCurrentSquare,
TreatAsSolidFloor/isFree/isBlockedTo/getMovingObjects, PathFindBehavior2,
ISWalkToTimedAction e ISTimedActionQueue. Nenhuma nova API Java presumida.

## Testes e limites

Suíte Python e Lua real 5.1/5.4 com APIs simuladas e ação nativa Lua do jogo:
203 testes aprovados. Inclui curva, posição fracionária, diagonal falsa positiva,
parede de canto verdadeira, API ausente, bloqueio dinâmico, replanejamento,
callback antigo, recuperação persistente com teto, remoção de obstáculo,
telemetria e toda a regressão anterior (UUIDs, jogador, inferência e persistência).
O teste antigo que exigia cancelar desvio seguro foi atualizado para exigir
continuidade; a verificação de percepção incompleta usa agora threatConfig.

Sem jogo ou serviços iniciados. Nenhuma alteração em câmera/FBO/balões,
JARs, saves, SQLite ou modelo. Sem combate, decisões gerais, RL, commit ou push.

Validação geométrica é conservadora: corredores estreitos ou desvio nativo
complexo podem exigir replanejamento; não há prova de sucesso do motor Java
sem teste manual. Velocidade usa relógio real e não tempo simulado. A grade não
estima o volume físico completo do personagem; a colisão continua responsabilidade
do pathfinding nativo. Ao esgotar nove tentativas não promete sobrevivência.
Aguardar teste manual antes da fase 3C.4A.
