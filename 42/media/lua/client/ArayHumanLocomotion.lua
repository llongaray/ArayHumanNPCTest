-- Reusable local interface. No policy loop, inference or reward assignment.
ArayHuman=ArayHuman or {}
ArayHuman.Locomotion={}
local L=ArayHuman.Locomotion
L.modes={WALK=true,RUN=true,SNEAK=true}
local pairsOfFlags={
    {"NPCGetRunning","NPCSetRunning"},{"isPathfindRunning","setPathfindRunning"},
    {"isRunning","setRunning"},{"isSneaking","setSneaking"},{"isSprinting","setSprinting"}}
local function call(o,name,...)
    local args={...}
    local ok,v=pcall(function() if o and o[name] then return o[name](o,unpack(args)) end end)
    if ok then return v end
end
local function copy(v)
    if type(v)~="table" then return v end
    local out={}; for k,x in pairs(v) do out[k]=copy(x) end; return out
end
L.copy=copy
local function known(v) return {known=v~=nil,value=v} end
local function health(c)
    local v=call(call(c,"getBodyDamage"),"getHealth")
    return type(v)=="number" and v==v and v~=math.huge and v~=-math.huge and v or nil
end
local function threat(uuid)
    local p=ArayHuman.Perception
    local obs=p and p.observeThreats and p.observeThreats(uuid)
    if not obs then return {known=false} end
    return {known=obs.active and obs.scan.complete or false,level=obs.level,immediate=obs.immediate,
        nearest=copy(obs.nearest),captured_at_ms=obs.captured_at_ms,world_id=obs.world_id,uuid=obs.uuid}
end
function L.captureFlags(c)
    if call(c,"isNPC")~=true then return nil,"UNSUPPORTED_npc_mode" end
    local result={}
    for _,pair in ipairs(pairsOfFlags) do
        local ok,exists=pcall(function() return c[pair[2]]~=nil end)
        local v=call(c,pair[1])
        if not ok or not exists or type(v)~="boolean" then return nil,"UNSUPPORTED_movement_flags" end
        result[pair[2]]=v
    end
    return result
end
function L.restoreFlags(c,flags)
    local success=true
    for _,pair in ipairs(pairsOfFlags) do
        local ok=pcall(function() c[pair[2]](c,flags[pair[2]]) end)
        success=success and ok
    end
    return success
end
function L.safeNativeState(c)
    return call(c,"isClimbing")==false and call(c,"isKnockedDown")==false
end
function L.applyMode(c,mode)
    if not L.modes[mode] and mode~="STOP" then return nil,"movement_mode_invalid" end
    local md=call(c,"getModData")
    if not md or not md.ARAY_IsNPC or c==ArayHuman.getLocalPlayer() then return nil,"not_npc" end
    if not L.safeNativeState(c) then return nil,"native_state_unsafe" end
    local before,reason=L.captureFlags(c); if not before then return nil,reason end
    local desired={NPCSetRunning=mode=="RUN",setPathfindRunning=mode=="RUN",setRunning=mode=="RUN",
        setSneaking=mode=="SNEAK" or (mode=="STOP" and before.setSneaking),setSprinting=false}
    for _,pair in ipairs(pairsOfFlags) do
        local ok=pcall(function() c[pair[2]](c,desired[pair[2]]) end)
        if not ok then L.restoreFlags(c,before); return nil,"movement_mode_failed" end
    end
    for _,pair in ipairs(pairsOfFlags) do
        if call(c,pair[1])~=desired[pair[2]] then
            L.restoreFlags(c,before); return nil,"movement_mode_unconfirmed"
        end
    end
    return before
end
function L.beginMetrics(c,uuid)
    return {started_at_ms=getTimestampMs(),distance_travelled=0,duration_ms=0,
        position={x=c:getX(),y=c:getY(),z=c:getZ()},position_initial={x=c:getX(),y=c:getY(),z=c:getZ()},speed=0,
        collision_samples={known=false},damage_received={known=false},health_before=known(health(c)),
        threat_before=threat(uuid),samples=0,
        survival_before=ArayHuman.Survival and ArayHuman.Survival.getSnapshot(uuid)}
end
function L.sampleMetrics(m,c,force)
    local at=getTimestampMs(); local elapsed=at-(m.sample_at_ms or m.started_at_ms)
    if not force and elapsed<250 then return end
    local x,y,z=c:getX(),c:getY(),c:getZ()
    local d=math.sqrt((x-m.position.x)^2+(y-m.position.y)^2)
    m.distance_travelled=m.distance_travelled+d; m.speed=elapsed>0 and d*1000/elapsed or 0
    if m.target then
        local remaining=math.sqrt((x-m.target.x)^2+(y-m.target.y)^2)
        m.target_distance_remaining=remaining; m.target_progress=m.target_distance_start-remaining
    end
    m.position={x=x,y=y,z=z}; m.sample_at_ms=at; m.duration_ms=at-m.started_at_ms; m.samples=m.samples+1
    m.running=known(call(c,"isRunning")); m.sneaking=known(call(c,"isSneaking"))
    local collided=call(c,"isCollidedThisFrame")
    if type(collided)=="boolean" then
        m.collision_samples.known=true; m.collision_samples.value=(m.collision_samples.value or 0)+(collided and 1 or 0)
    end
    local hp=health(c); local previous=m.health_after or m.health_before
    if hp~=nil and previous.known then
        m.damage_received.known=true
        m.damage_received.value=(m.damage_received.value or 0)+math.max(0,previous.value-hp)
    end
    m.health_after=known(hp)
end
function L.endMetrics(m,c,uuid,valid)
    if valid then L.sampleMetrics(m,c,true); m.threat_after=threat(uuid)
    else m.threat_after={known=false}; m.health_after={known=false} end
    m.position_final=valid and {x=c:getX(),y=c:getY(),z=c:getZ()} or {known=false}
    m.ended_at_ms=getTimestampMs(); m.duration_ms=m.ended_at_ms-m.started_at_ms
    m.survival_after=valid and ArayHuman.Survival and ArayHuman.Survival.getSnapshot(uuid) or nil
end
-- Every request is validated by the executor, including tokens returned below.
function L.submit(request)
    if not ArayHuman.Executor or not ArayHuman.Executor.requestLocomotion then return false,"executor_unavailable" end
    return ArayHuman.Executor.requestLocomotion(request)
end
function L.validateDestination(uuid,target_id)
    local p=ArayHuman.Perception; local s=p and p.updateSnapshot(uuid)
    if not s or not s.active then return nil,"perception_unavailable" end
    for _,t in ipairs(s.tiles or {}) do
        local id="tile:"..t.x..":"..t.y..":"..t.z
        if id==target_id and t.traversable_candidate.known and t.traversable_candidate.value then
            return {uuid=uuid,world_id=s.world_id,target_id=id,validated_at_ms=s.captured_at_ms}
        end
    end
    return nil,"destination_not_in_snapshot"
end
function L.getState(uuid)
    local r=ArayHuman.Executor.getState(uuid); if not r then return nil end
    return {uuid=r.uuid,action=r.action,target_id=r.destination and r.destination.target_id,
        movement_mode=r.movement_mode,action_id=r.requestActionId or r.actionId,
        execution_id=r.actionId,state=r.state,result=r.result,world_id=r.world_id,observations=r.observations}
end
local results={}
function L.clearResults() results={} end
function L.recordResult(r)
    local list=results[r.uuid] or {}; results[r.uuid]=list
    local result={uuid=r.uuid,action=r.action,action_id=r.requestActionId,execution_id=r.actionId,
        movement_mode=r.movement_mode,world_id=r.world_id,target_id=r.destination and r.destination.target_id,
        state=r.state,result=r.result,observations=copy(r.observations)}
    for i=#list,1,-1 do if list[i].action_id==r.requestActionId then table.remove(list,i) end end
    list[#list+1]=result
    while #list>16 do table.remove(list,1) end
    local m=r.observations or {}
    print("[ARAY-LOCOMOTION] uuid="..r.uuid.." action_id="..r.requestActionId.." mode="..tostring(r.movement_mode)
        .." state="..r.state.." result="..tostring(r.result).." distance="..tostring(m.distance_travelled)
        .." duration_ms="..tostring(m.duration_ms))
end
function L.getResult(uuid,action_id)
    -- Trigger the executor's world invalidation before returning cached outcomes.
    if ArayHuman.Executor then ArayHuman.Executor.getState(uuid) end
    for _,r in ipairs(results[uuid] or {}) do if r.action_id==action_id then return copy(r) end end
    return nil
end
