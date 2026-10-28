-- Bounded, on-demand observations. Never creates NPCs or requests execution.
require "ArayHumanCapabilities"
require "ArayHumanPerception"
require "ArayHumanCharacterBuild"
ArayHuman=ArayHuman or {}
local A={schema_version=1,config={intervalMs=1000,maxNPCs=128,maxCandidates=96,maxMoveCandidates=32,
 maxInventoryCandidates=48,maxItems=32,maxEvents=8,maxResults=4}}
ArayHuman.AgentState=A
local C=ArayHuman.Capabilities
local cache,worldSeen,serial={},nil,0
local function checkWorld()
 local w=C.checkWorld(); if w~=worldSeen then cache={}; worldSeen=w end
 return w
end
function A.invalidate(id) cache[id]=nil end
function A.clearAll() cache={} end
local function slice(list,n)
 local out={}; for i=1,math.min(#(list or {}),n) do out[i]=C.copy(list[i]) end
 return out
end
local function tail(list,n)
 local out={}; for i=math.max(1,#(list or {})-n+1),#(list or {}) do out[#out+1]=C.copy(list[i]) end
 return out
end
local function compactResult(r)
 return C.copy({action_id=r.action_id,requested_action=r.requested_action,executed_action=r.executed_action,
  state=r.state,result=r.result,duration_ms=r.duration_ms,damage_received=r.damage_received,
  progress=r.progress,resources_used=r.resources_used,failure_reason=r.failure_reason})
end
local function runtime(id)
 local e=ArayHuman.Executor.getState(id); local n=ArayHuman.Navigation.getState(id)
 local i=ArayHuman.Inventory.getState(id)
 return C.copy({execution=e and {action=e.action,action_id=e.requestActionId or e.actionId,state=e.state,
   result=e.result,world_id=e.world_id,destination=e.destination,movement_mode=e.movement_mode,
   emergency=e.localSurvival==true},
  navigation=n and {action_id=n.action_id,state=n.state,result=n.result,step_index=n.step_index},
  inventory_action=i,control=ArayHuman.Executor.getControlState(id)})
end
local function build(id,c)
 local at=C.now(); serial=serial+1
 local p=ArayHuman.Perception.getSnapshot(id)
 if not p or c and not c:isDead() and (not p.active or not p.position or p.position.x~=c:getX()
  or p.position.y~=c:getY() or p.position.z~=c:getZ()) or not C.finite(p.captured_at_ms)
  or at<p.captured_at_ms or at-p.captured_at_ms>=A.config.intervalMs then
  p=ArayHuman.Perception.updateSnapshot(id)
 end
 local s=ArayHuman.Survival.getSnapshot(id)
 local alive=p and p.alive and p.alive.known and p.alive.value==true
 local active=c~=nil and alive and p.active==true
 local inv=active and ArayHuman.Inventory.getSnapshot(id) or nil
 local md=c and c:getModData() or {}
 local out={schema_version=1,uuid=id,world_id=worldSeen,captured_at_ms=at,
  observation_id="observation:"..serial,expires_at_ms=at+A.config.intervalMs,
  active=active==true,identity={uuid=id,name=C.value(md.ARAY_Name)},
  position=C.copy(p and p.position or {known=false}),direction=C.copy(p and p.direction or {known=false}),
  perception={captured_at_ms=p and p.captured_at_ms,player=C.copy(p and p.player),
   nearby_npcs=slice(p and p.nearby_npcs,16),nearby_zombies=slice(p and p.nearby_zombies,16),
   scan=C.copy(p and p.scan),observation=p and p.observation},
  threat=C.copy(s and s.threat or {known=false}),
  survival=s and {captured_at_ms=s.captured_at_ms,health=C.copy(s.health),conditions=C.copy(s.conditions),
   wounds=C.copy(s.wounds),states=C.copy(s.states),state_list=C.copy(s.state_list),needs=C.copy(s.needs),
   needs_policy=C.copy(s.needs_policy)} or {available=false,reason="survival_unavailable"},
  inventory=inv and {available=inv.available,reason=inv.scan and inv.scan.reason,
   captured_at_ms=inv.captured_at_ms,items=slice(inv.items,A.config.maxItems),
   total_observed_items=#(inv.items or {}),items_truncated=#(inv.items or {})>A.config.maxItems,
   weight=C.value(inv.weight),capacity=C.value(inv.capacity),scan=C.copy(inv.scan)}
   or {available=false,reason=active and "inventory_unavailable" or "inactive_npc"},
  profile={schema_version=1,available=false,reason="3C.4D.1_not_implemented",
   profession={status="unavailable"},traits={status="unavailable"},skills={status="unavailable"},
   xp={status="unavailable"},points={status="unavailable"}},
  candidates={},candidate_scope="bounded_observed_candidates_require_executor_revalidation",
  events=tail(ArayHuman.Survival.getEvents(id) or {},A.config.maxEvents),results={}}
 if p and C.finite(p.captured_at_ms) then out.expires_at_ms=math.min(out.expires_at_ms,p.captured_at_ms+A.config.intervalMs) end
 local function add(action,target,expiry)
  if #out.candidates>=A.config.maxCandidates then out.candidates_truncated=true; return end
  if not C.finite(expiry) or expiry<=at then return end
  out.candidates[#out.candidates+1]={action=action,target_id=target,uuid=id,world_id=worldSeen,
   observation_id=out.observation_id,expires_at_ms=math.min(expiry,out.expires_at_ms)}
 end
 if active then
  local moves=0; local tiles={}
  for _,tile in ipairs(p.tiles or {}) do tiles[#tiles+1]=tile end
  local function distance(tile,pos) return ((tile.x+.5-pos.x)^2+(tile.y+.5-pos.y)^2)^.5 end
  table.sort(tiles,function(a,b)
   local da,db=distance(a,p.position),distance(b,p.position)
   if da~=db then return da<db end
   if a.x~=b.x then return a.x<b.x end
   return a.y<b.y
  end)
  for _,tile in ipairs(tiles) do
   local t=tile.traversable_candidate
   local playerPos=p.player and p.player.known and p.player.position
   if t and t.known and t.value and distance(tile,p.position)<=ArayHuman.Executor.config.maxMoveDistance
    and playerPos and tile.z==math.floor(playerPos.z)
    and distance(tile,playerPos)<=ArayHuman.Executor.config.playerLimit then
    moves=moves+1
    if moves<=A.config.maxMoveCandidates then
     local target="tile:"..tile.x..":"..tile.y..":"..tile.z
     -- One candidate carries modes, avoiding three identical spatial records.
     add("MOVE",target,out.expires_at_ms)
    else out.candidates_truncated=true; break end
   end
  end
  if p.player and p.player.known then add("FACE_TARGET","PLAYER",out.expires_at_ms) end
  for _,edge in ipairs(ArayHuman.Physical.getCandidates(id) or {}) do
   for action,allowed in pairs(edge.actions or {}) do if allowed then add(action,edge.target_id,out.expires_at_ms) end end
  end
  for index,item in ipairs(inv and inv.candidates or {}) do
   if index>A.config.maxInventoryCandidates then out.candidates_truncated=true; break end
   add(item.action,item.target_id,item.expires_at_ms)
  end
 end
 return out
end
function A.getSnapshot(id)
 checkWorld()
 local c,reason=C.actor(id,true)
 if reason=="uuid_invalid" then return nil,reason end
 if not C.validId(id,36) or #id~=36 then return nil,"uuid_invalid" end
 local at=C.now(); local r=cache[id]
 local dead=c and c:isDead()
 local p=ArayHuman.getLocalPlayer and ArayHuman.getLocalPlayer()
 if not r or r.character~=c or r.dead~=dead or r.player~=p or at<r.snapshot.captured_at_ms
  or at>=r.snapshot.expires_at_ms then
  if not r then
   local count=0; for _ in pairs(cache) do count=count+1 end
   if count>=A.config.maxNPCs then return nil,"registry_full" end
  end
  r={character=c,dead=dead,player=p,snapshot=build(id,c)}; cache[id]=r
 end
 local out=C.copy(r.snapshot)
 if ArayHuman.CharacterBuild then out.profile=ArayHuman.CharacterBuild.getProfile(id) end
 if not c then out.reason=reason end
 out.runtime=runtime(id); out.capabilities=C.getCatalog(id)
 for _,result in ipairs(tail(C.getRecentResults(id),A.config.maxResults)) do
  out.results[#out.results+1]=compactResult(result)
 end
 return out
end
-- No refresh here: an expired or replaced observation never silently authorizes a request.
function A.validateCandidate(id,action,target,observation)
 checkWorld(); local r=cache[id]
 if type(target)~="string" or #target>128 then return false,"target_id_invalid" end
 if not r or observation~=r.snapshot.observation_id then return false,"observation_mismatch" end
 if r.character~=C.actor(id) or r.snapshot.world_id~=worldSeen then return false,"instance_changed" end
 if C.now()<r.snapshot.captured_at_ms or C.now()>=r.snapshot.expires_at_ms then return false,"candidate_expired" end
 for _,candidate in ipairs(r.snapshot.candidates) do
  local matches=candidate.action==action or candidate.action=="MOVE" and
   (action=="WALK" or action=="RUN" or action=="SNEAK" or action=="FACE_TARGET")
  if matches and candidate.target_id==target and candidate.expires_at_ms>C.now() then return true end
 end
 return false,"candidate_not_in_observation"
end
