# Correção Fase 1: Diagnóstico de Leitura

## Problema identificado

O Python estava criando os arquivos JSON corretamente em `to_lua/`, mas o Lua não os estava lendo. 

## Causa provável

A função `fileExists()` no Lua pode não estar disponível ou não funcionar corretamente para caminhos relativos no cache. A verificação `if not fileExists or not fileExists(rel)` estava impedindo a leitura mesmo quando os arquivos existiam.

## Correções aplicadas

### 1. Remoção da dependência de `fileExists`

**Antes:**
```lua
if not getFileReader or not fileExists or not fileExists(rel) then return nil end
```

**Depois:**
```lua
if not getFileReader then return nil, "no_reader" end
-- Tenta ler diretamente, captura erro via pcall
```

### 2. Logs diagnósticos aprimorados

- Retorno de código de erro em `readFile`
- Log do caminho e erro quando a leitura falha
- Log detalhado em `acceptPong` para cada etapa de validação
- Verificação se o JSON está vazio

### 3. Limpeza para novo teste

Arquivos antigos removidos para garantir teste limpo.

## Teste de validação

### Passo 1: Iniciar o Python

```powershell
cd C:\Users\llongaray\Zomboid\mods\ArayHumanNPCTest
python ai\bridge.py
```

### Passo 2: Recarregar Lua no jogo

Menu Debug → Reload Lua Files

### Passo 3: Verificar console do jogo

**Sucesso esperado:**
```
[ARAY] ponte carregada
[ARAY] ponte ping id=<timestamp>-1 world_id=Sandbox/<world>
[ARAY] ponte pong recebido id=<timestamp>-1
```

**Se ainda falhar, novos logs vão mostrar:**
- `ponte leitura falhou path=... err=...` (se não conseguir ler)
- `ponte arquivo vazio id=...` (se ler mas estiver vazio)
- `ponte resposta sem id` (se JSON não tiver id)
- `ponte recusada kind=...` (se kind não for "pong")
- `ponte recusada ok=...` (se ok não for true)

### Passo 4: Verificar console do Python

Deve mostrar o mesmo ID:
```
[ARAY] ponte ping id=<timestamp>-1 world_id=Sandbox/<world>
[ARAY] ponte pong id=<timestamp>-1
```

## Arquivos modificados

- `42/media/lua/client/ArayHumanBridge.lua` (2 alterações)

## Se ainda não funcionar

Os novos logs vão indicar exatamente onde a validação está falhando.
