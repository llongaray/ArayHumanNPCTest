-- Aray Human NPC Test - B42.13.1
-- Safety gate: do not register an IsoSurvivor whose core components are absent.
-- This is a diagnostic build, not a functional NPC implementation.
local attempted = false

local function testSurvivor()
    if attempted then return end
    local player = getPlayer()
    local cell = getCell()
    if not player or not cell then return end
    attempted = true

    local x = math.floor(player:getX()) + 3
    local y = math.floor(player:getY()) + 3
    local z = math.floor(player:getZ())
    if not cell:getGridSquare(x, y, z) then
        print('[ARAY] DIAGNOSTIC: spawn square not loaded; skipped')
        return
    end

    local ok, err = pcall(function()
        if not SurvivorDesc or not IsoSurvivor then
            error('SurvivorDesc or IsoSurvivor not exposed to Lua')
        end

        local desc = SurvivorDesc.new()
        desc:setForename('Aray')
        desc:setSurname('NPC')
        local npc = IsoSurvivor.new(desc, cell, x, y, z)
        if not npc then error('IsoSurvivor constructor returned nil') end

        local damageOk, damage = pcall(function() return npc:getBodyDamage() end)
        print('[ARAY] DIAGNOSTIC: IsoSurvivor instantiated; BodyDamage accessible=' ..
            tostring(damageOk) .. ', initialized=' .. tostring(damage ~= nil))

        if not damageOk or damage == nil then
            print('[ARAY] SAFETY: BodyDamage absent. NPC NOT added to moving objects or survivor list.')
            return
        end

        -- No automatic registration until the complete update lifecycle is verified.
        print('[ARAY] SAFETY: BodyDamage present, but registration disabled pending lifecycle validation.')
    end)
    if not ok then print('[ARAY] ERROR: ' .. tostring(err)) end
end

Events.OnTick.Add(testSurvivor)
