-- Aray Human NPC Test - B42.13.1
-- IsoSurvivor fica com BodyDamage nulo e quebra no update.
-- IsoPlayer é a classe que o jogo inicializa com BodyDamage, moodles e visual humano.
local attempted = false
local sweptLegacy = false

local function setJavaField(obj, name, value)
    local ok, err = pcall(function()
        local cls = obj:getClass()
        local field = nil
        while cls do
            local found, result = pcall(function() return cls:getDeclaredField(name) end)
            if found and result then
                field = result
                break
            end
            cls = cls:getSuperclass()
        end
        if not field then error("campo ausente: " .. tostring(name)) end
        pcall(function() field:setAccessible(true) end)
        if type(value) == "boolean" then
            field:setBoolean(obj, value)
        elseif type(value) == "number" then
            field:setInt(obj, math.floor(value))
        else
            field:set(obj, value)
        end
    end)
    if not ok then
        print("[ARAY] ERROR campo " .. tostring(name) .. ": " .. tostring(err))
    end
    return ok
end

local function readJavaField(obj, name, kind)
    local ok, value = pcall(function()
        local cls = obj:getClass()
        while cls do
            local found, field = pcall(function() return cls:getDeclaredField(name) end)
            if found and field then
                pcall(function() field:setAccessible(true) end)
                if kind == "boolean" then return field:getBoolean(obj) end
                if kind == "int" then return field:getInt(obj) end
                return field:get(obj)
            end
            cls = cls:getSuperclass()
        end
        return nil
    end)
    if not ok then return nil end
    return value
end

local function discard(npc, reason)
    if npc then
        pcall(function() npc:removeFromWorld() end)
        pcall(function() npc:removeFromSquare() end)
    end
    print("[ARAY] ERROR: " .. tostring(reason))
end

-- remote=true faz o update do IsoPlayer sair antes de roubar a camera e o IsoPlayer.instance.
local function protectNpc(npc)
    if not npc or npc == getPlayer() then return false end
    pcall(function() npc:setNPC(true) end)
    local remoteSet = setJavaField(npc, "remote", true)
    local remote = readJavaField(npc, "remote", "boolean")
    setJavaField(npc, "playerIndex", -1)
    local index = readJavaField(npc, "playerIndex", "int")
    if not remoteSet or remote ~= true then
        discard(npc, "remote nao ficou true (set=" .. tostring(remoteSet) .. ", lido=" .. tostring(remote) .. "). NPC removido.")
        return false
    end
    local md = npc:getModData()
    md.ARAY_IsNPC = true
    md.ARAY_Name = "Aray"
    print("[ARAY] protecao ok remote=" .. tostring(remote) .. " playerIndex=" .. tostring(index))
    return true
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
            pcall(function() obj:removeFromWorld() end)
            pcall(function() obj:removeFromSquare() end)
            removed = removed + 1
        end
    end
    local survivors = cell:getSurvivorList()
    if survivors then
        for i = survivors:size() - 1, 0, -1 do
            local obj = survivors:get(i)
            if obj and instanceof(obj, "IsoSurvivor") then
                pcall(function() survivors:remove(obj) end)
                pcall(function() obj:removeFromWorld() end)
                removed = removed + 1
            end
        end
    end
    if removed > 0 then
        print("[ARAY] removidos " .. tostring(removed) .. " IsoSurvivor legado (BodyDamage nulo).")
    end
end

local function findExisting(cell)
    local list = cell:getObjectList()
    if not list then return nil end
    for i = 0, list:size() - 1 do
        local obj = list:get(i)
        if obj and obj ~= getPlayer() and obj.getModData then
            local ok, md = pcall(function() return obj:getModData() end)
            if ok and md and md.ARAY_IsNPC then return obj end
        end
    end
    return nil
end

local function spawnNpc(player, cell)
    local x = math.floor(player:getX()) + 3
    local y = math.floor(player:getY())
    local z = math.floor(player:getZ())
    local square = cell:getGridSquare(x, y, z)
    if not square then return false end

    local desc = nil
    local createdOk, created = pcall(function() return SurvivorFactory.CreateSurvivor() end)
    if createdOk and created then
        desc = created
    else
        desc = SurvivorDesc.new()
    end
    desc:setForename("Aray")
    desc:setSurname("NPC")

    local npc = IsoPlayer.new(cell, desc, x, y, z)
    if not npc then
        print("[ARAY] ERROR: IsoPlayer.new retornou nil")
        return true
    end
    if not protectNpc(npc) then return true end

    local damage = npc:getBodyDamage()
    if not damage then
        discard(npc, "IsoPlayer sem BodyDamage")
        return true
    end

    npc:setCurrent(square)
    local movers = square:getMovingObjects()
    if movers and not movers:contains(npc) then
        movers:add(npc)
    end

    print("[ARAY] NPC criado em " .. x .. "," .. y .. "," .. z
        .. " classe=IsoPlayer BodyDamage=true vida=" .. tostring(damage:getOverallBodyHealth())
        .. " npc=" .. tostring(npc:isNPC()))
    return true
end

local function testSurvivor()
    if attempted then return end
    local player = getPlayer()
    local cell = getCell()
    if not player or not cell then return end

    removeLegacySurvivors(cell)

    local existing = findExisting(cell)
    if existing then
        attempted = true
        protectNpc(existing)
        print("[ARAY] NPC existente reaproveitado")
        return
    end

    if not cell:getGridSquare(math.floor(player:getX()) + 3, math.floor(player:getY()), math.floor(player:getZ())) then
        return
    end

    attempted = true
    local ok, err = pcall(function() spawnNpc(player, cell) end)
    if not ok then print("[ARAY] ERROR: " .. tostring(err)) end
end

Events.OnTick.Add(testSurvivor)
