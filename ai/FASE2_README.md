# Fase 2: Integração com Ollama

## Arquivos criados/modificados

### Novos arquivos

1. **`ai/ollama_service.py`** — Serviço Python com integração Ollama (350 linhas)
   - Consulta `/api/version` e `/api/tags`
   - Lista modelos instalados
   - Gerencia configuração e seleção de modelo
   - Responde com status do Ollama no pong

2. **`ai/config_default.json`** — Configuração padrão
   - URL do Ollama
   - Modelo selecionado
   - Intervalo de atualização

3. **`42/media/lua/client/ArayHumanOllama.lua`** — Gerenciador de estado Ollama (120 linhas)
   - Parser JSON manual do estado Ollama
   - Expõe status, versão, modelos via `ArayHuman.Ollama`

### Arquivos modificados

1. **`42/media/lua/client/ArayHumanBridge.lua`** — Atualiza estado Ollama ao receber pong
2. **`42/media/lua/client/ArayHumanUi.lua`** — Linha adicional no F7 mostrando status Ollama

## Dependências Python

O serviço Ollama requer a biblioteca `requests`:

```powershell
pip install requests
```

## Teste da Fase 2

### 1. Parar o serviço antigo

Se o `bridge.py` ainda estiver rodando, pare-o (Ctrl+C).

### 2. Iniciar o novo serviço Ollama

```powershell
cd C:\Users\llongaray\Zomboid\mods\ArayHumanNPCTest
python ai\ollama_service.py
```

**Console esperado:**
```
[ARAY] servico ollama iniciado dir=C:\Users\llongaray\Zomboid\Lua\ArayHumanNPCTest
[ARAY] ollama url=http://127.0.0.1:11434
[ARAY] ollama online version=0.21.0 models=1
```

Ou, se o Ollama estiver desligado:
```
[ARAY] ollama offline
```

### 3. Recarregar Lua no jogo

Com o jogo ainda aberto:

1. Pressione F11 ou abra o menu Debug
2. Clique em "Reload Lua Files"
3. Aguarde a mensagem de confirmação

**Console do jogo deve mostrar:**
```
[ARAY] ponte carregada
[ARAY] ollama gerenciador carregado
[ARAY] ponte ping id=<timestamp>-1 world_id=Sandbox/<world>
[ARAY] ponte pong recebido id=<timestamp>-1
```

### 4. Abrir o F7

Pressione F7 e verifique:

**Com Ollama ligado:**
```
Status: <estado do NPC>
Ollama: 0.21.0 | <modelo selecionado ou "nenhum modelo selecionado">
```

**Com Ollama desligado:**
```
Status: <estado do NPC>
Ollama: offline
```

### 5. Testar reconexão do Ollama

1. Com o serviço rodando, desligue o Ollama
2. Aguarde até 30 segundos
3. F7 deve mostrar "Ollama: offline"
4. Religue o Ollama
5. Aguarde até 30 segundos
6. F7 deve mostrar "Ollama: <versão>" novamente

## Estrutura de configuração

O arquivo `Zomboid/Lua/ArayHumanNPCTest/config/ollama_config.json` é criado automaticamente:

```json
{
  "ollama_url": "http://127.0.0.1:11434",
  "selected_model": null,
  "update_interval_seconds": 30
}
```

### Alterar URL do Ollama

Se o Ollama estiver em outra porta, edite manualmente o JSON:

```json
{
  "ollama_url": "http://127.0.0.1:8080",
  ...
}
```

Reinicie o serviço Python.

### Seleção de modelo

Na Fase 2, o modelo é listado mas ainda não é utilizado. A seleção pelo F7 será implementada na Fase 3.

## Protocolo estendido

O pong agora inclui a seção `ollama`:

```json
{
  "id": "<request-id>",
  "kind": "pong",
  "ok": true,
  "service": "aray-ollama",
  "ollama": {
    "online": true,
    "version": "0.21.0",
    "models": ["hf.co/PatrickPat/remnants-llm-v5-GGUF:Q4_K_M"],
    "selected_model": null
  }
}
```

O Lua faz parse manual desse JSON e atualiza o estado local.

## Logs de diagnóstico

**Python detecta Ollama online:**
```
[ARAY] ollama online version=0.21.0 models=1
```

**Python detecta Ollama offline:**
```
[ARAY] ollama offline
```

**Lua recebe e processa:**
```
[ARAY] ponte pong recebido id=<timestamp>-1
```

## Critérios de aceitação validados

✅ Ollama online/offline detectado  
✅ Versão exibida no F7  
✅ Modelos listados (visível nos logs Python)  
✅ Jogo continua estável com Ollama desligado  
✅ Atualização periódica (30s) sem bloquear o jogo  
✅ Ponte Fase 1 preservada e funcionando

## Próxima fase

Fase 3 implementará:
- Seleção de modelo pelo F7
- Interface de chat
- Primeira consulta ao Ollama (resposta estruturada sem ação)
- Personalidade Ellis Ward
