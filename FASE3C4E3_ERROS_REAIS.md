# 3C.4E.3 — correções dos erros reais B42.13.1

## Resultado e escopo

Corrigidos os caminhos de `context_budget`, serialização de roupa com `inventoryItem` nulo e polling com `reader_nil`. Regressão completa: **817 testes aprovados**, sendo os **798 anteriores + 19 regressões novas**. Os testes usam Lua real via Lupa 5.1/5.4 com APIs simuladas, mailbox em memória e Python com SQLite temporário/Ollama simulado. Não foi executado teste dentro do jogo.

Não foram iniciados jogo, Ollama ou serviços. Não houve alteração de JARs, executáveis, saves ou SQLite real, nem commit/push. FBO, câmera, WASD, balões, modelo e Executor não foram modificados. PUSH_ZOMBIE e CLIMB_STAIRS permanecem bloqueados. A fase 3C.5 não foi iniciada.

## 1. Chat: causa e correção

O cliente media o JSON compacto emitido por Lua, enquanto `conversation_handler.validate` reserializava com os padrões do Python: espaços adicionais e `ensure_ascii=True`. Um caractere como `ç` ocupa dois bytes UTF-8 no formato de transporte, mas seis caracteres como escape `\u00e7`. Assim, um contexto válido próximo de 23,8 KB podia ultrapassar artificialmente 24.000 bytes na validação Python. O tamanho de percepção/AgentState contribuía com campos detalhados desnecessários para perguntas simples. A inspeção não encontrou necessidade de alterar os produtores de snapshots ou seus caches.

Implementação:

- `Conversation.compact(context, pergunta, orçamento)` projeta inventário em ID/tipo/quantidade, mantém saúde/condições/necessidades/política e remove detalhes redundantes de observação/scan. O snapshot original de AgentState/Perception não é alterado.
- Meta inicial de **12.000 bytes** de contexto; remoção de campos/entradas inteiras, sempre seguida de serialização JSON completa para medir. Nunca há corte arbitrário do JSON.
- Perguntas de inventário preservam seus itens antes das listas espaciais. Itens cujo nome de tipo aparece literalmente na pergunta são priorizados, com ordenação estável para os demais. Perguntas gerais recebem até oito itens; ameaças têm preferência sobre NPCs próximos e portas nesse caso. Essa seleção é lexical, não interpretação semântica de todos os sinônimos.
- Reduções mantêm UUID/mundo/timestamps, quantidades desconhecidas e sinalizadores de resumo/parcialidade. Listas reduzidas não são anunciadas como completas. Não há inferência de itens nem consulta adicional ao mapa.
- `Chat.sendMessage` inclui pergunta e todo o envelope de protocolo na medição de **32.768 bytes**. Há redução adicional por orçamento quando necessário. O contexto revalidado na resposta usa a mesma pergunta/relevância.
- Python conta JSON compacto em UTF-8, sem escape ASCII artificial, mantendo os limites de 24.000 bytes para contexto recebido e 32.768 para requisição lógica completa.
- Ao montar mensagens de inferência, o orçamento inclui a serialização da lista de mensagens, incluindo escapes/overhead. Turnos antigos completos são descartados antes dos recentes e da pergunta atual quando ultrapassam 32.768 bytes. O limite independente do prompt de sistema continua existindo para entradas excepcionais.
- UUID, mundo, sessão, sequência, expiração, vínculo de inventário, descarte de respostas antigas e natureza apenas verbal da resposta Python continuam validados.

Os orçamentos são em bytes; não equivalem a garantia de número de tokens. Modelo, perfil e janela de contexto do Ollama não foram alterados. Contextos essenciais excepcionalmente grandes ou malformados ainda são recusados com erro explícito; não são substituídos por informações inventadas.

## 2. Aparência: causa nativa comprovada

Inspeção estática da instalação local, com `javap -c -p`, sem executar o jogo:

- `InventoryItem.getVisual()` cria/configura o `ItemVisual` quando o recurso de roupa está pronto, mas **não chama `setInventoryItem(this)`** nesse caminho.
- `ItemVisual.getLastStandString()` lê `inventoryItem` e chama diretamente `InventoryItem.getFullType()` (offsets 62–65 do bytecode), sem teste de nulo. Isso explica a NPE reproduzida.
- `ItemVisual.getInventoryItem()` e `setInventoryItem(InventoryItem)` estão presentes na B42.13.1.

`Appearance` agora usa a mesma função protegida na captura e no round-trip de restauração:

1. Obtém o visual a partir do item real da lista de roupas vestidas ou do item nativo recém-criado.
2. Consulta o dono com proteção para API indisponível.
3. Se o dono é nulo, associa esse item real por `setInventoryItem`.
4. Reconsulta e exige identidade com o item esperado.
5. Só então chama `getLastStandString`.

Dono diferente não é sobrescrito. Visual indisponível, API ausente ou associação não confirmada retornam diagnósticos específicos (`clothing_visual_unavailable`, `clothing_owner_api`, `clothing_owner_mismatch`, `clothing_owner_unavailable`). A captura falha sem publicar dados incompletos e sem lançar a exceção ao spawn. A restauração continua falhando de forma fechada se o visual não puder ser reproduzido.

Não foram adicionados itens, randomização, alterações de condição ou novas regras de spawn. A função apenas liga o visual ao item que já o possui. A gravação imutável dos sidecars, recusas de conflito e migração de aparência legada foram preservadas. O formato visual e suas limitações anteriores (por exemplo, body visuals extras) continuam os mesmos.

## 3. Bridge: causa e correção

`readFile` chamava explicitamente `error("reader_nil")` quando `getFileReader` retornava nulo. Esse resultado é esperado enquanto o Python ainda não publicou o pong. `pcall` capturava a falha em Lua, mas o caminho criava uma exceção a cada polling. Além disso, uma falha em `readLine` podia deixar o reader sem fechamento, e o parser antigo por padrões aceitava fragmentos sem validar o documento JSON completo.

Agora:

- Ausência do arquivo retorna `not_ready`, sem chamar `error`.
- Falhas de abertura/leitura ficam contidas e retornam indisponibilidade temporária. O fechamento é tentado mesmo após erro ou excesso de tamanho.
- Leitura limitada a **65.536 bytes** por resposta; arquivos vazios, incompletos, inválidos, com chaves duplicadas, tipo incorreto ou ID diferente não consomem a requisição pendente.
- `acceptPong` usa o decoder JSON de dados existente, exige ID exato, `kind=pong`, `ok=true` e ausência de campo de ação. O parser por padrões foi removido.
- Arquivo inválido/temporário não gera log recorrente por frame nem reinicia o prazo. Permanecem polling de 1 s, timeout de 10 s e máximo de três tentativas. Um pong válido posterior ainda pode concluir o mesmo pedido.
- Não houve alteração no protocolo de persistência ou no serviço Python por causa desta correção.

## Arquivos

Modificados:

- `42/media/lua/client/ArayHumanConversation.lua`: compactação por pergunta e bytes.
- `42/media/lua/client/ArayHumanChat.lua`: orçamento total do envelope e revalidação por mesma pergunta.
- `42/media/lua/client/ArayHumanAppearance.lua`: associação/validação nativa antes da serialização.
- `42/media/lua/client/ArayHumanBridge.lua`: leitura limitada, fechamento e validação JSON do pong.
- `ai/conversation_handler.py`: contagem UTF-8 consistente e orçamento de histórico.
- `ai/test_real_integration_fixes.py`: simulação das APIs reais de dono do visual na fixture existente.

Criados:

- `ai/test_real_error_fixes.py`: 19 regressões específicas.
- Este relatório.

## Testes executados

Comando de regressão: `python -B -m pytest ai -q -p no:cacheprovider --tb=short`, com o runtime Lupa de testes em PYTHONPATH temporário.

Cobertura nova:

- Contexto UTF-8 de aproximadamente 23,8 KB aceito, embora a serialização antiga excedesse o limite; envelope realmente excedente continua recusado.
- Histórico extenso reduzido por turnos, preservando o mais recente e a pergunta atual.
- Pergunta simples com 128 itens extensos: requisição Lua válida, pequena e aceita pelo validador Python real, seguida de resposta correlacionada.
- Inventário pertinente priorizado sobre percepção extensa; item citado no final da lista preservado; quantidade desconhecida não convertida em zero.
- Dono visual nulo reparado antes da chamada nativa simulada; captura repetível sem duplicar itens; dono estranho, API ausente e setter sem efeito recusados sem chamar serialização inválida.
- Bridge sem arquivo, com JSON parcial/duplicado/ID errado e posterior resposta válida; nenhum `error` no caminho normal de ausência.
- Falha de leitura fecha reader e mantém correlação para nova tentativa; tamanho excessivo é contido; timeout e três tentativas continuam limitados.

As regressões anteriores continuam verificando restauração/imutabilidade, isolamento entre NPCs, mundo/sessão, expiração, prioridade emergencial, inventário do jogador preservado e persistência responsiva com inferência lenta.

SHA-256 do JAR local permaneceu `9F626AD644311AB301F8ABCD22AC93476B59B194BFF3147573DF96E3EAC86C2E`.

## Próxima validação manual

1. Perguntar “Olá, quem é você?” e sobre inventário em um ambiente com percepção extensa. Verificar resposta e tamanho do contexto nos logs, sem `context_budget` para esses casos normais.
2. Testar pergunta com acentos, dois NPCs, troca de seleção durante a espera e resposta após expiração; conferir ausência de mistura de respostas.
3. Criar NPC, verificar captura visual confirmada; recarregar o mesmo UUID/mundo e comparar roupas/cabelo/barba. Conferir ausência da NPE e de roupas duplicadas. Sidecar existente não deve ser regravado. Legado ausente deve continuar exigindo migração.
4. Com serviço inicialmente ausente ou demorando a publicar pong, observar espera/timeout sem `reader_nil` recorrente. Ao disponibilizar uma resposta válida dentro do prazo, conferir correlação normal. Nenhum serviço foi iniciado nesta entrega para executar essa etapa.

Estes passos ainda exigem teste real pelo usuário. Aguardar validação e novas instruções; não avançar à 3C.5.
