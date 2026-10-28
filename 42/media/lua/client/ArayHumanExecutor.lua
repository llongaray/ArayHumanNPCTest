-- Explicitly invoked execution only. This module never requests a decision.
require "ArayHumanWalking"
require "ArayHumanEscapePlanner"
ArayHuman = ArayHuman or {}
ArayHuman.Executor = ArayHuman.Executor or {}
local E = ArayHuman.Executor
E.config = { playerLimit = 12, permissionMode = "ASK", timeoutMs = 30000,
    noProgressMs = 5000, monitorMs = 250, followMs = 1000, followDistance = 2,
    maxMoveDistance = 10, snapshotMaxAgeMs = 1500, threatDistance = 3,
    emergencyDistance = 6, emergencyDurationMs = 6000, safeThreatDistance = 5 }
E.survivalConfig = { intervalMs=250, maxNPCsPerTick=2, rosterRefreshMs=1000,
    cooldownMs=1000, maxAttempts=3, recoveryMs=30000, maxRecoveries=2, clearAfterMs=3000, releaseDistance=4.5, maxRouteNodes=96 }
local states, generations, sequences, seen, manual, cutoff = {}, {}, {}, {}, {}, {}
local session, worldSeen, lastMonitor = nil, nil, 0
local serial = 0
local motionSeen={}
local episodes, safetyRoster, safetyCursor = {}, {}, 1
local lastSafety, lastRoster = nil, nil
local function diagnostic(uuid,event,details)
    print("[ARAY-SURVIVAL] uuid="..tostring(uuid).." event="..event.." "..tostring(details or ""))
end
local allowed = { IDLE=true, LOOK_AT_PLAYER=true, FOLLOW_PLAYER=true, MOVE_TO=true,
    WANDER_NEARBY=true, SAY=true, STOP=true }
local terminalStates = { COMPLETED=true, CANCELLED=true, FAILED=true }

local function now() return getTimestampMs and getTimestampMs() or 0 end
local function finite(n) return type(n)=="number" and n==n and n~=math.huge and n~=-math.huge end
local function integer(n) return finite(n) and n==math.floor(n) end
local function uuidValid(id)
    return type(id)=="string" and #id==36 and id:sub(9,9)=="-" and id:sub(14,14)=="-"
        and id:sub(19,19)=="-" and id:sub(24,24)=="-" and #id:gsub("-","")==32
        and id:gsub("-",""):match("^%x+$")~=nil
end
local function copy(value)
    if type(value)~="table" then return value end
    local out={}; for k,v in pairs(value) do out[k]=copy(v) end; return out
end
local function world()
    local w=getWorld and getWorld(); local c=getCore and getCore()
    return w and c and tostring(c:getGameMode()).."/"..tostring(w:getWorld()) or nil
end
local function dist(ax,ay,bx,by) return math.sqrt((ax-bx)^2+(ay-by)^2) end
local function tileId(x,y,z) return "tile:"..tostring(math.floor(x))..":"..tostring(math.floor(y))..":"..tostring(math.floor(z)) end
local function yes(value) return type(value)=="table" and value.known==true and value.value==true end
local function character(uuid)
    if not uuidValid(uuid) then return nil end
    local c=ArayHuman.getNpcByUuid and ArayHuman.getNpcByUuid(uuid)
    local md=c and c:getModData()
    if not md or md.ARAY_Uuid~=uuid or not md.ARAY_IsNPC or c:isDead() then return nil end
    local cell=getCell and getCell(); local square=c:getCurrentSquare()
    if not square or not cell or cell:getGridSquare(math.floor(c:getX()),math.floor(c:getY()),math.floor(c:getZ()))~=square then return nil end
    return c
end
local function player()
    local c=ArayHuman.getLocalPlayer and ArayHuman.getLocalPlayer()
    if not c or c:isDead() or (c:getModData() or {}).ARAY_IsNPC then return nil end
    return c
end
local function active(r) return r and not terminalStates[r.state] end
local function finish(r,state,result)
    if states[r.uuid]~=r or not active(r) then return end
    r.state,r.result,r.endedAt=state,result,now()
    if ArayHuman.Inventory then ArayHuman.Inventory.cancel(r.uuid,result) end
    if ArayHuman.Physical then ArayHuman.Physical.cancel(r.uuid,result) end
    ArayHuman.Walking.cancel(r.uuid,result,true)
    local w=ArayHuman.Walking.getState(r.uuid)
    local physical=r.physicalAction and ArayHuman.Physical.getState(r.uuid)
    if physical then r.observations=physical.observations end
    if w and w.id==r.walkId then r.observations=w.observations
    elseif r.localMotion and r.observations and not r.observations.ended_at_ms then
        local c=character(r.uuid)
        ArayHuman.Locomotion.endMetrics(r.observations,c,r.uuid,c~=nil and world()==r.world_id)
    end
    if r.localMotion then ArayHuman.Locomotion.recordResult(r) end
    if r.localSurvival then
        diagnostic(r.uuid,"escape_result","action="..r.actionId.." state="..state.." result="..tostring(result))
        local ep=episodes[r.uuid]
        if ep then
            ep.nextAttemptAt=now()+E.survivalConfig.cooldownMs
            if state~="COMPLETED" and r.destination then ep.excluded[r.destination.target_id]=true end
        end
    end
end
local function checkWorld()
    local current=world()
    if current~=worldSeen then
        for _,r in pairs(states) do finish(r,"CANCELLED","world_changed") end
        worldSeen=current; session=nil; sequences={}; seen={}; manual={}; cutoff={}; lastMonitor=0
        if ArayHuman.Locomotion then ArayHuman.Locomotion.clearResults() end
        motionSeen={}; episodes={}; safetyRoster={}; safetyCursor=1; lastSafety=nil; lastRoster=nil
    end
    return current
end
local function fresh(uuid,force)
    local p=ArayHuman.Perception
    if not p then return nil end
    local s=not force and p.getSnapshot(uuid) or nil
    if not s or not finite(s.captured_at_ms) or now()-s.captured_at_ms>E.config.snapshotMaxAgeMs then s=p.updateSnapshot(uuid) end
    if type(s)~="table" or s.uuid~=uuid or s.world_id~=worldSeen or s.active~=true
        or not yes(s.alive) or not finite(s.captured_at_ms) or s.captured_at_ms>now()
        or now()-s.captured_at_ms>E.config.snapshotMaxAgeMs then return nil end
    return s
end
local function tileMap(s)
    local map={}
    for _,t in ipairs(s.tiles or {}) do
        if integer(t.x) and integer(t.y) and integer(t.z) and yes(t.solid_floor)
            and yes(t.free) and yes(t.traversable_candidate) then map[tileId(t.x,t.y,t.z)]=t end
    end
    return map
end
local function resolveTarget(c,s,id,emergency)
    if type(id)~="string" then return nil,"target_id" end
    local t=tileMap(s)[id]
    if not t then return nil,"destination_not_in_snapshot" end
    local maxDistance=emergency and E.config.emergencyDistance or E.config.maxMoveDistance
    if t.z~=math.floor(c:getZ()) then return nil,"different_floor" end
    if dist(c:getX(),c:getY(),t.x+.5,t.y+.5)>maxDistance then return nil,"destination_too_far" end
    local sq=getCell():getGridSquare(t.x,t.y,t.z)
    if not sq or not ArayHuman.squareFree(sq,c) then return nil,"destination_blocked" end
    return sq
end
local function localThreats(c,s)
    if not s or (s.scan and (s.scan.entities_truncated or s.scan.entity_api_unknown)) then return nil end
    local threats, seenThreats, examined={}, {}, 0
    for _,z in ipairs(s.nearby_zombies or {}) do
        local p=z.position
        if p and p.known and finite(p.x) and finite(p.y) and finite(p.z) and math.floor(p.z)==math.floor(c:getZ()) then
            local sq=getCell():getGridSquare(math.floor(p.x),math.floor(p.y),math.floor(p.z))
            local movers=sq and sq:getMovingObjects()
            if movers then
                for i=0,movers:size()-1 do
                    examined=examined+1
                    if examined>128 then return nil end
                    local obj=movers:get(i)
                    if obj and not seenThreats[obj] and instanceof(obj,"IsoZombie") and not obj:isDead() then
                        seenThreats[obj]=true
                        threats[#threats+1]={x=obj:getX(),y=obj:getY(),z=obj:getZ(),square=sq}
                    end
                end
            end
        end
    end
    return threats
end
local function nearest(x,y,threats)
    local best=math.huge
    for _,t in ipairs(threats) do best=math.min(best,dist(x,y,t.x,t.y)) end
    return best
end
local function danger(c,threats)
    if not threats then return nil end
    for _,t in ipairs(threats) do
        if dist(c:getX(),c:getY(),t.x,t.y)<=E.config.threatDistance then
            local ok,blocked=pcall(function() return c:getCurrentSquare():isBlockedTo(t.square) end)
            if ok and blocked==false then return true end
        end
    end
    return false
end

function E.beginSession(id,startedAt)
    if not checkWorld() or type(id)~="string" or #id<1 or #id>128 or not id:match("^[%w._-]+$")
        or not integer(startedAt) or startedAt>now() then return false,"session_invalid" end
    if session then
        if session.id==id and session.startedAt==startedAt then return true end
        if startedAt<=session.startedAt then return false,"stale_session" end
    end
    for _,r in pairs(states) do if not r.localSurvival and not r.localMotion then finish(r,"CANCELLED","session_changed") end end
    session={id=id,startedAt=startedAt}; sequences={}; seen={}
    return true
end
-- Read-only priority gate for explicit policy adapters (never releases manual control).
function E.getControlState(uuid)
    checkWorld()
    local ep=episodes[uuid]
    local confirmed=ep and ep.immediate==true and ep.observedAt and now()>=ep.observedAt
        and now()-ep.observedAt<=E.survivalConfig.intervalMs*2
    return {manual_priority=manual[uuid]==true,
        emergency_priority=(active(states[uuid]) and states[uuid].localSurvival==true or confirmed)==true,
        threat_captured_at_ms=ep and ep.observedAt}
end
function E.getState(uuid)
    checkWorld()
    local r=states[uuid]; if not r then return nil end
    local out={}
    for _,k in ipairs({"uuid","goal","action","actionId","generation","destination","state","startedAt",
        "timeoutMs","result","endedAt","world_id","session_id","sequence","emergency","justification","permissionMode",
        "localSurvival","currentLeg","routeIndex","motion","transition","localMotion","requestActionId","movement_mode","observations","walkId","object_id"}) do out[k]=copy(r[k]) end
    local w=ArayHuman.Walking.getState(uuid)
    if w and w.id==r.walkId then out.observations=copy(w.observations) end
    if active(r) and r.physicalAction then
        local physical=ArayHuman.Physical.getState(uuid)
        if physical then out.observations=copy(physical.observations) end
    end
    out.authorization=copy(r.authorized)
    if ArayHuman.Survival then out.conditions=ArayHuman.Survival.getSnapshot(uuid) end
    return out
end
function E.cancel(uuid,reason)
    local r=states[uuid]
    local parentCancelled=ArayHuman.Navigation and ArayHuman.Navigation.onExecutorCancel(uuid,reason) or false
    if not active(r) then return parentCancelled end
    finish(r,"CANCELLED",reason or "cancelled")
    return true
end
function E.manualCommand(uuid)
    if not uuid then
        local c=ArayHuman.getNpc and ArayHuman.getNpc()
        uuid=c and c:getModData().ARAY_Uuid
    end
    if not uuid then return false end
    checkWorld(); cutoff[uuid]=now(); manual[uuid]=true
    if ArayHuman.Navigation then ArayHuman.Navigation.onManualCommand(uuid) end
    E.cancel(uuid,"manual_command")
    return true
end
function E.releaseManual(uuid)
    if ArayHuman.clearOrder then ArayHuman.clearOrder(uuid) end
    manual[uuid]=nil
end
local function makeState(uuid,action,goal,expires,localSurvival,localMotion)
    E.cancel(uuid,"replaced")
    generations[uuid]=(generations[uuid] or 0)+1; serial=serial+1
    local r={uuid=uuid,goal=goal or action,action=action,actionId=uuid..":"..tostring(serial),
        generation=generations[uuid],state="VALIDATING",startedAt=now(),timeoutMs=E.config.timeoutMs,
        world_id=worldSeen,session_id=localSurvival and "local-survival" or localMotion and "local-locomotion" or session.id,expiresAt=expires,
        localSurvival=localSurvival,localMotion=localMotion}
    states[uuid]=r
    return r
end
local function walk(r,s,id)
    local c=character(r.uuid)
    if not c then finish(r,"FAILED","instance_unavailable"); return false,"instance_unavailable" end
    local sq,reason=resolveTarget(c,s,id,r.emergency)
    if not sq then finish(r,"FAILED",reason); return false,reason end
    local destination={target_id=id,x=sq:getX(),y=sq:getY(),z=sq:getZ()}
    if r.localSurvival then r.currentLeg=destination else r.destination=destination end
    local p=player()
    if not p and not r.localSurvival then finish(r,"FAILED","player_unavailable"); return false,"player_unavailable" end
    local outside=p and dist(p:getX(),p:getY(),sq:getX()+.5,sq:getY()+.5)>E.config.playerLimit or false
    if outside and not r.emergency and not r.authorized then
        if E.config.permissionMode~="ASK" and E.config.permissionMode~="NOTIFY" then
            finish(r,"FAILED","permission_mode_invalid"); return false,"permission_mode_invalid"
        end
        r.permissionMode=E.config.permissionMode
        r.state,r.result="WAITING_PERMISSION","permission_required"
        return false,"permission_required"
    end
    r.state,r.result="RUNNING",nil
    local generation=r.generation
    local ok,walkId=ArayHuman.walkTo(sq,"executor",r.uuid,{
        movement_mode=r.movement_mode,observations=r.localMotion and r.observations or nil,
        timeoutMs=r.localSurvival and math.max(1,r.expiresAt-now()) or (r.emergency and E.config.emergencyDurationMs or r.timeoutMs),
        noProgressMs=r.localSurvival and math.min(1500,E.config.noProgressMs) or E.config.noProgressMs,
        onResult=function(result)
            if states[r.uuid]~=r or r.generation~=generation or r.state~="RUNNING" then return end
            if result=="sucesso" then
                if r.localSurvival and r.routeIndex<#r.route then
                    r.routeIndex=r.routeIndex+1; r.state="ESCAPING_STEP"
                    diagnostic(r.uuid,"waypoint_reached","action="..r.actionId.." next="..r.routeIndex)
                elseif r.localSurvival then finish(r,"COMPLETED","escape_target_reached")
                elseif r.action=="FOLLOW_PLAYER" then r.state="FOLLOWING"; r.nextFollow=now()+E.config.followMs
                else finish(r,"COMPLETED","success") end
            elseif result=="npc_dead" or result=="world_changed" or result=="instance_unavailable" or result=="cancelado" or result=="destination_blocked" then
                finish(r,"CANCELLED",result)
            else finish(r,"FAILED",result) end
        end })
    if not ok then finish(r,"FAILED",walkId); return false,walkId end
    r.walkId=walkId
    return true,r.actionId
end
local function follow(r,s)
    local c,p=character(r.uuid),player()
    if not c or not p then finish(r,"FAILED","player_unavailable"); return false,"player_unavailable" end
    if math.floor(c:getZ())~=math.floor(p:getZ()) then finish(r,"FAILED","different_floor"); return false,"different_floor" end
    if dist(c:getX(),c:getY(),p:getX(),p:getY())<=E.config.followDistance then
        r.state="FOLLOWING"; r.nextFollow=now()+E.config.followMs
        return true,r.actionId
    end
    local best,bestDistance=nil,nil
    for id,t in pairs(tileMap(s)) do
        local d=dist(p:getX(),p:getY(),t.x+.5,t.y+.5)
        if d<=E.config.followDistance and d>=.8 and resolveTarget(c,s,id,false) then
            local cost=dist(c:getX(),c:getY(),t.x+.5,t.y+.5)
            if not bestDistance or cost<bestDistance then best,bestDistance=id,cost end
        end
    end
    if not best then finish(r,"FAILED","follow_destination_unavailable"); return false,"follow_destination_unavailable" end
    return walk(r,s,best)
end
function E.submit(response,goal)
    checkWorld()
    local seenCount=0
    for requestId,expires in pairs(seen) do
        if expires<=now() then seen[requestId]=nil else seenCount=seenCount+1 end
    end
    if seenCount>=1024 then return false,"registry_full" end
    if type(response)~="table" or response.kind~="decision_response" or response.ok~=true then return false,"invalid_response" end
    local id=response.npc_id
    if not character(id) then return false,"instance_unavailable" end
    if ArayHuman.Physical and ArayHuman.Physical.busy(id) then return false,"physical_busy" end
    if not session or response.world_id~=worldSeen or response.session_id~=session.id
        or response.session_started_at_ms~=session.startedAt then return false,"world_or_session" end
    if not integer(response.sequence) or response.sequence<1 or response.sequence<=(sequences[id] or 0)
        or type(response.id)~="string" or #response.id>128 or not response.id:match("^[%w._-]+$") or seen[response.id] then return false,"stale_or_duplicate" end
    if not integer(response.issued_at_ms) or not integer(response.expires_at_ms)
        or response.issued_at_ms>now() or response.issued_at_ms<session.startedAt
        or response.expires_at_ms<=now() or response.expires_at_ms-response.issued_at_ms>30000 then return false,"expired" end
    if manual[id] or (cutoff[id] and response.issued_at_ms<=cutoff[id]) then return false,"manual_priority" end
    if response.emergency~=nil then return false,"model_emergency_forbidden" end
    local d=response.decision
    if type(d)~="table" or not allowed[d.action] or type(d.parameters)~="table"
        or type(d.reason)~="string" or not d.reason:match("%S") or #d.reason>240
        or not integer(d.priority) or d.priority<0 or d.priority>3 then return false,"decision_invalid" end
    for k in pairs(d) do if k~="action" and k~="parameters" and k~="reason" and k~="priority" then return false,"decision_invalid" end end
    if goal~=nil and (type(goal)~="string" or #goal>2000) then return false,"goal_invalid" end
    local target=d.parameters.candidate_id or d.parameters.target_id
    local count=0; for _ in pairs(d.parameters) do count=count+1 end
    if d.action=="MOVE_TO" or d.action=="WANDER_NEARBY" then
        if count~=1 or type(target)~="string" then return false,"target_id" end
    elseif d.action=="SAY" then
        if count~=1 or type(d.parameters.text)~="string" or not d.parameters.text:match("%S") or #d.parameters.text>300 then return false,"say_text" end
    elseif count~=0 then return false,"parameters" end
    local s=fresh(id,true)
    if not s then return false,"perception_unavailable" end
    local c=character(id)
    if target then local sq,reason=resolveTarget(c,s,target,false); if not sq then return false,reason end end
    if ArayHuman.Navigation then ArayHuman.Navigation.onLocomotionRequest(id) end
    sequences[id]=response.sequence; seen[response.id]=response.expires_at_ms
    local r=makeState(id,d.action,goal,response.expires_at_ms); r.sequence=response.sequence
    if d.action=="IDLE" or d.action=="STOP" then finish(r,"COMPLETED","success"); return true,r.actionId end
    if d.action=="SAY" then
        if not ArayHuman.SpeechBubble or not ArayHuman.SpeechBubble.show then finish(r,"FAILED","speech_unavailable"); return false,"speech_unavailable" end
        local ok=pcall(ArayHuman.SpeechBubble.show,c,d.parameters.text,false)
        if not ok then finish(r,"FAILED","speech_failed"); return false,"speech_failed" end
        finish(r,"COMPLETED","success"); return true,r.actionId
    end
    if d.action=="LOOK_AT_PLAYER" then
        local p=player()
        if not p or not c.faceLocation then finish(r,"FAILED","player_unavailable"); return false,"player_unavailable" end
        local ok=pcall(function() c:faceLocation(p:getX(),p:getY()) end)
        if not ok then finish(r,"FAILED","look_failed"); return false,"look_failed" end
        finish(r,"COMPLETED","success"); return true,r.actionId
    end
    if danger(c,localThreats(c,s))==true then finish(r,"FAILED","threat_nearby"); return false,"threat_nearby" end
    if d.action=="FOLLOW_PLAYER" then return follow(r,s) end
    return walk(r,s,target)
end

local function authorize(uuid,actionId,mode,evidence)
    checkWorld()
    local r=states[uuid]
    if not r or r.actionId~=actionId or r.state~="WAITING_PERMISSION" or r.permissionMode~=mode then return false,"permission_mismatch" end
    if (not r.localMotion and (not session or session.id~=r.session_id)) or r.world_id~=worldSeen or r.expiresAt<=now() then finish(r,"FAILED","expired"); return false,"expired" end
    if type(evidence)~="string" or not evidence:match("%S") or #evidence>240 then return false,"evidence_required" end
    if manual[uuid] and not r.manualOrigin then return false,"manual_priority" end
    local s=fresh(uuid,true)
    if not s then finish(r,"FAILED","perception_unavailable"); return false,"perception_unavailable" end
    local c=character(uuid)
    if not c or danger(c,localThreats(c,s))==true then finish(r,"FAILED","threat_nearby"); return false,"threat_nearby" end
    r.authorized={mode=mode,evidence=evidence,at=now()}
    print("[ARAY] executor permission "..mode.." uuid="..uuid.." action="..actionId.." evidence="..evidence)
    return walk(r,s,r.destination.target_id)
end
-- Trusted local hooks for a future approval UI; decision parameters cannot invoke them.
function E.approve(uuid,actionId) return authorize(uuid,actionId,"ASK","approved_by_player") end
function E.recordNotice(uuid,actionId,text) return authorize(uuid,actionId,"NOTIFY",text) end

-- Trusted local entry point for future adapters; model responses still use submit().
function E.requestLocomotion(request)
    checkWorld()
    if type(request)~="table" then return false,"invalid_request" end
    local fields={uuid=true,world_id=true,action=true,movement_mode=true,action_id=true,target_id=true,
        destination=true,source=true,expires_at_ms=true,text=true}
    for key in pairs(request) do if not fields[key] then return false,"invalid_request_field" end end
    local id=request.uuid; local c=character(id)
    if not c then return false,"instance_unavailable" end
    if request.world_id~=worldSeen then return false,"world_mismatch" end
    local action=request.action
    if action=="STAIRS" then
        diagnostic(id,"UNSUPPORTED","reason=UNSUPPORTED_STAIRS_NPC")
        return false,"UNSUPPORTED_STAIRS_NPC"
    end
    local interaction=ArayHuman.Physical.actions[action]==true
    local inventoryAction=ArayHuman.Inventory and ArayHuman.Inventory.actions[action]==true
    local unsupported=ArayHuman.Physical.unsupportedReason(action)
    if action~="MOVE_TO" and action~="STOP" and action~="FACE_TARGET" and action~="FOLLOW_PLAYER" and action~="SAY" and not interaction and not inventoryAction and not unsupported then return false,"action_invalid" end
    if action=="SAY" then
        if type(request.text)~="string" or not request.text:match("%S") or #request.text>300 then return false,"say_text" end
        if not ArayHuman.SpeechBubble or not ArayHuman.SpeechBubble.show then return false,"speech_unavailable" end
    elseif request.text~=nil then return false,"parameters_invalid" end
    local mode=request.movement_mode or "WALK"
    if action=="MOVE_TO" and not ArayHuman.Locomotion.modes[mode] then return false,"movement_mode_invalid" end
    if action~="MOVE_TO" and request.movement_mode~=nil then return false,"movement_mode_invalid" end
    local source=request.source or "policy"
    if source~="manual" and source~="policy" then return false,"source_invalid" end
    if source=="policy" and manual[id] then return false,"manual_priority" end
    if source=="policy" and active(states[id]) and states[id].localSurvival then return false,"emergency_priority" end
    local rid=request.action_id
    if type(rid)~="string" or #rid<1 or #rid>128 or not rid:match("^[%w._:-]+$") then return false,"action_id_invalid" end
    local count=0
    for key,expiry in pairs(motionSeen) do if expiry<=now() then motionSeen[key]=nil else count=count+1 end end
    local replayKey=id..":"..rid
    if motionSeen[replayKey] then return false,"duplicate_action_id" end
    if count>=1024 then return false,"registry_full" end
    local expires=request.expires_at_ms or (now()+E.config.timeoutMs)
    if not integer(expires) or expires<=now() or expires-now()>30000 then return false,"expired" end
    -- Reject audited unavailable capabilities before cancelling any owned action.
    -- In particular a manual PUSH_ZOMBIE request must not suppress emergency escape.
    if unsupported then
        diagnostic(id,"UNSUPPORTED","action="..action.." reason="..unsupported.." executed=false")
        return false,unsupported
    end
    local physical=ArayHuman.Physical and ArayHuman.Physical.busy(id)
    if physical and action~="STOP" then return false,"physical_busy" end
    local target=request.target_id
    if request.destination then
        local token=request.destination
        if type(token)~="table" or target~=nil or token.uuid~=id or token.world_id~=worldSeen
            or not integer(token.validated_at_ms) or token.validated_at_ms>now()
            or now()-token.validated_at_ms>E.config.snapshotMaxAgeMs then return false,"destination_token_invalid" end
        target=token.target_id
    end
    local snapshot,destination,px,py,physicalStep,inventoryTarget
    if action=="STOP" or action=="SAY" or action=="FOLLOW_PLAYER" then
        if target~=nil or request.destination~=nil then return false,"parameters_invalid" end
        if action=="FOLLOW_PLAYER" then
            snapshot=fresh(id,true)
            if not snapshot or not player() then return false,"player_unavailable" end
        end
    else
        snapshot=fresh(id,true)
        if not snapshot then return false,"perception_unavailable" end
        if inventoryAction then
            local why
            inventoryTarget,why=ArayHuman.Inventory.resolveCandidate(id,action,target)
            if not inventoryTarget then return false,why end
            destination={target_id=target}
        elseif interaction then
            local why
            physicalStep,why=ArayHuman.Physical.resolveCandidate(id,action,target)
            if not physicalStep then return false,why end
            destination={target_id=target,x=physicalStep.x,y=physicalStep.y,z=physicalStep.z}
            if action=="CLIMB_WINDOW" or action=="CLIMB_FENCE" then
                local p=player()
                if not p then return false,"player_unavailable" end
                if dist(p:getX(),p:getY(),physicalStep.x+.5,physicalStep.y+.5)>E.config.playerLimit then return false,"permission_required" end
            end
        elseif action=="FACE_TARGET" and target=="PLAYER" then
            local p=player()
            if not p or math.floor(p:getZ())~=math.floor(c:getZ()) then return false,"player_unavailable" end
            px,py=p:getX(),p:getY()
            destination={target_id="PLAYER",x=px,y=py,z=p:getZ()}
        else
            local sq,why=resolveTarget(c,snapshot,target,false)
            if not sq then return false,why end
            destination={target_id=target,x=sq:getX(),y=sq:getY(),z=sq:getZ()}
            px,py=sq:getX()+.5,sq:getY()+.5
        end
    end
    if source=="policy" and action~="STOP" then
        local obs=ArayHuman.Perception.observeThreats(id)
        if obs.active and obs.immediate then return false,"emergency_priority" end
    end
    if action=="MOVE_TO" then
        local flags,why=ArayHuman.Locomotion.captureFlags(c)
        if not flags then return false,why end
        if not ArayHuman.Locomotion.safeNativeState(c) then return false,"native_state_unsafe" end
    elseif action=="FACE_TARGET" then
        if not c.faceLocationF or not c.isFacingLocation or not c.shouldBeTurning then return false,"UNSUPPORTED_facing" end
        if not ArayHuman.Locomotion.safeNativeState(c) then return false,"native_state_unsafe" end
    end
    if ArayHuman.Navigation then ArayHuman.Navigation.onLocomotionRequest(id) end
    if source=="manual" then E.manualCommand(id) else E.cancel(id,"replaced") end
    if ArayHuman.clearOrder then ArayHuman.clearOrder(id) end
    ArayHuman.Walking.cancel(id,"replaced",true)
    local r=makeState(id,action,"locomotion",expires,false,true)
    r.requestActionId=rid; r.manualOrigin=source=="manual"; r.movement_mode=action=="MOVE_TO" and mode or nil
    r.destination=destination; motionSeen[replayKey]=expires
    r.observations=ArayHuman.Locomotion.beginMetrics(c,id)
    if action=="SAY" then
        local ok=pcall(ArayHuman.SpeechBubble.show,c,request.text,false)
        finish(r,ok and "COMPLETED" or "FAILED",ok and "speech_dispatched" or "speech_failed")
        return ok,ok and r.actionId or "speech_failed"
    end
    if action=="FOLLOW_PLAYER" then return follow(r,snapshot) end
    if inventoryAction then
        r.state="INVENTORY"; r.inventoryAction=true
        local accepted,why=ArayHuman.Inventory.start(id,inventoryTarget,r.generation,function(result,g,metrics)
            if states[id]~=r or r.generation~=g or r.state~="INVENTORY" then return end
            r.observations.inventory=copy(metrics)
            finish(r,result=="success" and "COMPLETED" or "FAILED",result)
        end,rid)
        if not accepted then finish(r,"FAILED",why); return false,why end
        return true,r.actionId
    end
    if action=="MOVE_TO" then return walk(r,snapshot,target) end
    if interaction then
        r.state="INTERACTING"; r.physicalAction=true; r.transition=action; r.object_id=target
        local generation=r.generation
        local obs=ArayHuman.Perception.observeThreats(id)
        local accepted,why=ArayHuman.Physical.start(id,c,physicalStep,obs,generation,function(result,g,metrics)
            if states[id]~=r or r.generation~=g or r.state~="INTERACTING" then return end
            if metrics then r.observations=metrics end
            finish(r,result=="success" and "COMPLETED" or "FAILED",result)
        end,{purpose="navigation",action_id=rid})
        if not accepted then finish(r,"FAILED",why); return false,why end
        return true,r.actionId
    end
    if action=="STOP" then
        if physical then
            ArayHuman.Physical.cancel(id,"locomotion_stop"); r.state="WAITING_PHYSICAL_STOP"
            return true,r.actionId
        end
        local flags,why=ArayHuman.Locomotion.applyMode(c,"STOP")
        if not flags then finish(r,"FAILED",why); return false,why end
        finish(r,"COMPLETED","stopped"); return true,r.actionId
    end
    local q=ISTimedActionQueue.queues[c]
    if q and q.queue and #q.queue>0 then finish(r,"FAILED","foreign_action_busy"); return false,"foreign_action_busy" end
    r.faceX,r.faceY=px,py
    local ok=pcall(function() c:faceLocationF(px,py) end)
    if not ok then finish(r,"FAILED","facing_failed"); return false,"facing_failed" end
    r.state="TURNING"
    return true,r.actionId
end

local function episode(uuid)
    local ep=episodes[uuid]
    if not ep then ep={attempts=0,nextAttemptAt=0,excluded={}}; episodes[uuid]=ep end
    return ep
end
local function routeSnapshot(r)
    local tiles={}
    for _,t in ipairs(r.route) do
        tiles[#tiles+1]={x=t.x,y=t.y,z=t.z,solid_floor={known=true,value=true},
            free={known=true,value=true},traversable_candidate={known=true,value=true}}
    end
    return {tiles=tiles}
end
local function nextLeg(r,observation)
    local c=character(r.uuid); local t=r.route[r.routeIndex]
    if not c or not t then finish(r,"FAILED","route_unavailable"); return false,"route_unavailable" end
    if t.kind and t.kind~="WALK" then
        r.state="INTERACTING"; r.transition=t.kind
        local accepted,result=ArayHuman.Physical.start(r.uuid,c,t,observation,r.generation,function(outcome,generation)
            if states[r.uuid]~=r or r.generation~=generation or r.state~="INTERACTING" then return end
            if outcome~="success" then finish(r,"FAILED",outcome); return end
            r.routeIndex=r.routeIndex+1; r.transition=nil
            if r.routeIndex>#r.route then finish(r,"COMPLETED","escape_target_reached")
            else r.state="ESCAPING_STEP" end
        end)
        if not accepted then finish(r,"FAILED",result) end
        return accepted,result
    end
    local ok,reason,detail=ArayHuman.EscapePlanner.validateLeg(c,t,observation)
    if not ok then diagnostic(r.uuid,reason,detail); finish(r,"FAILED",reason); return false,reason end
    diagnostic(r.uuid,"pathfinding_request","action="..r.actionId.." leg="..r.routeIndex.." target="..t.target_id)
    local accepted,result=walk(r,routeSnapshot(r),t.target_id)
    if accepted then diagnostic(r.uuid,"pathfinding_started","action="..r.actionId.." walk="..tostring(r.walkId)) end
    return accepted,result
end
local function startEscape(uuid,observation)
    local c=character(uuid)
    if not c or not observation or not observation.active or observation.uuid~=uuid
        or observation.world_id~=worldSeen or not observation.immediate then return false,"emergency_not_confirmed" end
    local ep=episode(uuid)
    if ArayHuman.Inventory and ArayHuman.Inventory.busy(uuid) then
        E.cancel(uuid,"local_threat"); ArayHuman.Inventory.cancel(uuid,"local_threat")
        return false,"inventory_cancel_pending"
    end
    if ArayHuman.Physical and ArayHuman.Physical.busy(uuid) then return false,"physical_busy" end
    if active(states[uuid]) and states[uuid].localSurvival then return false,"escape_in_progress" end
    local current=ArayHuman.Walking.getState(uuid)
    local order=ArayHuman.getOrderName and ArayHuman.getOrderName(uuid)
    if (current and not current.done) or active(states[uuid]) or (order and order~="Idle") then
        diagnostic(uuid,"action_interrupted","order="..tostring(order)
            .." walk="..tostring(current and current.id).." source="..tostring(current and current.source))
    end
    -- Stop unsafe ordinary movement even when planning is on cooldown or exhausted.
    E.cancel(uuid,"local_threat")
    if ArayHuman.clearOrder then ArayHuman.clearOrder(uuid) end
    ArayHuman.Walking.cancel(uuid,"local_threat",true)
    if ep.attempts>=E.survivalConfig.maxAttempts and (ep.recoveries or 0)<E.survivalConfig.maxRecoveries
        and now()>=(ep.recoveryAt or math.huge) then
        ep.recoveries=(ep.recoveries or 0)+1; ep.attempts=0; ep.exhaustedLogged=nil
        diagnostic(uuid,"controlled_recovery","burst="..ep.recoveries.." from="..c:getX()..","..c:getY())
    end
    if ep.attempts>=E.survivalConfig.maxAttempts then
        ep.recoveryAt=ep.recoveryAt or (now()+E.survivalConfig.recoveryMs)
        if not ep.exhaustedLogged then diagnostic(uuid,"attempts_exhausted","attempts="..ep.attempts); ep.exhaustedLogged=true end
        return false,"escape_attempts_exhausted"
    end
    if now()<ep.nextAttemptAt then return false,"escape_cooldown" end
    ep.attempts=ep.attempts+1; if ep.attempts==E.survivalConfig.maxAttempts then ep.recoveryAt=now()+E.survivalConfig.recoveryMs end; ep.nextAttemptAt=now()+E.survivalConfig.cooldownMs
    -- Safety preempts a manual order ONLY after fresh, locally confirmed danger.
    -- Keep its manual-priority latch; never silently resume the interrupted order.
    local cfg={emergencyDistance=E.config.emergencyDistance,safeThreatDistance=E.config.safeThreatDistance,
        maxRouteNodes=E.survivalConfig.maxRouteNodes}
    local plan,reason=ArayHuman.EscapePlanner.plan(c,observation,cfg,ep.excluded)
    if not plan and ArayHuman.Physical then
        cfg.allowInteractions=true
        plan,reason=ArayHuman.EscapePlanner.plan(c,observation,cfg,ep.excluded)
    end
    if not plan then
        if ArayHuman.Physical then
            local _,shoveReason=ArayHuman.Physical.defensiveShove(uuid,c,observation)
            diagnostic(uuid,"defensive_shove_unavailable",shoveReason)
        end
        ep.lastFailure=reason
        diagnostic(uuid,"escape_unavailable","attempt="..ep.attempts.." reason="..tostring(reason))
        return false,reason
    end
    local interactions=0
    for _,step in ipairs(plan.route) do if step.kind and step.kind~="WALK" then interactions=interactions+1 end end
    local duration=math.min(12000,E.config.emergencyDurationMs+interactions*2500)
    local r=makeState(uuid,"MOVE_TO","local_survival",now()+duration,true)
    r.emergency=true; r.justification="fresh_local_live_zombie_"..observation.level
    r.route=plan.route; r.routeIndex=1; r.corridor=plan.corridor
    r.destination=plan.destination; r.timeoutMs=duration
    ep.lastTarget=r.destination.target_id
    -- Do not retry the same destination during this danger episode, even after success.
    ep.excluded[ep.lastTarget]=true
    diagnostic(uuid,"escape_destination","action="..r.actionId.." target="..ep.lastTarget
        .." route_nodes="..#r.route.." distance="..string.format("%.2f",plan.distance).." attempt="..ep.attempts)
    return nextLeg(r,observation)
end
function E.escape(uuid)
    checkWorld()
    local p=ArayHuman.Perception
    if not p or not p.scanThreats then return false,"threat_api_unavailable" end
    return startEscape(uuid,p.scanThreats(uuid))
end
function E.getSurvivalState(uuid)
    checkWorld()
    return copy(episodes[uuid])
end
local function monitorOne(uuid)
    local ep=episode(uuid); local c=character(uuid)
    if not c then
        if active(states[uuid]) and states[uuid].localSurvival then finish(states[uuid],"CANCELLED","npc_dead_or_unloaded") end
        return
    end
    local p=ArayHuman.Perception
    if not p or not p.scanThreats then return end
    local observation=p.scanThreats(uuid)
    -- Observation only: the local threat policy and all escape budgets stay unchanged.
    if ArayHuman.Survival then ep.conditions=ArayHuman.Survival.getSnapshot(uuid) end
    local d=observation.nearest.known and string.format("%.2f",observation.nearest.value) or "unknown"
    if not ep.registered then diagnostic(uuid,"monitor_active","interval="..E.survivalConfig.intervalMs); ep.registered=true end
    if ep.level~=observation.level or ep.immediate~=observation.immediate then
        diagnostic(uuid,"threat_detected","level="..observation.level.." immediate="..tostring(observation.immediate)
            .." distance="..d.." health_drop="..tostring(observation.health_drop)
            .." evidence="..tostring(observation.evidence).." immediate_distance="..tostring(observation.immediate_distance)
            .." entities="..observation.scan.entities.." truncated="..tostring(observation.scan.truncated))
    end
    ep.level,ep.immediate,ep.distance=observation.level,observation.immediate,observation.nearest.value
    ep.observedAt=now()
    if observation.scan.connection_unknown and not observation.immediate then
        if not ep.connectionUnknown then diagnostic(uuid,"threat_unconfirmed","reason=collision_api_or_connection_budget distance="..d) end
        ep.connectionUnknown=true
    else ep.connectionUnknown=nil end
    local r=states[uuid]
    local clear=observation.active and not observation.immediate and observation.scan.complete
        and (#observation.threats==0 or (observation.nearest.known and observation.nearest.value>=E.survivalConfig.releaseDistance))
    if clear then
        ep.safeSince=ep.safeSince or now()
        if now()-ep.safeSince>=E.survivalConfig.clearAfterMs then ep.attempts=0; ep.recoveries=0; ep.recoveryAt=nil; ep.excluded={}; ep.exhaustedLogged=nil end
    else ep.safeSince=nil end
    if active(r) and r.localSurvival then
        if r.state=="INTERACTING" then
            if now()>=r.expiresAt then finish(r,"FAILED","timeout") end
            ArayHuman.Physical.update(uuid,observation)
            return
        end
        if not observation.active then finish(r,"CANCELLED","npc_dead_or_unloaded")
        elseif now()>=r.expiresAt then finish(r,"FAILED","timeout")
        elseif observation.scan.truncated or observation.scan.unknown then finish(r,"FAILED","threat_scan_incomplete")
        elseif clear then finish(r,"COMPLETED","danger_reduced")
        elseif r.state=="RUNNING" and r.currentLeg then
            r.motion=ArayHuman.Walking.getState(uuid)
            if now()>=(r.nextMotionLog or 0) then
                r.nextMotionLog=now()+1000
                local m=r.motion or {}
                diagnostic(uuid,"escape_progress","x="..c:getX().." y="..c:getY().." speed="..tostring(m.speed).." travelled="..tostring(m.travelled).." remaining="..tostring(m.remaining).." progress_age_ms="..tostring(m.progressAgeMs).." native="..tostring(m.nativeResult).." queued="..tostring(m.queued))
            end
            local ok,reason,detail=ArayHuman.EscapePlanner.validateLeg(c,r.currentLeg,observation)
            if not ok then diagnostic(uuid,reason,"position="..c:getX()..","..c:getY().." "..tostring(detail)); finish(r,"CANCELLED",reason) end
        elseif r.state=="ESCAPING_STEP" then nextLeg(r,observation)
        end
    elseif observation.immediate then startEscape(uuid,observation) end
end
local function survivalUpdate()
    if not worldSeen then return end
    if lastSafety and now()-lastSafety<E.survivalConfig.intervalMs then return end
    lastSafety=now()
    if not lastRoster or now()-lastRoster>=E.survivalConfig.rosterRefreshMs then
        local roster=ArayHuman.rosterSnapshot and ArayHuman.rosterSnapshot() or {}
        safetyRoster={}; local present={}
        for _,entry in ipairs(roster) do
            if uuidValid(entry.uuid) and not present[entry.uuid] then
                safetyRoster[#safetyRoster+1]=entry.uuid; present[entry.uuid]=true
            end
        end
        table.sort(safetyRoster)
        for uuid in pairs(episodes) do if not present[uuid] then episodes[uuid]=nil end end
        if safetyCursor>#safetyRoster then safetyCursor=1 end
        lastRoster=now()
    end
    local budget=math.max(1,math.min(4,E.survivalConfig.maxNPCsPerTick))
    for i=1,math.min(budget,#safetyRoster) do
        if safetyCursor>#safetyRoster then safetyCursor=1 end
        monitorOne(safetyRoster[safetyCursor]); safetyCursor=safetyCursor+1
    end
end

function E.update()
    checkWorld()
    if ArayHuman.Inventory then ArayHuman.Inventory.update() end
    if ArayHuman.Physical then ArayHuman.Physical.updateCancelled() end
    survivalUpdate()
    if now()-lastMonitor<E.config.monitorMs then return end
    lastMonitor=now()
    for uuid,r in pairs(states) do
        if active(r) and not r.localSurvival then
            local c=character(uuid)
            if not c then finish(r,"CANCELLED","npc_dead_or_unloaded")
            elseif not r.localMotion and (not session or r.session_id~=session.id) then finish(r,"CANCELLED","session_changed")
            elseif now()>=r.expiresAt then finish(r,"FAILED","expired")
            elseif now()-r.startedAt>=r.timeoutMs then finish(r,"FAILED","timeout")
            elseif r.state=="INVENTORY" then
                -- Inventory owns its native action and confirmation; the safety monitor may preempt it.
            elseif r.localMotion and r.physicalAction and r.state=="INTERACTING" then
                ArayHuman.Physical.update(uuid,ArayHuman.Perception.observeThreats(uuid))
            elseif r.localMotion and r.state=="WAITING_PHYSICAL_STOP" then
                if not ArayHuman.Physical.busy(uuid) then
                    local flags,why=ArayHuman.Locomotion.applyMode(c,"STOP")
                    finish(r,flags and "COMPLETED" or "FAILED",flags and "stopped" or why)
                end
            elseif r.localMotion and r.state=="TURNING" then
                ArayHuman.Locomotion.sampleMetrics(r.observations,c,false)
                local p=r.destination.target_id=="PLAYER" and player() or nil
                if r.destination.target_id=="PLAYER" and (not p or math.floor(p:getZ())~=math.floor(c:getZ())) then
                    finish(r,"FAILED","player_unavailable")
                elseif not ArayHuman.Locomotion.safeNativeState(c) then finish(r,"FAILED","native_state_unsafe")
                else
                    if p and dist(r.faceX,r.faceY,p:getX(),p:getY())>.1 then
                        r.faceX,r.faceY=p:getX(),p:getY()
                        local ok=pcall(function() c:faceLocationF(r.faceX,r.faceY) end)
                        if not ok then finish(r,"FAILED","facing_failed") end
                    end
                    if active(r) and c:isFacingLocation(r.faceX,r.faceY,.5) and not c:shouldBeTurning() then finish(r,"COMPLETED","faced_target") end
                end
            elseif r.state~="WAITING_PERMISSION" then
                local s=fresh(uuid,false)
                local threats=localThreats(c,s); local immediate=danger(c,threats)
                if not s or not threats then finish(r,"FAILED","perception_unavailable")
                elseif r.emergency and immediate~=true then finish(r,"COMPLETED","danger_reduced")
                elseif not r.emergency and immediate==true then finish(r,"CANCELLED","threat_nearby")
                elseif r.emergency and not r.corridor[tileId(c:getX(),c:getY(),c:getZ())] then finish(r,"CANCELLED","escape_corridor_deviation")
                elseif r.destination and not resolveTarget(c,s,r.destination.target_id,r.emergency)
                    and dist(c:getX(),c:getY(),r.destination.x+.5,r.destination.y+.5)>1 then finish(r,"CANCELLED","destination_blocked")
                elseif r.action=="FOLLOW_PLAYER" and r.state=="FOLLOWING" and now()>=(r.nextFollow or 0) then follow(r,s)
                end
            end
        end
    end
end
Events.OnTick.Add(E.update)

print("[ARAY-SURVIVAL] monitor_registered interval_ms="..E.survivalConfig.intervalMs.." npc_budget="..E.survivalConfig.maxNPCsPerTick)
