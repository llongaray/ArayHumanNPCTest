require "ArayHumanLocomotion"
require "ArayHumanInventory"
-- Native interactions for local escape and explicitly requested navigation. No input simulation, attack, damage or teleport.
ArayHuman = ArayHuman or {}
ArayHuman.Physical = {}
local F=ArayHuman.Physical
F.config={timeoutMs=7000,settleMs=250,shoveCooldownMs=2000}
local locks,shoves={},{}
local objectOwners={}
local candidates,candidateWorld,candidateSerial={},nil,0
local physicalResults={}
F.actions={OPEN_DOOR=true,CLOSE_DOOR=true,OPEN_WINDOW=true,CLIMB_WINDOW=true,CLIMB_FENCE=true}
local function now() return getTimestampMs() end
local function world()
    local core=getCore and getCore(); local w=getWorld and getWorld()
    return core and w and tostring(core:getGameMode())..'/'..tostring(w:getWorld()) or nil
end
local function call(o,k,...)
    local args={...}
    local ok,v=pcall(function() if o and o[k] then return o[k](o,unpack(args)) end end)
    if ok then return v end
end
local function method(o,k) local ok,v=pcall(function() return o and o[k] end); return ok and v~=nil end
local function log(id,event,reason) print('[ARAY-PHYSICAL] uuid='..tostring(id)..' event='..event..' '..tostring(reason or '')) end
local function square(x,y,z)
    local cell=getCell and getCell(); return cell and cell:getGridSquare(x,y,z) or nil
end
local function distance(x,y,px,py) return math.sqrt((x-px)^2+(y-py)^2) end
local function npc(c,id)
    local md=call(c,'getModData')
    return type(id)=='string' and #id==36 and id:match('^%x+%-%x+%-%x+%-%x+%-%x+$') and md and md.ARAY_IsNPC and md.ARAY_Uuid==id
        and call(c,'isNPC')==true and call(c,'isDead')==false
        and ArayHuman.getNpcByUuid(id)==c and c~=ArayHuman.getLocalPlayer()
end
-- Capability is an audited safety contract, not a method-presence feature toggle.
-- See FASE3C4B1_RECURSOS.md and FASE3C4B2_ZONA_SEGURANCA.md.
-- Never enable an attack just because NPCSetAttack exists.
function F.unsupportedReason(action)
    if action=='PUSH_ZOMBIE' or action=='DEFENSIVE_SHOVE' then return 'UNSUPPORTED_target_exclusive_native_shove' end
    if action=='CLIMB_STAIRS' then return 'UNSUPPORTED_STAIRS_VERTICAL_VALIDATION' end
    if action=='STAIRS' then return 'UNSUPPORTED_STAIRS_NPC' end -- existing callers
end
function F.inspectCapabilities(id)
    local c=ArayHuman.getNpcByUuid(id)
    if not npc(c,id) then return nil,'instance_unavailable' end
    local x,y,z=call(c,'getX'),call(c,'getY'),call(c,'getZ')
    local sq=call(c,'getCurrentSquare')
    if not world() or not sq or sq~=square(math.floor(x),math.floor(y),math.floor(z)) then return nil,'chunk_unavailable' end
    local function flag(k)
        local v=call(sq,k)
        if type(v)=='boolean' then return {known=true,value=v} end
        return {known=false}
    end
    return {uuid=id,world_id=world(),captured_at_ms=now(),
        PUSH_ZOMBIE={supported=false,reason=F.unsupportedReason('PUSH_ZOMBIE'),
            missing='exclusive_zombie_hit_filter_and_native_completion',
            safety_zone={target_max_distance=1.25,player_distance_must_exceed=2,
                collision_area={known=false,reason='native_melee_geometry_not_certified'},
                exclusion_during_animation={known=false,reason='no_verified_atomic_collision_veto'},
                selection_can_occur_at_collision=true,nonempty_hit_list_may_be_reused=true,
                native_collision_requires_local_player=true},
            api_present={NPCSetAttack=method(c,'NPCSetAttack'),setDoShove=method(c,'setDoShove'),
                NPCSetMelee=method(c,'NPCSetMelee'),
                setAuthorizeShoveStomp=method(c,'setAuthorizeShoveStomp'),pressedAttack=method(c,'pressedAttack')}},
        CLIMB_STAIRS={supported=false,reason=F.unsupportedReason('CLIMB_STAIRS'),
            missing='validated_vertical_candidates_route_and_cross_floor_threats',
            position={x=x,y=y,z=z},tile={x=math.floor(x),y=math.floor(y),z=math.floor(z)},
            has_stairs=flag('HasStairs'),has_stair_top=flag('HasStairTop'),has_stairs_below=flag('HasStairsBelow'),
            api_present={getPathFindBehavior2=method(c,'getPathFindBehavior2'),
                doStairs=method(c,'doStairs'),
                isSameStaircase=method(sq,'isSameStaircase'),isStairBlockedTo=method(sq,'isStairBlockedTo')}}}
end
local function free(sq,c)
    if not sq or call(sq,'TreatAsSolidFloor')~=true or call(sq,'isFree',false)~=true
        or not method(sq,'getBrokenGlass') then return false end
    local glassOK,glass=pcall(function() return sq:getBrokenGlass() end)
    if not glassOK or glass~=nil then return false end
    local list=call(sq,'getMovingObjects'); local count=call(list,'size')
    if type(count)~='number' or count>32 then return false end
    for i=0,count-1 do
        local obj=call(list,'get',i)
        if obj and obj~=c and (instanceof(obj,'IsoGameCharacter') or instanceof(obj,'IsoZombie')) then return false end
    end
    return true
end
local function direction(a,b)
    if not a or not b or a:getZ()~=b:getZ() then return nil end
    local dx,dy=b:getX()-a:getX(),b:getY()-a:getY()
    if math.abs(dx)+math.abs(dy)~=1 or not IsoDirections then return nil end
    return dx==1 and IsoDirections.E or dx==-1 and IsoDirections.W or dy==1 and IsoDirections.S or IsoDirections.N
end
local function onEdge(o,a,b)
    local s=call(o,'getSquare'); local n=call(o,'getNorth')
    if not s or type(n)~='boolean' then return false end
    local x,y,z=s:getX(),s:getY(),s:getZ()
    local ox,oy=x-(n and 0 or 1),y-(n and 1 or 0)
    return z==a:getZ() and ((a:getX()==x and a:getY()==y and b:getX()==ox and b:getY()==oy)
        or (b:getX()==x and b:getY()==y and a:getX()==ox and a:getY()==oy))
end
local function windowSafe(o)
    return call(o,'isBarricaded')==false and call(o,'isInvincible')==false
        and (call(o,'isSmashed')==false or (call(o,'isSmashed')==true and call(o,'isGlassRemoved')==true))
end
-- Returns trusted internal descriptors, never supplied by Ollama.
function F.edgeTransitions(c,a,b,requestedKind)
    local dir=direction(a,b)
    if not dir or not free(b,c) then return nil,'unsafe_landing' end
    local o=call(a,'getDoorTo',b)
    if o then
        if call(o,'isLocked')==true or call(o,'isLockedByKey')==true then return nil,'door_locked' end
        if call(o,'isBarricaded')==true then return nil,'door_barricaded' end
        if call(o,'isObstructed')==true then return nil,'door_obstructed' end
        if not instanceof(o,'IsoDoor') or not onEdge(o,a,b)
            or (requestedKind and requestedKind~='OPEN_DOOR' and requestedKind~='CLOSE_DOOR')
            or (not requestedKind and call(o,'IsOpen')~=false) or type(call(o,'IsOpen'))~='boolean'
            or call(o,'isLocked')~=false or call(o,'isLockedByKey')~=false
            or call(o,'isBarricaded')~=false or call(o,'isObstructed')~=false
            or call(o,'isInvincible')~=false or not method(o,'ToggleDoor') then return nil,'door_unavailable' end
        -- Composite doors have additional swept geometry, excluded from this adapter.
        if not IsoDoor or not IsoDoor.getDoubleDoorIndex or not IsoDoor.getGarageDoorIndex then return nil,'UNSUPPORTED_door_geometry' end
        local ok,multi,garage=pcall(function() return IsoDoor.getDoubleDoorIndex(o),IsoDoor.getGarageDoorIndex(o) end)
        if not ok or type(multi)~='number' or type(garage)~='number' or multi~=-1 or garage~=-1 then return nil,'UNSUPPORTED_composite_door' end
        if not free(a,c) then return nil,'unsafe_door_origin' end
        return {{kind=requestedKind or 'OPEN_DOOR',object=o,direction=dir}}
    end
    o=call(a,'getWindowTo',b)
    if o then
        if not instanceof(o,'IsoWindow') or not onEdge(o,a,b) or a:getZ()~=0
            or not free(a,c) or not windowSafe(o) then return nil,'unsafe_window' end
        if requestedKind=='OPEN_WINDOW' and call(o,'isSmashed')==false and call(o,'IsOpen')==true then
            return {{kind='OPEN_WINDOW',object=o,direction=dir}}
        end
        if requestedKind and requestedKind~='OPEN_WINDOW' and requestedKind~='CLIMB_WINDOW' then return nil,'object_action_mismatch' end
        if call(o,'IsOpen')==true or call(o,'isSmashed')==true then
            return {{kind='CLIMB_WINDOW',object=o,direction=dir}}
        end
        if call(o,'IsOpen')~=false or call(o,'isLocked')~=false or call(o,'isPermaLocked')~=false then return nil,'locked_window' end
        return {{kind='OPEN_WINDOW',object=o,direction=dir},{kind='CLIMB_WINDOW',object=o,direction=dir}}
    end
    o=call(a,'getHoppableTo',b)
    if o and (not requestedKind or requestedKind=='CLIMB_FENCE') and a:getZ()==0 and free(a,c) and call(o,'isTallHoppable')==false
        and call(o,'getObjectIndex') and call(o,'getObjectIndex')>=0 then
        return {{kind='CLIMB_FENCE',object=o,direction=dir}}
    end
    return nil,'UNSUPPORTED_obstacle'
end
-- Bounded capability discovery. Tokens retain object identity privately per UUID/world.
local function registry()
    if candidateWorld~=world() then candidates={}; physicalResults={}; candidateWorld=world() end
end
function F.getCandidates(id,fromTarget)
    registry()
    if not world() then return {},"world_unavailable" end
    local c=ArayHuman.getNpcByUuid(id)
    if not npc(c,id) then return {},"instance_unavailable" end
    local a=c:getCurrentSquare()
    if not a or square(math.floor(c:getX()),math.floor(c:getY()),math.floor(c:getZ()))~=a then return {},"instance_unavailable" end
    if fromTarget then
        local snap=ArayHuman.Perception.updateSnapshot(id); a=nil
        for _,t in ipairs(snap and snap.tiles or {}) do
            local key='tile:'..t.x..':'..t.y..':'..t.z
            if key==fromTarget and t.traversable_candidate.known and t.traversable_candidate.value then a=square(t.x,t.y,t.z); break end
        end
        if not a then return {},"destination_not_in_snapshot" end
    end
    local saved=candidates[id] or {}; candidates[id]=saved
    local result={}
    for _,delta in ipairs({{1,0},{-1,0},{0,1},{0,-1}}) do
        local b=square(a:getX()+delta[1],a:getY()+delta[2],a:getZ())
        if b then
            local choices={}
            for kind in pairs(F.actions) do
                for _,step in ipairs(F.edgeTransitions(c,a,b,kind) or {}) do
                    if step.kind==kind then choices[#choices+1]=step end
                end
            end
            for _,step in ipairs(choices) do
                local o=step.object; local index=call(o,'getObjectIndex'); local owner=call(o,'getSquare')
                if type(index)=='number' and index>=0 and owner then
                    local entry=nil
                    for _,old in ipairs(saved) do
                        if old.object==o and old.fromX==a:getX() and old.fromY==a:getY() and old.z==a:getZ()
                            and old.x==b:getX() and old.y==b:getY() then entry=old; break end
                    end
                    if not entry then
                        candidateSerial=candidateSerial+1
                        entry={id='edge:'..candidateSerial,object=o,fromX=a:getX(),fromY=a:getY(),z=a:getZ(),x=b:getX(),y=b:getY()}
                        saved[#saved+1]=entry
                        while #saved>64 do table.remove(saved,1) end
                    end
                    local public=nil
                    for _,item in ipairs(result) do if item.target_id==entry.id then public=item; break end end
                    if not public then
                        public={target_id=entry.id,from={x=entry.fromX,y=entry.fromY,z=entry.z},
                            destination={x=entry.x,y=entry.y,z=entry.z},object={index=index,
                            x=owner:getX(),y=owner:getY(),z=owner:getZ(),
                            category=instanceof(o,'IsoDoor') and 'IsoDoor' or instanceof(o,'IsoWindow') and 'IsoWindow' or 'low_fence'},actions={}}
                        result[#result+1]=public
                    end
                    public.actions[step.kind]=true
                end
            end
        end
    end
    return result
end
function F.resolveCandidate(id,kind,target)
    registry()
    if not world() then return nil,'world_unavailable' end
    local c=ArayHuman.getNpcByUuid(id)
    if not npc(c,id) then return nil,'instance_unavailable' end
    if not F.actions[kind] or type(target)~='string' then return nil,'invalid_physical_action' end
    for _,entry in ipairs(candidates[id] or {}) do
        if entry.id==target then
            local a,b=square(entry.fromX,entry.fromY,entry.z),square(entry.x,entry.y,entry.z)
            local choices,why=F.edgeTransitions(c,a,b,kind)
            for _,step in ipairs(choices or {}) do
                if step.kind==kind and step.object==entry.object and type(call(step.object,'getObjectIndex'))=='number' and call(step.object,'getObjectIndex')>=0 then
                    return {kind=kind,object=step.object,object_id=target,direction=step.direction,
                        fromX=entry.fromX,fromY=entry.fromY,x=entry.x,y=entry.y,z=entry.z}
                end
            end
            return nil,why or 'object_changed_or_blocked'
        end
    end
    return nil,'physical_target_unknown'
end
function F.getState(id)
    local r=locks[id]; if not r then return nil end
    return {state=r.state,action=r.step.kind,object_id=r.step.object_id,action_id=r.action_id,
        cancelled=r.cancelled,observations=ArayHuman.Locomotion.copy(r.metrics)}
end
local function safeState(c)
    local name=call(c,'getCurrentStateName')
    return name=='IdleState'
        and call(c,'isClimbing')==false and call(c,'isKnockedDown')==false
        and call(c,'isPerformingAttackAnimation')==false and call(c,'isPerformingShoveAnimation')==false
end
local function nativeBusy(c)
    -- Unknown state is unsafe to interrupt or to replace.
    return not safeState(c)
end
local function queued(c)
    local q=ISTimedActionQueue and ISTimedActionQueue.queues and ISTimedActionQueue.queues[c]
    return q and q.queue and #q.queue>0
end
local function risk(c,step,obs,purpose)
    if not obs or not obs.active or (purpose~='navigation' and not obs.immediate) or not obs.scan.complete or obs.world_id~=world()
        or type(obs.captured_at_ms)~='number' or now()-obs.captured_at_ms>1000 or obs.captured_at_ms>now() then return false,'threat_not_confirmed' end
    if purpose=='navigation' and obs.immediate then return false,'emergency_priority' end
    local margin=(step.kind=='OPEN_DOOR' or step.kind=='CLOSE_DOOR') and 1.25 or 2
    for _,t in ipairs(obs.threats or {}) do
        local p=t.position
        if distance(c:getX(),c:getY(),p.x,p.y)<margin
            or distance(step.x+.5,step.y+.5,p.x,p.y)<2.5 then return false,'interaction_threat_too_close' end
    end
    return true
end
function F.busy(id) return locks[id]~=nil or (ArayHuman.Inventory and ArayHuman.Inventory.busy(id)) or false end
function F.cancel(id,reason)
    local r=locks[id]; if not r then return end
    -- Never force a Java animation out of its state. Keep the per-UUID lock.
    r.cancelled=reason or 'cancelled'
    log(id,'cancel_pending',r.cancelled)
end
function F.start(id,c,step,obs,generation,callback,options)
    if ArayHuman.Inventory and ArayHuman.Inventory.busy(id) then return false,'inventory_busy' end
    options=options or {}
    if not world() then return false,"world_unavailable" end
    local purpose=options.purpose or "emergency"
    if purpose~="emergency" and purpose~="navigation" then return false,"invalid_interaction_purpose" end
    if not npc(c,id) then return false,'UNSUPPORTED_npc_instance' end
    if type(step)~='table' or type(generation)~='number' then return false,'invalid_transition' end
    for _,key in ipairs({'fromX','fromY','x','y','z'}) do
        local v=step[key]
        if type(v)~='number' or v~=v or v==math.huge or v==-math.huge or v~=math.floor(v) then return false,'invalid_transition' end
    end
    if not call(step.object,'getSquare') then return false,'UNSUPPORTED_object_position' end
    local objectIndex=call(step.object,'getObjectIndex')
    if type(objectIndex)~='number' or objectIndex<0 then return false,'object_removed_or_unknown' end
    if step.object and objectOwners[step.object] and objectOwners[step.object]~=id then return false,'object_busy' end
    if locks[id] or queued(c) or not safeState(c) then return false,'physical_busy' end
    if not method(c,'faceDirection') or not method(c,'shouldBeTurning') or not method(c,'isFacingLocation') then return false,'UNSUPPORTED_orientation' end
    local from=square(step.fromX,step.fromY,step.z); local to=square(step.x,step.y,step.z)
    if not from or math.floor(c:getX())~=step.fromX or math.floor(c:getY())~=step.fromY
        or math.floor(c:getZ())~=step.z or c:getCurrentSquare()~=from or distance(c:getX(),c:getY(),step.fromX+.5,step.fromY+.5)>.8 then return false,'interaction_out_of_reach' end
    if not direction(from,to) then return false,'interaction_edge_invalid' end
    local choices,reason=F.edgeTransitions(c,from,to,(purpose=="navigation" or step.kind=="CLOSE_DOOR") and step.kind or nil); local found=false
    for _,s in ipairs(choices or {}) do if s.kind==step.kind and s.object==step.object and s.direction==step.direction then found=true end end
    if not found then return false,reason or 'obstacle_changed' end
    if not obs or obs.uuid~=id then return false,'observation_uuid_mismatch' end
    local safe,why=risk(c,step,obs,purpose); if not safe then return false,why end
    if step.kind=='OPEN_WINDOW' and (not method(c,'openWindow') or type(c.contextPanic)~='number' or c.contextPanic>0) then return false,'UNSUPPORTED_window_state' end
    if step.kind=='CLIMB_WINDOW' and not method(c,'climbThroughWindow') then return false,'UNSUPPORTED_climb_window' end
    if step.kind=='CLIMB_FENCE' and not method(c,'climbOverFence') then return false,'UNSUPPORTED_climb_fence' end
    if step.kind=='CLIMB_WINDOW' and (not method(c,'climbThroughWindow') or call(step.object,'canClimbThrough',c)~=true) then return false,'window_not_climbable' end
    if step.kind=='CLIMB_FENCE' and (not method(c,'climbOverFence') or call(c,'isSafeToClimbOver',step.direction)~=true
        or call(from,'isPlayerAbleToHopWallTo',step.direction,to)~=true) then return false,'fence_not_climbable' end
    locks[id]={character=c,step=step,generation=generation,callback=callback,at=now(),world=world(),state='ORIENTING',purpose=purpose,action_id=options.action_id or ('physical:'..id..':'..generation),
        metrics=ArayHuman.Locomotion.beginMetrics(c,id)}
    registry()
    locks[id].metrics.object={initial_open={known=type(call(step.object,'IsOpen'))=='boolean',value=call(step.object,'IsOpen')},id=step.object_id,index=call(step.object,'getObjectIndex'),position={x=step.object:getSquare():getX(),y=step.object:getSquare():getY(),z=step.object:getSquare():getZ()}}
    locks[id].metrics.position_initial={x=c:getX(),y=c:getY(),z=c:getZ()}
    objectOwners[step.object]=id
    local oriented=pcall(function() c:faceDirection(step.direction) end)
    if not oriented then objectOwners[step.object]=nil; locks[id]=nil; return false,'UNSUPPORTED_orientation' end
    log(id,'interaction_start','kind='..step.kind..' generation='..generation..' action_id='..locks[id].action_id
        ..' object_id='..tostring(step.object_id)..' object_index='..objectIndex
        ..' from='..c:getX()..','..c:getY()..','..c:getZ())
    return true
end
function F.defensiveShove(id,c,obs)
    if not npc(c,id) then return false,'UNSUPPORTED_npc_instance' end
    local cx,cy,cz=call(c,'getX'),call(c,'getY'),call(c,'getZ')
    local origin=call(c,'getCurrentSquare')
    if not world() or not origin or origin~=square(math.floor(cx),math.floor(cy),math.floor(cz)) then return false,'chunk_unavailable' end
    if locks[id] or not safeState(c) then return false,'physical_busy' end
    if type(obs)~='table' or obs.uuid~=id or obs.world_id~=world() or not obs.active or not obs.immediate
        or type(obs.scan)~='table' or obs.scan.complete~=true or type(obs.threats)~='table' or type(obs.captured_at_ms)~='number'
        or obs.captured_at_ms~=obs.captured_at_ms
        or obs.captured_at_ms>now() or now()-obs.captured_at_ms>1000 then return false,'emergency_not_confirmed' end
    if shoves[id] and shoves[id].world==world() and now()<shoves[id].until_ms then return false,'shove_cooldown' end
    -- Re-find a live zombie locally. Never accept a player/NPC as the target.
    local target=nil; local examined=0
    local function finite(n) return type(n)=='number' and n==n and n~=math.huge and n~=-math.huge end
    for ti,t in ipairs(obs.threats) do
        if ti>32 then return false,'shove_scan_budget' end
        local p=type(t)=='table' and t.position
        if type(p)=='table' and finite(p.x) and finite(p.y) and finite(p.z)
            and distance(cx,cy,p.x,p.y)<=1.25 and math.abs(p.z-cz)<=.25 then
            local sq=square(math.floor(p.x),math.floor(p.y),math.floor(p.z))
            local list=call(sq,'getMovingObjects'); local count=call(list,'size')
            if type(count)~='number' or count<0 or count~=math.floor(count) then return false,'shove_scan_unavailable' end
            for i=0,count-1 do
                examined=examined+1; if examined>32 then return false,'shove_scan_budget' end
                local z=call(list,'get',i)
                local zx,zy,zz=call(z,'getX'),call(z,'getY'),call(z,'getZ')
                if instanceof(z,'IsoZombie') and call(z,'isDead')==false
                    and finite(zx) and finite(zy) and finite(zz) and math.abs(zz-cz)<=.25
                    and call(z,'getCurrentSquare')==sq and square(math.floor(zx),math.floor(zy),math.floor(zz))==sq
                    and distance(cx,cy,zx,zy)<=1.25
                    and (sq==origin or ArayHuman.Perception.edgePassable(origin,sq)==true)
                    and call(c,'isFacingLocation',zx,zy,.5)==true then target=z; break end
            end
        end
        if target then break end
    end
    if not target then return false,'shove_target_or_orientation_invalid' end
    -- Necessary current-distance check only. This cannot certify an area swept
    -- during a future animation: native collision may select targets later.
    local player=ArayHuman.getLocalPlayer()
    local px,py,pz=call(player,'getX'),call(player,'getY'),call(player,'getZ')
    local ps=call(player,'getCurrentSquare')
    if not player or player==c or call(player,'isDead')~=false
        or not finite(px) or not finite(py) or not finite(pz) or not ps
        or square(math.floor(px),math.floor(py),math.floor(pz))~=ps then return false,'shove_player_unavailable' end
    local playerDistance=distance(cx,cy,px,py)
    if playerDistance<=2 then return false,'shove_player_too_close' end
    shoves[id]={world=world(),until_ms=now()+F.config.shoveCooldownMs}
    -- DoAttack/pressedAttack select targets internally (and may use a weapon).
    -- No audited target-exclusive shove entry point: do not call any attack API.
    local reason=F.unsupportedReason('PUSH_ZOMBIE')
    log(id,'DEFENSIVE_SHOVE',reason..' distance='..distance(cx,cy,target:getX(),target:getY())
        ..' player_distance='..playerDistance..' collision_zone=unknown exclusion_during_animation=unproven executed=false')
    return false,reason
end
function F.update(id,obs)
    local r=locks[id]; if not r then return end
    local c,step=r.character,r.step
    local same=npc(c,id)
    if not same then r.cancelled=r.cancelled or 'npc_dead_or_replaced' end
    if r.world~=world() then r.cancelled=r.cancelled or 'world_changed' end
    local function done(result)
        local valid=r.world==world() and ArayHuman.getNpcByUuid(id)==c and c:getCurrentSquare()~=nil
            and c:getCurrentSquare()==square(math.floor(c:getX()),math.floor(c:getY()),math.floor(c:getZ()))
        ArayHuman.Locomotion.endMetrics(r.metrics,c,id,valid)
        r.metrics.position_final=valid and {x=c:getX(),y=c:getY(),z=c:getZ()} or {known=false}
        r.metrics.object_id=step.object_id; r.metrics.action=step.kind; r.metrics.result=result
        local open=call(step.object,'IsOpen')
        r.metrics.object.final_open={known=type(open)=='boolean',value=open}
        local a,b=square(step.fromX,step.fromY,step.z),square(step.x,step.y,step.z)
        local pass=nil
        if valid then pass=ArayHuman.Perception.edgePassable(a,b) end
        r.metrics.passage_clear={known=pass~=nil,value=pass}
        if valid then
            local list=physicalResults[id] or {}; physicalResults[id]=list
            for i=#list,1,-1 do if list[i].action_id==r.action_id then table.remove(list,i) end end
            list[#list+1]={uuid=id,action_id=r.action_id,action=step.kind,object_id=step.object_id,
                result=result,observations=ArayHuman.Locomotion.copy(r.metrics)}
            while #list>16 do table.remove(list,1) end
        end
        if objectOwners[step.object]==id then objectOwners[step.object]=nil end
        locks[id]=nil
        local final=r.metrics.position_final
        log(id,'interaction_result','kind='..step.kind..' action_id='..r.action_id..' object_id='..tostring(step.object_id)
            ..' duration_ms='..r.metrics.duration_ms..' result='..result
            ..' damage='..tostring(r.metrics.damage_received.known and r.metrics.damage_received.value or 'unknown')
            ..' to='..tostring(final.x)..','..tostring(final.y)..','..tostring(final.z))
        if r.callback then r.callback(result,r.generation,ArayHuman.Locomotion.copy(r.metrics)) end
    end
    if r.world==world() and ArayHuman.getNpcByUuid(id)==c and c:getCurrentSquare() then ArayHuman.Locomotion.sampleMetrics(r.metrics,c,false) end
    if call(c,'isDead')==true then done('npc_dead'); return end
    if r.state=='ORIENTING' then
        if r.cancelled then done(r.cancelled); return end
        if not obs or obs.uuid~=id then done('observation_uuid_mismatch'); return end
        local safe,why=risk(c,step,obs,r.purpose)
        if not safe then done(why); return end
        if now()-r.at>1500 then done('orientation_timeout'); return end
        if call(c,'shouldBeTurning')~=false or call(c,'isFacingLocation',step.x+.5,step.y+.5,.5)~=true then return end
        -- Revalidate after orientation; scene changes must not execute a stale transition.
        local index=call(step.object,'getObjectIndex')
        if type(index)~='number' or index<0 then done('object_removed_or_unknown'); return end
        local a=square(step.fromX,step.fromY,step.z); local b=square(step.x,step.y,step.z)
        local choices=F.edgeTransitions(c,a,b,(r.purpose=="navigation" or step.kind=="CLOSE_DOOR") and step.kind or nil); local found=false
        for _,s in ipairs(choices or {}) do if s.kind==step.kind and s.object==step.object then found=true end end
        if not found or not a or c:getCurrentSquare()~=a or math.floor(c:getX())~=step.fromX
            or math.floor(c:getY())~=step.fromY or math.floor(c:getZ())~=step.z
            or distance(c:getX(),c:getY(),step.fromX+.5,step.fromY+.5)>.8 or not safeState(c) then done('obstacle_or_state_changed'); return end
        if step.kind=='OPEN_WINDOW' and (type(c.contextPanic)~='number' or c.contextPanic>0) then done('unsafe_window_panic'); return end
        if step.kind=='CLIMB_WINDOW' and call(step.object,'canClimbThrough',c)~=true then done('window_not_climbable'); return end
        if step.kind=='CLIMB_FENCE' and (call(c,'isSafeToClimbOver',step.direction)~=true
            or call(a,'isPlayerAbleToHopWallTo',step.direction,b)~=true) then done('fence_not_climbable'); return end
        local ok=pcall(function()
            if step.kind=='OPEN_DOOR' or step.kind=='CLOSE_DOOR' then
                if step.object:IsOpen()~=(step.kind=='OPEN_DOOR') then step.object:ToggleDoor(c) end
            elseif step.kind=='OPEN_WINDOW' then if not step.object:IsOpen() then c:openWindow(step.object) end
            elseif step.kind=='CLIMB_WINDOW' then c:climbThroughWindow(step.object)
            elseif step.kind=='CLIMB_FENCE' then c:climbOverFence(step.direction) end
        end)
        r.state='NATIVE'; r.invokedAt=now()
        if not ok then r.cancelled='native_api_failed' end
        return
    end
    local index=call(step.object,'getObjectIndex')
    if type(index)~='number' or index<0 then r.cancelled=r.cancelled or 'object_removed_or_unknown' end
    if obs and obs.active then
        local safe,why=risk(c,step,obs,r.purpose)
        if not safe and r.purpose=='navigation' then r.cancelled=r.cancelled or why end
        if not safe and not r.riskLogged then log(id,'interaction_risk','reason='..tostring(why)..' policy=wait_native_safe'); r.riskLogged=true end
    end
    if now()-r.at>=F.config.timeoutMs then
        if not r.cancelled then log(id,'interaction_timeout','policy=wait_native_safe') end
        r.cancelled=r.cancelled or 'interaction_timeout'
    end
    if nativeBusy(c) then return end
    if now()-r.invokedAt<F.config.settleMs then return end
    if r.cancelled then done(r.cancelled); return end
    if step.kind=='OPEN_DOOR' or step.kind=='CLOSE_DOOR' or step.kind=='OPEN_WINDOW' then
        if call(step.object,'IsOpen')==(step.kind~='CLOSE_DOOR') then done('success')
        elseif now()-r.invokedAt>=1000 then done(step.kind=='CLOSE_DOOR' and 'native_close_failed' or 'native_open_failed') end
    else
        local landing=square(step.x,step.y,step.z)
        if landing and c:getCurrentSquare()==landing and math.floor(c:getX())==step.x
            and math.floor(c:getY())==step.y and math.floor(c:getZ())==step.z then done('success')
        elseif now()-r.invokedAt>=1000 then done('native_crossing_failed') end
    end
end
-- A canceled executor still needs safe animation retirement; no callback can revive it.
local lastCancelledUpdate=0
function F.updateCancelled()
    if now()-lastCancelledUpdate<250 then return end
    lastCancelledUpdate=now()
    for id,r in pairs(locks) do if r.cancelled then F.update(id,nil) end end
end

function F.getResult(id,actionId)
    registry()
    for _,result in ipairs(physicalResults[id] or {}) do
        if result.action_id==actionId then return ArayHuman.Locomotion.copy(result) end
    end
end
