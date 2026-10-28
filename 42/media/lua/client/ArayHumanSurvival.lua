-- Read-only physical observations. No policy, native updates, setters or persistence.
ArayHuman=ArayHuman or {}
ArayHuman.Survival={}
local S=ArayHuman.Survival
S.config={intervalMs=1000,maxPerTick=2,maxBodyParts=32,maxInventoryItems=256,maxEvents=128,
    threatMaxAgeMs=1500,epsilon=0,criticalHealth=25,hunger=.25,thirst=.25,
    fatigue=.8,endurance=.2}
local cache,history,threats,sequences={},{},{},{}
local worldSeen,scheduled,cursor,lastCycle=nil,{},1,nil
local stats={hunger='HUNGER',thirst='THIRST',fatigue='FATIGUE',endurance='ENDURANCE',
    pain='PAIN',panic='PANIC',stress='STRESS',temperature='TEMPERATURE'}
local moodles={'ENDURANCE','TIRED','HUNGRY','THIRST','PANIC','BLEEDING','INJURED',
    'PAIN','STRESS','HEAVY_LOAD','HYPERTHERMIA','HYPOTHERMIA'}
local stateNames={'HEALTHY','INJURED','CRITICAL','EXHAUSTED','HUNGRY','THIRSTY','DEAD'}
local function copy(v)
    if type(v)~='table' then return v end
    local r={}; for k,x in pairs(v) do r[k]=copy(x) end; return r
end
local function finite(v) return type(v)=='number' and v==v and v~=math.huge and v~=-math.huge end
local function integer(v) return finite(v) and v==math.floor(v) and v>=0 end
local function call(o,k,...)
    local args={...}
    local ok,v=pcall(function() if o and o[k] then return o[k](o,unpack(args)) end end)
    if ok then return v end
end
local function global(f,...) if not f then return nil end; local ok,v=pcall(f,...); if ok then return v end end
local function stamp() return global(getTimestampMs) or 0 end
local function unavailable(reason,source) return {known=false,status='unavailable',reason=reason,source=source} end
local function unknown(reason,source) return {known=false,status='unknown',reason=reason,source=source} end
local function known(v,source) return {known=true,status='known',value=v,source=source} end
local function read(o,k,kind,source,...)
    source=source or k
    if not o then return unavailable('component_unavailable',source) end
    local args={...}
    local ok,exists,v=pcall(function()
        if not o[k] then return false end
        return true,o[k](o,unpack(args))
    end)
    if not ok then return unknown('api_error',source) end
    if not exists then return unavailable('api_unavailable',source) end
    if (kind=='number' and finite(v)) or (kind=='boolean' and type(v)=='boolean') then return known(v,source) end
    return unknown('invalid_value',source)
end
local function world()
    local name=call(global(getWorld),'getWorld'); local mode=call(global(getCore),'getGameMode')
    if name and mode and name~='unknown' and mode~='unknown' then return tostring(mode)..'/'..tostring(name) end
end
function S.clearAll()
    cache,history,threats,sequences={},{},{},{}
    scheduled,cursor,lastCycle={},1,nil
end
local function checkWorld()
    local w=world(); if w~=worldSeen then S.clearAll(); worldSeen=w end; return w
end
local function actor(id)
    if type(id)~='string' or #id~=36 or not id:match('^%x%x%x%x%x%x%x%x%-%x%x%x%x%-%x%x%x%x%-%x%x%x%x%-%x%x%x%x%x%x%x%x%x%x%x%x$') then return nil end
    local c=global(ArayHuman.getNpcByUuid,id); local md=call(c,'getModData')
    if c and md and md.ARAY_IsNPC==true and md.ARAY_Uuid==id and call(c,'isNPC')==true
        and c~=global(ArayHuman.getLocalPlayer) then return c end
end
local function loaded(c)
    local x,y,z=call(c,'getX'),call(c,'getY'),call(c,'getZ'); local sq=call(c,'getCurrentSquare')
    return finite(x) and finite(y) and finite(z) and sq~=nil
        and sq==call(global(getCell),'getGridSquare',math.floor(x),math.floor(y),math.floor(z))
end
local function bounded(key,default,lo,hi)
    local n=S.config[key]; if not finite(n) then n=default end
    return math.max(lo,math.min(hi,math.floor(n)))
end
local function threshold(key,default,lo,hi)
    local n=S.config[key]; if not finite(n) then n=default end
    return math.max(lo,math.min(hi,n))
end
local function constant(t,k) local ok,v=pcall(function() return t and t[k] end); if ok then return v end end
local function threat(id,c,at)
    local r=threats[id]
    if not r or r.character~=c then return unknown('not_observed','Perception.scanThreats') end
    if at<r.at or at-r.at>bounded('threatMaxAgeMs',1500,100,5000) then return unknown('stale','Perception.scanThreats') end
    return copy(r.value)
end
-- Reuse the emergency monitor's observation; never run a second spatial scan.
function S.recordThreat(id,obs)
    local w=checkWorld(); local c=actor(id); local at=stamp()
    if not w or not c or type(obs)~='table' or obs.uuid~=id or obs.world_id~=w
        or not finite(obs.captured_at_ms) or obs.captured_at_ms>at
        or at-obs.captured_at_ms>bounded('threatMaxAgeMs',1500,100,5000) then return false end
    local complete=obs.active==true and type(obs.scan)=='table' and obs.scan.complete==true
    local v={known=complete,status=complete and 'known' or 'unknown',source='Perception.scanThreats',
        reason=not complete and 'incomplete_observation' or nil,uuid=id,world_id=w,
        captured_at_ms=obs.captured_at_ms,level=obs.level,immediate=obs.immediate==true,
        nearest=copy(obs.nearest)}
    threats[id]={character=c,at=obs.captured_at_ms,value=v}; return true
end
local function bodyParts(body)
    local result={items={},examined=0,complete=false}
    local list=call(body,'getBodyParts'); local count=call(list,'size')
    if not integer(count) or count==0 then result.reason='body_parts_unavailable'; return result end
    local limit=bounded('maxBodyParts',32,1,32)
    local complete=count<=limit; local wounds,infected=0,0
    for i=0,math.min(count,limit)-1 do
        local p=call(list,'get',i); local item={index=i}
        local injured,all=false,true
        for _,k in ipairs({'bleeding','scratched','bitten','isCut','isInfectedWound'}) do
            local v=read(p,k,'boolean','BodyPart.'..k); item[k]=v
            if v.known then injured=injured or v.value else all=false end
        end
        item.bandaged=read(p,'bandaged','boolean','BodyPart.bandaged')
        item.infected=read(p,'IsInfected','boolean','BodyPart.IsInfected')
        item.health=read(p,'getHealth','number','BodyPart.getHealth')
        if item.health.known then injured=injured or item.health.value<100 else all=false end
        for _,k in ipairs({'getFractureTime','getBurnTime','getDeepWoundTime','getStitchTime'}) do
            local v=read(p,k,'number','BodyPart.'..k); item[k]=v
            if v.known then injured=injured or v.value>0 else all=false end
        end
        if injured then wounds=wounds+1 end
        if item.isInfectedWound.known and item.isInfectedWound.value then infected=infected+1 end
        complete=complete and all
        result.items[#result.items+1]=item; result.examined=result.examined+1
    end
    result.complete=complete; result.total=count
    result.wounded_parts=complete and known(wounds,'BodyPart observations') or unknown('partial_body_parts','BodyPart observations')
    result.wounded_parts.observed_minimum=wounds
    result.infected_wounds=complete and known(infected,'BodyPart.isInfectedWound') or unknown('partial_body_parts','BodyPart.isInfectedWound')
    if not complete then result.reason=count>limit and 'body_part_budget' or 'partial_body_parts' end
    return result
end
local function any(fields,pred)
    local complete=true
    for _,v in ipairs(fields) do if v.known then if pred(v.value) then return known(true,'observer_rule') end else complete=false end end
    return complete and known(false,'observer_rule') or unknown('insufficient_observations','observer_rule')
end
local function classify(s)
    local dead=s.conditions.dead; local states={}
    states.DEAD=copy(dead)
    -- Different native scales are compared separately; health is 0..100, counts are counts.
    local countInjury=any({s.conditions.bleeding_parts,s.conditions.scratched_parts,s.conditions.bitten_parts,
        s.wounds.wounded_parts or unknown('not_observed')},function(v) return v>0 end)
    local healthInjury=s.health.known and known(s.health.value<100,'observer_health_below_100') or copy(s.health)
    states.INJURED=any({countInjury,healthInjury,s.conditions.infected},function(v) return v==true end)
    if s.wounds.wounded_parts and s.wounds.wounded_parts.observed_minimum>0 then states.INJURED=known(true,'observed_wound') end
    states.CRITICAL=s.health.known and known(s.health.value<=threshold('criticalHealth',25,0,100),'observer_health_threshold') or unknown('health_unknown')
    states.HUNGRY=s.needs.hunger.known and known(s.needs.hunger.value>=threshold('hunger',.25,0,1),'observer_hunger_threshold') or copy(s.needs.hunger)
    states.THIRSTY=s.needs.thirst.known and known(s.needs.thirst.value>=threshold('thirst',.25,0,1),'observer_thirst_threshold') or copy(s.needs.thirst)
    local fatigue=s.needs.fatigue; local endurance=s.needs.endurance
    if (fatigue.known and fatigue.value>=threshold('fatigue',.8,0,1)) or (endurance.known and endurance.value<=threshold('endurance',.2,0,1)) then
        states.EXHAUSTED=known(true,'observer_fatigue_or_endurance_threshold')
    elseif fatigue.known and endurance.known then states.EXHAUSTED=known(false,'observer_fatigue_or_endurance_threshold')
    else states.EXHAUSTED=unknown('fatigue_or_endurance_unknown') end
    local all=dead.known and not dead.value and s.conditions.knocked_down.known and not s.conditions.knocked_down.value
        and s.conditions.infected.known and not s.conditions.infected.value
    local healthy=all; local unhealthy=(s.conditions.incapacitated.known and s.conditions.incapacitated.value)
        or (s.conditions.infected.known and s.conditions.infected.value)
    for _,k in ipairs({'INJURED','CRITICAL','EXHAUSTED','HUNGRY','THIRSTY'}) do
        all=all and states[k].known; if states[k].known and states[k].value then healthy=false; unhealthy=true end
    end
    states.HEALTHY=all and known(healthy,'observer_all_required_conditions') or unknown('insufficient_observations','observer_rule')
    if unhealthy then states.HEALTHY=known(false,'observed_condition') end
    if dead.known and dead.value then for _,k in ipairs(stateNames) do if k~='DEAD' then states[k]=known(false,'dead') end end end
    s.states=states; s.state_list={}
    states.HUNGRY.planning_eligible=false; states.THIRSTY.planning_eligible=false
    states.EXHAUSTED.planning_basis='endurance_only_fatigue_excluded'
    for _,k in ipairs(stateNames) do if states[k].known and states[k].value then s.state_list[#s.state_list+1]=k end end
end
local function emit(id,s,kind,field,before,after,duration)
    sequences[id]=(sequences[id] or 0)+1
    local e={uuid=id,world_id=s.world_id,timestamp_ms=s.captured_at_ms,sequence=sequences[id],
        type=kind,field=field,before=copy(before),after=copy(after),duration_ms=duration,threat=copy(s.threat)}
    if before and after and before.known and after.known and finite(before.value) and finite(after.value) then e.delta=after.value-before.value end
    local events=history[id] or {}; history[id]=events; events[#events+1]=e
    while #events>bounded('maxEvents',128,1,256) do table.remove(events,1) end
    return e
end
local function changed(a,b)
    if not a or a.status~=b.status then return true end
    if a.known and b.known then
        if finite(a.value) and finite(b.value) then return math.abs(a.value-b.value)>threshold('epsilon',0,0,1) end
        return a.value~=b.value
    end
    return a.reason~=b.reason
end
local function eventsFor(id,s,previous)
    local duration=previous and s.captured_at_ms-previous.captured_at_ms or 0
    if not previous then emit(id,s,'OBSERVATION_STARTED',nil,nil,nil,0) end
    if previous then
        local a,b=previous.health,s.health
        if changed(a,b) then
            local kind='OBSERVATION_CHANGED'
            if a.known and b.known then kind=b.value<a.value and 'DAMAGE' or 'RECOVERY' end
            emit(id,s,kind,'health',a,b,duration)
        end
        for _,group in ipairs({'needs','conditions','states','inventory','moodles'}) do
            for k,v in pairs(s[group]) do
                local before=previous[group][k]
                if changed(before,v) then
                    local kind=group=='needs' and 'NEED_CHANGED' or group=='states' and 'STATE_CHANGED' or 'CONDITION_CHANGED'
                    if not before or not before.known or not v.known then kind='OBSERVATION_CHANGED' end
                    emit(id,s,kind,group..'.'..k,before,v,duration)
                end
            end
        end
        for i,part in ipairs(s.wounds.items) do
            local old=previous.wounds.items[i]
            local changes={}; local count=0; local observed=false
            for k,v in pairs(part) do
                if type(v)=='table' and old and changed(old[k],v) then
                    changes[k]={before=copy(old[k]),after=copy(v)}; count=count+1
                    observed=observed or (old[k] and old[k].known and v.known)
                end
            end
            if count>0 then
                local event=emit(id,s,observed and 'CONDITION_CHANGED' or 'OBSERVATION_CHANGED',
                    'wounds.'..part.index,nil,nil,duration)
                event.changes=changes
            end
        end
    end
    if s.conditions.dead.known and s.conditions.dead.value
        and (not previous or not previous.conditions.dead.known or not previous.conditions.dead.value) then
        emit(id,s,'DEATH','conditions.dead',previous and previous.conditions.dead,s.conditions.dead,duration)
    end
end
function S.updateSnapshot(id)
    local w=checkWorld(); local c=actor(id); local at=stamp()
    if not w then return nil,'world_unavailable' end
    if not c then S.clearSnapshot(id); return nil,'instance_unavailable' end
    local previous=cache[id]
    if previous and (previous.character~=c or at<previous.snapshot.captured_at_ms) then
        previous=nil; history[id]=nil; threats[id]=nil -- do not infer damage across instances or clock resets
    end
    local s={schema_version=1,uuid=id,world_id=w,captured_at_ms=at,active=false,available=false,
        health=unavailable('not_observed'),needs={},conditions={},inventory={},moodles={},wounds={items={},examined=0,complete=false},
        threat=threat(id,c,at),state_duration_ms={},needs_policy=S.getNeedsPolicy()}
    s.conditions.dead=read(c,'isDead','boolean','IsoGameCharacter.isDead')
    s.conditions.alive=s.conditions.dead.known and known(not s.conditions.dead.value,'IsoGameCharacter.isDead') or copy(s.conditions.dead)
    local usable=w and loaded(c)
    if not w then s.reason='world_unavailable' elseif not usable then s.reason='chunk_unavailable' end
    local body=usable and call(c,'getBodyDamage') or nil
    local st=usable and call(c,'getStats') or nil
    local md=usable and call(c,'getMoodles') or nil
    local inv=usable and call(c,'getInventory') or nil
    s.health=read(body,'getHealth','number','BodyDamage.getHealth')
    for k,native in pairs(stats) do
        local key=constant(CharacterStat,native)
        s.needs[k]=key and read(st,'get','number','Stats.get(CharacterStat.'..native..')',key) or unavailable('constant_unavailable','CharacterStat.'..native)
    end
    s.conditions.asleep=usable and read(c,'isAsleep','boolean','IsoGameCharacter.isAsleep') or unavailable(s.reason)
    s.conditions.knocked_down=usable and read(c,'isKnockedDown','boolean','IsoGameCharacter.isKnockedDown') or unavailable(s.reason)
    if s.conditions.dead.known and s.conditions.dead.value then
        s.conditions.incapacitated=known(true,'IsoGameCharacter.isDead')
    elseif s.conditions.knocked_down.known and s.conditions.knocked_down.value then
        s.conditions.incapacitated=known(true,'IsoGameCharacter.isKnockedDown')
    else s.conditions.incapacitated=unknown('no_complete_incapacitation_api') end
    s.conditions.incapacitated.scope='dead_or_native_knocked_down_only'
    s.conditions.infected=read(body,'IsInfected','boolean','BodyDamage.IsInfected')
    s.conditions.bleeding_parts=read(body,'getNumPartsBleeding','number','BodyDamage.getNumPartsBleeding')
    s.conditions.scratched_parts=read(body,'getNumPartsScratched','number','BodyDamage.getNumPartsScratched')
    s.conditions.bitten_parts=read(body,'getNumPartsBitten','number','BodyDamage.getNumPartsBitten')
    s.wounds=bodyParts(body)
    s.inventory.capacity=usable and read(c,'getMaxWeight','number','IsoGameCharacter.getMaxWeight') or unavailable(s.reason)
    s.inventory.item_count=read(call(inv,'getItems'),'size','number','ItemContainer.getItems.size')
    local count=s.inventory.item_count
    if count.known and integer(count.value) and count.value<=bounded('maxInventoryItems',256,1,1024) then
        s.inventory.carried_weight=read(c,'getInventoryWeight','number','IsoGameCharacter.getInventoryWeight')
    else s.inventory.carried_weight=unknown(count.known and 'inventory_budget_or_invalid_count' or 'inventory_unavailable','IsoGameCharacter.getInventoryWeight') end
    for _,name in ipairs(moodles) do
        local key=constant(MoodleType,name)
        s.moodles[name]=key and read(md,'getMoodleLevel','number','Moodles.getMoodleLevel('..name..')',key) or unavailable('constant_unavailable','MoodleType.'..name)
    end
    s.available=usable==true; s.active=s.available and s.conditions.dead.known and not s.conditions.dead.value
    classify(s)
    local since={}
    for _,k in ipairs(stateNames) do
        if s.states[k].known and s.states[k].value then
            since[k]=previous and previous.since[k] or at
            s.state_duration_ms[k]=at-since[k]
        end
    end
    eventsFor(id,s,previous and previous.snapshot)
    cache[id]={character=c,snapshot=s,since=since}
    return copy(s)
end
function S.getSnapshot(id)
    if not checkWorld() then return nil,'world_unavailable' end
    local c=actor(id); local r=cache[id]; local at=stamp()
    if not c then S.clearSnapshot(id); return nil,'instance_unavailable' end
    if not r or r.character~=c or at<r.snapshot.captured_at_ms
        or at-r.snapshot.captured_at_ms>=bounded('intervalMs',1000,100,60000)
        or r.snapshot.available~=(worldSeen~=nil and loaded(c))
        or r.snapshot.conditions.dead.value~=call(c,'isDead') then return S.updateSnapshot(id) end
    local result=copy(r.snapshot); result.threat=threat(id,c,at); return result
end
function S.getEvents(id,afterSequence)
    checkWorld(); local result={}
    if not S.getSnapshot(id) then return result end
    for _,v in ipairs(history[id] or {}) do if not finite(afterSequence) or v.sequence>afterSequence then result[#result+1]=copy(v) end end
    return result
end
function S.clearSnapshot(id)
    if id~=nil then cache[id]=nil; history[id]=nil; threats[id]=nil end
end
function S.getCatalog()
    local r={schema_version=1,needs=copy(stats),states=copy(stateNames),actions={},scales={
        health={minimum=0,maximum=100,unit='native_health'},
        hunger={minimum=0,maximum=1},thirst={minimum=0,maximum=1},fatigue={minimum=0,maximum=1},
        endurance={minimum=0,maximum=1},stress={minimum=0,maximum=1},
        pain={minimum=0,maximum=100},panic={minimum=0,maximum=100},
        temperature={minimum=20,maximum=40,unit='celsius'},inventory={unit='native_weight'}}}
    for _,name in ipairs({'EAT','DRINK','REST','BANDAGE','SEEK_SAFETY'}) do
        r.actions[name]={executable=false,status='future_action_contract',reason='not_implemented_by_survival_observer'}
    end
    r.needs_policy=S.getNeedsPolicy()
    for _,name in ipairs({'EAT','DRINK','REST'}) do
        r.actions[name].status='excluded_by_project_policy'; r.actions[name].rl_objective=false
    end
    local inventory=ArayHuman.Inventory
    if inventory and inventory.getCapabilities then
        r.actions.BANDAGE=inventory.getCapabilities().BANDAGE
    end
    return r
end
function S.getNeedsPolicy()
    local r={endurance={preserved=true,observe_for_movement=true},rewards={food=false,water=false,rest=false}}
    for _,name in ipairs({'hunger','thirst','fatigue'}) do
        r[name]={requested_disabled=true,rl_objective=false,
            effective_disabled={known=false,status='unsupported',reason='UNSUPPORTED_isolated_native_need_switch'}}
    end
    return r
end
local function tick()
    if not checkWorld() then return end
    local at=stamp()
    if lastCycle==nil or at<lastCycle or (cursor>#scheduled and at-lastCycle>=bounded('intervalMs',1000,100,60000)) then
        scheduled=global(ArayHuman.rosterSnapshot) or {}; cursor=1; lastCycle=at
        local present={}
        for _,entry in ipairs(scheduled) do if entry.uuid then present[entry.uuid]=true end end
        for id in pairs(cache) do if not present[id] then S.clearSnapshot(id) end end
    end
    for _=1,bounded('maxPerTick',2,1,4) do
        local entry=scheduled[cursor]; if not entry then break end
        cursor=cursor+1; if entry.uuid then S.getSnapshot(entry.uuid) end
    end
end
if Events and Events.OnTick then Events.OnTick.Add(tick) end
