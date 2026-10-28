"""Unified explicit agent contracts, production Lua 5.1/5.4, simulated Java APIs."""
import pytest

from test_inventory_actions import inventory, observer, nav, physical, safety, lua
from test_executor import CLIENT


@pytest.fixture
def agent(inventory):
    for name in ("ArayHumanCapabilities.lua", "ArayHumanAgentState.lua"):
        inventory.execute((CLIENT / name).read_text(encoding="utf-8"))
    inventory.execute('''
        C=ArayHuman.Capabilities; A=ArayHuman.AgentState; agentSerial=0
        place(roster[uuidB],2.5,.5,0)
        for _,c in pairs(roster) do
            function c:faceLocationF(x,y) self.lookX=x; self.lookY=y; self.turning=true end
            function c:shouldBeTurning() return self.turning==true end
            function c:isFacingLocation(x,y) return not self.turning and self.lookX==x and self.lookY==y end
            function c:faceDirection(dir)
                self.facing=dir; self.turning=false
                self.lookX=math.floor(self:getX())+.5+(dir=="E" and 1 or dir=="W" and -1 or 0)
                self.lookY=math.floor(self:getY())+.5+(dir=="S" and 1 or dir=="N" and -1 or 0)
            end
        end
        function observation(id) return assert(A.getSnapshot(id or uuidA)) end
        function candidate(action,id)
            local s=observation(id)
            for _,t in ipairs(s.candidates) do
                if t.action==action or t.action=="MOVE" and (action=="WALK" or action=="RUN" or action=="SNEAK") then return t.target_id,s end
            end
            return nil,s
        end
        function req(action,id,target)
            agentSerial=agentSerial+1; id=id or uuidA
            local t,s=candidate(action,id)
            return {schema_version=1,uuid=id,world_id=s.world_id,action_id="agent:"..agentSerial,
                origin="rl",priority=2,action=action,expires_at_ms=clock+15000,
                observation_id=s.observation_id,target_id=target or t}
        end
        function send(action,id,target) return C.request(req(action,id,target)) end
    ''')
    return inventory


def test_snapshot_isolation_cache_policy_and_profile(agent):
    agent.execute('''
        local a=observation(); local b=observation(uuidB)
        assert(a.uuid==uuidA and b.uuid==uuidB and a.position.x~=b.position.x)
        assert(a.profile.available==false and a.profile.skills.status=="unavailable")
        assert(a.survival.needs_policy.hunger.rl_objective==false)
        assert(a.survival.needs_policy.hunger.effective_disabled.status=="unsupported")
        a.identity.name.value="tampered"; a.position.x=999; a.candidates={}
        local again=observation(); assert(again.position.x~=999 and #again.candidates>0)
        assert(again.observation_id==a.observation_id)
        assert(again.inventory.weight.known and again.inventory.weight.value==0)
        assert(forbiddenCalls==0)
    ''')


@pytest.mark.parametrize("action", ["WALK", "RUN", "SNEAK", "STOP", "FACE_TARGET", "LOOK_AT_PLAYER", "FOLLOW_PLAYER", "SAY"])
def test_basic_action_adapters(agent, action):
    agent.globals().testedAction = action
    agent.execute('''
        ArayHuman.SpeechBubble={show=function(c,text) assert(c~=player and text=="Olá"); spoken=true end}
        local r=req(testedAction)
        if testedAction=="FACE_TARGET" then r.target_id="PLAYER" end
        if testedAction=="SAY" then r.text="Olá" end
        local ok,result=C.request(r); assert(ok,type(result)=="table" and result.failure_reason or tostring(result))
        assert(result.requested_action==testedAction and result.request.origin=="rl")
        local s=E.getState(uuidA); assert(s.localMotion and not s.localSurvival)
        if testedAction=="RUN" then assert(roster[uuidA].running) end
        if testedAction=="SNEAK" then assert(roster[uuidA].sneaking) end
        if testedAction=="SAY" then assert(spoken and result.result=="speech_dispatched") end
        assert(not s.manualOrigin)
    ''')


@pytest.mark.parametrize("action", ["PUSH_ZOMBIE", "CLIMB_STAIRS", "EAT", "DRINK", "REST", "ATTACK", "os.execute"])
def test_blocked_actions(agent, action):
    agent.globals().testedAction = action
    agent.execute('''
        local ok,reason=send(testedAction); assert(not ok and type(reason)=="string")
        assert(queued(uuidA)==nil)
        local catalog=C.getCatalog(uuidA)
        assert(catalog.actions.PUSH_ZOMBIE.support=="UNSUPPORTED")
        assert(catalog.actions.CLIMB_STAIRS.available==false)
    ''')


@pytest.mark.parametrize("mutation", [
    'r.origin="manual"', 'r.origin="policy"', 'r.source="manual"',
    'r.priority=4', 'r.priority=1.5', 'r.priority=0/0',
    'r.world_id="other"', 'r.uuid="npc_1"', 'r.uuid=player:getModData().ARAY_Uuid',
    'r.action_id=""', 'r.action_id="exec()"', 'r.expires_at_ms=clock',
    'r.expires_at_ms=clock+30001', 'r.schema_version=2',
    'r.target_id="tile:999:999:0"', 'r.observation_id="old"',
    'r.destination={x=1,y=2,z=0}', 'r.text="code"', 'r.callback=function() end',
    'r.extra=roster[uuidA]', 'r.extra=r', 'setmetatable(r,{})',
])
def test_invalid_input_cannot_execute(agent, mutation):
    agent.execute('local r=req("WALK"); ' + mutation + '; local ok=C.request(r); assert(not ok); assert(queued(uuidA)==nil)')


def test_non_table_requests(agent):
    agent.execute('''
        for _,v in ipairs({"code",false,123}) do assert(not C.request(v)) end
        assert(not C.request(nil))
    ''')


def test_expired_candidates_cannot_refresh_themselves(agent):
    agent.execute('''
        local r=req("WALK"); clock=clock+1000
        local ok,why=C.request(r); assert(not ok and why=="candidate_expired")
        assert(queued(uuidA)==nil)
        local fresh=req("WALK"); assert(fresh.observation_id~=r.observation_id)
        assert(C.request(fresh))
    ''')


def test_manual_emergency_priorities_and_no_manual_impersonation(agent):
    agent.execute('''
        local r=req("WALK"); E.manualCommand(uuidA)
        local ok,why=C.request(r); assert(not ok and why=="manual_priority")
        local s=observation(); assert(s.runtime.control.manual_priority)
        assert(s.capabilities.actions.WALK.reason=="manual_priority")
        local accepted,info=send("WALK",uuidB); assert(accepted,type(info)=="table" and info.failure_reason or tostring(info))
        assert(not C.cancel(uuidB,"unknown","manual"))
    ''')


def test_two_npcs_cancel_and_old_callback(agent):
    agent.execute('''
        local a=req("WALK"); a.target_id="tile:4:0:0"
        -- Ensure the target was actually offered, rather than depending on ordering.
        a.target_id=assert(candidate("WALK"))
        local b=req("RUN",uuidB)
        assert(C.request(a)); local old=queued(uuidA)
        local accepted,info=C.request(b)
        assert(accepted,(type(info)=="table" and info.failure_reason or tostring(info)).." target="..tostring(b.target_id))
        local other=queued(uuidB)
        assert(C.cancel(uuidA,a.action_id,"rl"))
        old:perform()
        assert(queued(uuidB)==other and C.getResult(uuidA,a.action_id).state=="CANCELLED")
        assert(C.getResult(uuidB,b.action_id).state~="CANCELLED")
        assert(not C.cancel(uuidB,b.action_id,"ollama"))
    ''')


def test_duplicate_replacement_and_result_contract(agent):
    agent.execute('''
        local r=req("WALK"); assert(C.request(r))
        local ok,why=C.request(r); assert(not ok and why=="duplicate_action_id")
        local stop=req("STOP"); assert(C.request(stop))
        local old=C.getResult(uuidA,r.action_id); assert(old.state=="CANCELLED")
        local result=C.getResult(uuidA,stop.action_id)
        assert(result.before and result.after and result.duration_ms.known)
        assert(result.progress.distance_travelled.known and result.requested_action=="STOP")
        assert(result.executed_action=="STOP" and result.unknown_fields and result.reward==nil)
        result.before.position.x=999
        assert(C.getResult(uuidA,stop.action_id).before.position.x~=999)
    ''')


def test_world_change_and_death(agent):
    agent.execute('''
        local r=req("WALK"); assert(C.request(r))
        worldName="another"
        assert(C.getResult(uuidA,r.action_id)==nil)
        local s=observation(); assert(s.world_id=="Sandbox/another" and #s.results==0)
        roster[uuidA].dead=true
        s=observation(); assert(not s.active and #s.candidates==0)
        assert(not send("STOP"))
        assert(observation(uuidB).active)
    ''')


def test_partial_data_no_optional_apis_and_chunk_loss(agent):
    agent.execute('''
        roster[uuidA].getStats=nil; roster[uuidA].getBodyDamage=nil
        ArayHuman.Survival.clearAll(); A.clearAll()
        local s=observation(); assert(not s.survival.health.known)
        assert(not s.survival.needs.hunger.known)
        local old=roster[uuidA].getCurrentSquare
        roster[uuidA].getCurrentSquare=function() return nil end
        s=observation(); assert(not s.active and #s.candidates==0)
        assert(not send("WALK"))
        roster[uuidA].getCurrentSquare=old
        assert(observation().active)
    ''')


@pytest.mark.parametrize("action", ["PICKUP_ITEM", "LOOT_CONTAINER", "TRANSFER_ITEM", "BANDAGE"])
def test_inventory_routes_and_real_results(agent, action):
    agent.globals().testedAction=action
    agent.execute('''
        local c=roster[uuidA]; local item
        if testedAction=="PICKUP_ITEM" then item=groundItem("Nails")
        elseif testedAction=="LOOT_CONTAINER" then item=newItem("Nails",furniture(1,0))
        elseif testedAction=="TRANSFER_ITEM" then furniture(1,0); item=newItem("Nails",c.inv)
        else c.parts[1].values.bleeding=true; item=newItem("Bandage",c.inv) end
        local t=assert(candidate(testedAction)); local r=req(testedAction,nil,t)
        assert(C.request(r)); completeItem()
        local result=C.getResult(uuidA,r.action_id)
        assert(result.state=="COMPLETED",tostring(result.failure_reason))
        assert(result.resources_used.native_item_id==item.id)
        assert(c.hp==100 and player~=c)
    ''')


@pytest.mark.parametrize("action", ["OPEN_DOOR", "CLOSE_DOOR", "OPEN_WINDOW", "CLIMB_WINDOW", "CLIMB_FENCE"])
def test_physical_routes_and_native_confirmation(agent, action):
    agent.globals().testedAction=action
    agent.execute('''
        local o=obstacle((testedAction=="OPEN_DOOR" or testedAction=="CLOSE_DOOR") and "IsoDoor"
            or testedAction=="CLIMB_FENCE" and "IsoObject" or "IsoWindow")
        if testedAction=="CLOSE_DOOR" or testedAction=="CLIMB_WINDOW" then o.open=true end
        local t=assert(candidate(testedAction)); local r=req(testedAction,nil,t)
        local ok,result=C.request(r); assert(ok,tostring(result))
        assert(E.getState(uuidA).action==testedAction)
        assert(result.requested_action==testedAction)
    ''')


def test_finite_navigation_only_and_target_validation(agent):
    agent.execute('''
        local t,s=candidate("WALK"); local r=req("NAVIGATE")
        r.steps={{action="WALK",target_id=t},{action="RUN",target_id=t}}
        assert(C.request(r)); assert(N.getState(uuidA).requested_steps or N.getState(uuidA).state=="READY")
        assert(C.cancel(uuidA,r.action_id,"rl"))
        local invalid=req("NAVIGATE"); invalid.steps={{action="WALK",target_id="tile:999:0:0"}}
        assert(not C.request(invalid))
        invalid=req("NAVIGATE"); invalid.steps={{action="PUSH_ZOMBIE",target_id=t}}
        assert(not C.request(invalid))
    ''')


def test_bounded_reads_no_autonomous_loop(agent):
    agent.execute('''
        local original=I.getSnapshot; inventoryReads=0
        I.getSnapshot=function(...) inventoryReads=inventoryReads+1; return original(...) end
        local originalP=ArayHuman.Perception.updateSnapshot; spatialReads=0
        ArayHuman.Perception.updateSnapshot=function(...) spatialReads=spatialReads+1; return originalP(...) end
        for n=1,20 do local s=observation(); assert(#s.candidates<=A.config.maxCandidates) end
        assert(inventoryReads==1 and spatialReads<=1)
        assert(queued(uuidA)==nil and E.getState(uuidA)==nil)
        assert(#C.getRecentResults(uuidA)==0 and forbiddenCalls==0)
    ''')


def test_eligible_catalog_is_not_an_in_game_compatibility_claim(agent):
    agent.execute('''
        local catalog=C.getCatalog(uuidA)
        for name,v in pairs(catalog.actions) do
            assert(v.manual_validation=="pending")
            assert(v.support=="experimental" or v.support=="UNSUPPORTED")
        end
        roster[uuidA].NPCGetRunning=nil; roster[uuidA].faceLocationF=nil
        roster[uuidA].openWindow=nil; roster[uuidA].climbThroughWindow=nil; roster[uuidA].climbOverFence=nil
        ArayHuman.SpeechBubble=nil; ISGrabItemAction=nil
        catalog=C.getCatalog(uuidA)
        assert(not catalog.actions.RUN.available and not catalog.actions.FACE_TARGET.available)
        assert(not catalog.actions.SAY.available and not catalog.actions.PICKUP_ITEM.available)
        assert(not catalog.actions.OPEN_WINDOW.available and not catalog.actions.CLIMB_WINDOW.available)
        assert(not catalog.actions.CLIMB_FENCE.available)
        assert(A.getSnapshot("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")==nil)
    ''')


def test_policy_priority_cannot_replace_higher_request(agent):
    agent.execute('''
        local r=req("WALK"); r.priority=3; assert(C.request(r)); local old=queued(uuidA)
        local s=req("STOP"); s.priority=1
        local ok,why=C.request(s); assert(not ok and why=="policy_priority")
        assert(queued(uuidA)==old)
        s.priority=3; assert(C.request(s)); assert(C.getResult(uuidA,r.action_id).state=="CANCELLED")
    ''')


def test_emergency_cannot_be_cancelled_or_impersonated(agent):
    agent.execute('''
        local r=req("WALK"); assert(C.request(r))
        character(nil,-.5,.5,0,"IsoZombie"); fireTick(250)
        assert(E.getControlState(uuidA).emergency_priority,table.concat(logs," | "))
        local current=queued(uuidA)
        local ok,why=C.cancel(uuidA,r.action_id,"rl")
        assert(not ok and why=="emergency_priority" and queued(uuidA)==current)
        local stop=req("STOP"); stop.priority=3
        ok,why=C.request(stop); assert(not ok and why=="emergency_priority")
        stop.emergency=true; assert(not C.request(stop))
        assert(queued(uuidA)==current)
    ''')


def test_partial_observation_expiry_instance_and_player_change(agent):
    agent.execute('''
        local s=observation(); local r=req("WALK")
        local old=player; old.dead=true
        player=character(nil,1.5,3.5,0)
        local next=observation(); assert(next.observation_id~=s.observation_id)
        assert(next.perception.player.known and next.perception.player.position.y==3.5)
        assert(not C.request(r))
        player=old; old.dead=false
        local s2=observation(); clock=clock+1000
        assert(observation().observation_id~=s2.observation_id)
        local x,y,z=math.floor(roster[uuidA]:getX()),math.floor(roster[uuidA]:getY()),0
        squares[x..":"..y..":"..z]=nil
        next=observation(); assert(not next.active and #next.candidates==0)
    ''')


def test_real_movement_health_and_resource_outcomes(agent):
    agent.execute('''
        local r=req("WALK")
        for _,t in ipairs(observation().candidates) do
            if t.action=="MOVE" and t.target_id=="tile:1:0:0" then r.target_id=t.target_id end
        end
        assert(r.target_id=="tile:1:0:0" and C.request(r))
        roster[uuidA].hp=90; complete(uuidA)
        local result=C.getResult(uuidA,r.action_id)
        assert(result.state=="COMPLETED" and result.progress.distance_travelled.value==1)
        assert(result.damage_received.known and result.damage_received.value==10)
        assert(result.before.health.value==100 and result.after.health.value==90)
        assert(result.resources_used.known==false)
        assert(result.after.position.x==1.5 and result.reward==nil)
    ''')


def test_native_userdata_and_non_finite_nested_payload_rejected(agent):
    agent.execute('''
        local r=req("SAY"); r.text=io.stdout
        assert(not C.request(r))
        r=req("NAVIGATE"); r.steps={{action="WALK",target_id=0/0}}
        assert(not C.request(r))
        r.steps={[2]={action="WALK",target_id="tile:0:0:0"}}
        assert(not C.request(r))
    ''')


def test_native_window_sequence_reports_confirmed_steps(agent):
    agent.execute('''
        local w=obstacle("IsoWindow")
        local t=assert(candidate("OPEN_WINDOW")); local r=req("NAVIGATE")
        r.steps={{action="OPEN_WINDOW",target_id=t},{action="CLIMB_WINDOW",target_id=t},
            {action="RUN",target_id="tile:2:1:0"}}
        local ok,info=C.request(r); assert(ok,type(info)=="table" and info.failure_reason or tostring(info))
        assert(untilTick(function() return roster[uuidA].state=="OpenWindowState" end))
        assert(C.getResult(uuidA,r.action_id).state~="COMPLETED")
        finishNative(uuidA)
        assert(untilTick(function() return roster[uuidA]:isClimbing() end))
        assert(N.getState(uuidA).step_index==2)
        finishNative(uuidA)
        assert(untilTick(function() return queued(uuidA)~=nil end)); complete(uuidA)
        assert(untilTick(function() return N.getState(uuidA).state=="COMPLETED" end))
        local result=C.getResult(uuidA,r.action_id)
        assert(result.state=="COMPLETED" and #result.backend.steps==3)
        assert(result.backend.steps[2].action=="CLIMB_WINDOW" and result.after.position.x==2.5)
    ''')


def test_cancelled_native_window_retires_before_terminal_result(agent):
    agent.execute('''
        obstacle("IsoWindow"); local r=req("OPEN_WINDOW"); assert(C.request(r))
        assert(untilTick(function() return roster[uuidA].state=="OpenWindowState" end))
        assert(C.cancel(uuidA,r.action_id,"rl"))
        assert(C.getResult(uuidA,r.action_id).state=="CANCEL_PENDING")
        assert(not send("WALK"))
        finishNative(uuidA); fireTick(250)
        local result=C.getResult(uuidA,r.action_id)
        assert(result.state=="CANCELLED" and result.physical_result)
        assert(not F.busy(uuidA) and result.after.position.x==.5)
    ''')


def test_result_end_sample_not_taken_from_later_action(agent):
    agent.execute('''
        local r=req("WALK"); r.target_id="tile:1:0:0"; assert(C.request(r)); complete(uuidA)
        place(roster[uuidA],5.5,.5,0); roster[uuidA].hp=70
        local result=C.getResult(uuidA,r.action_id)
        assert(result.after.position.x==1.5 and result.after.health.value==100)
        assert(result.damage_received.value==0)
    ''')


def test_bounded_registries_reject_instead_of_unbounded_growth(agent):
    agent.execute('''
        C.config.maxNPCs=1; assert(send("STOP"))
        local ok,why=send("STOP",uuidB); assert(not ok and why=="registry_full")
        A.clearAll(); A.config.maxNPCs=1; assert(observation())
        local s,reason=A.getSnapshot(uuidB); assert(s==nil and reason=="registry_full")
    ''')
