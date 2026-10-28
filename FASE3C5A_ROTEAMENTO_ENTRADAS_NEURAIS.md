# 3C.5A — roteamento obrigatório e entradas neurais

## Resultado

Integração do resolvedor ao chat real, envio múltiplo limitado, eventos individuais de conversa e contratos de observação implementados. **914 testes aprovados: 856 cenários anteriores + 58 regressões novas.** As entradas dos testes antigos de conversa foram adaptadas para conter vocativos explícitos; nenhum cenário anterior foi removido para obter esse resultado.

Os testes usam Lua real via Lupa 5.1/5.4 com APIs simuladas e Python com SQLite temporário/Ollama simulado. Não comprovam funcionamento dentro da B42.13.1. Não foram iniciados jogo, Ollama ou serviços. Não houve instalação/download, commit/push, alterações de JARs/executáveis/saves/SQLite real, FBO, câmera, WASD, modelo ou renderização/posição/estilo dos balões. Não há RN, política neural, RL, recompensas ou treinamento.

## 1. Fronteira de destinatários

`Chat.sendMessage` chama obrigatoriamente `Recipients.resolve` antes de obter contexto, executar comando ou criar requisição. UUID selecionado no F7 não determina o destinatário. O argumento antigo de seleção é ignorado como destino; segue existindo para compatibilidade de assinatura. TalkBar e ChatWindow enviam texto original e mundo esperado, sem inferir destinatário a partir do NPC exibido.

Exemplos:

| Entrada | Destino |
|---|---|
| `Carlos, venha aqui` | UUID de Carlos |
| `Carlos e Tania: venham aqui` | dois UUIDs, sessões próprias |
| `Vocês, venham aqui` | grupo elegível, com orçamento verbal |
| `Venha aqui` | ninguém; nenhuma observação de estado, chamada Ollama ou ação |

Resolver destino **não** interpreta “venha aqui” como movimento. A gramática antiga continua restrita às frases já suportadas, como `me siga`, `pare` e `vá até ali` com candidato válido. O vocativo é separado sintaticamente para encaminhar somente o corpo a essa gramática existente. A mensagem original, com nomes e Unicode, é preservada no histórico, eventos e mailbox. Ollama permanece exclusivamente verbal e não escolhe intenções/ações.

Nomes/aliases são comparados pelo normalizador de acentos/caixa, sem transformar os dados originais. Nomes/aliases ambíguos, aliases coincidentes com palavras coletivas, desconhecidos, UUID inválido, ator morto/descarregado, mundo divergente, mensagem vazia e falta de destinatário são recusados. O conjunto inteiro passa por validação de atores, contexto/alcance e prioridade emergencial antes do primeiro despacho. Nomes são resolvidos no roster atual de NPCs vivos/carregados; um morto sem nome elegível não é destinatário.

Sintaxe continua determinística: vocativo inicial encerrado por `,` ou `:`; nomes unidos por `e`/`&`; listas com vírgulas usam `:` ao final (`Carlos, Tania: ...`). Menções narrativas não bastam. Não há interpretação livre de apelidos, pronomes ou significado. Aliases são registros locais confiáveis, transitórios e limitados; não são recebidos do modelo nem persistidos no SQLite.

A TalkBar deixou de fechar ou rejeitar envio porque o NPC selecionado morreu/se afastou. Agora valida jogador/mundo para manter a barra e valida o alcance real de cada destinatário ao enviar. O alcance do pipeline de contexto é até 10 tiles, mesmo andar. F7 continua selecionando a visualização de inventário/histórico, sem ser endereçamento implícito. A janela de histórico permanece por NPC; uma resposta para outro UUID aparece nos balões desse ator e no histórico correto.

## 2. Fan-out, segurança e concorrência

- Até **8 destinatários** por mensagem, únicos e ordenados por UUID.
- Conversa verbal explicitamente dirigida a vários nomes cria uma requisição/sessão por NPC, limitada pela capacidade disponível: **4 pendentes no total e 1 por NPC**.
- Chamada coletiva verbal cria **uma** requisição, para o primeiro UUID da lista ordenada. Os demais registram `OBSERVED_SILENT`, sem inferência nem resposta forçada. É uma seleção mecânica temporária, não uma política neural; não há rodízio inteligente.
- Comando reconhecido pela gramática existente é solicitado uma vez por destinatário, com IDs próprios e as validações do Executor. Alvo de movimentação por `target_id` exige destinatário único, impedindo aplicar o mesmo candidato de um NPC a outros.
- Cooldown de 2 s entre chamadas com múltiplos destinatários. `STOP` não fica bloqueado por esse cooldown. Comandos manuais não aguardam conversa pendente: respostas antigas desses NPCs são descartadas localmente, sem cancelar ou substituir ações de outro UUID.
- Deduplicação curta de comandos idênticos por mundo/texto/alvo (1 s), mapa limitado; não bloqueia automaticamente uma nova pergunta após resposta anterior descartada.
- Mundo e ponteiro/identidade são revalidados imediatamente antes de cada envio. Resultados tardios continuam vinculados a UUID/mundo/sessão/sequência/expiração e contexto atual. Respostas do modelo nunca entram no caminho manual.
- O serviço mantém despacho assíncrono existente: um worker de conversa, fila limitada e conexão SQLite curta/somente leitura por worker. `persist`/`ping` não aguardam inferência.

Toda falha de pré-validação bloqueia o grupo antes de ações ou publicação. Uma falha operacional posterior (por exemplo, escrita da segunda mailbox ou pathfinding nativo) pode ocorrer depois do primeiro destinatário ter aceitado: não há transação atômica entre atores/arquivos. O retorno inclui resultados parciais e cada memória mantém o estado real; não há retry automático do grupo nem declaração falsa de sucesso global.

`Chat.sendMessage(text, ignored_selection, target_id, expected_world)` retorna `ok, request_or_action_id, resultados_por_uuid`. O primeiro ID permite compatibilidade com a UI anterior; a lista contém IDs independentes dos despachos realizados. `Chat.isPending(uuid)` continua individual.

## 3. Mailbox e validação Python

O protocolo de conversa v2 foi preservado, acrescido de cabeçalho obrigatório de roteamento v1 e projeção de estado opcional:

```json
{
  "protocol_version": 2,
  "kind": "chat_request",
  "npc_id": "UUID_REAL_DO_DESTINATARIO",
  "world_id": "MODO/MUNDO",
  "message": "Carlos e Tania: olá!",
  "routing": {
    "schema_version": 1,
    "world_id": "MODO/MUNDO",
    "recipients": ["UUID_CARLOS", "UUID_TANIA"],
    "event_id": "speech:TIMESTAMP:SEQUENCIA",
    "captured_at_ms": 123456,
    "collective": false
  },
  "agent_input": {"schema_version": 1, "uuid": "UUID_REAL_DO_DESTINATARIO"}
}
```

Exemplo abreviado: os UUIDs/timestamps acima são placeholders; pedido real inclui os campos existentes de sessão/sequência/prazo/contexto e os demais campos do estado. Cada envelope contém contexto e identidade do destinatário daquele pedido, não uma mistura de históricos.

`validate_routing` exige versão, mundo, lista única de UUIDs canônicos contendo o destinatário, evento e timestamp recente. Ausência do cabeçalho ou texto sem vocativo delimitado é recusada antes da inferência. O caminho legado do serviço também exige cabeçalho: não permanece como bypass de mensagens sem destinatário.

A resolução semântica de nomes/aliases para atores é responsabilidade da fronteira Lua confiável, que conhece o roster nativo; Python verifica o vínculo estrutural e a identidade no SQLite. O cabeçalho não é autenticação criptográfica contra outro programa com permissão de escrever na mailbox. Nenhum conteúdo vindo de Ollama possui autoridade para criar comandos manuais.

## 4. Auditoria do codificador local

Foi inspecionado o Python utilizado pelo caminho normal do launcher (`python` no PATH): `C:/Users/llongaray/AppData/Local/Programs/Python/Python311/python.exe`.

| Opção local | Resultado da inspeção |
|---|---|
| SentenceTransformers multilíngue | pacote ausente |
| Transformers + PyTorch em CPU | ambos ausentes |
| ONNX em CPU / modelo quantizado | `onnxruntime` e pesos locais não encontrados nos caches consultados |
| Tokenização/array auxiliar | `tokenizers` e `numpy` ausentes nesse runtime |
| Cache padrão Hugging Face / SentenceTransformers | diretórios ausentes |
| Caches alternativos por variável de ambiente | HF_HOME, HUGGINGFACE_HUB_CACHE, TRANSFORMERS_CACHE e SENTENCE_TRANSFORMERS_HOME não configurados |

Isso é uma auditoria desses locais/runtime, não uma varredura de todos os discos. Nenhum modelo foi baixado, pacote instalado ou biblioteca pesada importada para descobrir disponibilidade.

`ai/language_encoder.py` é independente do Ollama e expõe interface versionada. No ambiente atual retorna:

```json
{"schema_version":1,"status":"UNAVAILABLE","model_id":null,"vector":null,"dimensions":null,"reason":"no_local_encoder_configured"}
```

Não gera zeros, hashes ou embeddings supostamente semânticos. Uma interface de adaptador local confiável fica reservada para integração posterior explícita; não é selecionável por requisição/modelo. A validação limita texto a 2.000 bytes, dimensões a 768 e recusa valores não numéricos/não finitos ou falhas. Nenhum adaptador/modelo semântico foi implementado ou homologado nesta fase; adequação real a PT-BR e latência em CPU dependem de futura escolha e medição. Hoje o caminho `UNAVAILABLE` não faz computação de embeddings.

## 5. Contrato de estado neural

Lua `NeuralInput.observe(uuid)` reutiliza AgentState/Capabilities e projeta somente dados serializáveis, sem executar ações. Verifica UUID, mundo, ator ativo e timestamp de até 1.500 ms. A projeção tem até 10.000 bytes; eventos/resultados são omitidos com marca de parcialidade se necessário. Não instala monitor adicional nem faz varredura global.

Python `neural_state.build_observation` combina essa projeção com identidade real de leitura SQLite, contexto do chat e estado do codificador. Contrato v1:

- `uuid`, `world_id`, `session_id`, `request_id`, captura e expiração.
- `message` original e `routing`.
- `language`: embedding ou `UNAVAILABLE` explícito.
- `identity` e `profile`: identidade/profissão/personalidade e perfil nativo quando disponível.
- `perception`, `threat`, `health`, `inventory`: dados observados, preservando marcadores internos de desconhecimento/parcialidade e linha de visão. Listas vazias com visibilidade desconhecida não provam ausência de ameaças.
- `capabilities`: catálogo real; PUSH_ZOMBIE e CLIMB_STAIRS continuam `UNSUPPORTED`.
- `action_results`: resultados recentes do catálogo/AgentState.
- `conversation_memory`: resumo limitado dos eventos do próprio NPC.
- `personal_memory`: `UNAVAILABLE`, pois não existe provedor persistente de memória episódica. Lore permanece identidade/background e não é anunciada como memória de eventos reais.

Campos usam `KNOWN`, `PARTIAL`, `UNKNOWN` ou `UNAVAILABLE`, com motivo quando aplicável; os descritores nativos `known`, `available`, `complete` continuam dentro dos valores. Arrays vazios vindos de Lua como `{}` são normalizados nos campos de memória/resultados.

Observação Python tem limite de 32.768 bytes e expira em até 1.500 ms desde o contexto, mesmo que o prazo da conversa seja maior. Dados de outro UUID/mundo ou antigos são recusados. `ChatDispatcher.get_observation(world_id, uuid)` retorna cópia ou `UNAVAILABLE` se ausente/expirada; cache de até 128 entradas. Não é uma API de decisão nem autorização de execução.

Por segurança, pedido que aguarde demais no worker pode ter a projeção neural recusada por idade antes da inferência. Assim, fan-out não garante resposta de todos: fila/expiração, indisponibilidade ou alteração de contexto podem encerrar um pedido. O consumidor futuro deverá solicitar observações novas; não há replanejamento/inferência automática nesta fase.

## 6. Memória de conversa e resultado posterior

`Chat.getEvents(uuid)` expõe eventos v1, em memória e por mundo/UUID, sem SQLite:

```json
{
  "schema_version":1,
  "event_id":"speech:TIMESTAMP:SEQUENCIA",
  "uuid":"UUID_DO_NPC",
  "world_id":"MODO/MUNDO",
  "speaker":{"kind":"player","session":"player-session:TIMESTAMP:SEQUENCIA"},
  "recipients":["UUID_DO_NPC"],
  "text":"Carlos: me siga",
  "timestamp_ms":123456,
  "context":{"observation_id":"observacao","threat":{"known":false}},
  "request_id":"ID_DA_ACAO_OU_CHAT",
  "result":{"state":"ACTION_REQUESTED"}
}
```

Posteriormente `result` recebe resposta verbal, falha, descarte, expiração ou resultado nativo de ação. Comando substituído/cancelado atualiza apenas o evento correspondente ao seu ID. Gerações/callbacks continuam protegidos pelos mecanismos existentes do Executor/Locomotion. Uma ação aceita não é marcada como concluída antecipadamente.

Cada NPC guarda até 8 eventos, até 128 NPCs por mundo. A exposição retorna cópia; modificar o retorno não altera o registro interno. A troca do sobrevivente gera novo identificador de falante e descarta pedidos antigos, mantendo eventos individuais do mesmo mundo; troca de mundo invalida esses registros. Nada é persistido após reiniciar o mod/jogo. Isso não equivale a memória pessoal persistente.

Até dois eventos recentes, reduzidos por registros inteiros a no máximo 6.000 bytes, acompanham a projeção de estado. A versão armazenada em Lua continua com o texto original. A resposta verbal de um NPC não é copiada para a memória privada dos demais. Em chamada coletiva, cada destinatário registra a fala compartilhada do jogador e seu próprio resultado, inclusive silêncio deliberado.

## 7. Arquivos

Criados:

- `42/media/lua/client/ArayHumanNeuralInput.lua` — projeção on-demand para observação.
- `ai/language_encoder.py` — interface de codificador, indisponibilidade real e validações.
- `ai/neural_state.py` — contrato de estado, idade/binding/orçamento.
- `ai/test_routing_neural.py` — 58 testes novos.
- Este relatório.

Modificados:

- `ArayHumanRecipients.lua` — corpo sintático/indicador coletivo e ambiguidade de aliases coletivos.
- `ArayHumanChat.lua` — fronteira obrigatória, fan-out, sessões, memória, prioridade manual e telemetria de resultados.
- `ArayHumanTalkBar.lua`, `ArayHumanChatWindow.lua` — envio independente da seleção implícita.
- `ArayHumanConversation.lua` — encaminhamento do resultado/cancelamento já observado para a memória, sem novo executor.
- `ai/conversation_handler.py`, `ai/ollama_service.py` — validação obrigatória e exposição limitada de observações.
- Fixtures/cenários em `test_real_integration_fixes.py`, `test_real_error_fixes.py`, `test_language_unicode.py`, `test_conversation_backend.py`, `test_decision_handler.py` — entradas explicitamente endereçadas para o novo contrato.

## 8. Testes e próximo teste manual

Comando: `python -B -m pytest ai -q -p no:cacheprovider --tb=short`, com runtime de testes Lupa em PYTHONPATH temporário. Resultado final: **914 passed**.

Regressões novas cobrem: ausência de nome mesmo com seleção F7, texto narrativo, nomes múltiplos, sessão própria, resposta cruzada, aliases/acento, nomes/aliases duplicados, palavra coletiva ambígua, grupo silencioso, limitação de chamadas, comandos existentes, deduplicação, STOP prioritário durante inferência/cooldown, alvo individual, distância/mundo/UUID/morte, memória original Unicode e resultado posterior, limite/cópia de eventos, TalkBar com seleção morta, cabeçalho ausente/inválido/antigo, estado neural isolado/expirado, perfil desconhecido e codificador ausente/inválido. A suíte anterior continua cobrindo pathfinding/callbacks, persistência responsiva, renderização preservada e segurança do jogador por APIs simuladas.

Validação real ainda pendente, a ser iniciada manualmente pelo usuário:

1. Com Carlos selecionado no F7, enviar `Venha aqui`: nenhum NPC deve responder ou agir. Depois selecionar Tania e enviar `Carlos: me siga`: somente Carlos deve receber o comando existente.
2. Enviar `Carlos e Tania: me siga`; confirmar movimentos independentes. Enviar `Vocês: pare` imediatamente, inclusive com uma conversa pendente; conferir prioridade e descarte da resposta antiga.
3. Enviar `Vocês, como estão?`: esperar no máximo uma resposta verbal e conferir evento individual dos demais como `OBSERVED_SILENT`.
4. Testar nome/alias ambíguo, ator morto, distância superior a 10 tiles e troca de mundo. Nenhuma execução parcial deve acontecer por erro detectável na pré-validação.
5. Testar nomes acentuados, emoji e troca de seleção durante inferência; consultar histórico/eventos por UUID. Confirmar que o modelo escolhido não mudou e que o codificador permanece `UNAVAILABLE`.
6. Conferir os erros reais de timeout/fila/alteração de contexto, além de câmera, FBO, controles e balões existentes. Os testes simulados não substituem essa verificação.

O hash do JAR permanece `9F626AD644311AB301F8ABCD22AC93476B59B194BFF3147573DF96E3EAC86C2E`. Aguardar instruções antes da 3C.5B.
