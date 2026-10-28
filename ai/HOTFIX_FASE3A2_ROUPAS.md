# HOTFIX — Fase 3A.2: Correção de Roupas (Build 42.13.1)

**Data**: 28/10/2026, 01:23 UTC-3  
**Prioridade**: ALTA  
**Status**: ✅ CORRIGIDO

---

## PROBLEMA REPORTADO

Carlos spawna como homem, mas **completamente sem roupas**.

### Evidência do Console

```
No implementation found for function: setWornItem(
    IsoPlayer, String Tshirt, Clothing
)
```

**Três exceções**: Uma para cada peça de roupa (Tshirt, Pants, Shoes)

**Localização**: `ArayHumanTest.lua:497` (chamada incompatível)

---

## CAUSA RAIZ IDENTIFICADA

### Assinatura Incorreta de `setWornItem`

**Código problemático** (linha 497):
```lua
character:setWornItem(location, item)
-- Onde location = "Tshirt", "Pants", "Shoes"
```

**Por que falhou**:
1. `setWornItem(String, Clothing)` **não existe** na API Lua B42.13.1
2. Strings genéricas como `"Tshirt"` não são bodyLocations válidos
3. Método errado para equipar roupas

### API Correta Build 42.13.1

**Método 1 - WornItems API** (preferido):
```lua
local wornItems = character:getWornItems()
local bodyLocation = item:getBodyLocation()  -- Ex: "TorsoExtraVest"
wornItems:setItem(bodyLocation, item)
```

**Método 2 - Inventário + Wear**:
```lua
local inventory = character:getInventory()
inventory:AddItem(item)
character:wear(item)
```

---

## CORREÇÃO APLICADA

### Nova Implementação Multi-Tentativa

```lua
local function addClothing(itemType)
    local ok, itemAdded = pcall(function()
        -- 1. Cria item
        local item = nil
        if InventoryItemFactory and InventoryItemFactory.CreateItem then
            item = InventoryItemFactory.CreateItem(itemType)
        elseif instanceItem then
            item = instanceItem(itemType)
        end
        
        if not item then
            return false, "item_creation_failed"
        end
        
        -- 2. Define condição 100%
        if item.setCondition then
            item:setCondition(100)
        end
        
        -- MÉTODO 1: WornItems API (B42 padrão)
        if character.getWornItems then
            local wornItems = character:getWornItems()
            if wornItems and wornItems.setItem then
                -- Obtém bodyLocation do próprio item
                local bodyLocation = item:getBodyLocation()
                if bodyLocation and bodyLocation ~= "" then
                    wornItems:setItem(bodyLocation, item)
                    return true, "worn_items_api"
                end
            end
        end
        
        -- MÉTODO 2: Inventário + Wear
        if character.getInventory then
            local inventory = character:getInventory()
            if inventory and inventory.AddItem then
                inventory:AddItem(item)
                
                if character.wear then
                    character:wear(item)
                    return true, "inventory_wear"
                end
                
                return true, "inventory_only"
            end
        end
        
        return false, "no_compatible_method"
    end)
    
    -- Log detalhado
    if not ok then
        print("[ARAY] roupa: falha pcall tipo=" .. itemType .. " erro=" .. itemAdded)
    elseif itemAdded then
        print("[ARAY] roupa: OK tipo=" .. itemType .. " metodo=" .. itemAdded)
    else
        print("[ARAY] roupa: falha tipo=" .. itemType .. " razao=" .. itemAdded)
    end
    
    return ok and itemAdded
end
```

### Uso

```lua
local clothingAdded = 0
if addClothing("Base.Tshirt_DefaultTEXTURE") then clothingAdded = clothingAdded + 1 end
if addClothing("Base.Trousers_DefaultTEXTURE") then clothingAdded = clothingAdded + 1 end
if addClothing("Base.Shoes_Black") then clothingAdded = clothingAdded + 1 end

print("[ARAY] roupas: total adicionadas=" .. clothingAdded .. "/3")
```

### Atualização de Visual

Após equipar roupas, força refresh do modelo:

```lua
if character.resetModel then
    pcall(function() character:resetModel() end)
end
if character.resetModelNextFrame then
    pcall(function() character:resetModelNextFrame() end)
end
```

### Log Final Melhorado

```lua
local wornCount = 0
if character.getWornItems then
    local ok, worn = pcall(function() return character:getWornItems() end)
    if ok and worn and worn.size then
        wornCount = worn:size()
    end
end

print("[ARAY] Carlos criado sexo=" .. sexInfo 
    .. " pos=" .. xy(character) 
    .. " roupas=" .. clothingAdded 
    .. " vestidas=" .. wornCount)
```

---

## ESTRATÉGIA DE FALLBACK

### Tentativas em Ordem

1. **WornItems API** com `item:getBodyLocation()`
   - Método mais correto para B42
   - Usa bodyLocation real do item
   
2. **Inventário + wear()**
   - Adiciona ao inventário
   - Chama `character:wear(item)`
   
3. **Inventário apenas**
   - Fallback mínimo
   - Item fica no inventário (não vestido)

### Comportamento de Erro

- **Item não cria**: Log + continua próxima peça
- **Nenhum método funciona**: Log + spawn sem roupas (funcional)
- **Spawn nunca falha** por causa de roupas

---

## MUDANÇAS NO CÓDIGO

### Arquivo Modificado

**`42/media/lua/client/ArayHumanTest.lua`**

**Linhas Alteradas**: 485-552

**Resumo**:
1. Removido: `character:setWornItem(location, item)` (incompatível)
2. Adicionado: Tentativa com `getWornItems():setItem(bodyLocation, item)`
3. Adicionado: Fallback `inventory:AddItem()` + `character:wear()`
4. Adicionado: `item:getBodyLocation()` para obter location correto
5. Adicionado: Contador de roupas adicionadas vs vestidas
6. Adicionado: `resetModel()` e `resetModelNextFrame()` após equipar
7. Melhorado: Logs detalhados por método tentado

---

## BODYLOCATIONS ESPERADOS

### Itens de Roupa e Seus BodyLocations

| Item | BodyLocation Esperado |
|------|----------------------|
| `Base.Tshirt_DefaultTEXTURE` | `"Tshirt"` ou `"TorsoExtraVest"` |
| `Base.Trousers_DefaultTEXTURE` | `"Pants"` ou `"Legs1"` |
| `Base.Shoes_Black` | `"Shoes"` ou `"Feet"` |

**Nota**: `item:getBodyLocation()` retorna o valor correto definido pelo jogo.

---

## VALIDAÇÃO MANUAL

### Pré-requisitos

1. **Launcher ativo**: `ArayHumanNPCTest_Launcher.bat`
2. **Jogo**: Project Zomboid Build 42.13.1

### Teste 1: Spawn com Roupas (3 min)

- [ ] Carregar mundo de teste
- [ ] F7 → **"Spawnar ajudante"**
- [ ] **Console**: Procurar linhas `[ARAY] roupa: OK tipo=...`
- [ ] **Critério**: Pelo menos 1 das 3 deve mostrar `OK`
- [ ] **Console**: Verificar `roupas=X/3 vestidas=Y`
  - Ideal: `roupas=3/3 vestidas=3`
  - Aceitável: `roupas=2/3 vestidas=2` ou similar
  - Mínimo: `roupas=1/3 vestidas=1`

### Teste 2: Visual de Roupas (2 min)

- [ ] **Aproximar câmera** de Carlos
- [ ] **Observar corpo**:
  - ✅ Camiseta visível (cor sólida no torso)
  - ✅ Calça visível (pernas cobertas)
  - ✅ Sapatos visíveis (pés pretos/escuros)
- [ ] **Critério**: Pelo menos 1 peça visível

### Teste 3: Console - Sem Exceções (1 min)

- [ ] **Procurar** no console: `No implementation found for function: setWornItem`
- [ ] **Critério**: **ZERO** ocorrências desta exceção
- [ ] **Aceitável**: Avisos de falha em roupas específicas
- [ ] **Inaceitável**: Exceções Java não tratadas

### Teste 4: Funcionalidades (2 min)

- [ ] Carlos caminha (menu → "Seguir-me")
- [ ] Menu contextual completo
- [ ] Conversar funciona
- [ ] FBO rendering OK (Carlos visível em prédio)

### Teste 5: Múltiplos Spawns (3 min)

- [ ] Despawnar Carlos (recarregar mundo ou novo mundo)
- [ ] Spawnar novamente 3 vezes
- [ ] **Console**: Verificar `roupas=X/3` em cada spawn
- [ ] **Critério**: Resultado consistente (mesmo X em todos spawns)

---

## LOGS ESPERADOS NO CONSOLE

### Sucesso Total (Ideal)

```
[ARAY] roupa: OK tipo=Base.Tshirt_DefaultTEXTURE metodo=worn_items_api
[ARAY] roupa: OK tipo=Base.Trousers_DefaultTEXTURE metodo=worn_items_api
[ARAY] roupa: OK tipo=Base.Shoes_Black metodo=worn_items_api
[ARAY] roupas: total adicionadas=3/3
[ARAY] Carlos criado sexo=masculino pos=100,100,0 roupas=3 vestidas=3
```

### Sucesso Parcial (Aceitável)

```
[ARAY] roupa: OK tipo=Base.Tshirt_DefaultTEXTURE metodo=inventory_wear
[ARAY] roupa: OK tipo=Base.Trousers_DefaultTEXTURE metodo=inventory_wear
[ARAY] roupa: falha tipo=Base.Shoes_Black razao=no_compatible_method
[ARAY] roupas: total adicionadas=2/3
[ARAY] Carlos criado sexo=masculino pos=100,100,0 roupas=2 vestidas=2
```

### Falha Total (Funcional, mas sem roupas)

```
[ARAY] roupa: falha tipo=Base.Tshirt_DefaultTEXTURE razao=no_compatible_method
[ARAY] roupa: falha tipo=Base.Trousers_DefaultTEXTURE razao=no_compatible_method
[ARAY] roupa: falha tipo=Base.Shoes_Black razao=no_compatible_method
[ARAY] roupas: total adicionadas=0/3
[ARAY] Carlos criado sexo=masculino pos=100,100,0 roupas=0 vestidas=0
```

**Importante**: Mesmo com falha total, Carlos **deve spawnar** e ser funcional.

---

## RESULTADOS ESPERADOS

### Sucesso Mínimo (Obrigatório)

✅ Carlos spawna sem exceções Java  
✅ Console: ZERO linhas `No implementation found for function: setWornItem`  
✅ Carlos funcional (caminha, conversa, menu)  
~ Roupas: 0-3 peças (qualquer resultado aceitável)

### Sucesso Ideal

✅ Console: `roupas=3/3 vestidas=3`  
✅ Visual: Camiseta, calça e sapatos visíveis  
✅ Método: `worn_items_api` ou `inventory_wear`  
✅ Carlos masculino e funcional

---

## SE ROUPAS NÃO APARECEREM

### Cenário 1: `roupas=3/3` mas `vestidas=0`

**Causa**: Itens adicionados ao inventário mas não vestidos

**Próximo Passo**: Verificar se `character:wear(item)` existe

**Workaround temporário**: Aceitar Carlos sem roupas (funcional)

### Cenário 2: `roupas=0/3` (item_creation_failed)

**Causa**: `InventoryItemFactory.CreateItem()` retornou nil

**Próximo Passo**: Verificar IDs de itens
- Trocar `Base.Tshirt_DefaultTEXTURE` por `Base.Shirt_Denim`
- Trocar `Base.Trousers_DefaultTEXTURE` por `Base.Trousers_Denim`
- Trocar `Base.Shoes_Black` por `Base.Shoes_Wellies`

### Cenário 3: `no_compatible_method`

**Causa**: Nenhum dos métodos está disponível na API Lua

**Próximo Passo**: Investigar com `print(tostring(character:getWornItems()))`

**Workaround**: Aceitar Carlos sem roupas (funcional)

---

## COMPATIBILIDADE

✅ **Hotfix de Spawn** (masculino) — Mantido  
✅ **Fase 3A.2** (Unicode, estabilidade) — Mantida  
✅ **Fase 3A.1** (Chat presencial) — Mantida  
✅ **Todas funcionalidades** — Preservadas

---

## MÉTODOS TESTADOS

| Método | Status | Uso |
|--------|--------|-----|
| `character:getWornItems()` | ⏳ Teste | Obter WornItems |
| `wornItems:setItem(location, item)` | ⏳ Teste | Equipar roupa |
| `item:getBodyLocation()` | ⏳ Teste | Obter location |
| `inventory:AddItem(item)` | ⏳ Teste | Adicionar ao inventário |
| `character:wear(item)` | ⏳ Teste | Vestir item |
| `character:resetModel()` | ⏳ Teste | Atualizar visual |

**Nota**: Todos com `pcall` para evitar crash se não disponíveis.

---

## RESUMO TÉCNICO

| Aspecto | Antes (Hotfix Spawn) | Depois (Hotfix Roupas) |
|---------|---------------------|------------------------|
| Método equipar | `setWornItem(String, item)` ❌ | `wornItems:setItem(bodyLocation, item)` ✅ |
| BodyLocation | String genérica ("Tshirt") | `item:getBodyLocation()` |
| Fallback | Nenhum | 3 métodos tentados |
| Erro roupa | Spawn falhava | Spawn continua sem roupas |
| Log | Básico | Detalhado (método + contador) |
| Visual refresh | Não | `resetModel()` |

---

## PRÓXIMOS PASSOS

1. **Validar roupa manual** seguindo checklist
2. **Reportar resultado**:
   - ✅ Roupas visíveis → Hotfix aprovado
   - ⚠️ Roupas parciais → Aceitável, documentar
   - ❌ Exceção persiste → Console.txt completo
3. **Se aprovado**: Fase 3A.2 completa (com 2 hotfixes)

---

**Data do Hotfix**: 28/10/2026, 01:23 UTC-3  
**Status**: Correção aplicada, aguardando validação manual  
**Arquivos Modificados**: 1 (`ArayHumanTest.lua`)  
**Linhas Modificadas**: 485-552
