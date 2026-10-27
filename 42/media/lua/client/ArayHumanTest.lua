-- Experimental IsoSurvivor test. Runs once on a disposable save.
local attempted = false
local function testSurvivor()
    if attempted then return end
    local player = getPlayer()
    local cell = getCell()
    if not player or not cell then return end
    attempted = true
    local x, y, z = math.floor(player:getX()) + 3, math.floor(player:getY()) + 3, math.floor(player:getZ())
    if not cell:getGridSquare(x, y, z) then
        print('[ARAY] Square not loaded; spawn skipped')
        return
    end
    local ok, err = pcall(function()
        if not SurvivorDesc or not IsoSurvivor then
            error('SurvivorDesc or IsoSurvivor is not exposed to Lua')
        end
        local desc = SurvivorDesc.new()
        desc:setForename('Aray')
        desc:setSurname('NPC')
        local npc = IsoSurvivor.new(desc, cell, x, y, z)
        cell:getSurvivorList():add(npc)
        cell:addMovingObject(npc)
        print('[ARAY] IsoSurvivor instantiated: ' .. tostring(npc:getObjectName()))
    end)
    if not ok then print('[ARAY] ERROR: ' .. tostring(err)) end
end
Events.OnTick.Add(testSurvivor)
