-- Aray Human NPC Test - B42.13.1
-- IsoSurvivor nasce com BodyDamage nulo e quebra no update.
-- IsoPlayer é a classe que o jogo inicializa como humano.
local attempted = false
local sweptLegacy = false
local npc = nil

local OFFSETS = {
    {1, 0}, {-1, 0}, {0, 1}, {0, -1},
    {1, 1}, {1, -1}, {-1, 1}, {-1, -1},
    {2, 0}, {0, 2}, {-2, 0}, {0, -2},
    {3, 0}, {0, 3},
}

local function restoreLocalPlayer()
    local me = getSpecificPlayer(0)
    if not me or me == npc then return end
    IsoPlayer.setInstance(me)
    if IsoCamera then
        IsoCamera.setCameraCharacter(me)
    end
end

local function findSpawnSquare(cell, player)
    local px = math.floor(player:getX())
    local py = math.floor(player:getY())
    local pz = math.floor(player:getZ())
    for i = 1, #OFFSETS do
        local sq = cell:getGridSquare(px + OFFSETS[i][1], py + OFFSETS[i][2], pz)
        if sq and sq:TreatAsSolidFloor() and sq:isFree(false) then
            return sq
        end
    end
    return nil
end

local function removeLegacySurvivors(cell)
    if sweptLegacy then return end
    sweptLegacy = true
    local list = cell:getObjectList()
    if not list then return end
    local removed = 0
    for i = list:size() - 1, 0, -1 do
        local obj = list:get(i)
        if obj and instanceof(obj, "IsoSurvivor") then
            obj:removeFromWorld()
            obj:removeFromSquare()
            removed = removed + 1
        end
    end
    if removed > 0 then
        print("[ARAY] removidos " .. tostring(removed) .. " IsoSurvivor legado")
    end
end

local function findExisting(cell)
    local list = cell:getObjectList()
    if not list then return nil end
    local me = getSpecificPlayer(0)
    for i = 0, list:size() - 1 do
        local obj = list:get(i)
        if obj and obj ~= me and obj.getModData then
            local md = obj:getModData()
            if md and md.ARAY_IsNPC then return obj end
        end
    end
    return nil
end

local function configureNpc(character, square)
    character:setNPC(true)
    local md = character:getModData()
    md.ARAY_IsNPC = true
    md.ARAY_Name = "Aray"
    if square then
        character:setCurrent(square)
        local movers = square:getMovingObjects()
        if movers and not movers:contains(character) then
            movers:add(character)
        end
    end
    local damage = character:getBodyDamage()
    print("[ARAY] NPC em " .. math.floor(character:getX()) .. "," .. math.floor(character:getY())
        .. " BodyDamage=" .. tostring(damage ~= nil)
        .. " vida=" .. tostring(damage and damage:getOverallBodyHealth() or "nil")
        .. " isNPC=" .. tostring(character:isNPC()))
    restoreLocalPlayer()
end

local function spawnNpc(player, cell)
    local square = findSpawnSquare(cell, player)
    if not square then
        print("[ARAY] sem tile livre ao lado do jogador")
        return false
    end

    local desc = SurvivorFactory.CreateSurvivor()
    if not desc then desc = SurvivorDesc.new() end
    desc:setForename("Aray")
    desc:setSurname("NPC")

    local character = IsoPlayer.new(cell, desc, square:getX(), square:getY(), square:getZ())
    if not character then
        print("[ARAY] ERROR: IsoPlayer.new retornou nil")
        return true
    end
    if not character:getBodyDamage() then
        character:removeFromWorld()
        character:removeFromSquare()
        print("[ARAY] ERROR: IsoPlayer sem BodyDamage")
        return true
    end

    npc = character
    configureNpc(character, square)
    return true
end

local function onPlayerUpdate(character)
    if npc and character == npc then
        restoreLocalPlayer()
    end
end

local function onTick()
    local player = getSpecificPlayer(0)
    local cell = getCell()
    if not player or not cell then return end

    if not attempted then
        removeLegacySurvivors(cell)
        local existing = findExisting(cell)
        if existing then
            npc = existing
            attempted = true
            configureNpc(existing, existing:getCurrentSquare())
            print("[ARAY] NPC existente reaproveitado")
        else
            local ok, doneOrErr = pcall(function() return spawnNpc(player, cell) end)
            if not ok then
                attempted = true
                print("[ARAY] ERROR: " .. tostring(doneOrErr))
            elseif doneOrErr then
                attempted = true
            end
        end
    end

    if npc then restoreLocalPlayer() end
end

Events.OnPlayerUpdate.Add(onPlayerUpdate)
Events.OnTick.Add(onTick)
