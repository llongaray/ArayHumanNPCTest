# 3C.4E.4 — PT-BR, Unicode e preparação de destinatários

## Resultado

**856 testes aprovados: 817 anteriores + 39 novos.** Testes Python com clientes simulados/SQLite temporário e testes Lua reais via Lupa 5.1/5.4 com APIs simuladas. A inspeção nativa foi estática; não houve teste dentro do Project Zomboid.

Não foram iniciados jogo, Ollama ou serviços. Não houve commit/push, alterações de saves/SQLite real, JARs/executáveis, modelo, FBO, câmera, WASD ou Executor. Não houve mudança de aparência, posição, estilo ou renderizador dos balões. Não há RN, RL ou novo interpretador de significado de comandos.

## Idioma e identidade

O prompt anterior dependia do `speaking_style` opcional para solicitar português e não tinha verificação de idioma. O contexto multilíngue, histórico e entradas em inglês podiam orientar o modelo em outra direção.

O prompt de conversa agora exige explicitamente PT-BR, inclusive quando a entrada é em outro idioma. Essa regra está no início e no fim das instruções de identidade. O caminho v2 usa nome/sobrenome, profissão registrada, lore, personalidade e estilo do NPC real lidos do SQLite em conexão própria e somente leitura. Não usa a persona de outro NPC ou uma profissão inventada. O caminho legado de conversa também recebe a política.

`ai/language_policy.py` detecta predominância de inglês por marcadores lexicais conservadores, incluindo saudações inequívocas curtas. Nomes próprios, siglas, termos de itens e profissões isoladas não são tratados automaticamente como erro de idioma. Essa heurística não é um classificador universal de línguas: mensagens curtas/ambíguas ou misturas podem não ser identificadas.

Se detectar inglês, permite **uma única correção**, usando o mesmo cliente, modelo, perfil, identidade, contexto e pergunta. O prazo da segunda chamada é o restante do orçamento original, sem reiniciá-lo: até 15 s no caminho v2, limitado também pela validade da requisição, e o timeout existente no legado. A correção não é um novo pedido de ação. Inglês persistente ou correção expirada retorna erro, sem terceira tentativa. A resposta recusada não entra no histórico v2; somente o resultado aceito é adicionado. Nenhuma memória ou identidade persistida é reescrita para traduzir texto.

Há limite de tamanho e redução de turnos antigos para acomodar a correção. O log novo informa apenas `event=language_correction result=accepted`, sem prompt nem conteúdo completo.

## Codificação: evidência e correções

Inspeção das classes locais B42.13.1:

- `LuaManager$GlobalObject.getFileReader/getFileWriter` usam `StandardCharsets.UTF_8` para a mailbox.
- `IndieFileLoader` usa UTF-8 no caminho normal de leitura dos arquivos Lua do mod; existe fallback dependente da plataforma, que não foi exercitado.
- Kahlua `StringLib.stringChar` converte inteiros em caracteres Java (`i2c` e `StringBuilder.append(char)`); `stringByte` opera sobre caracteres Java. Isso difere de Lua 5.1/5.4 padrão, onde strings são bytes.

Falhas confirmadas no código:

1. O parser próprio de persistência convertia escapes `\uXXXX` acima de 255 em `?`, perdendo informações de forma irreversível.
2. O codec JSON combinava `string.char` Latin-1 com sequências UTF-8 manuais, sem diferenciar Kahlua de Lua padrão. Unicode escapado e literal não tinham comportamento uniforme.
3. O chat continha uma conversão heurística UTF-8 → Latin-1 antes de exibir/guardar a resposta. Não há motivo para essa conversão no contrato atual de Unicode Java + mailbox UTF-8.
4. Cortes em 200 posições para bolhas e o clone genérico de histórico em 1.024 posições podiam dividir um caractere UTF-8 ou um par substituto, dependendo do runtime.

Correções:

- Novo `ArayHumanText.lua` distingue os dois modelos de string por uma verificação local da biblioteca, sem alterar o runtime.
- `Text.char` produz Unicode Java/UTF-16 em Kahlua e UTF-8 em Lua padrão, incluindo pares substitutos para caracteres suplementares. `Text.bytes` mede o custo UTF-8 real também em Kahlua; os limites de JSON/chat passam a usar essa contagem.
- `ArayHumanJson` usa essa conversão para todos os escapes Unicode; o parser de persistência foi substituído pelo mesmo codec de dados limitado. JSON literal e escapado preservam o mesmo texto.
- A conversão Latin-1 do chat foi removida. Histórico guarda os textos originais e retorna cópias dos registros sem o corte genérico em bytes. O número de registros e os limites de entrada/resposta continuam limitados.
- O envio de trechos ao mecanismo existente de balões respeita limites de caracteres UTF-8/pares UTF-16, sem mudar posição, estilo ou implementação visual.
- Os rótulos de persistência agora usam `Persistência`; o rótulo `Inventário` permanece Unicode.
- `Text.compare` é exclusivo para comparação: caixa, acentos latinos e formas decompostas equivalentes. A gramática atual de comandos usa esse normalizador, com as mesmas intenções e frases anteriores. Mensagens, nomes, memórias e dados originais não são substituídos pelo resultado normalizado.

Foram verificados 73 arquivos Lua/Python ativos: todos decodificam como UTF-8, sem U+FFFD e sem os literais `Invent?rio`/`Persist?ncia`. **Não foi possível provar a origem exata desses dois rótulos na sessão real nem reproduzir uma falha da fonte gráfica sem iniciar o jogo.** O parser antigo explica perda real de outros caracteres, mas não deve ser apresentado como prova suficiente de uma falha específica do glifo `á`/`ê` na UI. Os caminhos lossy identificados foram corrigidos; a renderização ainda exige teste manual.

Não foi ativada transliteração ASCII na interface, pois não existe evidência de incompatibilidade do componente visual. Não há reparação heurística de `?` já persistido: o caractere original não pode ser inferido com segurança. Nenhum banco existente foi migrado ou regravado.

## Contrato futuro de destinatários

Regra obrigatória da integração futura:

- Toda mensagem do jogador exige destinatário explícito: nome/alias de NPC, múltiplos nomes ou chamada coletiva (`vocês`, `pessoal`, `todos`).
- **Sem destinatário explícito, nenhum NPC deve responder nem executar ações.**
- A seleção do F7 não constitui destinatário implícito.
- Resolução resulta em UUIDs vinculados ao mundo; identidade ambígua ou desconhecida bloqueia o conjunto inteiro. Nenhum primeiro candidato é escolhido por conveniência.
- A RN futura interpreta o significado da mensagem somente depois dessa fronteira. O resolvedor não remove nomes do texto original, não escolhe intenção nem executa ações.

Foi implementado **somente o resolvedor isolado**, `ArayHuman.Recipients`, sem ligação ao pipeline atual:

```lua
Recipients.setAliases(uuid, {"Doutor João"}, expected_world_id)
Recipients.resolve("João e Maria: precisamos conversar", expected_world_id)
-- {schema_version=1, world_id=..., captured_at_ms=...,
--  status="resolved", uuids={uuid_joao, uuid_maria}}
```

Sintaxe determinística desta preparação: vocativo no início encerrado por `:` ou `,`. Para listas com vírgulas, usar `:` no fim: `João, Maria: ...`. Também aceita `João e Maria, ...`, `@João: ...`, aliases e equivalentes ASCII. Menção narrativa como “Vi João ontem” não é destinatário. Sem separador explícito não há resolução; outras formas ficam para a integração futura, sem inferir intenção agora.

Nomes vêm dos atores nativos validados no roster atual (`ARAY_Name` e descritor), não de uma seleção F7. Aliases são registrados apenas por chamada local confiável, copiados, limitados a oito por UUID e invalidados ao trocar de mundo. Não há persistência nova de aliases. Até 128 NPCs vivos/carregados são examinados, com entrada limitada a 2.000 bytes. Resultado é uma lista de UUIDs únicos e ordenados, sem referências Java ou código. `expected_world_id` permite recusar pedidos de outro mundo. Não existem callbacks, inferência, envio ou OnTick no módulo.

**Integração adiada para 3C.5A:** o chat atual possui uma requisição/retorno por NPC e a TalkBar verifica distância em relação a um ator selecionado. Envio coletivo, silêncio global sem vocativo e tratamento de resultados por destinatário exigem alterar essas interfaces; retirar vocativos antes do interpretador atual também mudaria o caminho de comandos. Fazer essa ligação parcial nesta etapa contrariaria a restrição de não alterar o pipeline/interpretador. Portanto, o contrato acima está preparado e testado, mas **a regra de silêncio ainda não é imposta ao chat legado/F7**. Não se deve anunciar roteamento coletivo operacional nesta fase.

A integração futura deverá chamar o resolvedor, recusar qualquer resultado não resolvido, revalidar mundo/UUID/alcance antes do envio e tratar cada destinatário em sua sessão própria, sem aceitar origem manual declarada pelo modelo.

## Arquivos

Criados:

- `42/media/lua/client/ArayHumanText.lua` — Unicode, contagem UTF-8, comparação e cortes seguros.
- `42/media/lua/client/ArayHumanRecipients.lua` — resolvedor isolado de destinatários.
- `ai/language_policy.py` — PT-BR, verificação e correção única com deadline.
- `ai/test_language_unicode.py` — 39 regressões novas.
- Este relatório.

Modificados:

- `ArayHumanJson.lua`, `ArayHumanPersist.lua` — codec Unicode uniforme.
- `ArayHumanChat.lua` — transporte/histórico sem conversão Latin-1, trechos Unicode seguros, orçamento em bytes.
- `ArayHumanConversation.lua` — normalização exclusiva de comparação e medição em bytes.
- `ArayHumanUi.lua`, `ArayHumanLifecycle.lua` — rótulo Unicode de persistência.
- `ai/chat_handler.py`, `ai/conversation_handler.py` — política de idioma, profissão/identidade e correção controlada.
- `ai/test_real_integration_fixes.py` — carga do módulo Text na fixture existente.

Não houve mudança em `ArayHumanSpeechBubble.lua` ou no Executor.

## Testes e validação pendente

Comando de regressão: `python -B -m pytest ai -q -p no:cacheprovider --tb=short`, usando o runtime Lupa de testes em PYTHONPATH temporário. Resultado final: **856 passed**.

Novos testes incluem: inglês/PT-BR, saudações, nomes e termos ambíguos; uma correção com mesmo modelo/identidade e prazo restante; inglês persistente sem loop/histórico contaminado; expiração; Unicode literal/escapado e caracteres fora de Latin-1/emoji; persistência simulada; acentos compostos/decompostos; cortes em limites de UTF-8; histórico acima de 1.024 bytes; rótulos passados aos construtores F7 simulados; nome/alias, múltiplos nomes, chamadas coletivas, ausência de vocativo, nomes/aliases duplicados, ator morto e invalidação por mundo. O resolvedor não emite arquivos ou ações nos testes.

Os testes não executam o Kahlua embarcado ou as fontes do jogo: esse ramo foi auditado estaticamente, e sua execução real permanece pendente. A heurística de idioma não garante reconhecimento de toda frase curta ou idioma misto. A fidelidade semântica das respostas geradas ainda depende de validação manual.

Próximo teste manual, iniciado pelo usuário:

1. Confirmar `Inventário`/`Persistência` no F7 e nomes acentuados após leitura da identidade. Se ainda houver `?`, registrar o componente e se o mesmo texto aparece íntegro no histórico/JSON, sem coletar prompts completos.
2. Conversar em português e inglês com dois NPCs, conferindo resposta em PT-BR, nome/profissão/persona corretos, modelo inalterado e isolamento por UUID. Uma resposta que permaneça em inglês deve falhar após no máximo uma correção.
3. Comparar mensagens com `João`, `ação`, caracteres não latinos e emoji na mailbox, histórico e balões. A disponibilidade de glifos específicos da fonte, especialmente emoji, não foi comprovada.
4. Recarregar identidade já existente sem regravá-la para tradução ou ASCII. Dados que já contenham `?` exigem migração explícita posterior, sem adivinhação.

SHA-256 do JAR permaneceu `9F626AD644311AB301F8ABCD22AC93476B59B194BFF3147573DF96E3EAC86C2E`. Aguardar instruções; não iniciar 3C.5A automaticamente.
