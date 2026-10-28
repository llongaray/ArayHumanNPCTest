"""Vanilla B42 pickup/transfer/bandage Lua + production adapter, simulated Java."""
import pytest

from test_survival_observer import observer, nav, physical, safety, lua
from test_executor import NATIVE


@pytest.fixture
def inventory(observer):
    r = observer
    r.execute('''
        I=ArayHuman.Inventory
        local oldList=list
        list=function(values)
            local result=oldList(values)
            result.contains=function(_,value) for _,v in ipairs(values) do if v==value then return true end end; return false end
            result.isEmpty=function() return #values==0 end
            return result
        end
        isClient=function() return false end; isServer=function() return false end
        ISBaseObject=ISBaseTimedAction
        function ISBaseTimedAction.new(self,c) return setmetatable({character=c},{__index=self}) end
        function ISBaseTimedAction:setActionAnim(name) self.character.state="LootState"; self.anim=name end
        function ISBaseTimedAction:setAnimVariable() end
        function ISBaseTimedAction:setOverrideHandModels() end
        function ISBaseTimedAction:getJobDelta() return .5 end
        function ISBaseTimedAction:setCurrentTime() end
        function ISBaseTimedAction:isTimedActionInstant() return false end
        local add=ISTimedActionQueue.add
        ISTimedActionQueue.add=function(a)
            add(a)
            table.insert(a.character.javaActions,a.action)
            a.action.stopTimedActionAnim=function() end
            a.action.setLoopedAction=function() end
            a.action.setTime=function() end
        end
        local oldStop=ISBaseTimedAction.stop; local oldPerform=ISBaseTimedAction.perform
        local function releaseJava(a)
            for n=#a.character.javaActions,1,-1 do if a.character.javaActions[n]==a.action then table.remove(a.character.javaActions,n) end end
        end
        function ISBaseTimedAction:stop() oldStop(self); releaseJava(self) end
        function ISBaseTimedAction:perform() oldPerform(self); releaseJava(self) end
        ISTimedActionQueue.getTimedActionQueue=function(c)
            assert(c~=player)
            local q=ISTimedActionQueue.queues[c] or {queue={}}
            ISTimedActionQueue.queues[c]=q; return q
        end
        ISInventoryPage={}; ISHealthPanel={
            DidPatientMove=function(c,p) assert(c~=player and c==p); return false end,
            getBandageType=function() return "Hand" end,
            setBodyPartActionForPlayer=function(c) assert(c~=player) end}
        getPlayerInventory=forbidden; getPlayerLoot=forbidden
        getPlayerData=function() return nil end
        getText=function(s) return s end
        createItemTransaction=function(c) assert(c~=player); return 1 end
        removeItemTransaction=function() end
        CharacterActionAnims={Bandage="Bandage"}; CharacterTrait={HEMOPHOBIC="Hemophobic"}
        Perks={Doctor="Doctor"}; BodyPartType={Groin=10,ToIndex=function(v) return v end}
        Metabolics={LightDomestic="LightDomestic"}
        ZombRandFloat=function(a,b) return (a+b)/2 end
        syncBodyPart=function() end; addXp=forbidden; syncPlayerStats=forbidden
        itemSerial=100; sourceRemovals=0; destinationAdds=0
        function newContainer(parent,items,kind,sq)
            local obj={parent=parent,items=items or {},kind=kind or "crate",sq=sq,capacity=50,exists=true}
            function obj:getParent() return self.parent end
            function obj:getContainingItem() return nil end
            function obj:getSourceGrid() return self.sq end
            function obj:isExistYet() return self.exists end
            function obj:getType() return self.kind end
            function obj:getItems() return list(self.items) end
            function obj:isRemoveItemAllowed() return not self.locked end
            function obj:isItemAllowed() return not self.reject end
            function obj:contains(item) for _,v in ipairs(self.items) do if v==item then return true end end; return false end
            function obj:hasRoomFor(c,item)
                assert(c~=player); local w=0; for _,v in ipairs(self.items) do w=w+v.weight end
                return w+item.weight<=self.capacity
            end
            function obj:DoRemoveItem(item)
                for n=#self.items,1,-1 do if self.items[n]==item then table.remove(self.items,n); item.container=nil; sourceRemovals=sourceRemovals+1 end end
            end
            obj.Remove=obj.DoRemoveItem
            function obj:AddItem(item)
                assert(type(item)=="table","resource creation forbidden")
                assert(not self:contains(item),"duplicate item")
                self.items[#self.items+1]=item; item.container=self; destinationAdds=destinationAdds+1
                return item
            end
            function obj:setDrawDirty() end
            return obj
        end
        function newItem(kind,container)
            itemSerial=itemSerial+1
            local item={id=itemSerial,kind=kind or "Nails",weight=.1,favorite=false,infected=false,container=container}
            function item:getID() return self.id end
            function item:getFullType() return "Base."..self.kind end
            function item:getType() return self.kind end
            function item:getActualWeight() return self.weight end
            function item:getContainer() return self.container end
            function item:getWorldItem() return self.world end
            function item:setWorldItem(v) self.world=v end
            function item:IsInventoryContainer() return self.bag==true end
            function item:getIsCraftingConsumed() return self.consumed==true end
            function item:isFavorite() return self.favorite end
            function item:getAttachedSlot() return self.slot or -1 end
            function item:isCanBandage() return self.kind=="Bandage" or self.kind=="BandageDirty" end
            function item:isInfected() return self.infected end
            function item:getBandagePower() return 1 end
            function item:getModule() return "Base" end
            function item:isAlcoholic() return false end
            function item:setJobDelta(v) self.delta=v end
            function item:setJobType(v) self.job=v end
            if container then table.insert(container.items,item) end
            return item
        end
        function groundItem(kind,x,y)
            local sq=squares[(x or 0)..":"..(y or 0)..":0"]
            local item=newItem(kind)
            local o={class="IsoWorldInventoryObject",sq=sq,item=item}
            function o:getSquare() return self.sq end
            function o:getItem() return self.item end
            function o:getWorldPosX() return self.sq:getX()+.5 end
            function o:getWorldPosY() return self.sq:getY()+.5 end
            function o:getWorldPosZ() return self.sq:getZ() end
            function o:setSquare(v) self.sq=v end
            function o:removeFromWorld() end
            function o:removeFromSquare()
                for n=#sq.worldObjects,1,-1 do if sq.worldObjects[n]==self then table.remove(sq.worldObjects,n) end end
            end
            item.world=o; sq.worldObjects[#sq.worldObjects+1]=o
            return item,o
        end
        function furniture(x,y,kind)
            local sq=squares[x..":"..y..":0"]
            local owner={class=kind or "IsoObject",sq=sq}
            function owner:getClass() return {getSimpleName=function() return self.class end} end
            function owner:getSquare() return self.sq end
            function owner:getObjectIndex() return self.removed and -1 or 0 end
            function owner:getContainerCount() return 1 end
            function owner:getContainerByIndex() return self.container end
            function owner:isLockedToCharacter(c) assert(c~=player); return self.locked==true end
            owner.container=newContainer(owner,{},"crate",sq)
            sq.objects[#sq.objects+1]=owner
            return owner.container,owner
        end
        for _,sq in pairs(squares) do
            sq.worldObjects={}
            function sq:getWorldObjects() return list(self.worldObjects) end
            function sq:transmitRemoveItemFromSquare() end
        end
        for _,c in pairs(roster) do
            c.javaActions={}
            function c:getCharacterActions() return list(self.javaActions) end
            function c:hasTimedActions() return #self.javaActions>0 end
            c.inv=newContainer(c,c.inventoryItems,"inventory",c:getCurrentSquare())
            function c:getInventory() return self.inv end
            function c:getInventoryWeight() local w=0; for _,item in ipairs(self.inv.items) do w=w+item.weight end; return w end
            function c:getSquare() return self:getCurrentSquare() end
            function c:getPlayerNum() return 0 end
            function c:isEquipped(item) return item.equipped==true end
            function c:isHandItem(item) return item.hand==true end
            function c:removeAttachedItem() end
            function c:reportEvent(name) self.lastEvent=name end
            function c:getPerkLevel() return 0 end
            function c:isTimedActionInstant() return false end
            function c:hasTrait() return false end
            function c:playSound() return nil end
            function c:playerVoiceSound() return nil end
            function c:getEmitter() return {isPlaying=function() return false end} end
            function c:setMetabolicTarget() end
            function c:stopOrTriggerSound() end
            for n,p in ipairs(c.parts) do
                local index=n-1
                function p:getIndex() return index end
                function p:HasInjury() return self.values.bleeding or self.values.hp<100 end
                function p:getBleedingTime() return self.values.bleeding and 1 or 0 end
                function p:isGetBandageXp() return false end
            end
            local body=c.body
            function body:SetBandaged(index,value)
                c.parts[index+1].values.bandaged=value
            end
        end
        function token(kind,id,item)
            for _,v in ipairs(assert(I.getSnapshot(id or uuidA)).candidates) do
                if v.action==kind and (not item or v.native_item_id==item.id) then return v.target_id end
            end
        end
        inventorySerial=0
        function requestItem(kind,target,id,source)
            inventorySerial=inventorySerial+1
            return L.submit({uuid=id or uuidA,world_id="Sandbox/"..worldName,action=kind,
                target_id=target,action_id="inventory-test:"..inventorySerial,source=source or "manual"})
        end
        function completeItem(id,performFirst)
            id=id or uuidA; local a=assert(queued(id))
            if a.Type=="ISApplyBandage" then
                if performFirst then a:perform(); a:complete() else a:complete(); a:perform() end
            else a:perform() end
            roster[id].state="IdleState"; I.update()
            return a
        end
    ''')
    root = NATIVE.parents[2]
    r.execute((root / "client/TimedActions/ISGrabItemAction.lua").read_text(encoding="utf-8"))
    r.execute((root / "shared/TimedActions/ISTransferAction.lua").read_text(encoding="utf-8"))
    r.execute((root / "shared/TimedActions/ISApplyBandage.lua").read_text(encoding="utf-8"))
    return r


def test_empty_inventory_and_native_capabilities(inventory):
    inventory.execute('''
        local s=assert(I.getSnapshot(uuidA))
        assert(#s.items==0 and s.weight==0 and s.capacity==12)
        assert(s.uuid==uuidA and s.world_id=="Sandbox/"..worldName)
        for _,k in ipairs({"PICKUP_ITEM","LOOT_CONTAINER","TRANSFER_ITEM","BANDAGE"}) do assert(s.capabilities[k].executable) end
        assert(not I.getSnapshot("npc_1") and not I.getSnapshot(nil))
        assert(not token("EAT") and not token("DRINK") and not token("REST"))
    ''')


def test_need_disable_request_is_honest_and_endurance_is_preserved(inventory):
    inventory.execute('''
        local c=roster[uuidA]; c.values.HUNGER=.7; c.values.THIRST=.8; c.values.FATIGUE=.9; c.values.ENDURANCE=.3
        local s=sample()
        for _,k in ipairs({"hunger","thirst","fatigue"}) do
            assert(s.needs_policy[k].requested_disabled and not s.needs_policy[k].rl_objective)
            assert(not s.needs_policy[k].effective_disabled.known and s.needs_policy[k].effective_disabled.status=="unsupported")
        end
        assert(s.needs.endurance.value==.3 and c.values.HUNGER==.7 and c.values.FATIGUE==.9)
        assert(not s.states.HUNGRY.planning_eligible and not s.states.THIRSTY.planning_eligible)
        for _,k in ipairs({"EAT","DRINK","REST"}) do assert(not S.getCatalog().actions[k].executable) end
        assert(S.getCatalog().actions.BANDAGE.executable)
        assert(not s.needs_policy.rewards.food and not s.needs_policy.rewards.rest)
    ''')


def test_pickup_vanilla_ownership_confirmation_and_weight(inventory):
    inventory.execute('''
        local item,obj=groundItem("Nails")
        local target=assert(token("PICKUP_ITEM",uuidA,item))
        assert(requestItem("PICKUP_ITEM",target))
        assert(roster[uuidA].lastEvent=="EventLootItem" and not roster[uuidA].inv:contains(item))
        completeItem()
        assert(roster[uuidA].inv:contains(item) and item:getWorldItem()==nil and obj:getSquare()==nil)
        local s=L.getState(uuidA); assert(s.state=="COMPLETED")
        local result=I.getResult(uuidA,s.action_id)
        assert(result.observations.quantity==1 and result.observations.weight_before==0 and result.observations.weight_after==.1)
        assert(result.observations.native_item_id==item.id and destinationAdds==1)
    ''')


def test_container_loot_and_transfer_use_same_real_item(inventory):
    inventory.execute('''
        local container=furniture(1,0)
        local item=newItem("Nails",container)
        local t=assert(token("LOOT_CONTAINER",uuidA,item))
        assert(requestItem("LOOT_CONTAINER",t)); completeItem()
        assert(roster[uuidA].inv:contains(item) and not container:contains(item))
        t=assert(token("TRANSFER_ITEM",uuidA,item))
        assert(requestItem("TRANSFER_ITEM",t)); completeItem()
        assert(container:contains(item) and not roster[uuidA].inv:contains(item))
        assert(destinationAdds==2 and sourceRemovals==2 and L.getState(uuidA).state=="COMPLETED")
    ''')


def test_full_inventory_and_changed_capacity_block_commit(inventory):
    inventory.execute('''
        local item=groundItem("Nails"); item.weight=13
        assert(not token("PICKUP_ITEM",uuidA,item))
        item.weight=1; local t=assert(token("PICKUP_ITEM",uuidA,item))
        assert(requestItem("PICKUP_ITEM",t)); local a=queued(uuidA)
        roster[uuidA].capacity=0
        a:perform(); roster[uuidA].state="IdleState"; I.update()
        assert(item:getWorldItem()~=nil and destinationAdds==0)
        assert(L.getState(uuidA).state=="FAILED")
    ''')


@pytest.mark.parametrize("perform_first", [False, True])
def test_bandage_vanilla_consumes_item_without_healing_setter(inventory, perform_first):
    inventory.globals().performFirst = perform_first
    inventory.execute('''
        local c=roster[uuidA]; c.hp=50; c.parts[1].values.bleeding=true
        local item=newItem("Bandage",c.inv); local t=assert(token("BANDAGE",uuidA,item))
        assert(requestItem("BANDAGE",t)); local a=completeItem(uuidA,performFirst)
        assert(c.parts[1]:bandaged() and not c.inv:contains(item) and c.hp==50)
        assert(L.getState(uuidA).state=="COMPLETED" and sourceRemovals==1)
        a:complete(); a:perform(); assert(sourceRemovals==1)
        local m=I.getResult(uuidA,L.getState(uuidA).action_id).observations
        assert(m.bandaged and m.health_before==50 and m.health_after==50 and m.quantity_consumed==1)
    ''')


def test_bandage_dirty_infected_and_no_wound_are_rejected(inventory):
    inventory.execute('''
        local c=roster[uuidA]; local item=newItem("Bandage",c.inv)
        assert(not token("BANDAGE"))
        c.parts[1].values.bleeding=true; item.infected=true
        assert(not token("BANDAGE"))
        item.infected=false; item.kind="BandageDirty"; assert(not token("BANDAGE"))
        item.kind="Bandage"; local t=assert(token("BANDAGE")); c.parts[1].values.bandaged=true
        assert(not requestItem("BANDAGE",t) and sourceRemovals==0)
    ''')


def test_cancel_bandage_blocks_late_complete_and_preserves_other_npc(inventory):
    inventory.execute('''
        for _,id in ipairs({uuidA,uuidB}) do
            local c=roster[id]; c.parts[1].values.bleeding=true
            newItem("Bandage",c.inv)
            assert(requestItem("BANDAGE",assert(token("BANDAGE",id)),id))
        end
        local old=queued(uuidA); E.cancel(uuidA,"manual_cancel")
        old:complete(); old:perform()
        assert(not roster[uuidA].parts[1]:bandaged() and #roster[uuidA].inv.items==1)
        assert(I.busy(uuidA) and I.busy(uuidB))
        roster[uuidA].state="IdleState"; I.update()
        completeItem(uuidB)
        assert(roster[uuidB].parts[1]:bandaged() and L.getState(uuidB).state=="COMPLETED")
        assert(L.getState(uuidA).state=="CANCELLED")
    ''')


def test_stale_target_uuid_world_and_replay_do_not_transfer(inventory):
    inventory.execute('''
        local item=groundItem("Nails"); local t=assert(token("PICKUP_ITEM"))
        assert(not requestItem("PICKUP_ITEM",t,uuidB))
        local ok,why=requestItem("PICKUP_ITEM",t); assert(ok)
        local old=queued(uuidA); E.cancel(uuidA,"cancel"); roster[uuidA].state="IdleState"; I.update()
        worldName="new-inventory-world"; E.update()
        old:perform(); assert(item:getWorldItem() and destinationAdds==0)
        assert(not requestItem("PICKUP_ITEM",t) and not I.getResult(uuidA,"inventory-test:2"))
    ''')


def test_item_lock_prevents_two_npcs_collecting_same_item(inventory):
    inventory.execute('''
        place(roster[uuidB],.8,.5,0)
        local item=groundItem("Nails"); local a=assert(token("PICKUP_ITEM",uuidA)); local b=assert(token("PICKUP_ITEM",uuidB))
        assert(requestItem("PICKUP_ITEM",a,uuidA))
        assert(not requestItem("PICKUP_ITEM",b,uuidB))
        completeItem(uuidA)
        assert(roster[uuidA].inv:contains(item) and not roster[uuidB].inv:contains(item) and destinationAdds==1)
    ''')


def test_player_owned_container_and_world_lock_are_never_accessed(inventory):
    inventory.execute('''
        local container,owner=furniture(1,0,"IsoThumpable"); local item=newItem("Nails",container)
        owner.locked=true; assert(not token("LOOT_CONTAINER"))
        owner.locked=false; local t=assert(token("LOOT_CONTAINER")); owner.locked=true
        assert(not requestItem("LOOT_CONTAINER",t) and container:contains(item))
        owner.class="IsoPlayer"; owner.locked=false
        assert(not token("LOOT_CONTAINER"))
        assert(player.pathCancelled==0 and destinationAdds==0)
    ''')


def test_wall_range_and_item_disappearance_are_revalidated(inventory):
    inventory.execute('''
        local item=groundItem("Nails",1,0); local t=assert(token("PICKUP_ITEM"))
        squares["0:0:0"].blockAll=true; assert(not requestItem("PICKUP_ITEM",t))
        squares["0:0:0"].blockAll=false
        assert(requestItem("PICKUP_ITEM",t)); local a=queued(uuidA)
        item.world:removeFromSquare(); a:perform(); roster[uuidA].state="IdleState"; I.update()
        assert(destinationAdds==0 and L.getState(uuidA).state=="FAILED")
    ''')


def test_navigation_finite_inventory_step_and_manual_preemption(inventory):
    inventory.execute('''
        local item=groundItem("Nails"); local t=assert(token("PICKUP_ITEM"))
        assert(N.submit(plan({{action="PICKUP_ITEM",target_id=t}})))
        assert(untilTick(function() return queued(uuidA)~=nil end))
        completeItem()
        assert(untilTick(function() local s=N.getState(uuidA); return s and s.state=="COMPLETED" end))
        assert(roster[uuidA].inv:contains(item))
    ''')


def test_emergency_cancels_inventory_before_native_commit(inventory):
    inventory.execute('''
        local item=groundItem("Nails"); assert(requestItem("PICKUP_ITEM",assert(token("PICKUP_ITEM"))))
        local a=queued(uuidA); character(nil,-.3,.5,0,"IsoZombie")
        fireTick(250); a:perform()
        assert(destinationAdds==0 and L.getState(uuidA).state=="CANCELLED")
        roster[uuidA].state="IdleState"; fireTick(250)
        assert(not I.busy(uuidA))
        assert(E.getState(uuidA).localSurvival)
    ''')


def test_missing_api_and_multiplayer_are_explicitly_unsupported(inventory):
    inventory.execute('''
        local item=groundItem("Nails"); local t=assert(token("PICKUP_ITEM"))
        local old=ISGrabItemAction; ISGrabItemAction=nil
        assert(not requestItem("PICKUP_ITEM",t) and not I.getCapabilities().PICKUP_ITEM.executable)
        ISGrabItemAction=old; isClient=function() return true end
        assert(not requestItem("PICKUP_ITEM",t) and not I.getCapabilities().BANDAGE.executable)
        assert(destinationAdds==0 and sourceRemovals==0)
    ''')


def test_timeout_and_uncertain_native_result_never_create_resources(inventory):
    inventory.execute('''
        local item=groundItem("Nails"); assert(requestItem("PICKUP_ITEM",assert(token("PICKUP_ITEM"))))
        local a=queued(uuidA); clock=clock+16000; I.update()
        a:perform(); roster[uuidA].state="IdleState"; I.update()
        assert(item.world and destinationAdds==0)
        assert(L.getState(uuidA).state=="FAILED")
        assert(F.unsupportedReason("PUSH_ZOMBIE") and F.unsupportedReason("CLIMB_STAIRS"))
    ''')


def test_transfer_repeated_callback_and_manual_cancel_are_individual(inventory):
    inventory.execute('''
        local container=furniture(1,0)
        local item=newItem("Nails",roster[uuidA].inv)
        assert(requestItem("TRANSFER_ITEM",assert(token("TRANSFER_ITEM"))))
        local old=completeItem(); old:perform(); old:complete()
        assert(container:contains(item) and sourceRemovals==1 and destinationAdds==1)
        assert(requestItem("LOOT_CONTAINER",assert(token("LOOT_CONTAINER"))))
        old=queued(uuidA); E.manualCommand(uuidA); old:perform()
        roster[uuidA].state="IdleState"; I.update()
        assert(container:contains(item) and destinationAdds==1 and L.getState(uuidA).state=="CANCELLED")
        assert(not I.busy(uuidB) and not queued(uuidB))
    ''')


def test_removed_or_full_destination_and_protected_item_are_rejected(inventory):
    inventory.execute('''
        local container,owner=furniture(1,0)
        local item=newItem("Nails",roster[uuidA].inv)
        for _,field in ipairs({"favorite","equipped","hand"}) do
            item[field]=true; assert(not token("TRANSFER_ITEM")); item[field]=false
        end
        item.slot=1; assert(not token("TRANSFER_ITEM")); item.slot=-1
        local t=assert(token("TRANSFER_ITEM")); owner.removed=true
        assert(not requestItem("TRANSFER_ITEM",t)); owner.removed=false
        assert(requestItem("TRANSFER_ITEM",t)); local a=queued(uuidA)
        container.capacity=0; a:perform(); roster[uuidA].state="IdleState"; I.update()
        assert(roster[uuidA].inv:contains(item) and destinationAdds==0)
    ''')


def test_bandage_fresh_threat_blocks_commit_and_old_callback(inventory):
    inventory.execute('''
        local c=roster[uuidA]; c.parts[1].values.bleeding=true; local item=newItem("Bandage",c.inv)
        assert(requestItem("BANDAGE",assert(token("BANDAGE"))))
        local a=queued(uuidA); character(nil,-.3,.5,0,"IsoZombie")
        a:complete(); a:perform(); c.state="IdleState"; I.update()
        assert(not c.parts[1]:bandaged() and c.inv:contains(item) and sourceRemovals==0)
        assert(L.getState(uuidA).state=="FAILED")
    ''')


def test_partial_native_transfer_failure_is_reported_without_retry_or_clone(inventory):
    inventory.execute('''
        local container=furniture(1,0); local item=newItem("Nails",container)
        local c=roster[uuidA]
        assert(requestItem("LOOT_CONTAINER",assert(token("LOOT_CONTAINER"))))
        c.inv.AddItem=function() error("destination API failed after removal") end
        local a=queued(uuidA); a:perform(); c.state="IdleState"; I.update()
        local state=L.getState(uuidA); assert(state.state=="FAILED")
        local result=I.getResult(uuidA,state.action_id)
        assert(result.result=="native_api_failed" and result.observations.native_error:find("destination API failed",1,true))
        assert(not c.inv:contains(item) and not container:contains(item))
        a:perform(); assert(sourceRemovals==1 and destinationAdds==0)
    ''')


def test_unconfirmed_native_bandage_is_failure_not_success(inventory):
    inventory.execute('''
        local c=roster[uuidA]; c.parts[1].values.bleeding=true; local item=newItem("Bandage",c.inv)
        assert(requestItem("BANDAGE",assert(token("BANDAGE"))))
        c.body.SetBandaged=function() end -- simulate native effect not applied
        completeItem()
        assert(L.getState(uuidA).state=="FAILED" and not c.parts[1]:bandaged())
        assert(I.getResult(uuidA,L.getState(uuidA).action_id).result=="native_bandage_unconfirmed")
    ''')


def test_tokens_expire_and_chunk_unload_does_not_consume_item(inventory):
    inventory.execute('''
        local item=groundItem("Nails"); local t=assert(token("PICKUP_ITEM"))
        clock=clock+10000
        assert(not requestItem("PICKUP_ITEM",t))
        t=assert(token("PICKUP_ITEM")); assert(requestItem("PICKUP_ITEM",t))
        local a=queued(uuidA); squares["0:0:0"]=nil
        a:perform(); I.update()
        assert(destinationAdds==0 and item:getWorldItem()~=nil)
        assert(not I.busy(uuidA))
    ''')


def test_unknown_ground_position_and_bounded_snapshot_are_not_invented(inventory):
    inventory.execute('''
        local item,obj=groundItem("Nails"); obj.getWorldPosX=nil
        assert(not token("PICKUP_ITEM"))
        for n=1,130 do newItem("Nails",roster[uuidA].inv) end
        local s=I.getSnapshot(uuidA)
        assert(not s.scan.complete and not s.available and #s.candidates==0)
        assert(s.scan.reason=="inventory_budget_or_unavailable")
    ''')


def test_multi_step_loot_then_bandage_confirms_each_before_next(inventory):
    inventory.execute('''
        local c=roster[uuidA]; c.parts[1].values.bleeding=true
        -- Existing own bandage and a separate ground item: both capabilities are real now.
        local bandage=newItem("Bandage",c.inv); local nails=groundItem("Nails")
        local pickup=assert(token("PICKUP_ITEM",uuidA,nails)); local aid=assert(token("BANDAGE",uuidA,bandage))
        assert(N.submit(plan({{action="PICKUP_ITEM",target_id=pickup},{action="BANDAGE",target_id=aid}})))
        assert(untilTick(function() return queued(uuidA)~=nil end)); completeItem()
        assert(not c.parts[1]:bandaged() and c.inv:contains(nails))
        assert(untilTick(function() return queued(uuidA)~=nil end)); completeItem()
        assert(untilTick(function() return N.getState(uuidA).state=="COMPLETED" end))
        assert(c.parts[1]:bandaged() and c.inv:contains(nails) and not c.inv:contains(bandage))
    ''')


def test_native_action_must_retire_even_if_state_already_idle(inventory):
    inventory.execute('''
        local item=groundItem("Nails"); assert(requestItem("PICKUP_ITEM",assert(token("PICKUP_ITEM"))))
        local a=queued(uuidA); a:perform()
        -- Simulate Java retaining the native action until a later engine update.
        roster[uuidA].javaActions={a.action}; roster[uuidA].state="IdleState"
        I.update(); assert(I.busy(uuidA) and L.getState(uuidA).state=="INVENTORY")
        assert(requestItem("STOP",nil))
        assert(L.getState(uuidA).state=="WAITING_PHYSICAL_STOP" and I.busy(uuidA))
        roster[uuidA].javaActions={}; I.update(); clock=clock+250; E.update()
        assert(not I.busy(uuidA) and L.getState(uuidA).state=="COMPLETED")
    ''')


def test_collection_does_not_call_eat_drink_or_rest(inventory):
    inventory.execute('''
        local c=roster[uuidA]; c.Eat=forbidden; c.DrinkFluid=forbidden; c.autoDrink=forbidden
        c.values.HUNGER=.8; c.values.THIRST=.8; c.values.FATIGUE=.8
        local food=groundItem("Apple"); local water=groundItem("WaterBottle")
        assert(requestItem("PICKUP_ITEM",assert(token("PICKUP_ITEM",uuidA,food)))); completeItem()
        assert(requestItem("PICKUP_ITEM",assert(token("PICKUP_ITEM",uuidA,water)))); completeItem()
        assert(c.inv:contains(food) and c.inv:contains(water))
        assert(c.values.HUNGER==.8 and c.values.THIRST==.8 and c.values.FATIGUE==.8)
        assert(destinationAdds==2 and sourceRemovals==0)
    ''')


def test_item_identifier_change_and_native_action_outside_our_queue_are_refused(inventory):
    inventory.execute('''
        local item=groundItem("Nails"); local t=assert(token("PICKUP_ITEM"))
        item.id=item.id+1; assert(not requestItem("PICKUP_ITEM",t))
        t=assert(token("PICKUP_ITEM")); roster[uuidA].javaActions={{foreign=true}}
        assert(not requestItem("PICKUP_ITEM",t) and destinationAdds==0)
        assert(not I.start(uuidA,nil,1,nil,"invalid"))
    ''')


def test_unknown_native_stack_keeps_lock_until_safe_retirement(inventory):
    inventory.execute('''
        local item=groundItem("Nails"); assert(requestItem("PICKUP_ITEM",assert(token("PICKUP_ITEM"))))
        local c=roster[uuidA]; local old=c.getCharacterActions
        E.cancel(uuidA,"manual_cancel"); c.state="IdleState"
        c.getCharacterActions=function() error("stack temporarily unavailable") end
        I.update()
        assert(I.busy(uuidA) and I.getState(uuidA).native_retirement=="native_stack_unavailable")
        assert(I.getState(uuidA).state=="CANCEL_PENDING" and destinationAdds==0)
        c.getCharacterActions=old; I.update()
        assert(not I.busy(uuidA) and item:getWorldItem()~=nil)
    ''')


def test_missing_container_list_is_incomplete_not_empty_known(inventory):
    inventory.execute('''
        local container=furniture(1,0); newItem("Nails",container)
        container.getItems=function() error("unavailable items") end
        local s=I.getSnapshot(uuidA)
        assert(not s.scan.complete and #s.candidates==0)
    ''')


def test_collect_real_bandage_then_refresh_capability_and_treat(inventory):
    inventory.execute('''
        local c=roster[uuidA]; c.hp=70; c.parts[1].values.bleeding=true
        local container=furniture(1,0); local bandage=newItem("Bandage",container)
        assert(not token("BANDAGE",uuidA,bandage))
        assert(requestItem("LOOT_CONTAINER",assert(token("LOOT_CONTAINER",uuidA,bandage))))
        completeItem(); assert(c.inv:contains(bandage))
        local aid=assert(token("BANDAGE",uuidA,bandage))
        assert(requestItem("BANDAGE",aid)); completeItem()
        assert(c.parts[1]:bandaged() and not c.inv:contains(bandage) and not container:contains(bandage))
        assert(c.hp==70 and destinationAdds==1 and sourceRemovals==2)
    ''')
