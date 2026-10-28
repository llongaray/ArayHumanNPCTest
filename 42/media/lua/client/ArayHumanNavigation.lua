-- Finite, explicit plans only. Delegates every step to the existing executor.
require "ArayHumanLocomotion"
require "ArayHumanPhysical"
ArayHuman=ArayHuman or {}
ArayHuman.Navigation={}
local N=ArayHuman.Navigation
N.config={intervalMs=250,maxSteps=12,maxActive=8,maxPerTick=2,maxDurationMs=120000}
local plans,history,seen,dispatching={},{},{},{}
local worldSeen,lastUpdate,cursor=nil,0,1
local L=ArayHuman.Locomotion
local function now() return getTimestampMs() end
local function world()
    local core=getCore and getCore(); local w=getWorld and getWorld()
    return core and w and tostring(core:getGameMode())..'/'..tostring(w:getWorld()) or nil
end
local function active(r) return r and (r.state=="READY" or r.state=="RUNNING" or r.state=="WAITING_PHYSICAL") end
local function actor(id)
    if not world() or type(id)~='string' or #id~=36 or not id:match('^%x+%-%x+%-%x+%-%x+%-%x+$') then return nil end
    local c=ArayHuman.getNpcByUuid and ArayHuman.getNpcByUuid(id); local md=c and c:getModData()
    local cell=getCell and getCell()
    if not cell or not c or not c.isNPC or c:isNPC()~=true then return nil end
    if not md or not md.ARAY_IsNPC or md.ARAY_Uuid~=id or c:isDead() or c==ArayHuman.getLocalPlayer() then return nil end
    if c:getCurrentSquare()~=cell:getGridSquare(math.floor(c:getX()),math.floor(c:getY()),math.floor(c:getZ())) or not c:getCurrentSquare() then return nil end
    return c
end
local function log(r,event,reason)
    print('[ARAY-NAVIGATION] uuid='..r.uuid..' action_id='..r.action_id..' event='..event
        ..' step='..r.step_index..' reason='..tostring(reason))
end
local function archive(r)
    local list=history[r.uuid] or {}; history[r.uuid]=list
    for i=#list,1,-1 do if list[i].action_id==r.action_id then table.remove(list,i) end end
    list[#list+1]=L.copy(r.public)
    while #list>16 do table.remove(list,1) end
end
local function finish(r,state,reason)
    if not active(r) then return end
    r.state=state; r.result=reason
    local child=ArayHuman.Executor.getState(r.uuid)
    if r.child_id and child and child.requestActionId==r.child_id then
        ArayHuman.Executor.cancel(r.uuid,reason)
        local result=L.getResult(r.uuid,r.child_id)
        if result and not r.step_results[r.step_index] then r.step_results[r.step_index]=result end
    end
    local c=actor(r.uuid)
    L.endMetrics(r.observations,c,r.uuid,c~=nil and r.world_id==world())
    r.public={uuid=r.uuid,action_id=r.action_id,world_id=r.world_id,state=state,result=reason,
        step_index=r.step_index,steps=L.copy(r.step_results),requested_steps=L.copy(r.steps),observations=L.copy(r.observations)}
    archive(r); log(r,'plan_result',reason)
end
local function checkWorld()
    local current=world()
    if worldSeen~=current then
        for _,r in pairs(plans) do if active(r) then finish(r,'CANCELLED','world_changed') end end
        worldSeen=current; seen={}; history={}; plans={}; cursor=1; lastUpdate=0
    end
end
function N.cancel(id,reason)
    local r=plans[id]; if not active(r) then return false end
    finish(r,'CANCELLED',reason or 'cancelled'); return true
end
function N.onManualCommand(id)
    if not dispatching[id] then N.cancel(id,'manual_command') end
end
function N.onExecutorCancel(id,reason)
    if not dispatching[id] then return N.cancel(id,reason or 'executor_cancelled') end
    return false
end
function N.onLocomotionRequest(id)
    if not dispatching[id] then N.cancel(id,'superseded') end
end
local function normalized(step)
    if type(step)~='table' then return nil,'invalid_step' end
    for k in pairs(step) do if k~='action' and k~='target_id' and k~='movement_mode' then return nil,'invalid_step_field' end end
    local action=step.action; local mode=step.movement_mode
    if L.modes[action] then
        if mode~=nil then return nil,'duplicate_movement_mode' end
        mode=action; action='MOVE_TO'
    end
    local unsupported=ArayHuman.Physical.unsupportedReason(action)
    if unsupported then return nil,unsupported end
    if action~='MOVE_TO' and not ArayHuman.Physical.actions[action]
        and not (ArayHuman.Inventory and ArayHuman.Inventory.actions[action]) then return nil,'action_invalid' end
    if action=='MOVE_TO' and not L.modes[mode or 'WALK'] then return nil,'movement_mode_invalid' end
    if action~='MOVE_TO' and mode~=nil then return nil,'movement_mode_invalid' end
    if type(step.target_id)~='string' or #step.target_id>128 then return nil,'target_id_invalid' end
    return {action=action,movement_mode=action=='MOVE_TO' and (mode or 'WALK') or nil,target_id=step.target_id}
end
function N.submit(request)
    checkWorld()
    if not worldSeen then return false,"world_unavailable" end
    if type(request)~='table' then return false,'invalid_request' end
    for k in pairs(request) do
        if k~='uuid' and k~='world_id' and k~='action_id' and k~='source' and k~='expires_at_ms' and k~='steps' then return false,'invalid_request_field' end
    end
    local id=request.uuid; local c=type(id)=='string' and actor(id)
    if not c then return false,'instance_unavailable' end
    if request.world_id~=worldSeen then return false,'world_mismatch' end
    local rid=request.action_id
    if type(rid)~='string' or #rid<1 or #rid>96 or not rid:match('^[%w._:-]+$') then return false,'action_id_invalid' end
    local source=request.source or 'policy'
    if source~='policy' and source~='manual' then return false,'source_invalid' end
    local expires=request.expires_at_ms or (now()+N.config.maxDurationMs)
    if type(expires)~='number' or expires~=math.floor(expires) or expires<=now() or expires-now()>N.config.maxDurationMs then return false,'expired' end
    local key=id..':'..rid; local count=0
    for k,at in pairs(seen) do if at<=now() then seen[k]=nil else count=count+1 end end
    if seen[key] then return false,'duplicate_action_id' end
    if count>=256 then return false,'registry_full' end
    if type(request.steps)~='table' or #request.steps<1 or #request.steps>N.config.maxSteps then return false,'step_limit' end
    for k in pairs(request.steps) do if type(k)~='number' or k~=math.floor(k) or k<1 or k>#request.steps then return false,'invalid_steps' end end
    local steps={}
    for i,step in ipairs(request.steps) do
        local entry,why=normalized(step)
        if not entry then
            print('[ARAY-NAVIGATION] uuid='..id..' action_id='..rid..' event=rejected reason='..why)
            return false,why
        end
        -- Check schema/candidate provenance now; reach, collision and threats are checked at execution.
        if entry.action=='MOVE_TO' then
            local z=entry.target_id:match('^tile:%-?%d+:%-?%d+:(%-?%d+)$')
            if z and tonumber(z)~=math.floor(c:getZ()) then return false,'UNSUPPORTED_STAIRS_NPC' end
            local token,reason=L.validateDestination(id,entry.target_id)
            if not token then return false,reason end
        elseif ArayHuman.Inventory and ArayHuman.Inventory.actions[entry.action] then
            local candidate,reason=ArayHuman.Inventory.resolveCandidate(id,entry.action,entry.target_id)
            if not candidate then return false,reason end
        else
            local candidate,reason=ArayHuman.Physical.resolveCandidate(id,entry.action,entry.target_id)
            if not candidate then return false,reason end
        end
        steps[i]=entry
    end
    local activeCount=0; for uuid,r in pairs(plans) do if uuid~=id and active(r) then activeCount=activeCount+1 end end
    if activeCount>=N.config.maxActive then return false,'active_plan_limit' end
    local current=ArayHuman.Executor.getState(id)
    if source=='policy' and current and current.localSurvival and current.state~='COMPLETED'
        and current.state~='FAILED' and current.state~='CANCELLED' then return false,'emergency_priority' end
    N.cancel(id,'replaced')
    if source=='manual' then
        dispatching[id]=true; ArayHuman.Executor.manualCommand(id); dispatching[id]=nil
    end
    local r={uuid=id,action_id=rid,world_id=worldSeen,state='READY',source=source,steps=steps,
        step_index=1,step_results={},expires_at_ms=expires,observations=L.beginMetrics(c,id)}
    plans[id]=r; seen[key]=expires
    log(r,'plan_accepted','explicit_finite_plan')
    return true,rid
end
local function updateOne(r)
    local c=actor(r.uuid)
    if not c then finish(r,'CANCELLED','npc_dead_or_unloaded'); return end
    if now()>=r.expires_at_ms then finish(r,'FAILED','timeout'); return end
    L.sampleMetrics(r.observations,c,false)
    local current=ArayHuman.Executor.getState(r.uuid)
    if r.child_id then
        local result=L.getResult(r.uuid,r.child_id)
        if not current or current.requestActionId~=r.child_id then
            if result then r.step_results[r.step_index]=result end
            finish(r,'CANCELLED','superseded_or_emergency'); return
        end
        if not result then return end
        r.step_results[r.step_index]=result; r.last_child_id=r.child_id; r.child_id=nil
        if result.state~='COMPLETED' then finish(r,result.state=='CANCELLED' and 'CANCELLED' or 'FAILED',result.result); return end
        log(r,'step_confirmed',result.result)
        r.step_index=r.step_index+1
        if r.step_index>#r.steps then finish(r,'COMPLETED','sequence_completed') else r.state='READY' end
        return
    end
    if r.last_child_id and current and current.requestActionId~=r.last_child_id then finish(r,'CANCELLED','superseded_or_emergency'); return end
    if ArayHuman.Physical.busy(r.uuid) then r.state='WAITING_PHYSICAL'; return end
    local step=r.steps[r.step_index]
    local child=r.action_id..':step:'..r.step_index
    r.child_id=child
    local dispatchedAt=now(); local initial={x=c:getX(),y=c:getY(),z=c:getZ()}
    dispatching[r.uuid]=true
    local ok,why=L.submit({uuid=r.uuid,world_id=r.world_id,action=step.action,target_id=step.target_id,
        movement_mode=step.movement_mode,source=r.source,action_id=child,
        expires_at_ms=math.min(r.expires_at_ms,now()+30000)})
    dispatching[r.uuid]=nil
    if not ok then
        if not L.getResult(r.uuid,child) then
            r.step_results[r.step_index]={uuid=r.uuid,action=step.action,action_id=child,target_id=step.target_id,
                state='FAILED',result=why,executed=false,observations={position_initial=initial,
                position_final={x=c:getX(),y=c:getY(),z=c:getZ()},duration_ms=now()-dispatchedAt,
                damage_received={known=false}}}
        end
        finish(r,'FAILED',why); return
    end
    r.state='RUNNING'; log(r,'step_started',step.action)
end
function N.update()
    checkWorld()
    if not worldSeen then return end
    if now()-lastUpdate<N.config.intervalMs then return end
    lastUpdate=now()
    local ids={}; for id,r in pairs(plans) do if active(r) then ids[#ids+1]=id end end; table.sort(ids)
    for i=1,math.min(#ids,N.config.maxPerTick) do
        if cursor>#ids then cursor=1 end
        local r=plans[ids[cursor]]; cursor=cursor+1
        if active(r) then updateOne(r) end
    end
end
function N.getState(id)
    checkWorld(); local r=plans[id]; if not r then return nil end
    if r.public then return L.copy(r.public) end
    return {uuid=id,action_id=r.action_id,world_id=r.world_id,state=r.state,step_index=r.step_index,
        steps=L.copy(r.step_results),requested_steps=L.copy(r.steps),observations=L.copy(r.observations)}
end
function N.getResult(id,rid)
    checkWorld()
    for _,r in ipairs(history[id] or {}) do if r.action_id==rid then return L.copy(r) end end
end
Events.OnTick.Add(N.update)
