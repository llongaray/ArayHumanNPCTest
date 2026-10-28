"""Explicit compound navigation, production Lua in 5.1/5.4; Java APIs simulated."""
import pytest

from test_physical_escape import physical, safety, lua


@pytest.fixture
def nav(physical):
    physical.execute('''
        N=ArayHuman.Navigation; L=ArayHuman.Locomotion
        for _,c in pairs(roster) do
            c.npcRun=false; c.pathRun=false; c.running=false; c.sneaking=false; c.sprinting=false; c.hp=100
            function c:NPCGetRunning() return self.npcRun end
            function c:NPCSetRunning(v) self.npcRun=v end
            function c:isPathfindRunning() return self.pathRun end
            function c:setPathfindRunning(v) self.pathRun=v end
            function c:isRunning() return self.running end
            function c:setRunning(v) self.running=v end
            function c:isSneaking() return self.sneaking end
            function c:setSneaking(v) self.sneaking=v end
            function c:isSprinting() return self.sprinting end
            function c:setSprinting(v) self.sprinting=v end
            function c:getBodyDamage() return {getHealth=function() return self.hp end} end
            function c:isCollidedThisFrame() return false end
            c.setX=forbidden; c.setY=forbidden; c.setZ=forbidden
        end
        for _,method in ipairs({"setX","setY","setZ","NPCSetRunning","setRunning","setSneaking"}) do player[method]=forbidden end
        navSerial=0
        function interaction(kind,token,id,source)
            navSerial=navSerial+1
            return L.submit({uuid=id or uuidA,world_id="Sandbox/"..worldName,action=kind,
                target_id=token,action_id="physical-"..navSerial,source=source or "policy"})
        end
        function tokenFor(o,from,id)
            for _,v in ipairs(F.getCandidates(id or uuidA,from)) do
                if v.object.x==o.sq:getX() and v.object.y==o.sq:getY() then return v.target_id,v end
            end
        end
        function plan(steps,id,source)
            navSerial=navSerial+1
            return {uuid=id or uuidA,world_id="Sandbox/"..worldName,action_id="plan-"..navSerial,
                source=source or "manual",steps=steps}
        end
        function untilTick(fn,limit)
            for i=1,(limit or 30) do if fn() then return true end; fireTick(250) end
            return fn()
        end
    ''')
    return physical


def test_doors_open_close_idempotence_and_telemetry(nav):
    nav.execute('''
        local d=obstacle("IsoDoor"); d.open=true
        local token=assert(tokenFor(d))
        assert(interaction("OPEN_DOOR",token))
        assert(untilTick(function() return L.getState(uuidA).state=="COMPLETED" end))
        assert(nativeCalls==0 and d.open)
        assert(interaction("CLOSE_DOOR",token))
        assert(untilTick(function() return L.getState(uuidA).state=="COMPLETED" end))
        assert(nativeCalls==1 and not d.open)
        local out=L.getState(uuidA)
        assert(out.observations.object.initial_open.value and not out.observations.object.final_open.value)
        assert(out.observations.position_initial.x==.5 and out.observations.position_final.x==.5)
        assert(out.observations.duration_ms>=250 and out.observations.object.id==token)
        assert(out.observations.damage_received.known and out.observations.damage_received.value==0)
        assert(not out.observations.passage_clear.value)
        assert(F.getResult(uuidA,out.action_id).result=="success")
        assert(interaction("OPEN_DOOR",token))
        assert(untilTick(function() return L.getState(uuidA).state=="COMPLETED" end))
        assert(d.open and nativeCalls==2)
    ''')


def test_locked_door_and_other_character_in_landing_are_refused(nav):
    nav.execute('''
        local d=obstacle("IsoDoor"); local token=assert(tokenFor(d))
        d.locked=true
        local ok,why=interaction("OPEN_DOOR",token)
        assert(not ok and why=="door_locked" and nativeCalls==0)
        d.locked=false; d.open=true
        place(roster[uuidB],1.5,.5,0)
        assert(not interaction("CLOSE_DOOR",token) and d.open and nativeCalls==0)
        place(roster[uuidB],20.5,10.5,0); place(player,1.5,.5,0)
        assert(not interaction("CLOSE_DOOR",token) and d.open)
        assert(player.pathCancelled==0)
    ''')


def test_compound_walk_open_door_walk(nav):
    nav.execute('''
        place(roster[uuidA],-1.5,.5,0)
        local d=obstacle("IsoDoor"); local token=assert(tokenFor(d,"tile:0:0:0"))
        local request=plan({{action="WALK",target_id="tile:0:0:0"},{action="OPEN_DOOR",target_id=token},
            {action="WALK",target_id="tile:4:0:0"}})
        assert(N.submit(request)); fireTick(250)
        assert(queued(uuidA) and nativeCalls==0)
        complete(uuidA)
        assert(untilTick(function() return d.open end))
        assert(untilTick(function() return queued(uuidA)~=nil end))
        assert(N.getState(uuidA).step_index==3)
        complete(uuidA)
        assert(untilTick(function() return N.getState(uuidA).state=="COMPLETED" end))
        local result=N.getResult(uuidA,request.action_id)
        assert(result.result=="sequence_completed" and #result.steps==3)
        assert(result.steps[2].observations.object.id==token and result.observations.distance_travelled>=6)
        local addedBefore=added; fireTick(5000); assert(added==addedBefore)
    ''')


def test_compound_window_waits_for_animation_then_runs(nav):
    nav.execute('''
        place(roster[uuidA],-1.5,.5,0)
        local w=obstacle("IsoWindow"); local token=assert(tokenFor(w,"tile:0:0:0"))
        assert(N.submit(plan({{action="WALK",target_id="tile:0:0:0"},{action="OPEN_WINDOW",target_id=token},
            {action="CLIMB_WINDOW",target_id=token},{action="RUN",target_id="tile:4:0:0"}})))
        fireTick(250); complete(uuidA)
        assert(untilTick(function() return roster[uuidA].state=="OpenWindowState" end))
        fireTick(1000); assert(N.getState(uuidA).step_index==2 and not queued(uuidA) and nativeCalls==1)
        finishNative(uuidA)
        assert(untilTick(function() return roster[uuidA]:isClimbing() end))
        assert(N.getState(uuidA).step_index==3 and not queued(uuidA))
        roster[uuidA].hp=92; finishNative(uuidA)
        assert(untilTick(function() return queued(uuidA)~=nil end))
        assert(roster[uuidA].running and N.getState(uuidA).step_index==4)
        complete(uuidA)
        assert(untilTick(function() return N.getState(uuidA).state=="COMPLETED" end))
        local result=N.getState(uuidA)
        assert(result.steps[3].observations.position_final.x==1.5)
        assert(result.steps[3].observations.damage_received.value==8)
        assert(not roster[uuidA].running and nativeCalls==2)
    ''')


def test_compound_low_fence_walk(nav):
    nav.execute('''
        place(roster[uuidA],-1.5,.5,0)
        local f=obstacle("IsoObject"); local token=assert(tokenFor(f,"tile:0:0:0"))
        assert(N.submit(plan({{action="WALK",target_id="tile:0:0:0"},{action="CLIMB_FENCE",target_id=token},
            {action="WALK",target_id="tile:4:0:0"}})))
        fireTick(250); complete(uuidA)
        assert(untilTick(function() return roster[uuidA].state=="ClimbOverFenceState" end))
        assert(not queued(uuidA))
        finishNative(uuidA)
        assert(untilTick(function() return queued(uuidA)~=nil end)); complete(uuidA)
        assert(untilTick(function() return N.getState(uuidA).state=="COMPLETED" end))
    ''')


def test_window_glass_height_and_fence_height(nav):
    nav.execute('''
        local w=obstacle("IsoWindow"); w.smashed=true
        assert(tokenFor(w)==nil)
        w.removed=true; local token=assert(tokenFor(w))
        squares["1:0:0"].glass={}
        assert(not interaction("CLIMB_WINDOW",token) and nativeCalls==0)
        squares["1:0:0"].glass=nil
        local f=obstacle("IsoObject"); f.tall=true
        assert(tokenFor(f)==nil)
        local ok,why=L.submit({uuid=uuidA,world_id="Sandbox/"..worldName,action="STAIRS",action_id="stairs-1"})
        assert(not ok and why=="UNSUPPORTED_STAIRS_NPC")
        ok,why=N.submit(plan({{action="STAIRS",target_id="tile:1:0:1"}}))
        assert(not ok and why=="UNSUPPORTED_STAIRS_NPC")
        ok,why=N.submit(plan({{action="WALK",target_id="tile:1:0:1"}}))
        assert(not ok and why=="UNSUPPORTED_STAIRS_NPC" and roster[uuidA]:getZ()==0)
    ''')


def test_threat_other_side_and_threat_during_animation(nav):
    nav.execute('''
        local w=obstacle("IsoWindow"); w.open=true
        local token=assert(tokenFor(w))
        local z=character(nil,2.6,.5,0,"IsoZombie")
        assert(not interaction("CLIMB_WINDOW",token) and nativeCalls==0)
        z.dead=true
        local request=plan({{action="CLIMB_WINDOW",target_id=token},{action="RUN",target_id="tile:4:0:0"}})
        assert(N.submit(request))
        assert(untilTick(function() return roster[uuidA]:isClimbing() end))
        character(nil,-.3,.5,0,"IsoZombie"); fireTick(250)
        assert(roster[uuidA]:isClimbing() and not queued(uuidA))
        finishNative(uuidA); fireTick(250); fireTick(250)
        assert(N.getState(uuidA).state~="COMPLETED" and N.getState(uuidA).state~="RUNNING")
        assert(nativeCalls==1) -- no second physical action or continuation to RUN
    ''')


def test_cancel_and_delayed_walk_callback_cannot_continue_sequence(nav):
    nav.execute('''
        local d=obstacle("IsoDoor"); local token=assert(tokenFor(d))
        local request=plan({{action="WALK",target_id="tile:0:0:0"},{action="OPEN_DOOR",target_id=token}})
        assert(N.submit(request)); fireTick(250)
        local old=queued(uuidA)
        assert(N.cancel(uuidA,"user_cancel"))
        old:perform(); old:stop(); old.onCompleteFunc()
        fireTick(1000)
        assert(not d.open and nativeCalls==0 and N.getState(uuidA).state=="CANCELLED")
        assert(not queued(uuidA))
    ''')


def test_manual_command_in_gap_cancels_parent(nav):
    nav.execute('''
        local d=obstacle("IsoDoor"); local token=assert(tokenFor(d))
        assert(N.submit(plan({{action="WALK",target_id="tile:0:0:0"},{action="OPEN_DOOR",target_id=token}})))
        fireTick(250); complete(uuidA); fireTick(250)
        assert(N.getState(uuidA).state=="READY")
        assert(ArayHuman.order({name="MOVE_TO",x=-1,y=0,z=0},uuidA))
        local manual=queued(uuidA); fireTick(1000)
        assert(N.getState(uuidA).state=="CANCELLED" and queued(uuidA)==manual and not d.open)
    ''')


def test_two_npcs_independent_plans_and_cancellation(nav):
    nav.execute('''
        place(roster[uuidB],.5,10.5,0)
        local a=obstacle("IsoDoor"); local b=obstacle("IsoDoor",10)
        local ta=assert(tokenFor(a)); local tb=assert(tokenFor(b,nil,uuidB))
        assert(N.submit(plan({{action="OPEN_DOOR",target_id=ta},{action="WALK",target_id="tile:4:0:0"}})))
        assert(N.submit(plan({{action="OPEN_DOOR",target_id=tb},{action="WALK",target_id="tile:4:10:0"}},uuidB)))
        fireTick(250); assert(F.busy(uuidA) and F.busy(uuidB))
        assert(N.cancel(uuidA,"individual"))
        assert(untilTick(function() return queued(uuidB)~=nil end))
        complete(uuidB)
        assert(untilTick(function() return N.getState(uuidB).state=="COMPLETED" end))
        assert(not a.open and b.open and N.getState(uuidA).state=="CANCELLED")
        assert(player.pathCancelled==0 and not ISTimedActionQueue.queues[player])
    ''')


def test_stale_object_tokens_world_and_missing_apis(nav):
    nav.execute('''
        local d=obstacle("IsoDoor"); local token=assert(tokenFor(d))
        local replacement=obstacle("IsoDoor")
        assert(not interaction("OPEN_DOOR",token) and nativeCalls==0)
        local fresh=assert(tokenFor(replacement))
        replacement.ToggleDoor=nil
        assert(not interaction("OPEN_DOOR",fresh))
        worldName="different"; fireTick(250)
        assert(not interaction("OPEN_DOOR",fresh))
        assert(not queued(uuidA))
    ''')


def test_blocked_next_step_timeout_and_plan_limits(nav):
    nav.execute('''
        local d=obstacle("IsoDoor"); local token=assert(tokenFor(d))
        local request=plan({{action="OPEN_DOOR",target_id=token},{action="WALK",target_id="tile:4:0:0"}})
        assert(N.submit(request))
        assert(untilTick(function() return d.open end))
        squares["4:0:0"].blocked=true
        assert(untilTick(function() return N.getState(uuidA).state=="FAILED" end))
        assert(not queued(uuidA))
        local request2=plan({{action="OPEN_DOOR",target_id=token}}); request2.expires_at_ms=clock+100
        assert(N.submit(request2)); fireTick(250)
        assert(N.getState(uuidA).result=="timeout")
        local tooMany={}; for i=1,13 do tooMany[i]={action="OPEN_DOOR",target_id=token} end
        local ok,why=N.submit(plan(tooMany)); assert(not ok and why=="step_limit")
    ''')


def test_close_failure_and_passage_failure_do_not_report_success(nav):
    nav.execute('''
        local d=obstacle("IsoDoor"); d.open=true
        local token=assert(tokenFor(d))
        d.ToggleDoor=function() nativeCalls=nativeCalls+1 end -- native refuses to close
        assert(interaction("CLOSE_DOOR",token))
        assert(untilTick(function() return L.getState(uuidA).state=="FAILED" end))
        assert(d.open and L.getState(uuidA).result=="native_close_failed")
        local w=obstacle("IsoWindow"); w.open=true
        local tw=assert(tokenFor(w)); assert(interaction("CLIMB_WINDOW",tw))
        assert(untilTick(function() return roster[uuidA]:isClimbing() end))
        roster[uuidA].state="IdleState" -- Java finished without reaching other tile
        assert(untilTick(function() return L.getState(uuidA).state=="FAILED" end))
        assert(L.getState(uuidA).result=="native_crossing_failed" and roster[uuidA]:getX()==.5)
    ''')


def test_executor_cancel_and_new_policy_request_supersede_pending_plan(nav):
    nav.execute('''
        local request=plan({{action="WALK",target_id="tile:4:0:0"}},uuidA,"policy")
        assert(N.submit(request))
        assert(E.cancel(uuidA,"cancel_pending_plan"))
        assert(N.getState(uuidA).state=="CANCELLED")
        assert(N.submit(plan({{action="WALK",target_id="tile:4:0:0"}},uuidA,"policy")))
        assert(L.submit({uuid=uuidA,world_id="Sandbox/"..worldName,action="MOVE_TO",target_id="tile:3:0:0",
            movement_mode="RUN",source="policy",action_id="newer-command"}))
        local new=queued(uuidA); fireTick(250)
        assert(N.getState(uuidA).state=="CANCELLED" and queued(uuidA)==new)
        assert(L.getState(uuidA).action_id=="newer-command")
    ''')


def test_world_unavailable_and_missing_chunk_are_safe(nav):
    nav.execute('''
        local d=obstacle("IsoDoor"); local token=assert(tokenFor(d))
        squares["1:0:0"]=nil
        assert(not interaction("OPEN_DOOR",token) and nativeCalls==0)
        local oldWorld=getWorld; getWorld=function() return nil end
        N.update(); F.updateCancelled()
        local list,why=F.getCandidates(uuidA)
        assert(#list==0 and why=="world_unavailable")
        local ok,reason=N.submit(plan({{action="WALK",target_id="tile:0:0:0"}}))
        assert(not ok and reason=="world_unavailable")
        getWorld=oldWorld
    ''')


def test_shared_object_has_exclusive_lease_and_missing_climb_api(nav):
    nav.execute('''
        local d=obstacle("IsoDoor"); local token=assert(tokenFor(d))
        assert(interaction("OPEN_DOOR",token))
        local step=stepFor(d,"OPEN_DOOR",0)
        local ok,why=F.start(uuidB,roster[uuidB],step,obs(uuidB),1,function() error("must not execute") end)
        assert(not ok and why=="object_busy" and not F.busy(uuidB))
        assert(untilTick(function() return L.getState(uuidA).state=="COMPLETED" end))
        local w=obstacle("IsoWindow"); w.open=true
        local tw=assert(tokenFor(w)); roster[uuidA].climbThroughWindow=nil
        ok,why=interaction("CLIMB_WINDOW",tw)
        assert(not ok and why=="UNSUPPORTED_climb_window" and nativeCalls==1)
    ''')


def test_cancel_during_native_animation_keeps_final_physical_observation(nav):
    nav.execute('''
        local w=obstacle("IsoWindow"); w.open=true; local token=assert(tokenFor(w))
        local request=plan({{action="CLIMB_WINDOW",target_id=token},{action="RUN",target_id="tile:4:0:0"}})
        assert(N.submit(request))
        assert(untilTick(function() return roster[uuidA]:isClimbing() end))
        local child=L.getState(uuidA).action_id
        assert(N.cancel(uuidA,"manual_cancel"))
        assert(F.busy(uuidA) and roster[uuidA]:isClimbing())
        finishNative(uuidA); fireTick(250)
        local physical=F.getResult(uuidA,child)
        assert(physical and physical.result=="manual_cancel")
        assert(physical.observations.position_final.x==1.5 and physical.observations.duration_ms>=250)
        assert(not F.busy(uuidA) and not queued(uuidA) and N.getState(uuidA).state=="CANCELLED")
        fireTick(1000); assert(not queued(uuidA) and nativeCalls==1)
    ''')


def test_tokens_and_results_are_isolated_and_copied(nav):
    nav.execute('''
        local d=obstacle("IsoDoor"); local token=assert(tokenFor(d))
        local ok,why=interaction("OPEN_DOOR",token,uuidB)
        assert(not ok and why=="physical_target_unknown")
        local request=plan({{action="OPEN_DOOR",target_id=token}})
        assert(N.submit(request))
        assert(untilTick(function() return N.getState(uuidA).state=="COMPLETED" end))
        local result=N.getResult(uuidA,request.action_id)
        result.steps[1].observations.object.id="changed"
        assert(N.getResult(uuidA,request.action_id).steps[1].observations.object.id==token)
        assert(N.getState(uuidB)==nil)
    ''')


def test_replay_discovery_scope_and_no_unrequested_actions(nav):
    nav.execute('''
        local d=obstacle("IsoDoor"); local token=assert(tokenFor(d))
        local list,why=F.getCandidates(uuidA,"tile:30:0:0")
        assert(#list==0 and why=="destination_not_in_snapshot")
        local request=plan({{action="OPEN_DOOR",target_id=token}})
        assert(N.submit(request))
        local ok,reason=N.submit(request)
        assert(not ok and reason=="duplicate_action_id")
        assert(untilTick(function() return N.getState(uuidA).state=="COMPLETED" end))
        local calls=nativeCalls; fireTick(10000)
        assert(nativeCalls==calls and not queued(uuidA))
    ''')


def test_upper_level_window_and_unsupported_landing_are_not_candidates(nav):
    nav.execute('''
        local w=obstacle("IsoWindow"); w.open=true
        local token=assert(tokenFor(w))
        local oldFloor=squares["1:0:0"].TreatAsSolidFloor
        squares["1:0:0"].TreatAsSolidFloor=function() return false end
        assert(not interaction("CLIMB_WINDOW",token) and nativeCalls==0)
        squares["1:0:0"].TreatAsSolidFloor=oldFloor
        local a=square(0,0,1); local b=square(1,0,1); local proto=squares["0:0:0"]
        for _,sq in ipairs({a,b}) do
            for _,method in ipairs({"getX","getY","getZ","isBlockedTo","isFree","getBrokenGlass","getWindowTo","getDoorTo","getHoppableTo"}) do sq[method]=proto[method] end
        end
        w.sq=b; place(roster[uuidA],.5,.5,1)
        assert(#F.getCandidates(uuidA)==0 and nativeCalls==0)
        w.class="IsoObject"
        assert(#F.getCandidates(uuidA)==0 and roster[uuidA]:getZ()==1)
    ''')


def test_world_change_during_native_animation_invalidates_plan_and_tokens(nav):
    nav.execute('''
        local w=obstacle("IsoWindow"); w.open=true; local token=assert(tokenFor(w))
        assert(N.submit(plan({{action="CLIMB_WINDOW",target_id=token},{action="RUN",target_id="tile:4:0:0"}})))
        assert(untilTick(function() return roster[uuidA]:isClimbing() end))
        local child=L.getState(uuidA).action_id
        worldName="different-world"; fireTick(250)
        assert(N.getState(uuidA)==nil and F.busy(uuidA))
        finishNative(uuidA); fireTick(250)
        assert(not F.busy(uuidA) and not queued(uuidA) and nativeCalls==1)
        assert(F.getResult(uuidA,child)==nil)
        local step,why=F.resolveCandidate(uuidA,"CLIMB_WINDOW",token)
        assert(not step and why=="physical_target_unknown")
    ''')
