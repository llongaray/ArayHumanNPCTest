# Causa Raiz da Fase 1

## Problema

O Lua não recebia os pongs do Python, resultando em timeout após 30 segundos.

## Investigação

### Evidências dos logs

**Python (funcionando):**
```
[ARAY] ponte ping id=1793155177804-1
[ARAY] ponte pong id=1793155177804-1
```

**Lua (falhando):**
```
[ARAY] ponte leitura falhou path=... err=java.lang.RuntimeException  # tentativas 1 e 2
[ARAY] ponte timeout id=1793155177804-1
[ARAY] ponte timeout id=1793155187846-2
[ARAY] ponte recusada ok=nil                                         # tentativa 3
[ARAY] ponte sem servico
```

### Arquivos no disco

Todos os arquivos JSON estavam corretos em `to_lua/`:
```json
{"id":"1793155177804-1","kind":"pong","ok":true,"service":"aray-bridge"}
```

## Causa Raiz Comprovada

### Bug no pattern Lua

```lua
local function jsonBool(json, key)
    return json:match('"' .. key .. '"%s*:%s*(true|false)')  # ERRADO
end
```

**Em Lua, `|` não é um operador OR em patterns.**

O pattern `(true|false)` procura literalmente a string `"true|false"`, não "true" OU "false".

### Por que falhou

1. JSON contém: `"ok":true`
2. Pattern procura: `"ok":` seguido de `"true|false"` literal
3. Match falha, retorna `nil`
4. Validação rejeita: `if ok ~= "true"` → `nil ~= "true"` → rejeita

### RuntimeException

`getFileReader` lança exceção quando o arquivo não existe. O polling acontece a cada 1 segundo, mas o Python pode demorar alguns milissegundos para publicar. Isso é comportamento normal e não precisa de log de erro.

## Correção Aplicada

### 1. Pattern corrigido

```lua
local function jsonBool(json, key)
    local val = json:match('"' .. key .. '"%s*:%s*(%a+)')
    if val == "true" or val == "false" then return val end
    return nil
end
```

Captura qualquer palavra alfanumérica após a chave e valida explicitamente se é "true" ou "false".

### 2. Log de leitura removido

Polling de arquivo inexistente é normal, não é erro. Log removido para não poluir o console.

## Arquivos Modificados

- `42/media/lua/client/ArayHumanBridge.lua` (2 funções)

## Teste de Validação

### 1. Iniciar Python

```powershell
cd C:\Users\llongaray\Zomboid\mods\ArayHumanNPCTest
python ai\bridge.py
```

### 2. Recarregar Lua

Menu Debug → Reload Lua Files (ou reiniciar o jogo)

### 3. Resultado esperado

**Console do jogo:**
```
[ARAY] ponte carregada
[ARAY] ponte ping id=<timestamp>-1 world_id=Sandbox/<world>
[ARAY] ponte pong recebido id=<timestamp>-1
```

**Console do Python:**
```
[ARAY] ponte ping id=<timestamp>-1 world_id=Sandbox/<world>
[ARAY] ponte pong id=<timestamp>-1
```

### 4. Teste de reconexão

1. Parar Python (Ctrl+C)
2. Recarregar Lua → deve exibir `[ARAY] ponte sem servico` após 3 tentativas
3. Reiniciar Python
4. Recarregar Lua → deve receber pong na primeira tentativa

## Conclusão

O bug estava no código Lua desde o início. O pattern regex usava sintaxe incompatível com Lua patterns. A correção é mínima e fundamentada: substituir o pattern por captura + validação explícita.
