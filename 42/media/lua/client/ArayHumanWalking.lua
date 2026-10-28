-- UUID-scoped adapter over the native B42 walking action. Never changes player/camera.
require "TimedActions/WalkToTimedAction"
require "TimedActions/ISTimedActionQueue"
require "ArayHumanLocomotion"
ArayHuman = ArayHuman or {}
ArayHuman.Walking = ArayHuman.Walking or {}
local W = ArayHuman.Walking
W.config = { timeoutMs = 30000, noProgressMs = 5000 }
local walks = {}
local serial = 0

local function now() return getTimestampMs and getTimestampMs() or 0 end
local function world()
    local w = getWorld and getWorld()
    local core = getCore and getCore()
    return w and core and tostring(core:getGameMode()) .. "/" .. tostring(w:getWorld()) or nil
end
local function resolve(uuid)
    local c = uuid and type(uuid) ~= "string" and uuid
        or uuid and ArayHuman.getNpcByUuid and ArayHuman.getNpcByUuid(uuid)
        or (not uuid and ArayHuman.getNpc and ArayHuman.getNpc())
    local md = c and c:getModData()
    if not md or not md.ARAY_IsNPC or (type(uuid)=="string" and md.ARAY_Uuid ~= uuid) then return nil end
    return c, md.ARAY_Uuid or c
end
local function distance(c, x, y)
    return math.sqrt((c:getX() - x)^2 + (c:getY() - y)^2)
end
local function arrived(c,r)
    return math.floor(c:getX())==r.x and math.floor(c:getY())==r.y and math.floor(c:getZ())==r.z
        and distance(c,r.x+.5,r.y+.5)<=.8
end
local function owned(r) return walks[r.uuid] == r and not r.done end
local function loaded(c)
    local cell = getCell and getCell()
    return cell and c:getCurrentSquare() and c:getCurrentSquare() == cell:getGridSquare(
        math.floor(c:getX()), math.floor(c:getY()), math.floor(c:getZ()))
end
local function contains(r)
    local q = ISTimedActionQueue and ISTimedActionQueue.queues and ISTimedActionQueue.queues[r.character]
    if not q or not q.queue then return false end
    for _, action in ipairs(q.queue) do if action == r.action then return true end end
    return false
end
local function captureEnd(r)
    local L=ArayHuman.Locomotion
    if L and r.observations and not r.observations.ended_at_ms then L.endMetrics(r.observations,r.character,r.uuid,world()==r.world and loaded(r.character)) end
    if r.modeFlags then
        if r.character:isDead() or L.safeNativeState(r.character) then
            r.modeRestored=L.restoreFlags(r.character,r.modeFlags); r.modeFlags=nil
            if r.observations then r.observations.mode_restored={known=true,value=r.modeRestored} end
            if not r.modeRestored then print("[ARAY-WALK] uuid="..r.uuid.." event=mode_restore_failed") end
        else r.restorePending=true; if r.observations then r.observations.mode_restored={known=false,pending=true} end end
    end
end
local function finish(r, result, silent)
    if not owned(r) then return end
    r.done, r.result = true, result
    captureEnd(r)
    print("[ARAY-WALK] uuid="..tostring(r.uuid).." id="..r.id.." event=finished source="..tostring(r.source).." result="..result)
    if r.callback then r.callback(result, r.id) end
    if not silent and ArayHuman.onWalkFinished then
        ArayHuman.onWalkFinished(result, r.source, r.uuid, r.id)
    end
    if not silent and r.source == "teste" and ArayHuman.setStatus then
        ArayHuman.setStatus("Caminhada: " .. result)
    end
end
local function stopOwned(r)
    -- Invalidate FIRST. Delayed native stop/perform must not touch the next path/queue.
    local action = r.action
    if action and action.forceStop then pcall(function() action:forceStop() end) end
    local q = ISTimedActionQueue and ISTimedActionQueue.queues and ISTimedActionQueue.queues[r.character]
    if q and q.queue then
        for i = #q.queue, 1, -1 do
            if q.queue[i] == action then table.remove(q.queue, i) end
        end
        if q.current == action then q.current = nil end
    end
    local c = r.character
    pcall(function()
        local behavior = c:getPathFindBehavior2()
        if behavior then behavior:cancel() end
        c:setPath2(nil)
    end)
end

function W.cancel(uuid, reason, silent)
    local c, key = resolve(uuid)
    -- Old instances may no longer resolve; their owned record still needs cancellation.
    local r = walks[uuid or key]
    if not r or r.done then return false end
    r.done, r.result = true, reason or "cancelado"
    print("[ARAY-WALK] uuid="..tostring(r.uuid).." id="..r.id.." event=cancelled source="..tostring(r.source).." result="..r.result)
    stopOwned(r)
    captureEnd(r)
    if r.callback then r.callback(r.result, r.id) end
    if not silent and ArayHuman.onWalkFinished then
        ArayHuman.onWalkFinished(r.result, r.source, r.uuid, r.id)
    end
    return true
end

function W.active(uuid)
    local _, key = resolve(uuid)
    local r = walks[uuid or key]
    return r ~= nil and not r.done
end
function W.getState(uuid)
    local _,key=resolve(uuid); local r=walks[uuid or key]
    if not r then return nil end
    return {id=r.id,source=r.source,done=r.done,result=r.result,x=r.x,y=r.y,z=r.z,
        actualX=r.character:getX(),actualY=r.character:getY(),speed=r.speed or 0,
        travelled=r.travelled or 0,lastProgressAt=r.lastProgress,queued=contains(r),
        remaining=distance(r.character,r.x+.5,r.y+.5),progressAgeMs=now()-r.lastProgress,
        nativeResult=tostring(r.action.result),nativeAction="ISWalkToTimedAction",
        movement_mode=r.movement_mode,observations=r.observations and ArayHuman.Locomotion.copy(r.observations),modeRestored=r.modeRestored}
end

function W.start(uuid, square, source, options)
    options = options or {}
    if ArayHuman.Physical and ArayHuman.Physical.busy(uuid) then return false,"physical_busy" end
    local c, key = resolve(uuid)
    if ArayHuman.Physical and ArayHuman.Physical.busy(key) then return false,"physical_busy" end
    if not c or c:isDead() or not loaded(c) or not square then return false, "instance_unavailable" end
    if not ISWalkToTimedAction or not ISTimedActionQueue or not ISTimedActionQueue.add or not ISTimedActionQueue.queues then
        return false, "walking_api_unavailable"
    end
    local previous=walks[key]
    if previous and previous.restorePending then
        if not ArayHuman.Locomotion.safeNativeState(c) then return false,"native_state_unsafe" end
        captureEnd(previous); previous.restorePending=nil
    end
    if options.movement_mode and (not ArayHuman.Locomotion or not ArayHuman.Locomotion.modes[options.movement_mode]) then return false,"movement_mode_invalid" end
    if options.movement_mode then
        local flags,why=ArayHuman.Locomotion.captureFlags(c)
        if not flags then return false,why end
        if not ArayHuman.Locomotion.safeNativeState(c) then return false,"native_state_unsafe" end
    end
    if getGameSpeed and getGameSpeed() > 2 then return false, "game_speed" end
    local cell = getCell()
    if cell:getGridSquare(square:getX(), square:getY(), square:getZ()) ~= square
        or math.floor(c:getZ()) ~= square:getZ() or not ArayHuman.squareFree(square, c) then
        return false, "destination_blocked"
    end
    if source ~= "executor" and ArayHuman.Executor then ArayHuman.Executor.manualCommand(key) end
    W.cancel(key, "cancelado", true)
    local q = ISTimedActionQueue.queues[c]
    if q and q.queue and #q.queue > 0 then return false, "foreign_action_busy" end
    serial = serial + 1
    local created, action = pcall(function() return ISWalkToTimedAction:new(c, square) end)
    if not created or not action then return false,"walking_api_unavailable" end
    local modeFlags,modeReason
    if ArayHuman.Locomotion then modeFlags,modeReason=ArayHuman.Locomotion.applyMode(c,options.movement_mode or "WALK") end
    if options.movement_mode and not modeFlags then return false,modeReason end
    local r = { uuid = key, character = c, id = serial, action = action, source = source,
        startedAt = now(), lastProgress = now(), lastX = c:getX(), lastY = c:getY(),
        sampleX=c:getX(),sampleY=c:getY(),sampleAt=now(),movement_mode=options.movement_mode or "WALK",modeFlags=modeFlags,
        x = square:getX(), y = square:getY(), z = square:getZ(), world = world(),
        timeoutMs = options.timeoutMs or W.config.timeoutMs,
        noProgressMs = options.noProgressMs or W.config.noProgressMs, callback = options.onResult }
    r.observations=options.observations or (ArayHuman.Locomotion and ArayHuman.Locomotion.beginMetrics(c,key))
    if r.observations then
        r.observations.target={x=r.x+.5,y=r.y+.5,z=r.z}
        r.observations.target_distance_start=distance(c,r.x+.5,r.y+.5)
        r.observations.target_distance_remaining=r.observations.target_distance_start
        r.observations.target_progress=0
    end
    walks[key] = r
    -- Guard all native entry points, not only our completion callback.
    for _, method in ipairs({ "start", "update", "stop", "perform" }) do
        local original = action[method]
        if original then
            action[method] = function(self, ...)
                if owned(r) then return original(self, ...) end
            end
        end
    end
    action:setOnComplete(function()
        if not owned(r) then return end
        if arrived(c,r) then
            finish(r, "sucesso")
        else
            finish(r, "falha")
        end
    end)
    local ok = pcall(function() ISTimedActionQueue.add(action) end)
    if not ok or not contains(r) then
        W.cancel(key, "falha", true)
        return false, "pathfinding_failed"
    end
    print("[ARAY-WALK] uuid="..tostring(key).." id="..r.id.." event=started source="..tostring(source)
        .." destination="..r.x..","..r.y..","..r.z)
    return true, r.id
end

function W.update()
    for key, r in pairs(walks) do
        if r.done and r.restorePending and ArayHuman.Locomotion.safeNativeState(r.character) then
            -- Retire flags only for the still-owned record, never a newer generation.
            r.modeRestored=ArayHuman.Locomotion.restoreFlags(r.character,r.modeFlags)
            if r.observations then r.observations.mode_restored={known=true,value=r.modeRestored} end
            r.modeFlags=nil; r.restorePending=nil
        end
        if not r.done then
            local c = resolve(key)
            local reason = nil
            if r.observations and world()==r.world and c==r.character and loaded(c) then
                ArayHuman.Locomotion.sampleMetrics(r.observations,c,false)
            end
            local elapsed=now()-(r.sampleAt or r.startedAt)
            if elapsed>=250 then
                local moved=distance(r.character,r.sampleX or r.lastX,r.sampleY or r.lastY)
                r.speed=moved*1000/elapsed; r.travelled=(r.travelled or 0)+moved
                r.sampleX,r.sampleY,r.sampleAt=r.character:getX(),r.character:getY(),now()
            end
            if world() ~= r.world then reason = "world_changed"
            elseif c ~= r.character or not loaded(r.character) then reason = "instance_unavailable"
            elseif c:isDead() then reason = "npc_dead"
            elseif now() - r.startedAt >= r.timeoutMs then reason = "timeout"
            elseif BehaviorResult and r.action.result == BehaviorResult.Failed then reason = "pathfinding_failed"
            elseif not contains(r) then
                if arrived(c,r) then
                    finish(r, "sucesso")
                else reason = "pathfinding_failed" end
            elseif distance(c, r.lastX, r.lastY) >= .1 then
                r.lastX, r.lastY, r.lastProgress = c:getX(), c:getY(), now()
            elseif now() - r.lastProgress >= r.noProgressMs then reason = "sem progresso" end
            if not reason and not r.done and now()>=(r.nextValidation or 0) then
                r.nextValidation=now()+250
                local sq=getCell() and getCell():getGridSquare(r.x,r.y,r.z)
                if not sq or not ArayHuman.squareFree(sq,c) then reason="destination_blocked" end
            end
            if reason then W.cancel(key, reason, false) end
        end
    end
end

-- Existing F7/context callers retain their signatures and implicitly use the focused NPC.
function ArayHuman.walkActive(uuid) return W.active(uuid) end
function ArayHuman.cancelWalk(silent, uuid) return W.cancel(uuid, "cancelado", silent) end
function ArayHuman.walkTo(square, source, uuid, options)
    return W.start(uuid, square, source or "comando", options)
end
Events.OnTick.Add(W.update)
