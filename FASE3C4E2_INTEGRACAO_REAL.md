# Fase 3C.4E.2 — integração após teste real

## Escopo e resultado

Implementação e testes isolados; o jogo e os serviços não foram iniciados. Nenhuma compatibilidade funcional no jogo é declarada por este relatório. A base de 725 testes foi preservada. A suíte final contém 798 testes aprovados: 725 anteriores e 73 novos, incluindo Lua 5.1/5.4 com APIs nativas simuladas e Python com SQLite temporário/Ollama simulado.

## Causas confirmadas no código

- O chat ainda usava `npc_1`, histórico compartilhado e o NPC em foco no momento da resposta. Uma troca de seleção podia associar a resposta ao personagem errado.
- Spawn/restauração criavam descritores aleatórios sem um registro visual inicial. As roupas padrão eram vestidas sem entrar primeiro no inventário nativo. A condição era forçada a 100, valor que pode exceder a condição máxima do item. Essas falhas de código foram corrigidas; não há evidência suficiente para atribuir a elas uma exceção nativa específica observada em outra sessão.
- Não existia um caminho seguro entre comandos humanos no chat e o executor, nem contexto real de inventário/percepção enviado na conversa.
- A interface F7 não tinha consulta do inventário próprio do NPC selecionado.
- O diagnóstico offline usava um timestamp recém-atualizado em uma condição que permanecia verdadeira, repetindo o aviso. Isso explica a repetição do log, não comprova a causa de indisponibilidade de rede nas outras sessões. Nenhuma sondagem HTTP real foi feita.

## Aparência e APIs verificadas localmente

A implementação segue o formato usado pelo Lua vanilla `LastStand/LastStandSetup.lua` e as assinaturas/implementações das classes locais B42.13.1:

- `HumanVisual.getLastStandString/loadLastStandString`, `getBodyVisuals`, `SurvivorDesc.new`, `setFemale`, `getHumanVisual`.
- `ItemVisual.getLastStandString`, `ItemVisual.createLastStandItem`, `InventoryItem.getBodyLocation`, `ItemContainer.AddItem`, `IsoGameCharacter.setWornItem`.
- A criação nova continua usando o mecanismo existente; a restauração visual registrada cria um descritor sem randomizar sobrevivente, aplica sexo/visual e recria roupas por mecanismo nativo. Falha de recurso ou divergência no round-trip recusa a nova instância.

O registro inicial usa arquivos sidecar imutáveis `<ARAY_BRIDGE_DIR>/appearance/<hash-do-mundo>/<UUID>.json`, criados pelo serviço existente quando ele for iniciado pelo usuário. O diretório padrão é `C:/Users/llongaray/Zomboid/Lua/ArayHumanNPCTest`. Não houve alteração de SQLite existente. O protocolo distingue pendente, encontrado, ausente, conflito e falha. Publicação exclusiva impede sobrescrever aparência existente; conflito requer migração. Cada resposta verifica mundo, UUID e requisição. Limites: 32 roupas, 60 KB de visual serializado, espera de 15 s; polling limitado a duas requisições por 100 ms.

Não é possível recuperar aparência legada nunca registrada. A restauração desse NPC fica marcada para migração, sem randomização e sem bloquear a persistência dos demais. Uma instância legada ainda carregada pode ser capturada sem modificar seu visual. A confirmação de gravação depende do ACK do serviço; sair antes dele não garante persistência.

O formato vanilla registra cabelo, barba, cores, pele e variações visuais das roupas, mas não equivale ao save binário integral dos itens. Body visuals extras (por exemplo, sobreposições personalizadas), alterações futuras, sangue, desgaste e buracos não têm garantia de round-trip completo nesta fase; body visuals não vazios são recusados com diagnóstico específico em vez de descartados silenciosamente. A validação manual deve confirmar o visual inicial efetivamente utilizado pelo mod.

## Conversa, comandos e contexto

`ArayHumanConversation` é a fronteira de comandos humanos. Uma gramática pequena reconhece variações de “me siga”, “pare” e “vá até ali”. Apenas esse caminho local pode encaminhar origem manual. Ele reutiliza validações/candidatos e `Executor.requestLocomotion`, preserva prioridade emergencial e acompanha o resultado pelo ID da ação. A aceitação não é anunciada como conclusão. Falhas exibem o motivo real.

“Vá até ali” exige `target_id` validado e vinculado à observação atual; sem ele, informa que falta destino. Não há interpretação de coordenadas livres nem novo seletor de destino na UI. O menu existente “Ir até” continua disponível. Exemplos de API: `Chat.sendMessage("me siga", uuid)`; `Chat.sendMessage("vá até ali", uuid, target_id)`.

O protocolo de conversa v2 contém `id`, `npc_id` real, `world_id`, `session_id`, `session_started_at_ms`, `sequence`, `issued_at_ms`, `expires_at_ms`, `message` e `context`. A resposta ecoa os vínculos e traz `verbal_only=true`, `executable=false`, `success` e `reply` ou `error`. Campos de ação/decisão na resposta são recusados. Texto livre nunca é avaliado como Lua/Python nem encaminhado ao executor.

Históricos e pedidos são separados por UUID/mundo/sessão. Troca do sobrevivente, mundo, instância, sessão ou fatos relevantes invalida a resposta. O contexto vem de AgentState, Perception, Survival e inventário nativo; valores desconhecidos permanecem explícitos. Há verificação de linha de visão com `IsoGameCharacter.CanSee` da instalação local, a partir do NPC e sem câmera. Isso não é uma garantia de campo visual angular. Entidades atrás de bloqueios não são incluídas. O filtro usa apenas quadrados carregados, raio de até 10 tiles, até 128 leituras de objetos, até 12 zumbis, 12 NPCs e 8 portas. Não faz varredura global nem revela recipientes/loot próximos não confirmados.

Contexto máximo de 24 KB, requisição de 32 KB, resposta de 64 KB, mensagem de 2.000 caracteres. O servidor exige contexto recente (até 1.500 ms na submissão). Pedido Lua expira em 20 s; inferência HTTP limitada a 15 s e ao prazo restante. Antes de exibir uma resposta, o cliente obtém novo contexto e compara inventário, contagens observadas, saúde/pânico e estado de execução. Essa comparação não é um rastreamento exaustivo de todas as posições e mudanças do mundo durante a inferência.

Perguntas factuais diretas sobre inventário, ameaças e portas usam resumo determinístico dos dados disponíveis. A conversa geral recebe contexto e instruções de desconhecimento; isso reduz, mas não prova ausência de alucinações semânticas do modelo. Respostas permanecem sem capacidade de executar ações.

## Concorrência e offline

Chat v2 usa um worker dedicado, fila máxima de quatro pedidos e sessões/históricos limitados. O loop da mailbox apenas admite pedidos e publica resultados. Cada worker lê identidade em conexão SQLite própria, curta e somente leitura; não compartilha a conexão de persistência entre threads. Ollama lento não bloqueia `persist`/`ping` nesse caminho. O modelo salvo por mundo é preservado. O caminho legado continua para compatibilidade; não houve redesenho de toda inferência antiga do serviço.

O indicador offline antigo não veta sozinho uma nova tentativa v2 com modelo configurado. Logs agora distinguem motivo sanitizado e transições online/offline. Exceções registram tipo, sem prompt, resposta completa ou dados sensíveis. A causa real de eventual servidor offline ainda depende de validação manual dos novos diagnósticos.

## Inventário e interface

`Inventory.readInventory(uuid)` lê exclusivamente o recipiente principal do NPC validado: itens, IDs nativos, tipo, quantidade conhecida/desconhecida, peso e capacidade. Máximo de 128 itens; leitura parcial declarada. Não expande bolsas aninhadas nem usa o inventário do jogador.

F7 tem seleção de NPC para conversa/inventário e botão “Inventário”. A janela é somente leitura, com atualização explícita, quantidade e carga. Não contém drag-and-drop, transferência ou criação de itens. Seleção não altera câmera/foco global. Controles manuais antigos mantêm seu funcionamento anterior. A janela fecha na troca de mundo; ator inválido não é substituído silenciosamente por outro NPC.

## Arquivos desta fase

Criados:

- `42/media/lua/client/ArayHumanJson.lua` — JSON limitado, sem avaliação de código.
- `42/media/lua/client/ArayHumanAppearance.lua` — captura/restauração e protocolo visual.
- `42/media/lua/client/ArayHumanConversation.lua` — contexto, intenções humanas e resultados.
- `42/media/lua/client/ArayHumanInventoryWindow.lua` — inventário somente leitura.
- `ai/appearance_store.py` — sidecar imutável.
- `ai/conversation_handler.py` — conversa v2, identidade isolada e despacho limitado.
- `ai/test_real_integration_fixes.py`, `ai/test_conversation_backend.py` — regressões novas.
- Este relatório.

Modificados:

- `ArayHumanTest.lua`, `ArayHumanLifecycle.lua` — spawn, roupas e restauração.
- `ArayHumanChat.lua`, `ArayHumanTalkBar.lua`, `ArayHumanChatWindow.lua` — UUID/sessão, protocolo, envio e retorno.
- `ArayHumanInventory.lua`, `ArayHumanUi.lua` — leitura nativa e seleção F7.
- `ai/ollama_service.py` — operações de aparência/chat, concorrência e diagnóstico.

Não foram alterados mecanismos de FBO, câmera, posição/estilo dos balões, modelo ou controle WASD. PUSH_ZOMBIE e CLIMB_STAIRS continuam bloqueados. Não há RL nem loop de decisões autônomas.

## Testes e limites da evidência

Comando: `python -B -m pytest ai -q -p no:cacheprovider --tb=short`, com runtime Lupa de testes no PYTHONPATH temporário.

Novos casos cobrem JSON malformado/injeção, vínculo UUID/mundo/sessão, resposta atrasada e foco trocado, isolamento de históricos/personalidades, comandos e emergência, inventários distintos/vazios/parciais, UI somente leitura, restauração visual e migração, APIs ausentes, visibilidade bloqueada, expiração, fila lenta com persistência responsiva, modelo selecionado e diagnóstico offline. SQLite e mailbox são temporários/simulados; nenhuma base existente foi aberta para escrita pelo teste.

As APIs Java foram inspecionadas estaticamente. Animações, vestuário, interface e comportamento físico ainda exigem o teste no jogo. Os testes não substituem essa evidência.

## Roteiro de validação manual posterior

1. Com serviço/jogo iniciados manualmente, criar NPC novo, anotar mundo/UUID e esperar confirmação `appearance_ready` da operação de criação. Registrar cabelo, barba, pele e roupas. Recarregar e comparar o mesmo UUID; verificar ausência de roupas duplicadas. NPC legado sem registro deve indicar migração, sem aparência nova.
2. Criar/selecionar dois NPCs no F7. Abrir inventário de cada um e conferir itens, quantidades e carga contra o estado nativo. Confirmar que jogador e outro NPC não sofrem alterações e que a janela não transfere itens.
3. Conversar com A e mudar seleção para B antes da resposta. Conferir que apenas A responde e que os históricos não se misturam. Testar morte, troca do sobrevivente e mundo durante pedido pendente.
4. Testar “me siga” e “pare” com dois NPCs; conferir `chat_intent`, `action_requested`, `action_result` e o resultado físico. Testar emergência concorrente e falhas de pathfinding/alcance. “Vá até ali” sem destino deve recusar explicitamente; com candidato válido deve passar pelas mesmas validações do executor.
5. Perguntar sobre inventário/ameaças/portas. Colocar zumbi atrás de parede, comparar leitura parcial, afastar além do alcance e alterar inventário durante inferência. Nenhuma ausência de dados deve ser apresentada como certeza de ambiente seguro.
6. Com Ollama indisponível, testar comandos locais e perguntas factuais, depois conversa geral. Conferir erro/timeout limitado, motivo sanitizado e um aviso por transição offline. Restaurar disponibilidade manualmente e verificar nova tentativa sem trocar o modelo.
7. Verificar no log os eventos `inventory_snapshot` e `perception_context`, sem prompts completos. Revalidar FBO, câmera, balões, controles e fuga existentes.

Aguardar validação manual e novas instruções antes de avançar.
