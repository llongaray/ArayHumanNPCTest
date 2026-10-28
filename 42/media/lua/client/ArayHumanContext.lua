-- Opcoes do ajudante no clique do corpo.
ArayHuman = ArayHuman or {}

local HIT_X = 36
local HIT_ABOVE = 90
local hitLogs = 0
local rejectLogs = 0
local screenLimit = false
local GoCursor = nil
local cursorLimit = false

local function note(kind)
    if kind == "acerto" then
        if hitLogs >= 3 then return end
        hitLogs = hitLogs + 1
        print("[ARAY] clique ajudante acerto")
        return
    end
    if rejectLogs >= 3 then return end
    rejectLogs = rejectLogs + 1
    print("[ARAY] clique ajudante rejeitado " .. tostring(kind))
end

local function screenOf(playerNum, character)
    return isoToScreenX(playerNum, character:getX(), character:getY(), character:getZ()),
        isoToScreenY(playerNum, character:getX(), character:getY(), character:getZ())
end

local function bodyHit(playerNum, character, mx, my)
    local sx, sy = screenOf(playerNum, character)
    local dx = math.abs(mx - sx)
    local above = sy - my
    return dx <= HIT_X and above >= 0 and above <= HIT_ABOVE
end

local function bodyScore(playerNum, character, mx, my)
    local sx, sy = screenOf(playerNum, character)
    local dx = mx - sx
    local dy = my - (sy - HIT_ABOVE * 0.5)
    return dx * dx + dy * dy
end

local function clickedSquare(worldobjects)
    if not worldobjects then return nil end
    for i = 1, #worldobjects do
        local obj = worldobjects[i]
        if obj and obj.getSquare then
            local square = obj:getSquare()
            if square then return square end
        end
    end
    return nil
end

local function consider(seen, character)
    if not character or seen[character] then return end
    if not instanceof(character, "IsoGameCharacter") then return end
    seen[character] = true
end

local function nearbyCharacters(square)
    local seen = {}
    if not square then return seen end
    local cell = getCell()
    if not cell then return seen end
    local x = square:getX()
    local y = square:getY()
    local z = square:getZ()
    for dx = -2, 2 do
        for dy = -2, 2 do
            local near = cell:getGridSquare(x + dx, y + dy, z)
            if near and near.getMovingObjects then
                local moving = near:getMovingObjects()
                for i = 0, moving:size() - 1 do
                    consider(seen, moving:get(i))
                end
            end
        end
    end
    return seen
end

local function pointerOnNpc(playerNum, npc, worldobjects)
    if not npc or npc:isDead() then return "morto" end
    local player = getSpecificPlayer(playerNum)
    if player and math.floor(player:getZ()) ~= math.floor(npc:getZ()) then return "andar" end
    if npc.isOnScreen and not npc:isOnScreen() then return "fora" end
    if not isoToScreenX or not isoToScreenY then
        if not screenLimit then
            screenLimit = true
            print("[ARAY] limite: conversao mundo-tela indisponivel")
        end
        return "tela"
    end
    local mx = getMouseX()
    local my = getMouseY()
    if not bodyHit(playerNum, npc, mx, my) then return "fora da caixa" end
    local npcScore = bodyScore(playerNum, npc, mx, my)
    local seen = nearbyCharacters(clickedSquare(worldobjects))
    consider(seen, player)
    for character, _ in pairs(seen) do
        if character ~= npc and not character:isDead() and bodyHit(playerNum, character, mx, my) then
            if bodyScore(playerNum, character, mx, my) < npcScore then
                return "outro personagem"
            end
        end
    end
    return true
end

local function onStay(uuid)
    if ArayHuman.order then ArayHuman.order({ name = "STAY" }, uuid) end
end

local function onFace(uuid)
    if ArayHuman.order then ArayHuman.order({ name = "FACE_TARGET" }, uuid) end
end

local function onFollow(uuid)
    if ArayHuman.order then ArayHuman.order({ name = "FOLLOW_PLAYER" }, uuid) end
end

local function ensureGoCursor()
    if GoCursor then return GoCursor end
    if not ISBuildingObject or not ISBuildingObject.derive then
        if not cursorLimit then
            cursorLimit = true
            print("[ARAY] limite: ISBuildingObject indisponivel")
        end
        return nil
    end
    local class = ISBuildingObject:derive("ArayGoCursor")

    function class:new(uuid)
        local o = {}
        setmetatable(o, self)
        self.__index = self
        o:init()
        o.character = getSpecificPlayer(0)
        o.player = 0
        o.npcUuid = uuid
        o.skipBuildAction = true
        o.skipWalk2 = true
        o.noNeedHammer = true
        return o
    end

    function class:isValid(square)
        local npc = self.npcUuid and ArayHuman.getNpcByUuid and ArayHuman.getNpcByUuid(self.npcUuid)
            or (not self.npcUuid and ArayHuman.getNpc and ArayHuman.getNpc())
        if not square or not npc or npc:isDead() then return false end
        if not square.TreatAsSolidFloor or not square:TreatAsSolidFloor() then return false end
        if ArayHuman.squareFree then
            return ArayHuman.squareFree(square, npc) == true
        end
        return false
    end

    function class:render(x, y, z, square)
        if not square or not self.getFloorCursorSprite then return end
        local color = getCore():getBadHighlitedColor()
        if self:isValid(square) then
            color = getCore():getGoodHighlitedColor()
        end
        self:getFloorCursorSprite():RenderGhostTileColor(
            square:getX(), square:getY(), square:getZ(),
            color:getR(), color:getG(), color:getB(), 0.8)
    end

    function class:create(x, y, z, north, sprite)
        local cell = getCell()
        if cell then cell:setDrag(nil, 0) end
        local square = cell and cell:getGridSquare(x, y, z)
        if not square or not self:isValid(square) then
            print("[ARAY] ir ate recusado")
            return
        end
        if ArayHuman.order then
            ArayHuman.order({
                name = "MOVE_TO",
                x = square:getX(),
                y = square:getY(),
                z = square:getZ(),
            }, self.npcUuid)
        end
    end

    GoCursor = class
    return GoCursor
end

local function onGoTo(uuid)
    local class = ensureGoCursor()
    local cell = getCell()
    if not class or not cell or not cell.setDrag then return end
    cell:setDrag(class:new(uuid), 0)
end

local function onTalk()
    if ArayHuman.SpeechBubble and ArayHuman.SpeechBubble.probe and ArayHuman.getNpc then
        ArayHuman.SpeechBubble.probe(ArayHuman.getNpc())
    end
    if ArayHuman.TalkBar and ArayHuman.TalkBar.open then
        ArayHuman.TalkBar.open()
    end
end

local function onFill(player, context, worldobjects, test)
    if not context or not context.addOption then return end
    local playerNum = player
    if type(player) ~= "number" then playerNum = 0 end
    if not ArayHuman.getNpc then return end
    local npc = ArayHuman.getNpc()
    local hit = pointerOnNpc(playerNum, npc, worldobjects)
    if hit ~= true then
        note(hit)
        return
    end
    note("acerto")
    if test == true then
        if ISWorldObjectContextMenu and ISWorldObjectContextMenu.setTest then
            ISWorldObjectContextMenu.setTest()
        end
        return
    end
    if not ISContextMenu or not ISContextMenu.getNew or not context.addSubMenu then return end
    local root = context:addOption("Ajudante", nil, nil)
    local menu = ISContextMenu:getNew(context)
    if not root or not menu then return end
    context:addSubMenu(root, menu)
    menu:addOption("Conversar", nil, onTalk)
    local uuid = npc.getModData and npc:getModData().ARAY_Uuid or nil
    menu:addOption("Ficar aqui", uuid, onStay)
    menu:addOption("Olhar para mim", uuid, onFace)
    menu:addOption("Seguir-me", uuid, onFollow)
    menu:addOption("Ir até...", uuid, onGoTo)
end

Events.OnFillWorldObjectContextMenu.Add(onFill)
print("[ARAY] contexto ajudante carregado")
