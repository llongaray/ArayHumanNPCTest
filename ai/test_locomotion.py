"""Structured native locomotion, actual Lua modules and native walk in both runtimes."""
import pytest

from test_executor import lua
from test_physical_escape import physical, safety


@pytest.fixture
def motion(lua):
    lua.execute('''
        L=ArayHuman.Locomotion
        for _,c in pairs(roster) do
            c.npcRun=false; c.pathRun=false; c.running=false; c.sneaking=false; c.sprinting=false
            c.hp=100; c.collided=false
            function c:isNPC() return true end
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
            function c:isClimbing() return self.climbing==true end
            function c:isKnockedDown() return self.knocked==true end
            function c:getBodyDamage() return {getHealth=function() return self.hp end} end
            function c:isCollidedThisFrame() return self.collided end
            function c:faceLocationF(x,y) self.lookX=x; self.lookY=y; self.turning=true end
            function c:shouldBeTurning() return self.turning==true end
            function c:isFacingLocation(x,y) return not self.turning and self.lookX==x and self.lookY==y end
        end
        for _,name in ipairs({"NPCSetRunning","setPathfindRunning","setRunning","setSneaking","setSprinting","faceLocationF","setX","setY"}) do player[name]=forbidden end
        motionSerial=0
        function req(id,mode,target,source)
            motionSerial=motionSerial+1
            return {uuid=id,world_id="Sandbox/"..worldName,action="MOVE_TO",movement_mode=mode,
                action_id="move-"..motionSerial,target_id=target or "tile:4:0:0",source=source or "policy"}
        end
        function simple(id,action,target,source)
            motionSerial=motionSerial+1
            return {uuid=id,world_id="Sandbox/"..worldName,action=action,target_id=target,
                action_id="simple-"..motionSerial,source=source or "policy"}
        end
    ''')
    return lua


@pytest.mark.parametrize("mode", ["WALK", "RUN", "SNEAK"])
def test_modes_apply_native_flags_and_restore(motion, mode):
    motion.globals().mode = mode
    motion.execute('''
        local c=roster[uuidA]
        c.sprinting=true -- restore original flags, do not leave mode behind
        local request=req(uuidA,mode)
        assert(L.submit(request))
        assert(c.running==(mode=="RUN") and c.npcRun==(mode=="RUN") and c.pathRun==(mode=="RUN"))
        assert(c.sneaking==(mode=="SNEAK") and not c.sprinting)
        assert(L.getState(uuidA).movement_mode==mode and L.getState(uuidA).action_id==request.action_id)
        assert(queued(uuidA).location==squares["4:0:0"])
        complete(uuidA)
        assert(not c.running and not c.npcRun and not c.pathRun and not c.sneaking and c.sprinting)
        assert(L.getState(uuidA).state=="COMPLETED")
    ''')


def test_mode_and_destination_replacement_ignore_old_callbacks(motion):
    motion.execute('''
        assert(L.submit(req(uuidA,"RUN")))
        local old=queued(uuidA); local oldId=L.getState(uuidA).execution_id
        place(roster[uuidA],.85,.72,0); advance(250)
        assert(L.submit(req(uuidA,"SNEAK","tile:5:1:0")))
        local new=queued(uuidA)
        assert(new~=old and roster[uuidA].sneaking and not roster[uuidA].running)
        old:perform(); old:stop(); old:update(); old.onCompleteFunc()
        assert(queued(uuidA)==new and roster[uuidA].sneaking)
        assert(L.getState(uuidA).execution_id~=oldId)
        complete(uuidA); assert(not roster[uuidA].sneaking)
    ''')


def test_two_npcs_different_modes_cancel_independently(motion):
    motion.execute('''
        assert(L.submit(req(uuidA,"RUN")))
        assert(L.submit(req(uuidB,"SNEAK","tile:5:1:0")))
        local b=queued(uuidB)
        assert(L.submit(simple(uuidA,"STOP")))
        assert(queued(uuidA)==nil and queued(uuidB)==b and roster[uuidB].sneaking)
        assert(L.getState(uuidA).result=="stopped")
        assert(player.pathCancelled==0 and player.faced==0)
    ''')


def test_fractional_distance_damage_collision_and_frozen_result(motion):
    motion.execute('''
        assert(L.submit(req(uuidA,"WALK")))
        local c=roster[uuidA]
        place(c,.8,.9,0); c.hp=93; c.collided=true; advance(250)
        local m=L.getState(uuidA).observations
        assert(math.abs(m.distance_travelled-.5)<.00001 and m.duration_ms==250)
        assert(m.target_progress>0 and m.target_distance_remaining<m.target_distance_start)
        assert(m.damage_received.known and m.damage_received.value==7)
        assert(m.collision_samples.known and m.collision_samples.value==1)
        assert(m.threat_before.known)
        c.collided=false; complete(uuidA)
        m=L.getState(uuidA).observations
        assert(m.distance_travelled>.5 and m.threat_after.known and m.ended_at_ms==clock)
        local final=m.distance_travelled; local duration=m.duration_ms
        place(c,7.4,2.2,0); advance(1000)
        assert(L.getState(uuidA).observations.distance_travelled==final)
        assert(L.getState(uuidA).observations.duration_ms==duration)
    ''')


def test_missing_observation_apis_are_unknown_not_zero(motion):
    motion.execute('''
        roster[uuidA].getBodyDamage=nil; roster[uuidA].isCollidedThisFrame=nil
        assert(L.submit(req(uuidA,"RUN"))); advance(250)
        local m=L.getState(uuidA).observations
        assert(not m.damage_received.known and m.damage_received.value==nil)
        assert(not m.collision_samples.known and m.collision_samples.value==nil)
        assert(not m.health_before.known)
    ''')


def test_observations_do_not_consume_emergency_health_or_closing_evidence(motion):
    motion.execute('''
        local c=roster[uuidA]
        local z=character(nil,3.3,.5,0,"IsoZombie")
        ArayHuman.Perception.scanThreats(uuidA)
        c.hp=90; clock=clock+250
        local m=L.beginMetrics(c,uuidA)
        L.endMetrics(m,c,uuidA,true)
        local obs=ArayHuman.Perception.scanThreats(uuidA)
        assert(obs.health_drop and obs.immediate and obs.level=="CONTACT")
        place(z,4.3,.5,0); clock=clock+250
        ArayHuman.Perception.scanThreats(uuidA)
        place(z,3.5,.5,0); clock=clock+250
        assert(ArayHuman.Perception.observeThreats(uuidA).immediate)
        assert(ArayHuman.Perception.scanThreats(uuidA).immediate)
    ''')


def test_mode_api_missing_or_failing_refuses_safely(motion):
    motion.execute('''
        local c=roster[uuidA]; c.NPCSetRunning=nil
        local ok,reason=L.submit(req(uuidA,"RUN"))
        assert(not ok and reason=="UNSUPPORTED_movement_flags" and added==0)
        function c:NPCSetRunning(v) self.npcRun=v end
        c.setSneaking=function() error("native unavailable") end
        ok,reason=L.submit(req(uuidA,"SNEAK"))
        assert(not ok and reason=="movement_mode_failed" and not c.running and not c.npcRun)
        assert(not queued(uuidA))
    ''')


def test_destination_token_revalidated_and_not_shared_between_npcs(motion):
    motion.execute('''
        local token=assert(L.validateDestination(uuidA,"tile:4:0:0"))
        local r=req(uuidA,"WALK"); r.target_id=nil; r.destination=token
        assert(L.submit(r)); E.cancel(uuidA,"test")
        r=req(uuidB,"WALK"); r.target_id=nil; r.destination=token
        assert(not L.submit(r))
        squares["4:0:0"].blocked=true
        r=req(uuidA,"RUN"); r.target_id=nil; r.destination=token
        assert(not L.submit(r) and not queued(uuidA))
    ''')


def test_invalid_world_uuid_action_replay_and_coordinates(motion):
    motion.execute('''
        local r=req(uuidA,"RUN"); r.world_id="other"
        assert(not L.submit(r))
        r=req("npc_1","WALK"); assert(not L.submit(r))
        r=req(uuidA,"TELEPORT"); assert(not L.submit(r))
        r=req(uuidA,"RUN"); r.x=5; assert(not L.submit(r))
        r=req(uuidA,"RUN"); r.action="EXECUTE_LUA"; assert(not L.submit(r))
        r=req(uuidA,"RUN"); assert(L.submit(r))
        local old=queued(uuidA); local ok,reason=L.submit(r)
        assert(not ok and reason=="duplicate_action_id" and queued(uuidA)==old)
    ''')


def test_twelve_tile_rule_permission_and_policy_manual_priority(motion):
    motion.execute('''
        place(roster[uuidA],8.5,.5,0)
        local r=req(uuidA,"RUN","tile:15:0:0","manual")
        local ok,reason=L.submit(r)
        assert(not ok and reason=="permission_required" and not queued(uuidA))
        local state=E.getState(uuidA)
        assert(state.state=="WAITING_PERMISSION" and not roster[uuidA].running)
        assert(E.approve(uuidA,state.actionId)); assert(queued(uuidA))
        ok,reason=L.submit(req(uuidA,"WALK","tile:9:0:0"))
        assert(not ok and reason=="manual_priority")
    ''')


def test_manual_override_and_emergency_preemption_restore_modes(motion):
    motion.execute('''
        assert(L.submit(req(uuidA,"SNEAK",nil,"manual")))
        assert(ArayHuman.order({name="MOVE_TO",x=5,y=0,z=0},uuidA))
        assert(not roster[uuidA].sneaking)
        character(nil,-.5,.5,0,"IsoZombie"); advance(250)
        assert(E.getState(uuidA).localSurvival and queued(uuidA))
        assert(not roster[uuidA].sneaking and not roster[uuidA].running)
        assert(not L.submit(req(uuidA,"RUN")))
    ''')


def test_blocked_target_no_path_and_no_progress_restore_flags(motion):
    motion.execute('''
        squares["4:0:0"].blocked=true
        assert(not L.submit(req(uuidA,"RUN")) and not roster[uuidA].running)
        squares["4:0:0"].blocked=false
        assert(L.submit(req(uuidA,"RUN")))
        queued(uuidA).result=BehaviorResult.Failed; advance(250)
        assert(L.getState(uuidA).result=="pathfinding_failed" and not roster[uuidA].running)
        assert(L.submit(req(uuidA,"SNEAK"))); advance(5001)
        assert(L.getState(uuidA).result=="sem progresso" and not roster[uuidA].sneaking)
    ''')


def test_face_target_native_fractional_position_and_current_player(motion):
    motion.execute('''
        assert(L.submit(simple(uuidA,"FACE_TARGET","tile:4:0:0")))
        local c=roster[uuidA]; assert(c.lookX==4.5 and c.lookY==.5 and not queued(uuidA))
        assert(L.getState(uuidA).state=="TURNING")
        c.turning=false; advance(250)
        assert(L.getState(uuidA).result=="faced_target")
        assert(L.submit(simple(uuidA,"FACE_TARGET","PLAYER")))
        local old=player; old.dead=true
        player=character(nil,3.7,4.2,0)
        advance(250); assert(c.lookX==3.7 and c.lookY==4.2)
        c.turning=false; advance(250)
        assert(L.getState(uuidA).state=="COMPLETED" and old.faced==0)
    ''')


def test_death_world_and_physical_busy(motion):
    motion.execute('''
        assert(L.submit(req(uuidA,"RUN")))
        roster[uuidA].dead=true; advance(250)
        assert(L.getState(uuidA).state=="CANCELLED" and not roster[uuidA].running)
        assert(L.submit(req(uuidB,"SNEAK","tile:5:1:0")))
        worldName="new-world"; advance(250)
        assert(L.getState(uuidB).result=="world_changed" and not roster[uuidB].sneaking)
        local original=ArayHuman.Physical.busy
        ArayHuman.Physical.busy=function(id) return id==uuidB end
        local ok,reason=L.submit(req(uuidB,"RUN"))
        assert(not ok and reason=="physical_busy")
        ArayHuman.Physical.busy=original
    ''')


def test_restore_waits_for_safe_native_state(motion):
    motion.execute('''
        assert(L.submit(req(uuidA,"RUN")))
        local c=roster[uuidA]; c.climbing=true
        E.cancel(uuidA,"manual_command")
        assert(c.running)
        local ok,reason=L.submit(req(uuidA,"SNEAK"))
        assert(not ok and reason=="native_state_unsafe")
        c.climbing=false; advance(250)
        assert(not c.running and not c.npcRun)
    ''')


def test_missing_native_state_api_is_refused_and_turn_times_out(motion):
    motion.execute('''
        local c=roster[uuidA]; c.isClimbing=nil
        local ok,reason=L.submit(req(uuidA,"RUN"))
        assert(not ok and reason=="native_state_unsafe" and not queued(uuidA))
        function c:isClimbing() return false end
        local r=simple(uuidA,"FACE_TARGET","tile:4:0:0"); r.expires_at_ms=clock+500
        assert(L.submit(r)); advance(501)
        assert(L.getState(uuidA).result=="expired" and not queued(uuidA))
    ''')


def test_dynamic_destination_block_restores_run_flags(motion):
    motion.execute('''
        assert(L.submit(req(uuidA,"RUN")))
        squares["4:0:0"].blocked=true; advance(250)
        assert(not queued(uuidA) and not roster[uuidA].running and not roster[uuidA].npcRun)
        assert(L.getState(uuidA).result=="destination_blocked")
        local m=L.getState(uuidA).observations
        assert(m.distance_travelled==0 and m.duration_ms==250)
    ''')


def test_structured_stop_preserves_sneak_posture_and_player(motion):
    motion.execute('''
        local c=roster[uuidA]; c.sneaking=true; c.running=true; c.npcRun=true
        assert(L.submit(simple(uuidA,"STOP")))
        assert(c.sneaking and not c.running and not c.npcRun and not c.pathRun)
        assert(player.pathCancelled==0 and not ISTimedActionQueue.queues[player])
    ''')


def test_completed_and_cancelled_results_are_retained_and_copied(motion):
    motion.execute('''
        local first=req(uuidA,"RUN"); assert(L.submit(first))
        assert(L.submit(req(uuidA,"SNEAK")))
        local result=L.getResult(uuidA,first.action_id)
        assert(result.state=="CANCELLED" and result.result=="replaced")
        result.observations.distance_travelled=999
        assert(L.getResult(uuidA,first.action_id).observations.distance_travelled~=999)
        worldName="different-world"; advance(250)
        assert(L.getResult(uuidA,first.action_id)==nil)
    ''')


def test_structured_stop_during_physical_animation_is_deferred(physical):
    physical.execute('''
        -- Add the native mode APIs to the physical-animation harness.
        local c=roster[uuidA]
        c.running=false; c.sneaking=false; c.sprinting=false; c.npcRun=false; c.pathRun=false
        function c:isRunning() return self.running end
        function c:setRunning(v) self.running=v end
        function c:isSneaking() return self.sneaking end
        function c:setSneaking(v) self.sneaking=v end
        function c:isSprinting() return self.sprinting end
        function c:setSprinting(v) self.sprinting=v end
        function c:NPCGetRunning() return self.npcRun end
        function c:NPCSetRunning(v) self.npcRun=v end
        function c:isPathfindRunning() return self.pathRun end
        function c:setPathfindRunning(v) self.pathRun=v end
        local w=obstacle("IsoWindow"); w.open=true
        character(nil,-1.7,.5,0,"IsoZombie"); fireTick(250); fireTick(250)
        assert(c:isClimbing())
        local L=ArayHuman.Locomotion
        assert(L.submit({uuid=uuidA,world_id="Sandbox/"..worldName,action="STOP",action_id="stop-native",source="manual"}))
        assert(L.getState(uuidA).state=="WAITING_PHYSICAL_STOP" and c:isClimbing())
        fireTick(250); assert(c:isClimbing() and not queued(uuidA))
        finishNative(uuidA); fireTick(250)
        assert(L.getState(uuidA).result=="stopped" and not F.busy(uuidA))
        assert(not queued(uuidA) and nativeCalls==1)
    ''')
