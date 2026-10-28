-- Aray Human NPC Test - B42.13.1
-- O ajudante nasce só pelo menu F7. O ModelManager recebe uma tentativa por NPC.
require "ArayHumanWalking"
ArayHuman = ArayHuman or {}

local npc = nil
local roster = {}
local originalPlayer = nil
local npcAge = nil
local modelRegistrationAttempted = false
local statusText = "Nenhum ajudante."
local renderDiag = { calls = 0, last = "ainda nao", fbo = "pendente", cutaway = "pendente" }
local cutawayBroken = false
local bornX = nil
local bornY = nil

local OFFSETS = {
    {1, 0}, {-1, 0}, {0, 1}, {0, -1},
    {1, 1}, {1, -1}, {-1, 1}, {-1, -1},
    {2, 0}, {0, 2}, {-2, 0}, {0, -2},
    {3, 0}, {0, 3},
}

local function restoreLocalPlayer()
    local me = ArayHuman.getLocalPlayer and ArayHuman.getLocalPlayer() or nil
    if not me then return end
    IsoPlayer.setInstance(me)
    if IsoCamera and IsoCamera.setCameraCharacter then
        if not IsoCamera.getCameraCharacter or IsoCamera.getCameraCharacter() ~= me then
            IsoCamera.setCameraCharacter(me)
        end
    end
end

local function squareBlocked(square, ignore)
    if not square or not square:TreatAsSolidFloor() or not square:isFree(false) then
        return true
    end
    local movers = square:getMovingObjects()
    if not movers then return false end
    for i = 0, movers:size() - 1 do
        local obj = movers:get(i)
        if obj and obj ~= ignore and instanceof(obj, "IsoGameCharacter") then
            return true
        end
    end
    return false
end

local function findSpawnSquare(cell, player, ignore)
    local px = math.floor(player:getX())
    local py = math.floor(player:getY())
    local pz = math.floor(player:getZ())
    for i = 1, #OFFSETS do
        local sq = cell:getGridSquare(px + OFFSETS[i][1], py + OFFSETS[i][2], pz)
        if not squareBlocked(sq, ignore) then
            return sq
        end
    end
    return nil
end

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

local function isOurNpc(character)
    if not character then return false end
    if character == npc then return true end
    for _, tracked in pairs(roster) do
        if tracked == character then return true end
    end
    if character.getModData then
        local ok, md = pcall(function() return character:getModData() end)
        if ok and md and md.ARAY_IsNPC then return true end
    end
    return false
end

local function trackNpc(character)
    if not character then return end
    local id = nil
    if character.getModData then
        local ok, md = pcall(function() return character:getModData() end)
        if ok and md then id = md.ARAY_Uuid end
    end
    if id and id ~= "" then roster[id] = character end
    npc = character
end

local function alivePlayer(character)
    if not character or isOurNpc(character) then return nil end
    if character.isDead and character:isDead() then return nil end
    return character
end

function ArayHuman.getLocalPlayer()
    local slot = getSpecificPlayer and alivePlayer(getSpecificPlayer(0)) or nil
    if slot then return slot end
    if getPlayer then return alivePlayer(getPlayer()) end
    return nil
end

local function syncLocalPlayer(player)
    player = alivePlayer(player) or ArayHuman.getLocalPlayer()
    if not player then return nil end
    if player == originalPlayer then return player end
    local previous = originalPlayer
    originalPlayer = player
    modelRegistrationAttempted = false
    for _, tracked in pairs(roster) do
        if tracked and not tracked:isDead() then
            if tracked.getModData then tracked:getModData().ARAY_ModelReady = nil end
            if tracked.setSceneCulled then tracked:setSceneCulled(false) end
        end
    end
    if previous then
        print("[ARAY] jogador local alterado")
        print("[ARAY] anterior=" .. tostring(previous))
        print("[ARAY] atual=" .. tostring(player))
        print("[ARAY] referencias atualizadas")
    end
    return player
end

local function recoverOne(player, character)
    if not character or character:isDead() or not player then return end
    local dx = character:getX() - player:getX()
    local dy = character:getY() - player:getY()
    if dx * dx + dy * dy > 80 * 80 then return end
    local alpha = character.getAlpha and character:getAlpha() or 1
    local target = character.getTargetAlpha and character:getTargetAlpha() or 1
    if alpha >= 0.05 or target >= 0.05 then return end
    if character.setAlpha then character:setAlpha(1) end
    if character.setTargetAlpha then character:setTargetAlpha(1) end
    if character.setSceneCulled then character:setSceneCulled(false) end
    print("[ARAY] npc visibilidade restaurada perto do jogador atual")
end

local function recoverNpcVisibility(player)
    if npc then recoverOne(player, npc) end
    for _, tracked in pairs(roster) do
        if tracked ~= npc then recoverOne(player, tracked) end
    end
end

local function xy(character)
    if not character then return "nil" end
    return math.floor(character:getX()) .. "," .. math.floor(character:getY()) .. "," .. math.floor(character:getZ())
end

local function rememberBorn(character)
    if not character then return end
    bornX = character:getX()
    bornY = character:getY()
end

local function planarDistance(x1, y1, x2, y2)
    local dx = x1 - x2
    local dy = y1 - y2
    return math.sqrt(dx * dx + dy * dy)
end

local function squareText(square)
    if not square then return "nil" end
    return square:getX() .. "," .. square:getY() .. "," .. square:getZ()
end

local function listContains(list, obj)
    if not list then return "nil" end
    return tostring(list:contains(obj))
end

local function drawText(character)
    if not character then return "nil" end
    local sprite = character:getSprite()
    local legs = character:getLegsSprite()
    local anim = character:getAnimationPlayer()
    return "doRender=" .. tostring(character:getDoRender())
        .. " alpha=" .. tostring(character:getAlpha())
        .. " target=" .. tostring(character:getTargetAlpha())
        .. " alphaZero=" .. tostring(character:isAlphaZero())
        .. " alphaTargetZero=" .. tostring(character:isAlphaAndTargetZero())
        .. " sprite=" .. tostring(sprite ~= nil)
        .. " legs=" .. tostring(legs ~= nil)
        .. " sameSprite=" .. tostring(sprite ~= nil and sprite == legs)
        .. " spriteName=" .. tostring(character:getSpriteName())
        .. " spriteInvisible=" .. tostring(character:isSpriteInvisible())
        .. " invisible=" .. tostring(character:isInvisible())
        .. " seated=" .. tostring(character:isSeatedInVehicle())
        .. " anim=" .. tostring(anim ~= nil)
end

local function squareSight(square)
    if not square then return "square=nil" end
    return "canSee=" .. tostring(square:isCanSee(0))
        .. " couldSee=" .. tostring(square:isCouldSee(0))
end

local function screenText(character)
    if not character then return "nil" end
    local square = character:getSquare()
    local current = character:getCurrentSquare()
    return "onScreen=" .. tostring(character:isOnScreen())
        .. " square=" .. tostring(square ~= nil)
        .. " sameSquare=" .. tostring(square ~= nil and square == current)
end

local fboCached = nil

local function fboCharactersActive()
    if fboCached ~= nil then return fboCached end
    local ok, value = pcall(function()
        return PerformanceSettings.fboRenderChunk
    end)
    if not ok or value == nil then
        renderDiag.fbo = "indisponivel"
        fboCached = true
        return true
    end
    fboCached = value == true
    renderDiag.fbo = tostring(fboCached)
    return fboCached
end

local function cutawayAllows(playerIndex, square)
    if cutawayBroken or FBORenderCutaways == nil or not FBORenderCutaways.getInstance then
        renderDiag.cutaway = "indisponivel"
        return true
    end
    local ok, allowed = pcall(function()
        return FBORenderCutaways.getInstance():shouldRenderBuildingSquare(playerIndex, square)
    end)
    if not ok then
        cutawayBroken = true
        renderDiag.cutaway = "erro"
        print("[ARAY] limite: shouldRenderBuildingSquare indisponivel")
        return true
    end
    renderDiag.cutaway = tostring(allowed == true)
    return allowed == true
end

-- FBORenderCell.renderMovingObject retorna se getClass()==IsoPlayer.
-- renderPlayers só percorre IsoPlayer.players[]. O NPC fica fora dos dois.
local function renderOneNpc(playerIndex, character)
    if not character or character:isDead() then return end
    local cell = getCell()
    local list = cell and cell:getObjectList() or nil
    if not list or not list:contains(character) then
        renderDiag.last = "fora da objectList"
        return
    end
    local square = character:getCurrentSquare()
    if not square then
        renderDiag.last = "currentSquare nil"
        return
    end
    if not character:isOnScreen() then
        renderDiag.last = "isOnScreen false"
        return
    end
    local lightOk, light = pcall(function()
        return square:getLightInfo(playerIndex)
    end)
    if not lightOk then
        renderDiag.failed = true
        renderDiag.last = "lightInfo falhou"
        print("[ARAY] limite: getLightInfo falhou e o desenho manual foi desligado")
        return
    end
    if not light then
        renderDiag.last = "lightInfo nil"
        return
    end
    if not cutawayAllows(playerIndex, square) then
        renderDiag.last = "cutaway oculto"
        return
    end
    local ok = pcall(function()
        character:render(character:getX(), character:getY(), character:getZ(), light, true, false, nil)
    end)
    if not ok then
        renderDiag.failed = true
        renderDiag.last = "render falhou"
        print("[ARAY] limite: npc:render falhou e foi desligado")
        return
    end
    renderDiag.calls = renderDiag.calls + 1
    renderDiag.last = "render chamado"
    if renderDiag.calls == 1 then
        print("[ARAY] npcRender chamado playerIndex=" .. tostring(playerIndex))
    end
end

local function renderNpcInWorld(playerIndex)
    if renderDiag.failed then return end
    if not fboCharactersActive() then
        renderDiag.last = "render classico"
        return
    end
    local seen = {}
    if npc then
        seen[npc] = true
        renderOneNpc(playerIndex, npc)
    end
    if renderDiag.failed then return end
    for _, tracked in pairs(roster) do
        if tracked and not seen[tracked] then
            seen[tracked] = true
            renderOneNpc(playerIndex, tracked)
            if renderDiag.failed then return end
        end
    end
end

local function modelText(character)
    if not character then return "nil" end
    local visual = character:getHumanVisual()
    local hair = "nil"
    if visual then
        hair = tostring(visual:getHairModel())
    end
    local worn = character:getWornItems()
    local wornSize = "nil"
    if worn then
        wornSize = tostring(worn:size())
    end
    local model = character:getModelInstance()
    return "added=" .. tostring(character:isAddedToModelManager())
        .. " active=" .. tostring(character:hasActiveModel())
        .. " model=" .. tostring(model ~= nil)
        .. " culled=" .. tostring(character:isSceneCulled())
        .. " hair=" .. hair
        .. " worn=" .. wornSize
end

local function logSnapshot(mark)
    local cell = getCell()
    local currentPlayer = getPlayer()
    local slotPlayer = getSpecificPlayer(0)
    print("[ARAY] tick=" .. tostring(mark)
        .. " npc=" .. tostring(npc)
        .. " instanceofIsoPlayer=" .. tostring(npc ~= nil and instanceof(npc, "IsoPlayer")))
    print("[ARAY] tick=" .. tostring(mark)
        .. " original=" .. tostring(originalPlayer)
        .. " getPlayer=" .. tostring(currentPlayer)
        .. " specific0=" .. tostring(slotPlayer))
    print("[ARAY] tick=" .. tostring(mark)
        .. " getPlayer==original " .. tostring(currentPlayer == originalPlayer)
        .. " specific0==original " .. tostring(slotPlayer == originalPlayer)
        .. " getPlayer==npc " .. tostring(npc ~= nil and currentPlayer == npc)
        .. " specific0==npc " .. tostring(npc ~= nil and slotPlayer == npc))
    print("[ARAY] tick=" .. tostring(mark)
        .. " originalXY=" .. xy(originalPlayer)
        .. " npcXY=" .. xy(npc))

    if not npc then
        print("[ARAY] tick=" .. tostring(mark) .. " npc ausente")
        return
    end

    local square = npc:getCurrentSquare()
    local moving = "nil"
    if square then
        moving = listContains(square:getMovingObjects(), npc)
    end
    print("[ARAY] tick=" .. tostring(mark)
        .. " currentSquare=" .. squareText(square)
        .. " movingContains=" .. moving)

    if cell then
        print("[ARAY] tick=" .. tostring(mark)
            .. " objectList=" .. listContains(cell:getObjectList(), npc)
            .. " addList=" .. listContains(cell:getAddList(), npc)
            .. " removeList=" .. listContains(cell:getRemoveList(), npc))
    else
        print("[ARAY] tick=" .. tostring(mark) .. " cell=nil")
    end

    local damage = npc:getBodyDamage()
    print("[ARAY] tick=" .. tostring(mark)
        .. " bodyDamage=" .. tostring(damage ~= nil)
        .. " isNPC=" .. tostring(npc:isNPC())
        .. " isDead=" .. tostring(npc:isDead())
        .. " isLocalPlayer=" .. tostring(npc:isLocalPlayer()))
    print("[ARAY] tick=" .. tostring(mark) .. " playerModel " .. modelText(originalPlayer))
    print("[ARAY] tick=" .. tostring(mark) .. " npcModel " .. modelText(npc))
    print("[ARAY] tick=" .. tostring(mark) .. " playerDraw " .. drawText(originalPlayer))
    print("[ARAY] tick=" .. tostring(mark) .. " npcDraw " .. drawText(npc))
    print("[ARAY] tick=" .. tostring(mark) .. " playerSquare " .. squareSight(originalPlayer and originalPlayer:getCurrentSquare() or nil))
    print("[ARAY] tick=" .. tostring(mark) .. " npcSquare " .. squareSight(npc:getCurrentSquare()))
    print("[ARAY] tick=" .. tostring(mark) .. " playerScreen " .. screenText(originalPlayer))
    print("[ARAY] tick=" .. tostring(mark) .. " npcScreen " .. screenText(npc))
    print("[ARAY] tick=" .. tostring(mark)
        .. " npcRender calls=" .. tostring(renderDiag.calls)
        .. " last=" .. tostring(renderDiag.last)
        .. " fbo=" .. tostring(renderDiag.fbo)
        .. " cutaway=" .. tostring(renderDiag.cutaway))

    local drift = "nil"
    if bornX ~= nil and bornY ~= nil then
        drift = string.format("%.2f", planarDistance(npc:getX(), npc:getY(), bornX, bornY))
    end
    local camera = nil
    if IsoCamera and IsoCamera.getCameraCharacter then
        camera = IsoCamera.getCameraCharacter()
    end
    local actionName = "nil"
    if npc.getCurrentActionContextStateName then
        actionName = tostring(npc:getCurrentActionContextStateName())
    end
    local queued = false
    if ISTimedActionQueue and ISTimedActionQueue.hasActionType then
        queued = ISTimedActionQueue.hasActionType(npc, "ISWalkToTimedAction") == true
    end
    print("[ARAY] tick=" .. tostring(mark)
        .. " controle drift=" .. drift
        .. " camera==original " .. tostring(camera == originalPlayer)
        .. " instance==original " .. tostring(getPlayer() == originalPlayer)
        .. " action=" .. actionName
        .. " walkQueued=" .. tostring(queued))
    if bornX ~= nil and not ArayHuman.walkActive() and tonumber(drift) and tonumber(drift) > 0.2 then
        print("[ARAY] tick=" .. tostring(mark) .. " deriva espontanea")
    end

    if getCore then
        local core = getCore()
        if core then
            local display = core:isDisplayPlayerModel()
            local animal = npc:isAnimal()
            local localCharacter = npc:isLocal()
            print("[ARAY] tick=" .. tostring(mark)
                .. " displayPlayerModel=" .. tostring(display)
                .. " isAnimal=" .. tostring(animal)
                .. " isLocal=" .. tostring(localCharacter)
                .. " renderEarlyReturn=" .. tostring((not display) and (not animal) and localCharacter))
        else
            print("[ARAY] tick=" .. tostring(mark) .. " limite: getCore retornou nil")
        end
    else
        print("[ARAY] tick=" .. tostring(mark) .. " limite: getCore ausente")
    end

    if mark == 0 then
        print("[ARAY] limite: Class.getName nao esta exposto ao Lua; classe registrada via instanceof e tostring")
    end
end

local function registerOne(character)
    local md = character.getModData and character:getModData() or nil
    if md and md.ARAY_ModelReady then return end
    if character:isAddedToModelManager() then
        if md then md.ARAY_ModelReady = true end
        modelRegistrationAttempted = true
        return
    end
    if not character:getCurrentSquare() then return end
    local legs = character:getLegsSprite()
    if not legs then
        if md then md.ARAY_ModelReady = true end
        modelRegistrationAttempted = true
        print("[ARAY] modelRegistration attempted=false limite: legsSprite nil")
        return
    end
    if md then md.ARAY_ModelReady = true end
    modelRegistrationAttempted = true
    character:setSceneCulled(false)
    local model = character:getModelInstance()
    print("[ARAY] modelRegistration attempted=true")
    print("[ARAY] modelRegistration added=" .. tostring(character:isAddedToModelManager()))
    print("[ARAY] modelRegistration active=" .. tostring(character:hasActiveModel()))
    print("[ARAY] modelRegistration model=" .. tostring(model ~= nil))
end

local function tryRegisterModel()
    local localPlayer = ArayHuman.getLocalPlayer()
    if not localPlayer or not localPlayer:isAddedToModelManager() then return end
    local seen = {}
    if npc and not npc:isDead() then
        seen[npc] = true
        registerOne(npc)
    end
    for _, tracked in pairs(roster) do
        if tracked and not tracked:isDead() and not seen[tracked] then
            seen[tracked] = true
            registerOne(tracked)
        end
    end
end

local function keepOnSquare(character, square)
    if not square then return end
    character:setCurrent(square)
    local movers = square:getMovingObjects()
    if movers and not movers:contains(character) then
        movers:add(character)
    end
end

local function configureNpc(character, square)
    character:setNPC(true)
    local md = character:getModData()
    md.ARAY_IsNPC = true
    md.ARAY_Name = "Aray"
    keepOnSquare(character, square)
    restoreLocalPlayer()
end

local function placeOnSquare(character, square)
    local x = square:getX() + 0.5
    local y = square:getY() + 0.5
    local z = square:getZ()
    character:removeFromSquare()
    character:teleportTo(x, y, z)
    character:setX(x)
    character:setY(y)
    character:setZ(z)
    character:setLastX(x)
    character:setLastY(y)
    character:setNextX(x)
    character:setNextY(y)
    character:setScriptNextX(x)
    character:setScriptNextY(y)
    character:setCurrentSquareFromPosition()
    keepOnSquare(character, character:getCurrentSquare() or square)
    restoreLocalPlayer()
end

local function applyDirection(character, direction)
    if not direction or not character or not character.setDir or not IsoDirections then return end
    local value = IsoDirections[direction]
    if not value then return end
    pcall(function() character:setDir(value) end)
end

local function spawnNpc(player, cell, config)
    config = config or {}
    local square = config.square
    if not square then
        square = findSpawnSquare(cell, player, nil)
    end
    if not square then
        statusText = "Sem tile livre ao lado do jogador."
        print("[ARAY] sem tile livre ao lado do jogador")
        return false
    end

    local desc = config.appearance and SurvivorDesc.new() or SurvivorFactory.CreateSurvivor()
    if not desc then desc = SurvivorDesc.new() end
    
    local wantFemale = config.sex == "female"
    local attempts = 0
    local maxAttempts = 20
    while not config.appearance and desc and attempts < maxAttempts do
        local isFemale = false
        if desc.isFemale then
            local ok, result = pcall(function() return desc:isFemale() end)
            if ok then isFemale = result end
        end
        if isFemale == wantFemale then break end
        attempts = attempts + 1
        desc = SurvivorFactory.CreateSurvivor()
        if not desc then desc = SurvivorDesc.new() end
    end
    
    desc:setForename(config.firstName or "Carlos")
    desc:setSurname(config.lastName or "Aray")
    if config.appearance then
        local ok=ArayHuman.Appearance and ArayHuman.Appearance.prepare(desc,config.appearance)
        if not ok then return false end
    end
    
    print("[ARAY] descritor criado tentativas=" .. attempts .. " masculino=" .. tostring(not (desc.isFemale and desc:isFemale())))

    -- Explicit initial builds only. Restores never replay creation bonuses.
    local buildToken
    if config.characterBuild then
        require "ArayHumanCharacterBuild"
        if not ArayHuman.CharacterBuild or config.restoring then return false end
        local why
        buildToken,why=ArayHuman.CharacterBuild.prepareDescriptor(desc,config.uuid,
            ArayHuman.Capabilities.world(),config.characterBuild)
        if not buildToken then
            print("[ARAY-BUILD] rejected uuid="..tostring(config.uuid).." reason="..tostring(why))
            return false
        end
    end

    local character = IsoPlayer.new(cell, desc, square:getX(), square:getY(), square:getZ())
    if not character then
        statusText = "IsoPlayer.new retornou nil."
        print("[ARAY] ERROR: IsoPlayer.new retornou nil")
        return false
    end
    if not character:getBodyDamage() then
        character:removeFromWorld()
        character:removeFromSquare()
        statusText = "IsoPlayer sem BodyDamage."
        print("[ARAY] ERROR: IsoPlayer sem BodyDamage")
        return false
    end

    if config.appearance then
        local ok,why=ArayHuman.Appearance.applyNew(character,config.appearance)
        if not ok then
            character:removeFromWorld(); character:removeFromSquare(); restoreLocalPlayer()
            print("[ARAY-VISUAL] uuid="..tostring(config.uuid).." reason="..tostring(why))
            return false
        end
    end
    if buildToken then
        local applied,why=ArayHuman.CharacterBuild.applyCreated(character,buildToken)
        if not applied then
            character:removeFromWorld(); character:removeFromSquare()
            restoreLocalPlayer()
            print("[ARAY-BUILD] discarded uuid="..tostring(config.uuid).." reason="..tostring(why))
            return false
        end
    end
    npc = character
    npcAge = nil
    modelRegistrationAttempted = false
    
    -- Adiciona roupas masculinas básicas (Build 42.13.1 compatível)
    local function addClothing(itemType)
        local ok, itemAdded, clothingReason = pcall(function()
            -- Cria item
            local item = nil
            if InventoryItemFactory and InventoryItemFactory.CreateItem then
                item = InventoryItemFactory.CreateItem(itemType)
            elseif instanceItem then
                item = instanceItem(itemType)
            end
            
            if not item then
                return false, "item_creation_failed"
            end
            
            -- Define condição
            -- Native factories initialize valid condition; never force 100 over ConditionMax.
            local inv=character:getInventory()
            if not inv then return false,"inventory_unavailable" end
            inv:AddItem(item)
            
            -- Método 1: Tenta getWornItems() API (B42 padrão)
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
            
            -- Método 2: Tenta adicionar ao inventário e depois vestir
            if character.getInventory then
                local inventory = character:getInventory()
                if inventory and inventory.AddItem then
                    -- Already inserted before equipping; never add the same item twice.
                    
                    -- Tenta wear() se disponível
                    if character.wear then
                        character:wear(item)
                        return true, "inventory_wear"
                    end
                    
                    return true, "inventory_only"
                end
            end
            
            return false, "no_compatible_method"
        end)
        
        if not ok then
            print("[ARAY] roupa: falha pcall tipo=" .. tostring(itemType) .. " erro=" .. tostring(itemAdded))
            return false
        elseif itemAdded then
            print("[ARAY] roupa: OK tipo=" .. tostring(itemType) .. " metodo=" .. tostring(itemAdded))
            return true
        else
            print("[ARAY] roupa: falha tipo=" .. tostring(itemType) .. " razao=" .. tostring(clothingReason))
            return false
        end
    end
    
    -- Adiciona roupas básicas masculinas
    local clothingAdded = 0
    if not config.appearance then
        if addClothing("Base.Tshirt_DefaultTEXTURE") then clothingAdded = clothingAdded + 1 end
        if addClothing("Base.Trousers_DefaultTEXTURE") then clothingAdded = clothingAdded + 1 end
        if addClothing("Base.Shoes_Black") then clothingAdded = clothingAdded + 1 end
    end
    
    print("[ARAY] roupas: total adicionadas=" .. clothingAdded .. "/3")
    
    configureNpc(character, square)
    if character.getModData then
        local md = character:getModData()
        md.ARAY_Uuid = config.uuid
        md.ARAY_Name = config.firstName or "Carlos"
    end
    trackNpc(character)
    if not config.appearance and config.uuid and ArayHuman.Appearance then
        ArayHuman.Appearance.saveInitial(character,config.uuid)
    end
    if config.exact and config.x and config.y and config.z then
        character:setX(config.x)
        character:setY(config.y)
        character:setZ(config.z)
        character:setCurrentSquareFromPosition()
        keepOnSquare(character, character:getCurrentSquare() or square)
    end
    applyDirection(character, config.direction)
    rememberBorn(character)
    
    -- Força atualização de visual após equipar roupas
    if character.resetModel then
        pcall(function() character:resetModel() end)
    end
    if character.resetModelNextFrame then
        pcall(function() character:resetModelNextFrame() end)
    end
    
    statusText = "Ajudante em " .. xy(character) .. "."
    
    -- Log detalhado para debug
    local sexInfo = "desconhecido"
    if character.isFemale then
        local ok, isFem = pcall(function() return character:isFemale() end)
        if ok then sexInfo = isFem and "feminino" or "masculino" end
    end
    
    local wornCount = 0
    if character.getWornItems then
        local ok, worn = pcall(function() return character:getWornItems() end)
        if ok and worn and worn.size then
            wornCount = worn:size()
        end
    end
    
    print("[ARAY] Carlos criado sexo=" .. sexInfo .. " pos=" .. xy(character) .. " roupas=" .. clothingAdded .. " vestidas=" .. wornCount)
    return true
end

function ArayHuman.getNpc()
    return npc
end

-- Read-only access for UUID-scoped observers; does not change the focused NPC.
function ArayHuman.getNpcByUuid(uuid)
    return roster[uuid]
end

function ArayHuman.getNpcName()
    if npc and npc.getModData then
        local ok, md = pcall(function() return npc:getModData() end)
        if ok and md and md.ARAY_Name and md.ARAY_Name ~= "" then return md.ARAY_Name end
    end
    return "Carlos"
end

function ArayHuman.rosterSnapshot()
    local list = {}
    local seen = {}
    local function add(character)
        if not character or seen[character] then return end
        seen[character] = true
        local id = nil
        if character.getModData then
            local ok, md = pcall(function() return character:getModData() end)
            if ok and md then id = md.ARAY_Uuid end
        end
        list[#list + 1] = {
            uuid = id,
            character = character,
            dead = character.isDead and character:isDead() or false,
        }
    end
    if npc then add(npc) end
    for _, tracked in pairs(roster) do add(tracked) end
    return list
end

function ArayHuman.getStatus()
    if npc and not npc:isDead() then
        return statusText
    end
    if npc and npc:isDead() then
        return "O ajudante morreu."
    end
    return statusText
end

function ArayHuman.spawnCarlos(config)
    config = config or {}
    if config.uuid and roster[config.uuid] and not roster[config.uuid]:isDead() then
        npc = roster[config.uuid]
        return true
    end
    local player = ArayHuman.getLocalPlayer()
    local cell = getCell()
    if not player or not cell then return false end
    player = syncLocalPlayer(player)
    if not player then return false end
    local existing = findExisting(cell)
    if existing then
        local existingId = existing.getModData and existing:getModData().ARAY_Uuid or nil
        if not config.uuid or not existingId or existingId == config.uuid then
            if config.uuid and existing.getModData then
                existing:getModData().ARAY_Uuid = config.uuid
            end
            if config.firstName and existing.getModData then
                existing:getModData().ARAY_Name = config.firstName
            end
            trackNpc(existing)
            npcAge = nil
            modelRegistrationAttempted = false
            rememberBorn(existing)
            statusText = "Ajudante já estava no mundo, em " .. xy(existing) .. "."
            return true
        end
    end
    local ok, created = pcall(spawnNpc, player, cell, config)
    return ok and created == true
end

function ArayHuman.findRestoreSquare(x, y, z)
    local cell = getCell()
    if not cell then return nil, "sem cell" end
    if type(x) ~= "number" or type(y) ~= "number" or type(z) ~= "number" then
        return nil, "coordenadas"
    end
    local sx = math.floor(x)
    local sy = math.floor(y)
    local sz = math.floor(z)
    local square = cell:getGridSquare(sx, sy, sz)
    if not square then return nil, "nao carregado" end
    if not squareBlocked(square, nil) then return square, "pronto" end
    local offsets = {
        {1, 0}, {-1, 0}, {0, 1}, {0, -1},
        {1, 1}, {1, -1}, {-1, 1}, {-1, -1},
    }
    for i = 1, #offsets do
        local near = cell:getGridSquare(sx + offsets[i][1], sy + offsets[i][2], sz)
        if near and not squareBlocked(near, nil) then
            return near, "adjacente"
        end
    end
    return nil, "bloqueado"
end

function ArayHuman.spawn()
    if ArayHuman.Lifecycle and ArayHuman.Lifecycle.manualSpawn then
        ArayHuman.Lifecycle.manualSpawn()
        return
    end
    local player = ArayHuman.getLocalPlayer()
    local cell = getCell()
    if not player or not cell then
        statusText = "Jogador ainda não está no mundo."
        return
    end
    player = syncLocalPlayer(player)
    if not player then
        statusText = "Jogador ainda não está no mundo."
        return
    end
    if npc and not npc:isDead() then
        statusText = "Já existe um ajudante."
        return
    end
    if npc and npc:isDead() then
        statusText = "Ajudante morto. Outro não foi criado."
        return
    end

    local existing = findExisting(cell)
    if existing then
        npc = existing
        npcAge = nil
        modelRegistrationAttempted = false
        configureNpc(existing, existing:getCurrentSquare())
        rememberBorn(existing)
        statusText = "Ajudante já estava no mundo, em " .. xy(existing) .. "."
        print("[ARAY] NPC existente reaproveitado")
        return
    end

    local ok, err = pcall(spawnNpc, player, cell)
    if not ok then
        statusText = "Falha ao criar o ajudante."
        print("[ARAY] ERROR: " .. tostring(err))
    end
end

local WALK_DIRS = { {4, 0}, {-4, 0}, {0, 4}, {0, -4} }

local function findWalkSquare(cell, character)
    local px = math.floor(character:getX())
    local py = math.floor(character:getY())
    local pz = math.floor(character:getZ())
    for i = 1, #WALK_DIRS do
        local sq = cell:getGridSquare(px + WALK_DIRS[i][1], py + WALK_DIRS[i][2], pz)
        if not squareBlocked(sq, character) then
            return sq
        end
    end
    return nil
end

function ArayHuman.setStatus(text)
    statusText = text
end

function ArayHuman.squareFree(square, ignore)
    return not squareBlocked(square, ignore)
end

function ArayHuman.testWalk()
    if not npc or npc:isDead() then
        statusText = "Nenhum ajudante para caminhar."
        return
    end
    local orderName = ArayHuman.getOrderName and ArayHuman.getOrderName() or "Idle"
    local commanded = orderName == "FOLLOW_PLAYER" or orderName == "MOVE_TO" or orderName == "FACE_TARGET"
    if ArayHuman.walkActive() then
        if commanded and ArayHuman.order then
            ArayHuman.order({ name = "STOP" })
        else
            ArayHuman.cancelWalk(false)
        end
        statusText = "Teste de caminhada cancelado."
        return
    end
    if commanded and ArayHuman.order then
        ArayHuman.order({ name = "STOP" })
    end
    local cell = getCell()
    if not cell then
        statusText = "Celula indisponivel."
        return
    end
    local square = findWalkSquare(cell, npc)
    if not square then
        statusText = "Sem destino livre a 4 tiles."
        print("[ARAY] walk sem destino")
        return
    end
    if ArayHuman.walkTo(square, "teste") then
        statusText = "Caminhada de teste para " .. square:getX() .. "," .. square:getY() .. "," .. square:getZ() .. "."
    else
        statusText = "Falha ao enfileirar a caminhada."
    end
end

function ArayHuman.pull()
    if ArayHuman.Executor then ArayHuman.Executor.manualCommand() end
    local player = ArayHuman.getLocalPlayer()
    local cell = getCell()
    if not npc or npc:isDead() then
        statusText = "Nenhum ajudante para puxar."
        return
    end
    if not player or not cell then
        statusText = "Jogador ainda não está no mundo."
        return
    end
    local square = findSpawnSquare(cell, player, npc)
    if not square then
        statusText = "Sem tile livre para puxar o ajudante."
        return
    end
    local orderName = ArayHuman.getOrderName and ArayHuman.getOrderName() or "Idle"
    if (orderName == "FOLLOW_PLAYER" or orderName == "MOVE_TO" or orderName == "FACE_TARGET") and ArayHuman.order then
        ArayHuman.order({ name = "STOP" })
    elseif ArayHuman.walkActive() then
        ArayHuman.cancelWalk(true)
    end
    placeOnSquare(npc, square)
    rememberBorn(npc)
    if ArayHuman.Lifecycle and ArayHuman.Lifecycle.markDirty then
        ArayHuman.Lifecycle.markDirty()
    end
    statusText = "Ajudante puxado para " .. xy(npc) .. "."
    print("[ARAY] ajudante puxado para " .. xy(npc))
end

local function onPlayerUpdate(character)
    if isOurNpc(character) then
        restoreLocalPlayer()
    end
end

local function onTick()
    local player = ArayHuman.getLocalPlayer()
    local cell = getCell()
    if not player or not cell then return end
    player = syncLocalPlayer(player)
    if not npc then
        for _, tracked in pairs(roster) do
            if tracked and not tracked:isDead() then
                npc = tracked
                break
            end
        end
    end
    if not npc then return end
    recoverNpcVisibility(player)

    if npcAge == nil then
        tryRegisterModel()
        npcAge = 0
        logSnapshot(0)
    else
        tryRegisterModel()
        npcAge = npcAge + 1
        if npcAge == 1 or npcAge == 30 or npcAge == 120 then
            logSnapshot(npcAge)
        end
    end

    restoreLocalPlayer()
end

Events.OnPlayerUpdate.Add(onPlayerUpdate)
Events.OnTick.Add(onTick)
Events.RenderOpaqueObjectsInWorld.Add(renderNpcInWorld)
