-- Versioned, explicitly invoked policy boundary. No inference, scheduler or rewards.
require "ArayHumanExecutor"
require "ArayHumanNavigation"
ArayHuman=ArayHuman or {}
local C={schema_version=1,config={maxRequests=16,maxNPCs=128,maxSteps=12,maxTTL=30000}}
ArayHuman.Capabilities=C
local records,worldSeen={},nil
local terminal={COMPLETED=true,FAILED=true,CANCELLED=true}
local specs={
 WALK={backend="MOVE_TO",mode="WALK",target=true}, RUN={backend="MOVE_TO",mode="RUN",target=true},
 SNEAK={backend="MOVE_TO",mode="SNEAK",target=true}, STOP={backend="STOP"},
 FACE_TARGET={backend="FACE_TARGET",target=true}, LOOK_AT_PLAYER={backend="FACE_TARGET",player=true},
 FOLLOW_PLAYER={backend="FOLLOW_PLAYER"}, SAY={backend="SAY",text=true},
 OPEN_DOOR={target=true},CLOSE_DOOR={target=true},OPEN_WINDOW={target=true},
 CLIMB_WINDOW={target=true},CLIMB_FENCE={target=true},PICKUP_ITEM={target=true},
 LOOT_CONTAINER={target=true},TRANSFER_ITEM={target=true},BANDAGE={target=true},
 NAVIGATE={sequence=true},PUSH_ZOMBIE={blocked="UNSUPPORTED_target_exclusive_native_shove"},
 CLIMB_STAIRS={blocked="UNSUPPORTED_STAIRS_VERTICAL_VALIDATION"}}
function C.now() return getTimestampMs() end
function C.world()
 local w=getWorld and getWorld(); local c=getCore and getCore()
 return w and c and tostring(c:getGameMode()).."/"..tostring(w:getWorld()) or nil
end
function C.checkWorld()
 local w=C.world(); if w~=worldSeen then records={}; worldSeen=w end
 return w
end
function C.validId(v,max)
 return type(v)=="string" and #v>0 and #v<=max and v:match("^[%w._:-]+$")~=nil
end
function C.finite(v) return type(v)=="number" and v==v and v~=math.huge and v~=-math.huge end
function C.actor(id,allowDead)
 if type(id)~="string" or #id~=36 or not id:match("^%x%x%x%x%x%x%x%x%-%x%x%x%x%-%x%x%x%x%-%x%x%x%x%-%x%x%x%x%x%x%x%x%x%x%x%x$") then return nil,"uuid_invalid" end
 local c=ArayHuman.getNpcByUuid and ArayHuman.getNpcByUuid(id)
 local ok,valid=pcall(function()
  local md=c and c:getModData(); local cell=getCell and getCell()
  return c and c~=ArayHuman.getLocalPlayer() and c:isNPC()==true and md.ARAY_IsNPC==true and md.ARAY_Uuid==id
   and (allowDead or c:isDead()==false) and cell and c:getCurrentSquare()
   and c:getCurrentSquare()==cell:getGridSquare(math.floor(c:getX()),math.floor(c:getY()),math.floor(c:getZ()))
 end)
 if ok and valid then return c end
 return nil,"instance_unavailable_or_dead"
end
-- Only plain serializable values cross the boundary. Outbound truncation is explicit.
function C.copy(value)
 local budget=16384; local seen={}; local truncated=false
 local function visit(v,depth)
  budget=budget-1
  if budget<0 or depth>12 then truncated=true; return nil end
  local t=type(v)
  if t=="string" then if #v>1024 then truncated=true; return v:sub(1,1024) end; return v end
  if t=="boolean" or (t=="number" and C.finite(v)) then return v end
  if t~="table" then return nil end
  if seen[v] or getmetatable(v)~=nil then truncated=true; return nil end
  seen[v]=true; local r={}; local count=0
  for k,x in pairs(v) do
   count=count+1; if count>128 then truncated=true; break end
   if (type(k)=="string" and #k<=128) or (type(k)=="number" and k>=1 and k<=128 and k%1==0) then r[k]=visit(x,depth+1) end
  end
  seen[v]=nil; return r
 end
 local result=visit(value,0)
 if truncated and type(result)=="table" then result.serialization_truncated=true end
 return result
end
function C.value(v,reason)
 if v==nil then return {known=false,status="unknown",reason=reason or "not_observed"} end
 if type(v)=="number" and not C.finite(v) then return {known=false,status="unknown",reason="non_finite_value"} end
 if type(v)~="number" and type(v)~="boolean" and type(v)~="string" then
  return {known=false,status="unknown",reason="non_scalar_value"}
 end
 return {known=true,status="known",value=v}
end
function C.getCatalog(uuid)
 C.checkWorld()
 local c,why=C.actor(uuid); local control=ArayHuman.Executor.getControlState(uuid)
 local inv=ArayHuman.Inventory and ArayHuman.Inventory.getCapabilities() or {}
 local result={schema_version=1,uuid=uuid,world_id=worldSeen,actions={}}
 for name,spec in pairs(specs) do
  local reason=spec.blocked
  if not reason and not c then reason=why end
  if not reason and control.manual_priority then reason="manual_priority" end
  if not reason and control.emergency_priority then reason="emergency_priority" end
  if not reason and name~="STOP" and ArayHuman.Physical.busy(uuid) then reason="physical_busy" end
  if not reason and inv[name] and not inv[name].executable then reason=inv[name].status end
  if not reason and spec.mode then
   local flags,err=ArayHuman.Locomotion.captureFlags(c); if not flags then reason=err end
  end
  if not reason and (name=="FACE_TARGET" or name=="LOOK_AT_PLAYER")
   and (not c.faceLocationF or not c.isFacingLocation or not c.shouldBeTurning) then reason="UNSUPPORTED_facing" end
  if not reason and name=="SAY" and not (ArayHuman.SpeechBubble and ArayHuman.SpeechBubble.show) then reason="speech_unavailable" end
  if not reason and ArayHuman.Physical.actions[name]
   and (not c.faceDirection or not c.shouldBeTurning or not c.isFacingLocation) then reason="UNSUPPORTED_orientation" end
  local nativeMethods={OPEN_WINDOW="openWindow",CLIMB_WINDOW="climbThroughWindow",CLIMB_FENCE="climbOverFence"}
  if not reason and nativeMethods[name] and not c[nativeMethods[name]] then reason="UNSUPPORTED_native_action_api" end
  result.actions[name]={action=name,backend=spec.backend or name,movement_mode=spec.mode,
   support=spec.blocked and "UNSUPPORTED" or "experimental",available=reason==nil,reason=reason,
   availability_status=reason and "unavailable" or "eligible_for_validation",
   evidence="local_B42_native_API_audit_and_simulated_Lua_tests",manual_validation="pending",
   requires_target=spec.target==true,revalidation_required=true}
 end
 result.policy={source="policy",manual_origin_allowed=false,rewards_implemented=false,
  hunger_objective=false,thirst_objective=false,fatigue_objective=false}
 return result
end
local function plain(v,depth,seen,budget)
 budget.n=budget.n+1; if budget.n>512 or depth>6 then return false end
 local t=type(v)
 if t=="number" then return C.finite(v) end
 if t=="string" then return #v<=512 end
 if t=="boolean" then return true end
 if t~="table" or getmetatable(v) or seen[v] then return false end
 seen[v]=true
 for k,x in pairs(v) do
  if not ((type(k)=="string" and #k<=64) or (type(k)=="number" and k%1==0 and k>=1 and k<=12))
   or not plain(x,depth+1,seen,budget) then seen[v]=nil; return false end
 end
 seen[v]=nil; return true
end
local function priority(id)
 local control=ArayHuman.Executor.getControlState(id)
 if control.manual_priority then return "manual_priority" end
 if control.emergency_priority then return "emergency_priority" end
end
local function summary(id,force)
 local S=ArayHuman.Survival
 local s=S and (force and S.updateSnapshot(id) or S.getSnapshot(id))
 local c=C.actor(id,true)
 return C.copy({captured_at_ms=C.now(),survival_captured_at_ms=s and s.captured_at_ms,
  position=c and {known=true,x=c:getX(),y=c:getY(),z=c:getZ()} or {known=false},health=s and s.health,
  conditions=s and s.conditions,state_list=s and s.state_list,threat=s and s.threat,
  needs=s and s.needs,needs_policy=s and s.needs_policy})
end
local function lookup(id,action,target,observation)
 local a=ArayHuman.AgentState
 if not a then return false,"state_unavailable" end
 return a.validateCandidate(id,action,target,observation)
end
local function refresh(r)
 if terminal[r.state] then return end
 local A=ArayHuman
 local raw
 if r.request.action=="NAVIGATE" then raw=A.Navigation.getResult(r.uuid,r.action_id)
 else raw=A.Locomotion.getResult(r.uuid,r.action_id) end
 local current=A.Executor.getState(r.uuid)
 if not raw and r.request.action=="NAVIGATE" then
  local n=A.Navigation.getState(r.uuid)
  if n and n.action_id==r.action_id then raw=n end
 end
 if not raw and current and current.requestActionId==r.action_id then raw=current end
 if not raw then r.state="UNKNOWN"; r.failure_reason="backend_result_unavailable"; return end
 r.state=raw.state; r.result=raw.result
 local physicalResult=A.Physical.getResult(r.uuid,r.action_id)
 local m=physicalResult and physicalResult.observations or raw.observations or {}
 r.duration_ms=C.value(m.duration_ms)
 r.progress=C.copy({distance_travelled=C.value(m.distance_travelled),progress=C.value(m.target_progress),
  collisions=m.collision_samples or C.value(nil)})
 r.damage_received=C.copy(m.damage_received or {known=false,status="unknown",reason="not_observed"})
 r.resources_used=C.copy(m.inventory or {known=false,status="unknown",reason="not_observed"})
 -- Cancellation can outlive the executor: preserve the real native inventory outcome.
 local item=A.Inventory and A.Inventory.getResult(r.uuid,r.action_id)
 if item then r.resources_used=C.copy(item.observations) end
 if terminal[r.state] then
  local physical=A.Physical.getState(r.uuid); local inventory=A.Inventory.getState(r.uuid)
  local function owned(lock)
   return lock and (lock.action_id==r.action_id or r.request.action=="NAVIGATE"
    and lock.action_id:sub(1,#r.action_id+6)==r.action_id..":step:")
  end
  if owned(physical) or owned(inventory) then r.state="CANCEL_PENDING"; return end
  local survival=m.survival_after
  -- Freeze the backend's actual end sample; never attribute a later command to this action.
  r.after=C.copy({captured_at_ms=m.ended_at_ms,position=m.position_final or {known=false},
   health=m.health_after or {known=false},threat=m.threat_after or {known=false},
   survival_captured_at_ms=survival and survival.captured_at_ms,
   needs=survival and survival.needs,conditions=survival and survival.conditions,
   state_list=survival and survival.state_list,needs_policy=survival and survival.needs_policy})
  r.completed_at_ms=C.now(); r.physical_result=C.copy(physicalResult)
  if r.state~="COMPLETED" then r.failure_reason=r.result end
  local steps={}
  for _,step in ipairs(raw.steps or {}) do
   local metrics=step.observations or {}
   steps[#steps+1]={action=step.action,state=step.state,result=step.result,
    duration_ms=C.value(metrics.duration_ms),resources_used=C.copy(metrics.inventory),
    damage_received=C.copy(metrics.damage_received)}
  end
  r.backend=C.copy({action=raw.action,state=raw.state,result=raw.result,steps=steps})
 end
end
function C.getResult(uuid,actionId)
 C.checkWorld()
 for _,r in ipairs(records[uuid] or {}) do
  if r.action_id==actionId then refresh(r); return C.copy(r) end
 end
end
function C.getRecentResults(uuid)
 C.checkWorld(); local out={}
 for _,r in ipairs(records[uuid] or {}) do refresh(r); out[#out+1]=C.copy(r) end
 return out
end
function C.request(request)
 C.checkWorld()
 if type(request)~="table" or not plain(request,0,{}, {n=0}) then return false,"non_serializable_request" end
 local fields={schema_version=true,uuid=true,world_id=true,action_id=true,origin=true,priority=true,
  expires_at_ms=true,action=true,target_id=true,observation_id=true,text=true,steps=true}
 for k in pairs(request) do if not fields[k] then return false,"invalid_request_field" end end
 if request.schema_version~=1 then return false,"schema_version" end
 local c,why=C.actor(request.uuid); if not c then return false,why end
 if not worldSeen or request.world_id~=worldSeen then return false,"world_mismatch" end
 if not C.validId(request.action_id,96) then return false,"action_id_invalid" end
 if request.origin~="ollama" and request.origin~="rl" and request.origin~="neural" then return false,"origin_invalid" end
 if not C.finite(request.priority) or request.priority%1~=0 or request.priority<0 or request.priority>3 then return false,"priority_invalid" end
 if not C.finite(request.expires_at_ms) or request.expires_at_ms%1~=0 or request.expires_at_ms<=C.now()
  or request.expires_at_ms-C.now()>C.config.maxTTL then return false,"expired" end
 local spec=specs[request.action]; if not spec then return false,"action_invalid" end
 if spec.blocked then return false,spec.blocked end
 local gate=priority(request.uuid); if gate then return false,gate end
 local list=records[request.uuid]
 if not list then
  local count=0; for _ in pairs(records) do count=count+1 end
  if count>=C.config.maxNPCs then return false,"registry_full" end
  list={}; records[request.uuid]=list
 end
 for _,r in ipairs(list) do if r.action_id==request.action_id then return false,"duplicate_action_id" end end
 for _,r in ipairs(list) do
  refresh(r)
  if not terminal[r.state] and r.request.priority>request.priority then return false,"policy_priority" end
 end
 if #list>=C.config.maxRequests then
  refresh(list[1]); if not terminal[list[1].state] then return false,"registry_full" end
  table.remove(list,1)
 end
 local target=request.target_id
 if spec.target then
  local ok,reason=lookup(request.uuid,request.action,target,request.observation_id)
  if not ok then return false,reason end
 elseif target~=nil then return false,"unexpected_target" end
 if spec.text then
  if type(request.text)~="string" or #request.text>300 or not request.text:match("%S") then return false,"say_text" end
 elseif request.text~=nil then return false,"unexpected_text" end
 if not spec.sequence and request.steps~=nil then return false,"unexpected_steps" end
 local adapted={uuid=request.uuid,world_id=worldSeen,action_id=request.action_id,
  source="policy",expires_at_ms=request.expires_at_ms}
 if spec.sequence then
  if type(request.steps)~="table" or #request.steps<1 or #request.steps>C.config.maxSteps then return false,"invalid_steps" end
  adapted.steps={}
  for k in pairs(request.steps) do if type(k)~="number" or k%1~=0 or k<1 or k>#request.steps then return false,"invalid_steps" end end
  for _,step in ipairs(request.steps) do
   if type(step)~="table" then return false,"invalid_step" end
   for k in pairs(step) do if k~="action" and k~="target_id" then return false,"invalid_step_field" end end
   local st=specs[step.action]
   if not st or not st.target or step.action=="FACE_TARGET" then return false,"invalid_step_action" end
   local ok,reason=lookup(request.uuid,step.action,step.target_id,request.observation_id)
   if not ok then return false,reason end
   adapted.steps[#adapted.steps+1]={action=step.action,target_id=step.target_id}
  end
 else
  adapted.action=spec.backend or request.action; adapted.movement_mode=spec.mode
  adapted.target_id=spec.player and "PLAYER" or target; adapted.text=request.text
 end
 local r={schema_version=1,uuid=request.uuid,world_id=worldSeen,action_id=request.action_id,
  request=C.copy(request),requested_action=request.action,dispatched_action=adapted.action or "NAVIGATE",
  movement_mode=spec.mode,state="REQUESTED",started_at_ms=C.now(),before=summary(request.uuid,true),
  unknown_fields={"reward","profession","traits","skills","xp","points"}}
 local ok,result
 local previousExecution=ArayHuman.Executor.getState(request.uuid)
 if spec.sequence then ok,result=ArayHuman.Navigation.submit(adapted)
 else ok,result=ArayHuman.Executor.requestLocomotion(adapted) end
 r.accepted=ok==true; r.execution_id=ok and result or nil
 local owned=ArayHuman.Executor.getState(request.uuid)
 local allocated=owned and owned.requestActionId==request.action_id
  and (not previousExecution or previousExecution.generation~=owned.generation)
 if ok or allocated then
  r.executed_action=adapted.action or "NAVIGATE"; r.state="RUNNING"
 else r.state="FAILED"; r.result=result; r.failure_reason=result; r.after=summary(request.uuid) end
 list[#list+1]=r
 if ok or allocated then refresh(r) end
 if ArayHuman.AgentState then ArayHuman.AgentState.invalidate(request.uuid) end
 return ok,C.copy(r)
end
function C.cancel(uuid,actionId,origin)
 C.checkWorld()
 if origin~="ollama" and origin~="rl" and origin~="neural" then return false,"origin_invalid" end
 local gate=priority(uuid); if gate then return false,gate end
 for _,r in ipairs(records[uuid] or {}) do
  if r.action_id==actionId then
   if r.request.origin~=origin then return false,"origin_mismatch" end
   refresh(r); if terminal[r.state] then return false,"already_terminal" end
   local current=ArayHuman.Executor.getState(uuid)
   if r.request.action=="NAVIGATE" then
    local n=ArayHuman.Navigation.getState(uuid)
    if not n or n.action_id~=actionId then return false,"superseded" end
    ArayHuman.Navigation.cancel(uuid,"agent_cancelled")
   elseif current and current.requestActionId==actionId then ArayHuman.Executor.cancel(uuid,"agent_cancelled")
   else return false,"superseded" end
   refresh(r); return true,C.copy(r)
  end
 end
 return false,"action_unknown"
end
