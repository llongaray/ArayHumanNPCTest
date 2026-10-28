# Análise: Persistência de NPCs entre sessões

## Estado atual

### O que já existe

O código atual em `ArayHumanTest.lua` implementa **persistência parcial**:

```lua
local function findExisting(cell)
    local list = cell:getObjectList()
    if not list then return nil end
    local slot = getSpecificPlayer(0)
    for i = 0, list:size() - 1 do
        local obj = list:get(i)
        if obj and obj ~= originalPlayer and obj ~= slot and obj.getModData then
            local md = obj:getModData()
            if md and md.ARAY_IsNPC then return obj end
        end
    end
    return nil
end
```

**Funciona quando:**
- O NPC foi spawnado na sessão atual
- A célula permanece carregada
- O jogador não saiu do mundo

**Não funciona quando:**
- O jogador fecha o jogo e reabre
- O jogador sai do mundo e entra em outro
- A célula é descarregada e recarregada

## Por que NPCs não persistem nativamente

### Arquitetura do Project Zomboid

O Project Zomboid Build 42.13.1 **não salva NPCs customizados** automaticamente porque:

1. **`IsoPlayer.setNPC(true)` não é um "verdadeiro NPC":**
   - É uma flag que desabilita controles do jogador
   - O objeto ainda é tecnicamente um `IsoPlayer`
   - O sistema de save só salva o jogador local (slot 0)

2. **Objetos temporários:**
   - NPCs criados via `addPlayer()` são considerados temporários
   - Não são incluídos no ciclo de serialização de saves

3. **ModData de personagens não persiste entre sessões:**
   - `character:getModData()` só existe enquanto o objeto existe na memória
   - Quando o jogador sai do mundo, o objeto é destruído
   - ModData vai junto

## Como implementar persistência verdadeira

### Opção 1: Salvar no ModData do mapa (RECOMENDADO)

```lua
-- Ao spawnar ou modificar NPC:
local mapModData = getWorld():getModData()
mapModData.ARAY_NPCs = mapModData.ARAY_NPCs or {}
mapModData.ARAY_NPCs[npcId] = {
    x = npc:getX(),
    y = npc:getY(),
    z = npc:getZ(),
    username = npc:getUsername(),
    inventory = serializeInventory(npc:getInventory()),
    health = npc:getBodyDamage():getHealth(),
    -- outros dados relevantes
}

-- Ao carregar o mundo (OnGameStart):
local mapModData = getWorld():getModData()
if mapModData.ARAY_NPCs then
    for npcId, data in pairs(mapModData.ARAY_NPCs) do
        -- Recriar NPC na posição salva
        -- Restaurar inventário
        -- Restaurar saúde
    end
end
```

**Vantagens:**
- ModData do mundo persiste entre sessões
- Suporta múltiplos NPCs
- Suporta múltiplos mundos/mapas

**Desvantagens:**
- Complexo de implementar corretamente
- Precisa serializar/deserializar inventário manualmente
- Precisa lidar com casos de borda (NPC morto, célula não carregada, etc)

### Opção 2: Usar eventos de save/load

```lua
Events.OnSave.Add(function()
    if not npc or npc:isDead() then return end
    
    local data = {
        x = npc:getX(),
        y = npc:getY(),
        z = npc:getZ(),
        -- ...
    }
    
    -- Salvar em ModData global ou arquivo externo
end)

Events.OnLoad.Add(function()
    -- Recuperar dados e recriar NPC
end)
```

**Problema:**
- `OnSave` / `OnLoad` podem não disparar consistentemente para mods
- Timing complicado (célula pode não estar carregada ainda)

### Opção 3: Serialização via Lua file I/O

```lua
-- Usar getFileWriter/getFileReader para salvar JSON
-- Similar ao sistema de world_models.json

local function saveNPC()
    local data = { x = npc:getX(), y = npc:getY(), ... }
    local writer = getFileWriter("ArayHumanNPCTest/npc_save.json", true, false)
    writer:write(json.stringify(data))
    writer:close()
end

-- Carregar ao entrar no mundo
```

**Vantagens:**
- Controle total sobre quando salvar
- Fácil de debugar (arquivo legível)

**Desvantagens:**
- Precisa gerenciar timing manualmente
- Pode conflitar com múltiplos mundos (precisa separar por world_id)

## Desafios técnicos

### 1. Inventário

`IsoPlayer:getInventory()` retorna objetos Java complexos. Serializar requer:
- Iterar cada item
- Salvar tipo, condição, quantidade, mods
- Recriar itens na deserialização via `InventoryItemFactory.CreateItem()`

### 2. Estado de saúde

`BodyDamage` é complexo:
- Saúde geral
- Feridas individuais por parte do corpo
- Infecção, temperatura, fome, sede

### 3. Timing de restauração

- NPC deve ser recriado **após** a célula estar carregada
- Mas **antes** de renderizar o primeiro frame
- Evento adequado: `OnGameStart` ou primeiro `OnTick` após spawn

### 4. Múltiplos NPCs

Atualmente o código suporta apenas 1 NPC (`local npc`). Para múltiplos:
- Usar tabela `local npcs = {}`
- Identificador único por NPC
- Gerenciar cada um separadamente

## Recomendação para Fase 3

**NÃO implementar persistência completa na Fase 2.**

Motivos:
1. Complexo e propenso a bugs
2. Requer testes extensivos
3. Pode causar corrupção de saves se mal implementado
4. Melhor esperar até ter outras funcionalidades estáveis

**Para Fase 3:**
1. Implementar sistema de save/load completo
2. Testar em mundo descartável primeiro
3. Adicionar validação de integridade
4. Documentar limitações conhecidas

## Alternativa temporária

**Para a Fase 2, documentar comportamento atual:**

> **Nota de persistência:**
> Atualmente, o ajudante NPC não é salvo entre sessões.
> Ao fechar o jogo ou sair do mundo, o NPC desaparece.
> Ao reabrir, pressione F7 → "Spawnar ajudante" novamente.
> 
> A persistência completa será implementada na Fase 3.

## Código mínimo para testar persistência (Fase 3)

```lua
-- Salvar ao sair do mundo
Events.OnExitWorld.Add(function()
    if not npc or npc:isDead() then return end
    
    local worldId = getWorld():getWorld() or "unknown"
    local modData = getWorld():getModData()
    modData.ARAY_NPC_Save = {
        worldId = worldId,
        x = npc:getX(),
        y = npc:getY(),
        z = npc:getZ(),
        username = npc:getUsername(),
        health = npc:getBodyDamage():getHealth(),
    }
    
    print("[ARAY] NPC salvo para " .. worldId)
end)

-- Restaurar ao entrar no mundo
Events.OnGameStart.Add(function()
    local modData = getWorld():getModData()
    local saved = modData.ARAY_NPC_Save
    
    if not saved then return end
    
    local worldId = getWorld():getWorld() or "unknown"
    if saved.worldId ~= worldId then return end
    
    -- Aguardar célula carregar
    Events.OnTick.Add(function()
        local cell = getCell()
        if not cell then return end
        
        -- Remover este handler após executar uma vez
        Events.OnTick.Remove(???)
        
        -- Recriar NPC
        local square = cell:getGridSquare(saved.x, saved.y, saved.z)
        if square then
            -- spawnNpc logic here
            print("[ARAY] NPC restaurado")
        end
    end)
end)
```

## Status

- ❌ **Persistência completa não implementada**
- ✅ **Recuperação de NPC na mesma sessão funciona** (via `findExisting`)
- ⏳ **Persistência entre sessões planejada para Fase 3**

## TODO para Fase 3

1. Criar `ArayHumanPersistence.lua`
2. Implementar serialização de inventário
3. Implementar serialização de saúde
4. Testar em mundo descartável
5. Adicionar validação de integridade
6. Documentar limitações
7. Atualizar TODO `npc-save-proof`
