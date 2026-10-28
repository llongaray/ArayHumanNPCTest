-- Explicit, UUID-owned item actions over vanilla timed actions/helpers. SP only.
require "TimedActions/ISBaseTimedAction"
require "TimedActions/ISGrabItemAction"
require "TimedActions/ISTransferAction"
require "TimedActions/ISApplyBandage"
ArayHuman=ArayHuman or {}
ArayHuman.Inventory={}
local I=ArayHuman.Inventory
I.actions={PICKUP_ITEM=true,LOOT_CONTAINER=true,TRANSFER_ITEM=true,BANDAGE=true}
I.config={maxItems=128,maxObjects=64,maxCandidates=256,tokenMs=10000,timeoutMs=15000,range=1.5}
local registry,locks,itemOwners,results={},{},{},{}
local worldSeen,serial=nil,0
local function copy(v)
    if type(v)~='table' then return v end
    local r={}; for k,x in pairs(v) do r[k]=copy(x) end; return r
end
local function call(o,k,...)
    local args={...}; local ok,v=pcall(function() if o and o[k] then return o[k](o,unpack(args)) end end)
    if ok then return v end
end
local function finite(v) return type(v)=='number' and v==v and v~=math.huge and v~=-math.huge end
local function validCount(v,limit) return finite(v) and v>=0 and v==math.floor(v) and v<=limit end
local function now() return getTimestampMs() end
local function world()
    local core=getCore and getCore(); local w=getWorld and getWorld()
    local name=call(w,'getWorld'); local mode=call(core,'getGameMode')
    if name and mode then return tostring(mode)..'/'..tostring(name) end
end
local function sp() return isClient and isServer and isClient()==false and isServer()==false end
local function square(x,y,z) return call(getCell and getCell(),'getGridSquare',x,y,z) end
local function actor(id)
    if type(id)~='string' or #id~=36 or id:sub(9,9)~='-' or id:sub(14,14)~='-'
        or id:sub(19,19)~='-' or id:sub(24,24)~='-' or not id:match('^%x+%-%x+%-%x+%-%x+%-%x+$') then return nil end
    local c=ArayHuman.getNpcByUuid and ArayHuman.getNpcByUuid(id); local md=call(c,'getModData')
    if not c or not md or md.ARAY_Uuid~=id or not md.ARAY_IsNPC or call(c,'isNPC')~=true
        or call(c,'isDead')~=false or c==ArayHuman.getLocalPlayer() then return nil end
    local x,y,z=call(c,'getX'),call(c,'getY'),call(c,'getZ')
    if not finite(x) or not finite(y) or not finite(z) then return nil end
    local sq=call(c,'getCurrentSquare')
    if sq and square(math.floor(x),math.floor(y),math.floor(z))==sq then return c end
end
local function isType(o,k) return o and instanceof(o,k)==true end
local function member(list,obj,limit)
    local count=call(list,'size')
    if not finite(count) or count<0 or count~=math.floor(count) or count>limit then return false end
    for n=0,count-1 do if call(list,'get',n)==obj then return true end end
    return false
end
local function owns(container,item) return container and call(item,'getContainer')==container
    and member(call(container,'getItems'),item,I.config.maxItems) end
local function idle(c)
    return call(c,'getCurrentStateName')=='IdleState' and call(c,'isClimbing')==false
        and call(c,'isKnockedDown')==false and call(c,'isPerformingAttackAnimation')==false
        and call(c,'isPerformingShoveAnimation')==false
end
local function queue(c)
    local q=ISTimedActionQueue and ISTimedActionQueue.queues and ISTimedActionQueue.queues[c]
    return q and q.queue
end
local function removeOwned(r)
    if r.character==ArayHuman.getLocalPlayer() then return end
    local q=queue(r.character)
    if q then for n=#q,1,-1 do if q[n]==r.native then table.remove(q,n) end end end
end
function I.cancel(id,reason)
    local r=locks[id]; if not r or r.stopRequested then return false end
    r.cancelled=r.cancelled or reason or 'cancelled' -- invalidate mutating entry points FIRST
    r.stopRequested=true
    if r.character~=ArayHuman.getLocalPlayer() and r.native and r.native.forceStop then pcall(function() r.native:forceStop() end) end
    return true
end
local function checkWorld()
    local w=world()
    if w~=worldSeen then
        for id in pairs(locks) do I.cancel(id,'world_changed') end
        registry={}; results={}; worldSeen=w
    end
    return w
end
local function reachable(c,sq,x,y)
    if not sq or square(sq:getX(),sq:getY(),sq:getZ())~=sq or math.floor(c:getZ())~=sq:getZ() then return false end
    x=x or sq:getX()+.5; y=y or sq:getY()+.5
    if not finite(x) or not finite(y) or (c:getX()-x)^2+(c:getY()-y)^2>I.config.range^2 then return false end
    local a=c:getCurrentSquare()
    if a==sq then return true end
    local p=ArayHuman.Perception
    return p and p.edgePassable(a,sq)==true -- adjacent cardinal edges only
end
local function staticContainer(c,container,owner)
    if not container or not owner or isType(owner,'IsoGameCharacter') or isType(owner,'IsoDeadBody')
        or isType(owner,'BaseVehicle') or isType(owner,'IsoWorldInventoryObject') then return false end
    -- Only ordinary world furniture. No worn bags, vehicles, corpses or appliances.
    local name=call(call(owner,'getClass'),'getSimpleName')
    if name~='IsoObject' and name~='IsoThumpable' then return false end
    if name=='IsoThumpable' and call(owner,'isLockedToCharacter',c)~=false then return false end
    local sq=call(owner,'getSquare'); local index=call(owner,'getObjectIndex')
    if not finite(index) or index<0 or not reachable(c,sq) or call(container,'getParent')~=owner
        or call(container,'getSourceGrid')~=sq or call(container,'getContainingItem')~=nil
        or call(container,'isExistYet')~=true then return false end
    if not member(call(sq,'getObjects'),owner,I.config.maxObjects) then return false end
    local kind=call(container,'getType')
    if kind~='crate' and kind~='counter' and kind~='shelves' and kind~='locker' and kind~='wardrobe' then return false end
    local count=call(owner,'getContainerCount')
    if not finite(count) or count<1 or count>4 then return false end
    for n=0,count-1 do if call(owner,'getContainerByIndex',n)==container then return true end end
    return false
end
local function safeItem(item)
    local kind=call(item,'getType')
    return item and finite(call(item,'getID')) and type(call(item,'getFullType'))=='string'
        and call(item,'IsInventoryContainer')==false and not isType(item,'Radio')
        and kind~='CandleLit' and kind~='Lantern_HurricaneLit' and call(item,'getIsCraftingConsumed')==false
end
local function threatSafe(id)
    local p=ArayHuman.Perception; local o=p and p.observeThreats(id)
    if not o or o.uuid~=id or o.world_id~=worldSeen or o.active~=true or not o.scan or o.scan.complete~=true
        or not finite(o.captured_at_ms) or o.captured_at_ms>now() or now()-o.captured_at_ms>1000 then return false,'threat_unconfirmed' end
    if o.immediate then return false,'emergency_priority' end
    return true
end
local function api(kind)
    if not sp() then return false end
    if kind=='PICKUP_ITEM' then return ISGrabItemAction and ISGrabItemAction.new and ISGrabItemAction.perform end
    if kind=='BANDAGE' then return ISApplyBandage and ISApplyBandage.new and ISApplyBandage.complete
        and ISHealthPanel and ISHealthPanel.DidPatientMove end
    return ISTransferAction and ISTransferAction.transferItem and ISBaseTimedAction and ISBaseTimedAction.new
end
function I.getCapabilities()
    local r={}
    for kind in pairs(I.actions) do r[kind]={executable=api(kind) and true or false,
        status=api(kind) and 'experimental_native_singleplayer' or 'UNSUPPORTED_native_action_or_authority',
        manual_validation='pending'} end
    return r
end
local function validate(id,r,threat)
    local c=actor(id)
    if not c or r.character~=c or r.world~=worldSeen then return false,'instance_or_world_changed' end
    if not sp() or not api(r.kind) then return false,'UNSUPPORTED_native_action_or_authority' end
    if r.expires<=now() then return false,'inventory_token_expired' end
    if not safeItem(r.item) or call(r.item,'getID')~=r.itemId then return false,'item_changed' end
    local inv=call(c,'getInventory')
    if not inv or (r.src~=inv and r.dest~=inv) then return false,'ownership_invalid' end
    if r.kind=='PICKUP_ITEM' then
        local sq=call(r.ground,'getSquare')
        local wx,wy,wz=call(r.ground,'getWorldPosX'),call(r.ground,'getWorldPosY'),call(r.ground,'getWorldPosZ')
        if call(r.ground,'getItem')~=r.item or call(r.item,'getWorldItem')~=r.ground
            or not member(call(sq,'getWorldObjects'),r.ground,I.config.maxItems)
            or not finite(wx) or not finite(wy) or not finite(wz) or math.abs(wz-c:getZ())>.5
            or not reachable(c,sq,wx,wy) then return false,'ground_item_unavailable' end
    else
        if not owns(r.src,r.item) then return false,'source_item_unavailable' end
        if r.src~=inv and not staticContainer(c,r.src,r.owner) then return false,'source_container_unavailable' end
        if r.dest~=inv and not staticContainer(c,r.dest,r.owner) then return false,'destination_container_unavailable' end
    end
    if r.src==inv and (call(inv,'isRemoveItemAllowed',r.item)~=true or call(c,'isEquipped',r.item)~=false
        or call(c,'isHandItem',r.item)~=false or call(r.item,'isFavorite')~=false
        or call(r.item,'getAttachedSlot')~=-1) then return false,'item_in_use_or_protected' end
    if r.kind=='BANDAGE' then
        local part=call(call(c,'getBodyDamage'),'getBodyParts')
        if call(part,'get',r.partIndex)~=r.part or call(r.part,'getIndex')~=r.partIndex
            or call(r.part,'HasInjury')~=true or call(r.part,'bandaged')~=false
            or call(r.item,'isCanBandage')~=true or call(r.item,'isInfected')~=false
            or not finite(call(r.item,'getBandagePower'))
            or tostring(call(r.item,'getType')):find('Dirty',1,true) then return false,'bandage_or_wound_invalid' end
    else
        if call(r.dest,'hasRoomFor',c,r.item)~=true or call(r.dest,'isItemAllowed',r.item)~=true then return false,'capacity_or_item_rejected' end
        if r.dest==inv then
            local weight,capacity,itemWeight=call(c,'getInventoryWeight'),call(c,'getMaxWeight'),call(r.item,'getActualWeight')
            if not finite(weight) or not finite(capacity) or not finite(itemWeight) or itemWeight<0
                or weight+itemWeight>capacity then return false,'carry_capacity_exceeded' end
        end
        if r.src and call(r.src,'isRemoveItemAllowed',r.item)~=true then return false,'source_locked' end
        if r.src==inv and (call(c,'isEquipped',r.item)~=false or call(c,'isHandItem',r.item)~=false
            or call(r.item,'isFavorite')~=false or call(r.item,'getAttachedSlot')~=-1) then return false,'item_in_use_or_protected' end
    end
    if threat then return threatSafe(id) end
    return true
end
local function register(id,c,kind,item,src,dest,owner,ground,part,index)
    local list=registry[id] or {}; registry[id]=list
    for _,r in ipairs(list) do
        if r.kind==kind and r.item==item and r.itemId==call(item,'getID') and r.src==src and r.dest==dest and r.part==part and r.ground==ground then
            r.expires=now()+I.config.tokenMs; return r
        end
    end
    if #list>=I.config.maxCandidates then return nil end
    serial=serial+1
    local r={token='inventory:'..serial,world=worldSeen,character=c,kind=kind,item=item,
        itemId=call(item,'getID'),src=src,dest=dest,owner=owner,ground=ground,part=part,partIndex=index,expires=now()+I.config.tokenMs}
    list[#list+1]=r; return r
end
local function addCandidate(out,id,c,kind,item,src,dest,owner,ground,part,index)
    if out.scan.candidates_examined>=I.config.maxCandidates then out.scan.complete=false; out.scan.reason='candidate_budget'; return end
    out.scan.candidates_examined=out.scan.candidates_examined+1
    local r=register(id,c,kind,item,src,dest,owner,ground,part,index)
    if not r then out.scan.complete=false; out.scan.reason='candidate_budget'; return end
    local ok=validate(id,r,false)
    if ok then out.candidates[#out.candidates+1]={uuid=id,world_id=worldSeen,target_id=r.token,action=kind,
        item_id=id..':item:'..r.itemId,native_item_id=r.itemId,full_type=call(item,'getFullType'),quantity=1,part_index=index,expires_at_ms=r.expires,
        source=ground and 'ground' or src==call(c,'getInventory') and 'npc_inventory' or 'world_container',
        container_position=owner and {x=owner:getSquare():getX(),y=owner:getSquare():getY(),z=owner:getSquare():getZ(),object_index=call(owner,'getObjectIndex')} or nil} end
end
function I.getSnapshot(id)
    checkWorld(); local c=actor(id)
    if not worldSeen or not c then return nil,'instance_unavailable' end
    local out={uuid=id,world_id=worldSeen,captured_at_ms=now(),items={},containers={},candidates={},
        needs_policy=ArayHuman.Survival and ArayHuman.Survival.getNeedsPolicy(),
        available=false,scan={complete=true,items_examined=0,objects_examined=0,candidates_examined=0},capabilities=I.getCapabilities()}
    local inv=call(c,'getInventory'); local list=call(inv,'getItems'); local count=call(list,'size')
    if not validCount(count,I.config.maxItems) then out.scan.complete=false; out.scan.reason='inventory_budget_or_unavailable'; return out end
    out.available=true
    local own={}
    for n=0,count-1 do
        local item=call(list,'get',n); out.scan.items_examined=out.scan.items_examined+1
        if owns(inv,item) and finite(call(item,'getID')) then
            own[#own+1]=item; out.items[#out.items+1]={item_id=id..':item:'..tostring(call(item,'getID')),native_item_id=call(item,'getID'),full_type=call(item,'getFullType'),
                weight=call(item,'getActualWeight'),bandage=call(item,'isCanBandage')==true}
        end
    end
    out.weight=call(c,'getInventoryWeight'); out.capacity=call(c,'getMaxWeight')
    -- Reuse stable capability tokens until expiry; stale entries cannot accumulate forever.
    local entries=registry[id] or {}
    for n=#entries,1,-1 do if entries[n].expires<now() or entries[n].character~=c then table.remove(entries,n) end end
    local bodies=call(call(c,'getBodyDamage'),'getBodyParts'); local bodyCount=call(bodies,'size')
    if not validCount(bodyCount,32) then bodyCount=0; out.scan.complete=false end
    for _,item in ipairs(own) do
        if call(item,'isCanBandage')==true then for n=0,bodyCount-1 do
            local part=call(bodies,'get',n)
            if call(part,'HasInjury')==true then addCandidate(out,id,c,'BANDAGE',item,inv,inv,nil,nil,part,n) end
        end end
    end
    for _,d in ipairs({{0,0},{1,0},{-1,0},{0,1},{0,-1}}) do
        local sq=square(math.floor(c:getX())+d[1],math.floor(c:getY())+d[2],math.floor(c:getZ()))
        if sq and reachable(c,sq) then
            local ground=call(sq,'getWorldObjects'); local size=call(ground,'size')
            if not validCount(size,I.config.maxItems) then out.scan.complete=false else
                for n=0,size-1 do
                    if out.scan.items_examined>=I.config.maxItems then out.scan.complete=false; break end
                    out.scan.items_examined=out.scan.items_examined+1
                    local obj=call(ground,'get',n); local item=call(obj,'getItem')
                    addCandidate(out,id,c,'PICKUP_ITEM',item,nil,inv,nil,obj)
                end
            end
            local objects=call(sq,'getObjects'); local sizeO=call(objects,'size')
            if not validCount(sizeO,I.config.maxObjects) then out.scan.complete=false else
                for n=0,sizeO-1 do
                    if out.scan.objects_examined>=I.config.maxObjects then out.scan.complete=false; break end
                    out.scan.objects_examined=out.scan.objects_examined+1
                    local obj=call(objects,'get',n); local cnt=call(obj,'getContainerCount')
                    if not validCount(cnt,4) then cnt=0; out.scan.complete=false end
                    for k=0,cnt-1 do
                        local container=call(obj,'getContainerByIndex',k)
                        if staticContainer(c,container,obj) then
                            out.containers[#out.containers+1]={x=sq:getX(),y=sq:getY(),z=sq:getZ(),object_index=call(obj,'getObjectIndex'),container_index=k}
                            local items=call(container,'getItems'); local num=call(items,'size')
                            if not validCount(num,I.config.maxItems) then out.scan.complete=false else for j=0,num-1 do
                                if out.scan.items_examined>=I.config.maxItems then out.scan.complete=false; break end
                                out.scan.items_examined=out.scan.items_examined+1
                                addCandidate(out,id,c,'LOOT_CONTAINER',call(items,'get',j),container,inv,obj)
                            end end
                            for _,item in ipairs(own) do
                                if out.scan.candidates_examined>=I.config.maxCandidates then out.scan.complete=false; break end
                                addCandidate(out,id,c,'TRANSFER_ITEM',item,inv,container,obj)
                            end
                        end
                    end
                end
            end
        elseif not sq then out.scan.complete=false end
    end
    return out
end
function I.resolveCandidate(id,kind,token)
    checkWorld()
    for _,r in ipairs(registry[id] or {}) do if r.token==token and r.kind==kind then
        local ok,why=validate(id,r,true); if ok then return r end; return nil,why
    end end
    return nil,'inventory_target_invalid'
end
function I.busy(id) return locks[id]~=nil end
local function nativeReleased(r)
    local actions=call(r.character,'getCharacterActions'); local count=call(actions,'size')
    if not validCount(count,16) then r.retirement='native_stack_unavailable'; return false end
    for n=0,count-1 do if call(actions,'get',n)==r.native.action then r.retirement='native_action_active'; return false end end
    r.retirement='released'
    return true
end
local function finish(id,r,outcome)
    if locks[id]~=r then return end
    local c=r.character; local valid=worldSeen==r.world and actor(id)==c
    local item=r.target.item; local inv=call(c,'getInventory')
    local observations={duration_ms=now()-r.at,item_id=id..':item:'..r.target.itemId,native_item_id=r.target.itemId,full_type=call(item,'getFullType'),
        quantity=valid and 0 or nil,quantity_known=valid,weight_before=r.weight,weight_after=valid and call(c,'getInventoryWeight') or nil,
        health_before=r.health,health_after=valid and call(call(c,'getBodyDamage'),'getHealth') or nil,
        mutation_attempted=r.mutated==true,native_error=r.native_error}
    if valid and r.target.part then observations.bandaged=call(r.target.part,'bandaged'); observations.bandaged_known=type(observations.bandaged)=='boolean' end
    if valid and r.target.kind=='BANDAGE' then
        observations.item_removed_from_inventory=not owns(inv,item)
        if r.completeDone and observations.bandaged==true and observations.item_removed_from_inventory then
            observations.quantity=1; observations.quantity_consumed=1
        end
    end
    if valid and r.target.kind~='BANDAGE' and owns(r.target.dest,item)
        and (not r.target.src or not owns(r.target.src,item)) and call(item,'getWorldItem')==nil then observations.quantity=1 end
    if not r.cancelled and outcome=='success' then
        if r.target.kind=='BANDAGE' then
            if observations.bandaged~=true or owns(inv,item) then outcome='native_bandage_unconfirmed' end
        elseif observations.quantity~=1 then outcome='native_transfer_unconfirmed' end
    end
    local result={uuid=id,world_id=r.world,action=r.target.kind,action_id=r.actionId,result=outcome,observations=observations}
    local list=results[id] or {}; if valid then results[id]=list; list[#list+1]=copy(result); while #list>16 do table.remove(list,1) end end
    if itemOwners[item]==r then itemOwners[item]=nil end
    locks[id]=nil
    print('[ARAY-INVENTORY] uuid='..id..' action_id='..r.actionId..' action='..r.target.kind..' result='..outcome..' quantity='..tostring(observations.quantity)..' duration_ms='..observations.duration_ms)
    if ArayHuman.Survival and valid then ArayHuman.Survival.updateSnapshot(id) end
    if r.callback then r.callback(outcome,r.generation,observations) end
end
function I.start(id,target,generation,callback,actionId)
    checkWorld(); local c=actor(id)
    if type(target)~='table' then return false,'inventory_target_invalid' end
    local registered=false
    for _,entry in ipairs(registry[id] or {}) do if entry==target then registered=true end end
    if not registered then return false,'inventory_target_invalid' end
    if not c or target.character~=c then return false,'instance_unavailable' end
    local ok,why=validate(id,target,true); if not ok then return false,why end
    if locks[id] or itemOwners[target.item] or (ArayHuman.Physical and ArayHuman.Physical.busy(id)) then return false,'inventory_busy' end
    if not idle(c) or call(c,'hasTimedActions')~=false or (queue(c) and #queue(c)>0) then return false,'foreign_action_or_animation' end
    if call(call(c,'getCharacterActions'),'size')~=0 then return false,'UNSUPPORTED_native_action_stack' end
    local r={character=c,world=worldSeen,target=target,generation=generation,callback=callback,actionId=actionId,
        at=now(),weight=call(c,'getInventoryWeight'),health=call(call(c,'getBodyDamage'),'getHealth')}
    locks[id]=r; itemOwners[target.item]=r
    local constructed,native=pcall(function()
        if target.kind=='PICKUP_ITEM' then return ISGrabItemAction:new(c,target.ground,50) end
        if target.kind=='BANDAGE' then return ISApplyBandage:new(c,c,target.item,target.part,true) end
        local a=ISBaseTimedAction:new(c); a.Type='ArayHumanItemTransfer'; a.maxTime=50
        a.start=function(self) self:setActionAnim('Loot'); self:setOverrideHandModels(nil,nil); c:reportEvent('EventLootItem') end
        a.isValid=function() return true end
        a.perform=function(self)
            ISTransferAction:transferItem(c,target.item,target.src,target.dest,nil)
            ISBaseTimedAction.perform(self)
        end
        a.complete=function() return true end
        return a
    end)
    if not constructed or not native then finish(id,r,'native_constructor_failed'); return false,'native_constructor_failed' end
    r.native=native
    local function owned() return locks[id]==r and r.world==world() and actor(id)==c end
    local function canMutate()
        if not owned() or r.cancelled or now()-r.at>I.config.timeoutMs then return false end
        local valid,reason=validate(id,target,true)
        if not valid then r.cancelled=reason; return false end
        return true
    end
    -- Guard native entry points, including complete: delayed callbacks cannot consume an item.
    for _,name in ipairs({'start','update','isValid','waitToStart','perform','complete','transferItem'}) do
        local old=native[name]
        if old then
            local methodName=name
            native[name]=function(self,...)
                if not owned() or r.cancelled then return false end
                local mutating=methodName=='perform' or (methodName=='complete' and target.kind=='BANDAGE') or methodName=='transferItem'
                -- transferItem is nested inside vanilla pickup perform; do not claim success twice.
                if mutating and methodName~='transferItem' and r[methodName..'Done'] then return false end
                local bandageCleanup=methodName=='perform' and target.kind=='BANDAGE' and r.completeDone
                if mutating and not bandageCleanup and not canMutate() then return false end
                if methodName=='isValid' then local good,reason=validate(id,target,false); if not good then r.cancelled=reason; return false end end
                if mutating then r.mutated=true; r[methodName..'Done']=true end
                local success,value=pcall(old,self,...)
                if not success or (methodName=='complete' and value==false) then
                    r.cancelled='native_api_failed'; r.native_error=methodName..':'..tostring(value); return false
                end
                if methodName=='perform' then r.performed=true end
                return value
            end
        end
    end
    local oldStop=native.stop
    native.stop=function(self,...)
        if not owned() or r.stopped then return end
        r.stopped=true; r.cancelled=r.cancelled or 'native_stopped'
        local ours=false
        for _,v in ipairs(queue(c) or {}) do if v==native then ours=true end end
        if oldStop and ours then pcall(oldStop,self,...) end
    end
    -- B42 calls complete separately from perform for bandaging. Both are observed below.
    local added=pcall(function() ISTimedActionQueue.add(native) end)
    if not added then
        I.cancel(id,'native_queue_failed')
        if idle(c) then removeOwned(r); finish(id,r,'native_queue_failed') end
        return false,'native_queue_failed'
    end
    return true
end
function I.update()
    checkWorld()
    for id,r in pairs(locks) do
        local current=actor(id)
        if current~=r.character or r.world~=worldSeen then I.cancel(id,'instance_or_world_changed') end
        if now()-r.at>=I.config.timeoutMs then I.cancel(id,'inventory_timeout') end
        if not r.cancelled and not r.performed and (not r.lastValidation or now()-r.lastValidation>=250) then
            r.lastValidation=now()
            local good,why=validate(id,r.target,true); if not good then I.cancel(id,why) end
        end
        if r.cancelled and not r.stopRequested then I.cancel(id,r.cancelled) end
        if r.cancelled and (r.world~=worldSeen or current~=r.character) then
            removeOwned(r); finish(id,r,r.cancelled)
        elseif r.cancelled then
            if idle(r.character) and nativeReleased(r) then removeOwned(r); finish(id,r,r.cancelled) end
        elseif r.performed and (r.target.kind~='BANDAGE' or r.completeDone) and idle(r.character) and nativeReleased(r) then removeOwned(r); finish(id,r,'success') end
    end
end
function I.getResult(id,actionId)
    checkWorld(); for _,r in ipairs(results[id] or {}) do if r.action_id==actionId then return copy(r) end end
end
function I.getState(id)
    checkWorld(); local r=locks[id]; if not r then return nil end
    return {uuid=id,world_id=r.world,action_id=r.actionId,action=r.target.kind,
        state=r.cancelled and 'CANCEL_PENDING' or 'NATIVE_RUNNING',reason=r.cancelled,
        started_at_ms=r.at,duration_ms=now()-r.at,native_retirement=r.retirement}
end
-- UI/chat read path: principal native inventory only, no nearby-container scans or mutations.
function I.readInventory(id)
    checkWorld(); local c=actor(id)
    if not c then return nil,'instance_unavailable' end
    local out={uuid=id,world_id=worldSeen,captured_at_ms=now(),items={},complete=false,read_only=true,
        weight={known=false},capacity={known=false},scope='principal_inventory_no_nested_bags'}
    local weight,capacity=call(c,'getInventoryWeight'),call(c,'getMaxWeight')
    if finite(weight) then out.weight={known=true,value=weight} end
    if finite(capacity) then out.capacity={known=true,value=capacity} end
    local inv=call(c,'getInventory'); local items=call(inv,'getItems'); local count=call(items,'size')
    if not validCount(count,I.config.maxItems) then out.reason='inventory_budget_or_api'; return out end
    out.complete=true
    for i=0,count-1 do
        local item=call(items,'get',i)
        if call(item,'getContainer')~=inv then out.complete=false else
            local quantity=call(item,'getCount'); local kind=call(item,'getFullType'); local nativeId=call(item,'getID')
            if type(kind)~='string' or not finite(nativeId) then out.complete=false else
                local q={known=false}; if validCount(quantity,1000000) then q={known=true,value=quantity} end
                out.items[#out.items+1]={item_id=id..':item:'..nativeId,full_type=kind,quantity=q,
                    weight={known=finite(call(item,'getActualWeight')),value=call(item,'getActualWeight')}}
            end
        end
    end
    print('[ARAY] event=inventory_snapshot uuid='..id..' items='..#out.items..' complete='..tostring(out.complete))
    return out
end
