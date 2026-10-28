# Fase 3C.3.1 — Correção de sobrevivência e fuga

## Causa identificada no código anterior

A ausência de reação tinha lacunas concretas, independentemente da inferência:

1. `Executor.update()` percorria somente `states` ativos, criados por decisões
   explicitamente submetidas. Caminhadas do F7/menu usam `Walking`/`Commands`;
   um NPC parado ou apenas sob comando manual podia não possuir estado do executor.
2. O ramo de perigo do executor chamava somente `finish(..., "threat_nearby")`.
   Cancelava a ação, mas não chamava `escape()`.
3. `escape()` exigia sessão de decisões e recusava `manual[uuid]`. Um comando
   manual acionava justamente esse bloqueio, impedindo sua substituição pela fuga.
4. A percepção produzia dados, sem reagir. A recuperação de ameaças do executor
   podia usar snapshot de até 1500 ms e voltar somente aos tiles antigos dos
   zumbis, em vez de pesquisar novamente seus ocupantes atuais.
5. A verificação de ocupação da caminhada já existia para o destino. Ela não
   substituía um monitor de zumbis aproximando-se ou encontrados no trajeto.

Também havia fragilidade na seleção de fuga: quatro raios retos e comparação
da separação na posição fracionária com centros de tiles. Isso podia recusar
rotas viáveis ou ignorar alternativas com curvas. Não atribuímos o ataque relatado
especificamente a esse ponto: os requisitos de sessão e a falta de monitoramento
de comandos manuais já impediam uma reação garantida.

O `console.txt` existente foi consultado somente para leitura. Não contém
telemetria suficiente de ameaça/ataque/executor para reconstruir o evento exato.
Não foi presumida falha de uma API Java específica nem reproduzido o jogo.

## Arquivos

Modificados: `ArayHumanPerception.lua`, `ArayHumanExecutor.lua`,
`ArayHumanWalking.lua` e o harness/teste de reação de `ai/test_executor.py`.

Criados: `ArayHumanEscapePlanner.lua`, `ai/test_survival.py` e este relatório.

Não foram alterados FBO, câmera, balões, chat, SQLite, modelo ou serviço Python.

## Detecção local independente

`Perception.scanThreats(uuid)` é uma consulta fresca e limitada, separada do
snapshot amplo da 3C.1. Usa `getCell():getGridSquare()`, `getMovingObjects()`,
`instanceof(..., "IsoZombie")`, `isDead()`, `getX/Y/Z()` e
`getCurrentSquare()`. Zumbis mortos e outros andares são excluídos. A consulta
não usa visibilidade da câmera, lista global de zumbis ou Ollama.

O retângulo local é derivado da posição fracionária do NPC; os tiles intersectam
o raio, e a distância final é calculada contra a posição real do zumbi. Não se
descarta uma entidade dentro do raio porque o centro do tile está fora dele.

| Classificação | Evidência |
| --- | --- |
| `NEARBY` | Zumbi vivo observado até seis tiles. Não significa ataque ou emergência. |
| `APPROACHING` | Distância diminuindo; perigo imediato se até 3,5 tiles e aproximação confirmada, ou até 2,5 tiles com conexão confirmada. |
| `CONTACT` | Até 1,25 tile, ou perda de saúde com zumbi vivo conectado até três tiles. |

A perda de saúde é lida por `getBodyDamage():getHealth()`. Não é tratada como
prova isolada de ataque: deve haver ameaça viva local e conexão confirmada.
Não foram presumidos `getTarget()`, `isAttacking()` ou eventos de ataque não
verificados na exposição Lua do zumbi.

A conexão usa busca local limitada por ligações adjacentes cardinais.
`isBlockedTo()` é consultado nos dois sentidos, com piso sólido; não é usado
como uma suposta linha de visão entre tiles arbitrariamente distantes. API ou
conexão desconhecida não equivale a caminho livre. Tiles descarregados continuam
desconhecidos. No mesmo tile, a presença viva é confirmação local de contato.

## Integração com OnTick e prioridade

`Executor.update()`, já registrado em `OnTick`, agora mantém uma ronda do roster
inteiro antes de processar estados de decisões. NPC parado, em FOLLOW manual,
teste de caminhada ou MOVE manual entra nessa ronda, sem sessão Ollama.

Uma ameaça imediata confirmada invalida o estado/callback anterior, encerra a
ordem manual daquele UUID e cancela sua caminhada. Somente essa exceção local
pode sobrepor a prioridade manual e ultrapassar 12 tiles. O bloqueio de prioridade
manual contra decisões gerais permanece; a ordem interrompida não é retomada
silenciosamente após fugir. Novos comandos manuais ainda podem cancelar a ação,
sujeitos à próxima avaliação de segurança se o perigo persistir.

O estado emergencial usa `localSurvival=true` e identificação local própria;
não cria sessão de decisões nem requisição Ollama. Reconexão da sessão de
decisões não cancela a fuga local. Troca de mundo, morte e perda da instância
cancelam a ação. Não há combate nem decisões autônomas gerais.

## Seleção e execução da fuga

O planejador faz uma busca local limitada, por custo de percurso, considerando:

- Posição fracionária de partida, piso, ocupação e carregamento de cada tile.
- Colisões em cada ligação entre tiles, nos dois sentidos.
- Distância dos segmentos aos zumbis observados, e não só distância do destino.
- Distância total percorrida e deslocamento, ambos limitados inicialmente a seis tiles.
- Destino a pelo menos cinco tiles das ameaças observadas e com ganho de pelo menos dois tiles na separação inicial.
- Destinos já tentados no episódio, que não são reutilizados.

Curvas ao redor de obstáculos são permitidas. A rota é executada em trechos
adjacentes pelo `ISWalkToTimedAction`/`PathFindBehavior2` nativos; não há escrita
de coordenadas nem controle de movimento frame a frame. Cada trecho é revalidado
antes de iniciar e durante o acompanhamento. Isso evita pedir ao pathfinding
um destino final distante que permita um atalho não avaliado perto do zumbi.

Os callbacks continuam protegidos pelo registro, ID e geração. A caminhada só
confirma chegada dentro do tile solicitado, em vez de considerar sucesso apenas
estar a até um tile do centro. O monitor distingue chegada ao destino de fuga
(`escape_target_reached`) e redução observada do perigo (`danger_reduced`).

Sem rota, a ação insegura continua interrompida e o motivo é registrado, por
exemplo `safe_escape_unavailable`, `route_budget_exhausted`,
`threat_scan_incomplete`, `route_edge_blocked` ou `route_threatened`.
Cooldown ou tentativas esgotadas não permitem retomar um movimento inseguro.

## Limites de processamento e repetição

| Recurso | Padrão/limite |
| --- | --- |
| Ronda local | Intervalo de 250 ms, até dois NPCs por rodada. |
| Roster | Atualizado a cada 1000 ms, com cursor circular entre NPCs. |
| Varredura por NPC | Raio de seis tiles, até 169 tiles e 96 ocupantes examinados. |
| Conexões | Até oito buscas, até 48 nós cada. |
| Planejamento por tentativa | Até 96 nós, máximo defensivo de 128; até 256 ocupantes e 24 ameaças. |
| Fuga | Até seis tiles e seis segundos no total. Cada trecho recebe o prazo restante. |
| Ausência de progresso | Até 1500 ms durante fuga. |
| Cooldown | 1000 ms antes de outra tentativa. |
| Tentativas | No máximo três por episódio, com destinos distintos quando há rota. |
| Reinício do episódio | Após pelo menos 3000 ms de situação local suficientemente coberta e segura. |

Com mais de dois NPCs, o intervalo efetivo por NPC cresce com a ronda. As
checagens leves de caminhada continuam nos ticks nativos; varreduras e busca de
rota não são repetidas em todo frame. Não foram medidos tempos ou FPS no jogo.

## Diagnóstico para o próximo teste manual

O carregamento registra `monitor_registered`. Cada NPC registra `monitor_active`.
As mudanças de ameaça e ações usam prefixos `[ARAY-SURVIVAL]` e `[ARAY-WALK]`,
com UUID, ID da ação, distância, classificação e resultado. Eventos principais:

```text
[ARAY-SURVIVAL] uuid=... event=threat_detected level=CONTACT immediate=true distance=...
[ARAY-SURVIVAL] uuid=... event=action_interrupted order=MOVE_TO walk=... source=comando
[ARAY-SURVIVAL] uuid=... event=escape_destination action=... target=tile:... route_nodes=...
[ARAY-SURVIVAL] uuid=... event=pathfinding_request action=... leg=... target=tile:...
[ARAY-SURVIVAL] uuid=... event=pathfinding_started action=... walk=...
[ARAY-SURVIVAL] uuid=... event=escape_result action=... state=... result=...
```

Falhas de confirmação geométrica produzem `threat_unconfirmed`. Falta de rota
produz `escape_unavailable`; limite de tentativas, `attempts_exhausted`. Os logs
são emitidos por mudança ou tentativa, sem uma linha por frame.

## Testes

Comando executado: `python -B -m pytest ai -q -p no:cacheprovider`, usando o
runtime temporário Lupa já disponível. **191 testes aprovados**, incluindo a
suíte anterior e 36 execuções novas (18 cenários em Lua 5.1/Lua 5.4).

Os testes novos despacham os handlers registrados de OnTick em sua ordem real
no harness: caminhada, comandos, percepção e executor. Somente a manutenção
preexistente de renderização/câmera, não simulada pelo motor Java de teste, é
excluída. O módulo nativo B42 `WalkToTimedAction.lua` continua sendo executado.

Cobertura: reação parada sem sessão, caminhada manual, aproximação, contato,
perda de saúde com ameaça, dano sem ameaça, zumbi morto, outro andar, posições
fracionárias, borda do raio, fuga com curva, parede e API de colisão desconhecida,
destino ocupado, bloqueio dinâmico, pathfinding sem progresso/falha, alternativas,
cooldown, esgotamento e reinício do episódio, dois NPCs, callbacks antigos,
cancelamento individual, orçamento/justiça da ronda, limite de 12 tiles, chunk
indisponível e controle do jogador preservado.

O teste anterior que exigia cancelamento sem fuga foi atualizado para exigir a
nova reação automática local. O harness passou a expor um roster coerente e a
simular a herança real de IsoZombie/IsoPlayer para IsoGameCharacter; isso permite
que o teste de ocupação exercite o mesmo critério do código de produção.

## Limitações e encerramento

Os testes simulam o motor Java; não comprovam velocidade, animações ou exposição
efetiva de todas as APIs durante o ataque real. A reação é por amostragem, não
garante evitar toda mordida. Agarrões, animações de dano, multidões, colisões
dinâmicas ou orçamento insuficiente podem impedir a fuga. Não há combate,
invulnerabilidade, cura, teleporte ou aceleração artificial do NPC. Informações
desconhecidas podem levar a recusa segura da rota, registrada no log.

Não foi iniciado jogo/serviço, alterado JAR/save/SQLite/modelo, nem feito
commit/push. Aguarda novo teste manual do usuário. A fase 3C.4A não foi iniciada.
