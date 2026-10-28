# Fase 3C.2 — Decisões Ollama sem execução

## Arquivos

- `ai/decision_handler.py`: validação, identidade SQLite, candidatos, prompt,
  decisão e dispatcher limitado.
- `ai/ollama_service.py`: operação `decision_request`, publicação de respostas e
  prioridade de despacho por lote.
- `ai/test_decision_handler.py`: testes isolados do motor, transporte e concorrência.

Nenhum arquivo Lua foi alterado nesta fase. Não há emissor automático Lua,
executor, ativação de autonomia ou alteração de ordens/movimentação.

## Entrada pela ponte

Publicar o JSON em `to_py/<id>.json.tmp` e, após fechar, publicar `<id>.ok`,
seguindo o protocolo existente. `id` deve ser igual ao nome do arquivo.

Campos obrigatórios:

| Campo | Contrato |
| --- | --- |
| `kind` | `decision_request` |
| `id` | Token único, 1–128 caracteres ASCII alfanuméricos, ponto, hífen ou sublinhado |
| `world_id` | Mundo válido, igual ao snapshot e ao registro SQLite |
| `npc_id` | UUID canônico real, igual a `snapshot.uuid`; `npc_1` é rejeitado |
| `session_id` | Token de sessão com o mesmo formato de `id` |
| `session_started_at_ms` | Epoch Unix em ms; estável durante a sessão e crescente ao abrir outra |
| `sequence` | Inteiro positivo, crescente por mundo/NPC/sessão |
| `issued_at_ms` | Epoch Unix em ms da emissão |
| `expires_at_ms` | Epoch Unix em ms, posterior à emissão e no máximo 30000 ms depois |
| `snapshot` | Snapshot 3C.1 ativo, vivo conhecido, posição válida e timestamp recente |
| `goal` | Opcional: texto de até 500 caracteres |

`snapshot.captured_at_ms` deve estar entre `issued_at_ms - 30000` e
`issued_at_ms`. Há tolerância de até 2000 ms para emissão no futuro. Um futuro
emissor deve garantir a mesma base de tempo epoch do serviço Python.

O motor consulta a identidade diretamente no SQLite por `world_id + npc_id`.
Identidade/persona enviada pelo solicitante não substitui o banco. Não há
histórico de chat, persona global ou chave `npc_1` no prompt das decisões.
O banco precisa ter sido inicializado pelo fluxo de persistência existente;
decisões não criam banco nem executam migrações.

## Decisão e candidatos

O conteúdo solicitado ao modelo é exatamente um objeto JSON completo:

```json
{
  "action": "FOLLOW_PLAYER",
  "parameters": {},
  "reason": "O jogador esta proximo.",
  "priority": 2
}
```

| Ação | Parâmetros aceitos |
| --- | --- |
| `IDLE`, `LOOK_AT_PLAYER`, `FOLLOW_PLAYER`, `STOP` | `{}` |
| `MOVE_TO`, `WANDER_NEARBY` | `{"candidate_id":"tile:100:200:0"}` |
| `SAY` | `{"text":"Texto de ate 300 caracteres"}` |

`reason`: texto não vazio de até 240 caracteres. `priority`: inteiro de 0 a 3,
sem booleanos. Campos extras, coordenadas arbitrárias, ações não permitidas,
parâmetros incorretos, JSON parcial, markdown, chaves repetidas e NaN/Infinity
são rejeitados. LOOK/FOLLOW exigem jogador conhecido no snapshot.

Os IDs de destino são derivados, no Python, exclusivamente dos tiles presentes
no snapshot 3C.1: `tile:x:y:z`. Exigem coordenadas inteiras, mesmo andar, raio
válido e `solid_floor`, `free`, `traversable_candidate` conhecidos e verdadeiros.
São oferecidos até 48 candidatos, ordenados por proximidade. MOVE/WANDER só
aceitam IDs dessa lista oferecida. Não há alteração do módulo de percepção.
Esses candidatos não garantem caminho livre; isso continua sendo responsabilidade
de um futuro executor, que deverá revalidar o mundo antes de qualquer ação.

O motor utiliza a implementação HTTP `OllamaClient` existente, com instância e
Session próprias do worker. Usa somente o modelo selecionado por mundo na
admissão do pedido, sem fallback de modelo, seleção automática ou gravação de
`world_models.json`. A seleção e disponibilidade são consultadas no estado já
mantido pelo serviço. O perfil deriva do perfil de decisão existente, com
384 tokens, temperatura 0, contexto 8192, `stream=false` e `keep_alive=30m`.
O perfil legado de 12 tokens e o perfil de chat permanecem inalterados.

## Resposta pela ponte

Publicada atomicamente em `to_lua/<id>.json`. Exemplo de sucesso:

```json
{
  "id": "decision-1",
  "kind": "decision_response",
  "world_id": "Sandbox/exemplo",
  "npc_id": "11111111-1111-4111-8111-111111111111",
  "session_id": "session-1",
  "session_started_at_ms": 1793200000000,
  "sequence": 1,
  "issued_at_ms": 1793200001000,
  "expires_at_ms": 1793200011000,
  "ok": true,
  "executable": false,
  "decision": {
    "action": "FOLLOW_PLAYER",
    "parameters": {},
    "reason": "O jogador esta proximo.",
    "priority": 2
  }
}
```

Os tempos do exemplo são ilustrativos. Em falha, `ok=false`, `decision.action`
é `IDLE` com parâmetros vazios e `error` contém um código, por exemplo
`{"code":"expired"}`. Isso é um resultado de diagnóstico, não uma instrução
para um executor. Todas as respostas têm `executable=false` nesta fase.

Não há interpretação de texto como Lua/Python, `eval`, execução de shell ou
chamada de API do jogo. Mesmo um texto SAY contendo código permanece dado inerte.

## Concorrência, limites e invalidação

- Um worker daemon exclusivo para decisões; admissão de até quatro pedidos
  pendentes e fila física limitada. A fila de conclusões também é limitada.
- O loop da mailbox não chama Ollama para decisões. Ele valida/admite pedidos e
  publica conclusões. Persist/ping precedem chat, e chat precede decisões na
  classificação de cada lote disponível.
- O worker possui sua própria Session HTTP e abre conexões SQLite somente de
  leitura, com timeout de lock de 0,2 s. Fecha cada conexão antes da inferência;
  nenhuma transação ou conexão SQLite é compartilhada entre threads.
- HTTP de decisão: até 15 s, reduzido ao prazo restante do pedido, sem repetição
  automática. Validade total máxima: 30 s, incluindo fila. A mailbox verifica
  vencimento independentemente da conclusão do worker.
- Consulta SQLite após inferência verifica novamente existência e morte. Expiração
  é verificada antes/depois da inferência e ao publicar. Sequência/sessão superadas
  nunca publicam a decisão antiga; produzem erro com IDLE.
- Duplicatas aceitas não disparam nova inferência nem substituem a resposta
  original. Arquivo de resposta já existente também impede sobrescrita após
  reinício. Registros de sequência/sessão em memória são limitados a 1024 pares
  mundo/NPC; IDs recentes também têm limite de 1024.
- Requisições: até 256 KiB; conteúdo de resposta do modelo: até 4096 caracteres;
  contexto enviado: até 20000 caracteres. Excesso gera erro seguro.

## Testes e limites conhecidos

Execução: `python -B -m pytest ai -q -p no:cacheprovider`, com Lupa disponível
apenas no runtime temporário de testes da fase anterior. Resultado: **109 testes
aprovados**, incluindo os 68 anteriores e 41 novos casos.

Cobertura nova: JSON/ações/parâmetros inválidos, personalidades distintas, UUID
inexistente, isolamento de mundo, morte inclusive durante inferência, candidatos,
modelo/perfil HTTP, expiração antes/depois, duplicatas, sequência/sessão antigas,
fila cheia, conclusão tardia, integridade do SQLite somente de leitura, propriedade
do worker e ausência de execução. A ponte real foi exercitada com Ollama bloqueado
por um evento: save_state, ping e chat responderam antes da liberação da decisão.
Também foi verificada a prioridade de despacho de um lote misto.

Não foi iniciado o serviço real, Ollama ou jogo. Nenhum JAR/save, banco real,
seleção de modelo ou código de renderização/câmera/movimentação foi alterado.

Limitações: não há preempção de inferência já iniciada no Ollama nem garantia de
prioridade de GPU. Timeout HTTP é de socket; uma conexão que não termine não
bloqueia a mailbox, mas pode ocupar o único worker. Nessa situação os pedidos
expiram e a fila passa a recusar novas admissões, sem criar threads ilimitadas.
Os fluxos legados de chat, geração de identidade e atualização de status ainda
podem fazer suas próprias chamadas síncronas; esta fase não os reescreve.
Portanto, 50 ms é o intervalo nominal da mailbox, não um prazo garantido para
respostas durante uma operação legada lenta.

O controle de sessão/sequência é local ao processo; após reinício, a proteção
durável cobre IDs cujo arquivo de resposta continua presente. Não há autenticação
de sessão nem descoberta do mundo ativo no jogo. Um futuro emissor/receptor Lua
deverá manter sessão própria e rejeitar respostas de outro mundo/sessão, sequência
ou prazo. Nenhuma autonomia foi ativada nesta entrega.
