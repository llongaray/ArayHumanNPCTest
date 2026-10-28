# 3C.4C — observação de sobrevivência e necessidades

Implementado observador de condições físicas por UUID, sem decisões ou execução
de ações. Base de 375 testes preservada; suíte final: **413 testes aprovados**.

## APIs verificadas na instalação B42.13.1

Inspeção somente para leitura das classes com `javap -p`/`javap -c -p` e dos Lua
em `E:/Games/Project.Zomboid.v42.13.1/game`.
SHA-256 do `projectzomboid.jar` examinado:
`9F626AD644311AB301F8ABCD22AC93476B59B194BFF3147573DF96E3EAC86C2E`.

| Dado | API efetivamente usada | Interpretação |
|---|---|---|
| Identidade/instância | getModData, isNPC, getNpcByUuid, getLocalPlayer | UUID real completo, marca do mod, instância do roster e exclusão do sobrevivente controlado |
| Disponibilidade espacial | getCurrentSquare, getX/Y/Z, getCell.getGridSquare | Apenas posição real fracionária e tile carregado da mesma instância |
| Vida/morte | IsoGameCharacter.isDead | Vivo é a negação da flag conhecida, sem inferir morte por saúde zero |
| Saúde | BodyDamage.getHealth | Valor nativo em escala 0–100 |
| Infecção sistêmica | BodyDamage.IsInfected() | Flag nativa; separada de infecção de ferimento |
| Sangramento e lesões | getNumPartsBleeding, getNumPartsScratched, getNumPartsBitten | Contagens nativas |
| Partes do corpo | BodyDamage.getBodyParts, lista size/get | Leitura limitada por orçamento; índice do snapshot é o índice na lista |
| Ferimentos locais | BodyPart.getHealth, bleeding, scratched, bitten, isCut, bandaged, IsInfected, isInfectedWound | Flags locais, bandagem e saúde por parte |
| Outras lesões | BodyPart.getFractureTime, getBurnTime, getDeepWoundTime, getStitchTime | Valores nativos; valor positivo constitui evidência de lesão |
| Fome/sede/fadiga | Stats.get(CharacterStat.HUNGER/THIRST/FATIGUE) | Escalas nativas 0–1; não são percentuais normalizados pelo observador |
| Resistência | Stats.get(CharacterStat.ENDURANCE) | 0–1, direção oposta à fadiga: valores baixos indicam pouca resistência |
| Sono | IsoGameCharacter.isAsleep | Flag de estar dormindo; fadiga permanece um dado separado |
| Dor/pânico | Stats.get(CharacterStat.PAIN/PANIC) | Escalas nativas 0–100 |
| Estresse | Stats.get(CharacterStat.STRESS) | Escala nativa 0–1 |
| Temperatura | Stats.get(CharacterStat.TEMPERATURE) | Valor nativo, limites de registro 20–40 e padrão 37 °C |
| Moodles | getMoodles.getMoodleLevel(MoodleType.*) | Níveis retornados pelo motor, sem chamar Update e sem recalcular a partir dos Stats |
| Carga/inventário | getInventory, ItemContainer.getItems.size, getInventoryWeight, getMaxWeight | Quantidade, peso nativo e capacidade; nenhum item consumido ou enumerado pelo código Lua |
| Queda/incapacitação | IsoGameCharacter.isKnockedDown | Queda observada é evidência positiva de incapacitação; ausência de queda não comprova capacidade geral |

As constantes auditadas de Moodles usadas são ENDURANCE, TIRED, HUNGRY, THIRST,
PANIC, BLEEDING, INJURED, PAIN, STRESS, HEAVY_LOAD, HYPERTHERMIA e HYPOTHERMIA.
Não foram inventados getters antigos como getHunger ou um getter de "sono"
numérico. Usos reais das APIs também foram conferidos em
`shared/TimedActions/ISRestAction.lua`, `ISBaseTimedAction.lua`,
`ISReloadWeaponAction.lua`, `client/ISUI/ISFitnessUI.lua` e
`client/XpSystem/ISUI/ISHealthPanel.lua`.

### Limite específico de setNPC(true)

Getters existem na hierarquia IsoPlayer/IsoGameCharacter e são lidos na instância
NPC, sem trocar jogador. A auditoria de updateInternal confirma o ramo de
IsoAIModule para isNpc, além de chamadas nativas de Moodles/BodyDamage.
Isso não demonstra metabolismo e simulação idênticos aos do jogador controlado.

BodyDamage.Update contém comportamento especial para IsoPlayer não local em
cliente multiplayer, incluindo retorno antecipado/restauração de saúde; também
há tratamento de GodMode. DamageFromWeapon possui verificação de jogador local.
Esses caminhos foram apenas examinados. O observador não chama Update, não
repara valores e não força dano ou fome para produzir sinais de treinamento.

`getApparentInfectionLevel` não foi usado como um percentual de infecção:
o bytecode combina fontes como febre, infecção e food sickness. A entrega usa
flags explícitas para evitar atribuir uma causa incorreta.

## Arquivos criados e modificados

- Criado `42/media/lua/client/ArayHumanSurvival.lua`: leitura, cache, estados,
  histórico circular de eventos, catálogo e amostragem distribuída.
- Modificado `42/media/lua/client/ArayHumanPerception.lua`: carrega o observador,
  acrescenta `snapshot.survival` e repassa observações existentes de ameaça.
- Modificado `42/media/lua/client/ArayHumanLocomotion.lua`: acrescenta
  `survival_before` e `survival_after` às métricas de ações.
- Modificado `42/media/lua/client/ArayHumanExecutor.lua`: expõe snapshot em
  `getState(uuid).conditions` e no estado do monitor em `getSurvivalState(uuid).conditions`.
- Criado `ai/test_survival_observer.py`: 19 cenários em Lua 5.1 e 5.4, 38 testes.
- Modificados `ai/test_executor.py` e `ai/test_perception.py`: carregamento da
  dependência real no harness; testes anteriores preservados.
- Criado este relatório.

Physical, Walking, Navigation, EscapePlanner, chat, persistência, renderização,
câmera e balões não foram alterados nesta fase. PUSH_ZOMBIE e CLIMB_STAIRS mantêm
os mesmos diagnósticos UNSUPPORTED da 3C.4B.2.

## Contrato para consumidores futuros

```lua
ArayHuman.Survival.getSnapshot(uuid)           -- cache ou atualização se necessário
ArayHuman.Survival.updateSnapshot(uuid)        -- amostra explícita, apenas leitura
ArayHuman.Survival.getEvents(uuid, sequence)   -- eventos posteriores à sequência
ArayHuman.Survival.getCatalog()               -- escalas, estados e contratos futuros
ArayHuman.Survival.clearSnapshot(uuid)
ArayHuman.Survival.clearAll()
```

Resultados são cópias independentes. Campos escalares possuem `known`, `status`,
`value` quando conhecido, `source` e motivo quando aplicável:

- `known`: getter retornou valor finito/booleano do tipo esperado; zero e false
  permanecem valores conhecidos.
- `unavailable`: componente, método, constante ou acesso espacial não disponível.
- `unknown`: leitura falhou, valor inválido, informação parcial ou conclusão
  não sustentada pelos dados disponíveis.

`available` indica instância espacialmente disponível; `active` exige também
vida confirmada. NPC morto produz snapshot inativo com DEAD conhecido. UUID
inválido, instância ausente ou mundo desconhecido retorna nil e motivo.
Em chunk indisponível, os campos físicos ficam indisponíveis; isDead pode ser
lido da própria referência, com origem explícita.

A flag `knocked_down` é reportada separadamente. `incapacitated` é verdadeiro
quando morte/queda confirmam a condição; nos demais casos permanece desconhecido,
pois não foi identificada uma API geral segura que confirme todas as formas
de incapacitação. Seu campo scope explicita essa limitação.

### Estados simultâneos e limiares

| Estado | Regra do observador |
|---|---|
| INJURED | Saúde < 100, sangramento/lesão/infecção observada; evidência positiva vale mesmo com lista parcial |
| CRITICAL | Saúde <= 25 |
| EXHAUSTED | Fadiga >= 0,8 ou resistência <= 0,2 |
| HUNGRY | Fome >= 0,25 |
| THIRSTY | Sede >= 0,25 |
| DEAD | isDead conhecido e verdadeiro |
| HEALTHY | Todos os critérios exigidos foram observados sem lesão, infecção, queda ou necessidades acima dos limiares |

Os limiares são configuráveis, descritivos e próprios deste observador; não
pretendem reproduzir os limiares internos de Moodles ou representar uma política.
HEALTHY descreve esses critérios observados, sem afirmar ausência de qualquer
incapacitação possível. Campos insuficientes mantêm a classificação desconhecida.
Morte desativa os outros rótulos. Os rótulos físicos/necessidades podem coexistir
enquanto vivo, por exemplo INJURED, CRITICAL, EXHAUSTED, HUNGRY e THIRSTY.

Exemplo abreviado ilustrativo:

```json
{
  "schema_version": 1,
  "uuid": "11111111-1111-4111-8111-111111111111",
  "world_id": "Sandbox/Exemplo",
  "captured_at_ms": 10000,
  "active": true,
  "health": {"known": true, "status": "known", "value": 75, "source": "BodyDamage.getHealth"},
  "needs": {
    "hunger": {"known": true, "status": "known", "value": 0.5},
    "endurance": {"known": true, "status": "known", "value": 0.1}
  },
  "state_list": ["INJURED", "EXHAUSTED", "HUNGRY"]
}
```

Os dados disponíveis para RL são os valores brutos, flags de validade, escalas,
ferimentos por parte, estados simultâneos, timestamp, UUID/mundo, duração
observada dos estados e contexto de ameaça. Não há recompensa, normalização
oculta, rede neural, treinamento ou transporte novo para Python.

O catálogo EAT, DRINK, REST, BANDAGE e SEEK_SAFETY contém
`executable=false` e `status=future_action_contract` para todos. A fuga explícita
existente em Executor.escape continua separada desse catálogo e preservada.

## Eventos e integração

Eventos ficam apenas em memória, por UUID/mundo, com sequência, timestamp,
tipo, campo, antes/depois, delta quando numérico, duração entre amostras e ameaça
observada. Tipos: OBSERVATION_STARTED, OBSERVATION_CHANGED, DAMAGE, RECOVERY,
NEED_CHANGED, CONDITION_CHANGED, STATE_CHANGED e DEATH.

Alterações de ferimentos são agrupadas por parte para evitar que centenas de
mudanças de flags expulsem o evento de dano da mesma amostra. Histórico padrão:
128 eventos/UUID, configurável até 256; consumidores devem acompanhar sequência
e coletar antes da rotação. clearAll reinicia o histórico e sua sequência.

Eventos de dano/recuperação exigem duas leituras conhecidas da mesma instância.
Troca de mundo, instância, regressão do relógio ou ausência de leitura entre
amostras estabelece nova base; não inventa dano ocorrido em dados inacessíveis.
Mudanças de disponibilidade são eventos próprios. O epsilon padrão é zero para
preservar mudanças pequenas reais de Stats; pode ser configurado explicitamente.
As durações são observadas entre amostras, não horários exatos de início nativo.

A ameaça é repassada pelo scan já realizado para emergência, sem segunda
varredura. Evidência incompleta ou com mais de 1500 ms fica desconhecida; ausência
de evidência não vira NONE conhecido. Consultas read-only de ameaça feitas pela
telemetria não consomem o histórico de aproximação/dano do monitor existente.

As decisões e os orçamentos de fuga permanecem os mesmos. Fome, sede ou rótulos
físicos não geram ordens, caminhada, tratamento ou qualquer ação nesta entrega.

## Frequência, custo e limitações

Intervalo padrão de 1000 ms; amostrador próprio distribui até 2 NPCs por tick,
configurável de 1 a 4. Acesso por outras integrações também pode atualizar cache
vencido; morte, troca de instância e mudança de disponibilidade invalidam cache
imediatamente quando consultados. Muitos NPCs podem aumentar a latência do ciclo.

Leitura limitada a 32 partes do corpo, 8 Stats e 12 Moodles por amostra. Em um
corpo com 17 partes são cerca de 230–260 chamadas de getters, mais as validações
e cópias de tabelas; é uma estimativa por contagem, não medição de custo no jogo.
Não há varredura de mapa ou inventário item a item pelo Lua. O getter nativo de
peso percorre itens: só é chamado com tamanho do inventário conhecido e até 256
itens diretos por padrão. O custo interno de itens/recipientes depende do motor.
Inventário acima do orçamento deixa peso desconhecido, sem estimativa inventada.

Leituras confirmam o estado retornado pelo motor, não garantem a progressão
natural de todas as necessidades em IsoPlayer.setNPC(true). Essa progressão,
sincronização de Moodles e efeitos de autoridade multiplayer requerem validação
manual. Morte só é registrada se a flag nativa for observada; remoção do roster
não é interpretada como morte. Mudanças ocorridas inteiramente entre amostras
podem não aparecer no histórico.

## Verificação

Suíte executada com `python -B -m pytest ai -q -p no:cacheprovider` e runtime
Lupa temporário já utilizado pelo projeto. Resultado final:
**413 passed in 16.35s** — 375 anteriores e 38 novos.

Cobertura nova: dois NPCs, cópias independentes, zero/false, estados simultâneos,
Stats/Moodles/ferimentos/inventário, APIs ausentes/com erro/NaN, dano e recuperação,
lacunas de observação, morte imediata e inicial, mundo indisponível/trocado,
chunk descarregado, troca de instância, identidade inválida, jogador excluído,
cache e invalidação, limites e sequências, listas parciais, duração, relógio,
contexto de ameaça sem nova varredura, integração de métricas/executor/percepção,
catálogo não executável e ausência de ações por necessidades.

Nenhum jogo/serviço iniciado; nenhum commit/push; JARs, executáveis, saves,
SQLite existente, FBO, câmera, balões e modelo Ollama preservados.
Aguardar instruções antes da 3C.4D.
