# Fase 2 — Seleção de Modelos e Inicialização Automática

## ✅ Implementado

### 1. Seleção de modelos por mundo

**Recursos:**
- Dropdown no F7 com todos os modelos detectados pelo Ollama
- Seleção persistida por `world_id` (modo/nome do mundo)
- Ao entrar em um mundo, o mod restaura automaticamente o modelo previamente selecionado
- Se o modelo salvo não estiver mais disponível, mostra "nenhum modelo selecionado" e aguarda seleção manual
- Validação no Python: modelo deve existir em `/api/tags`
- Confirmação via pong após salvar a configuração

**Arquivos:**
- `42/media/lua/client/ArayHumanUi.lua` — Dropdown `ISComboBox` adicionado ao F7
- `42/media/lua/client/ArayHumanOllama.lua` — Função `selectModel()` para enviar seleção
- `42/media/lua/client/ArayHumanBridge.lua` — Função `sendModelSelection()` para comunicação
- `ai/ollama_service.py` — Processamento de `set_model` e integração com `world_models.py`
- `ai/world_models.py` — **NOVO** módulo para gerenciar seleções por mundo

**Persistência:**
- `Zomboid/Lua/ArayHumanNPCTest/world_models.json` — mapeamento `world_id -> model_name`

### 2. Inicialização automática do serviço Python

**Resultado da investigação técnica:**

O Lua do Project Zomboid **não pode iniciar processos externos**. APIs verificadas:
- `os.execute` — não disponível
- `io.popen` — não disponível
- `Runtime.exec` / `ProcessBuilder` (Java) — não expostos ao Lua
- `LuaManager.GlobalObject` — sem métodos de execução de processos

**Solução implementada: Launcher Batch**

Arquivo: `ArayHumanNPCTest_Launcher.bat`

**Funcionalidades:**
1. Detecta Python automaticamente (PATH, `py` launcher, localizações comuns)
2. Verifica se o serviço já está rodando via PID file
3. Inicia `ollama_service.py` em segundo plano
4. Inicia o Project Zomboid
5. Aguarda o jogo fechar
6. Encerra o serviço Python automaticamente pelo PID
7. Limpa recursos (PID file, processos órfãos)

**Logs:**
- `ai/service.log` — saída completa do Python
- `ai/service.pid` — PID do processo Python

**Encerramento seguro:**
- PID salvo no início do serviço
- `atexit` registra limpeza automática
- Launcher encerra via `taskkill /PID`
- Fallback: encerra via linha de comando contendo `ollama_service.py`

**Segurança:**
- Não requer privilégios de administrador
- Não cria serviços permanentes do Windows
- Não modifica registro ou tarefas agendadas
- Fácil de reverter (usar executável original)

**Limitação documentada:**
- Iniciar o jogo pelo executável original **não iniciará o serviço automaticamente**
- Para automação completa, usar o launcher `.bat`
- Inicialização manual via PowerShell continua funcionando normalmente

## Como testar

### Opção 1: Launcher automático (RECOMENDADO)

1. Fechar o jogo e o serviço Python se estiverem rodando
2. Ajustar `GAME_DIR` no topo de `ArayHumanNPCTest_Launcher.bat` se necessário
3. Executar `ArayHumanNPCTest_Launcher.bat`
4. O Python e o jogo serão iniciados automaticamente
5. Entrar no mundo de teste
6. Pressionar F7
7. Verificar dropdown "Modelo:" com os 3 modelos disponíveis
8. Selecionar um modelo
9. Verificar no console do launcher: `[ARAY] modelo selecionado world=...`
10. Fechar o jogo — o Python será encerrado automaticamente

### Opção 2: Inicialização manual (continua funcionando)

1. Abrir PowerShell no diretório do mod
2. Executar: `python ai\ollama_service.py`
3. Iniciar o jogo normalmente
4. Entrar no mundo
5. F7 → selecionar modelo
6. Ao sair, encerrar o PowerShell manualmente (Ctrl+C)

### Opção 3: Testar sem o jogo

```powershell
cd c:\Users\llongaray\Zomboid\mods\ArayHumanNPCTest
python ai\ollama_service.py
# Verificar criação de ai/service.pid
# Ctrl+C para encerrar
# Verificar remoção automática de ai/service.pid
```

## Validação esperada

### No F7:
```
Ollama: 0.21.0 | <modelo_selecionado>

Modelo:
[Dropdown com 3 opções]
```

### No console Python:
```
[ARAY] servico PID=12345 gravado em ...
[ARAY] servico ollama iniciado dir=...
[ARAY] ollama online version=0.21.0 models=3
[ARAY] ponte ping id=... world_id=sandbox/Riverside
[ARAY] modelo selecionado world=sandbox/Riverside model=hf.co/PatrickPat/remnants-llm-v5-GGUF:Q4_K_M
[ARAY] ponte pong id=...
```

### No console Lua (in-game):
```
[ARAY] ponte ping id=...
[ARAY] ollama modelo selecionado via UI name=...
[ARAY] ponte pong recebido id=...
```

### Ao reiniciar o mundo:
- Modelo previamente selecionado aparece automaticamente no dropdown
- Não precisa selecionar novamente

### Ao trocar de mundo/mapa:
- Cada mundo tem sua própria seleção de modelo salva
- Modelo é restaurado automaticamente ao entrar no mundo

## Arquivos criados/modificados

### Novos:
- `ai/world_models.py` — gerenciamento de modelos por mundo
- `ArayHumanNPCTest_Launcher.bat` — launcher automático
- `FASE2_COMPLETO.md` — esta documentação
- `INICIALIZACAO_AUTOMATICA.md` — investigação técnica

### Modificados:
- `42/media/lua/client/ArayHumanUi.lua` — dropdown de modelos
- `42/media/lua/client/ArayHumanOllama.lua` — função `selectModel()`
- `42/media/lua/client/ArayHumanBridge.lua` — função `sendModelSelection()`
- `ai/ollama_service.py` — integração com `world_models.py`, PID tracking

### Gerados automaticamente:
- `ai/service.pid` — PID do processo Python (deletado ao encerrar)
- `ai/service.log` — log do serviço Python
- `Zomboid/Lua/ArayHumanNPCTest/world_models.json` — seleções por mundo

## Como reverter

### Para voltar à Fase 1:
1. Deletar `ai/world_models.py`
2. Deletar `ArayHumanNPCTest_Launcher.bat`
3. Restaurar backups de:
   - `ArayHumanUi.lua`
   - `ArayHumanOllama.lua`
   - `ArayHumanBridge.lua`
   - `ollama_service.py`

### Para desabilitar automação:
- Continuar usando `python ai\ollama_service.py` manualmente
- Não usar o launcher `.bat`

## Próxima fase (Fase 3)

**Não implementado ainda:**
- Chat com o NPC
- Personalidade editável
- Autonomia de decisões
- Execução de ações baseadas em IA
- Memória de conversas

## Limitações conhecidas

1. **Launcher não é nativo do mod:**
   - Abrir o jogo pelo executável original não inicia o Python
   - Solução: documentar claramente no README principal

2. **PID file pode permanecer após crash:**
   - Se o jogo/Python travar, `service.pid` pode não ser deletado
   - Solução: launcher oferece opção de limpar PID antigo

3. **Detecção de Python:**
   - Tenta PATH, `py`, e localizações comuns
   - Se não encontrar, falha com mensagem clara

4. **Múltiplas instâncias:**
   - Launcher detecta PID existente e avisa
   - Oferece encerrar automaticamente

## Segurança mantida

✅ Nenhum comando arbitrário executado  
✅ Nenhuma modificação de saves  
✅ Nenhuma ação autônoma (ainda)  
✅ Nenhuma modificação do JAR do jogo  
✅ Nenhum privilégio elevado necessário  
✅ Fácil de reverter  
✅ Processo Python isolado e terminável  

## Estado dos TODOs

- ✅ **mailbox** — Ponte Lua ↔ Python validada
- ✅ **ollama-status** — Ollama detectado, modelos listados, seleção por mundo implementada
- ⏳ **chat-persona** — Aguardando Fase 3
- ⏳ **four-actions** — Aguardando Fase 3
- ⏳ **memory** — Aguardando Fase 3
- ⏳ **npc-save-proof** — Aguardando Fase 3
- ⏳ **autospawn** — Aguardando Fase 3
- ⏳ **inventory-tools** — Aguardando Fase 3
