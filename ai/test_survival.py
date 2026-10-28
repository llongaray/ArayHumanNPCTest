"""Local survival through registered OnTick handlers, no Ollama/game/service start."""
import pytest

from test_executor import lua  # Reuse production/native Lua harness in both Lua runtimes.


@pytest.fixture
def safety(lua):
    lua.execute('''
        logs={}
        print=function(message) logs[#logs+1]=tostring(message) end
        function fireTick(ms)
            clock=clock+ms
            for _,fn in ipairs(handlers) do
                -- Baseline renderer/camera upkeep is outside this simulated engine.
                -- All production perception, command, walk and executor OnTicks run.
                if fn~=baselineTick then fn() end
            end
        end
        worldName="survival-without-decision-session"
        fireTick(0)
        function logContains(text)
            for _,line in ipairs(logs) do if line:find(text,1,true) then return true end end
            return false
        end
    ''')
    return lua


def test_idle_contact_flees_without_decision_session(safety):
    safety.execute('''
        assert(not E.submit(decision(uuidA,"IDLE")))
        character(nil,-.5,.5,0,"IsoZombie")
        fireTick(250)
        local s=E.getState(uuidA)
        assert(s and s.localSurvival and s.emergency and s.state=="RUNNING")
        assert(queued(uuidA) and queued(uuidB)==nil)
        assert(E.getSurvivalState(uuidA).level=="CONTACT")
        assert(logContains("uuid="..uuidA.." event=threat_detected"))
        assert(logContains("event=pathfinding_started"))
    ''')


def test_nearby_then_approaching_classification(safety):
    safety.execute('''
        local z=character(nil,5.5,.5,0,"IsoZombie")
        fireTick(250)
        assert(E.getSurvivalState(uuidA).level=="NEARBY" and added==0)
        place(z,4,.5,0); fireTick(250)
        assert(E.getSurvivalState(uuidA).level=="APPROACHING")
        assert(E.getState(uuidA).localSurvival and queued(uuidA))
    ''')


def test_health_drop_with_confirmed_zombie_triggers_contact(safety):
    safety.execute('''
        local hp=100
        roster[uuidA].getBodyDamage=function() return {getHealth=function() return hp end} end
        character(nil,3.3,.5,0,"IsoZombie")
        fireTick(250)
        assert(queued(uuidA)==nil)
        hp=90; fireTick(250)
        assert(E.getSurvivalState(uuidA).level=="CONTACT")
        assert(E.getState(uuidA).emergency and logContains("health_drop=true"))
    ''')


def test_health_drop_alone_dead_zombie_and_other_floor_do_not_flee(safety):
    safety.execute('''
        local hp=100
        roster[uuidA].getBodyDamage=function() return {getHealth=function() return hp end} end
        fireTick(250); hp=90; fireTick(250)
        assert(added==0)
        local z=character(nil,-.5,.5,0,"IsoZombie"); z.dead=true
        character(nil,.5,.5,1,"IsoZombie")
        fireTick(250); assert(added==0)
    ''')


def test_manual_walk_is_interrupted_and_old_callbacks_are_inert(safety):
    safety.execute('''
        assert(ArayHuman.order({name="MOVE_TO",x=5,y=0,z=0},uuidA))
        local old=queued(uuidA)
        character(nil,-.5,.5,0,"IsoZombie"); fireTick(250)
        local escape=queued(uuidA)
        assert(escape and escape~=old and E.getState(uuidA).localSurvival)
        assert(ArayHuman.getOrderName(uuidA)=="Idle")
        local id=E.getState(uuidA).actionId
        old:stop(); old:perform(); old.onCompleteFunc()
        assert(queued(uuidA)==escape and E.getState(uuidA).actionId==id)
        assert(logContains("event=action_interrupted order=MOVE_TO"))
    ''')


def test_zombie_occupies_manual_destination_during_walk(safety):
    safety.execute('''
        assert(ArayHuman.order({name="MOVE_TO",x=5,y=0,z=0},uuidA))
        character(nil,5.5,.5,0,"IsoZombie")
        fireTick(250)
        assert(queued(uuidA)==nil)
        assert(logContains("result=destination_blocked"))
    ''')


def test_two_npcs_escape_independently_and_cancel_individually(safety):
    safety.execute('''
        place(roster[uuidB],10.5,10.5,0)
        character(nil,-.5,.5,0,"IsoZombie")
        character(nil,9.5,10.5,0,"IsoZombie")
        fireTick(250)
        assert(queued(uuidA) and queued(uuidB))
        local b=queued(uuidB)
        E.cancel(uuidA,"local_test_cancel")
        assert(queued(uuidA)==nil and queued(uuidB)==b)
        fireTick(250)
        assert(queued(uuidA)==nil and queued(uuidB)==b)
    ''')


def test_fractional_positions_and_radius_boundary(safety):
    safety.execute('''
        place(roster[uuidA],.01,.01,0)
        local far=character(nil,6,.01,0,"IsoZombie")
        local s=ArayHuman.Perception.scanThreats(uuidA)
        assert(#s.threats==1 and math.abs(s.nearest.value-5.99)<.001)
        far.dead=true
        place(roster[uuidA],.95,.95,0)
        character(nil,1.05,.95,0,"IsoZombie")
        fireTick(250)
        assert(E.getState(uuidA) and E.getState(uuidA).localSurvival and queued(uuidA))
        assert(E.getSurvivalState(uuidA).distance<.11)
    ''')


def test_escape_route_turns_around_obstacle_using_native_waypoints(safety):
    safety.execute('''
        character(nil,-.5,.5,0,"IsoZombie")
        for _,xy in ipairs({{1,0},{0,1},{0,-2}}) do squares[xy[1]..":"..xy[2]..":0"].blocked=true end
        fireTick(250)
        assert(queued(uuidA) and E.getState(uuidA).localSurvival)
        assert(E.getState(uuidA).currentLeg.x==0 and E.getState(uuidA).currentLeg.y==-1)
        local initialId=E.getState(uuidA).actionId
        for i=1,8 do
            if queued(uuidA) then complete(uuidA) end
            fireTick(250)
            if E.getState(uuidA).state=="COMPLETED" then break end
        end
        assert(E.getState(uuidA).actionId==initialId)
        assert(E.getState(uuidA).state=="COMPLETED")
        assert(added<=6 and logContains("event=waypoint_reached"))
    ''')


def test_wall_and_unknown_collision_prevent_unconfirmed_emergency(safety):
    safety.execute('''
        character(nil,1.6,.5,0,"IsoZombie")
        roster[uuidA].sq.blockAll=true
        fireTick(250); assert(queued(uuidA)==nil)
        roster[uuidA].sq.blockAll=false
        roster[uuidA].sq.isBlockedTo=nil
        fireTick(250); assert(queued(uuidA)==nil)
    ''')


def test_no_route_has_bounded_retries_and_never_resumes_unsafe_manual_walk(safety):
    safety.execute('''
        character(nil,-.5,.5,0,"IsoZombie")
        for _,xy in ipairs({{1,0},{0,1},{0,-1}}) do squares[xy[1]..":"..xy[2]..":0"].blocked=true end
        fireTick(250)
        assert(queued(uuidA)==nil and E.getSurvivalState(uuidA).attempts==1)
        for i=1,10 do fireTick(10) end
        assert(E.getSurvivalState(uuidA).attempts==1)
        fireTick(2000); fireTick(2000); fireTick(2000)
        assert(E.getSurvivalState(uuidA).attempts==3)
        local n=added
        assert(ArayHuman.order({name="MOVE_TO",x=4,y=0,z=0},uuidA))
        fireTick(250)
        assert(queued(uuidA)==nil and added==n+1)
        for i=1,10 do fireTick(2500) end
        assert(E.getSurvivalState(uuidA).attempts==3 and added==n+1)
        assert(logContains("event=escape_unavailable") and logContains("event=attempts_exhausted"))
    ''')


def test_pathfinding_failures_choose_alternatives_and_stop_after_limit(safety):
    safety.execute('''
        local z=character(nil,-.5,.5,0,"IsoZombie")
        fireTick(250)
        local targets={}
        for i=1,3 do
            local s=E.getState(uuidA)
            assert(queued(uuidA) and not targets[s.destination.target_id])
            targets[s.destination.target_id]=true
            queued(uuidA).result=BehaviorResult.Failed
            fireTick(250)
            assert(queued(uuidA)==nil)
            fireTick(2000)
        end
        assert(E.getSurvivalState(uuidA).attempts==3 and queued(uuidA)==nil)
        assert(logContains("result=pathfinding_failed"))
        z.dead=true; fireTick(250); fireTick(3001)
        assert(E.getSurvivalState(uuidA).attempts==0)
    ''')


def test_cooldown_limits_processing_and_roster_budget(safety):
    safety.execute('''
        local original=ArayHuman.Perception.scanThreats
        scans=0
        ArayHuman.Perception.scanThreats=function(id) scans=scans+1; return original(id) end
        for i=1,100 do fireTick(1) end
        assert(scans==0)
        fireTick(150); assert(scans==2)
        local obs=original(uuidA)
        assert(obs.scan.tiles<=169 and obs.scan.entities<=96)
    ''')


def test_only_confirmed_emergency_can_cross_player_limit(safety):
    safety.execute('''
        place(player,.5,.5,0); place(roster[uuidA],11.5,.5,0)
        local z=character(nil,10.5,.5,0,"IsoZombie")
        fireTick(250)
        local s=E.getState(uuidA)
        assert(s.localSurvival and s.emergency and s.destination.x>12 and s.state=="RUNNING")
        z.dead=true; fireTick(250)
        assert(E.getState(uuidA).state=="COMPLETED" and queued(uuidA)==nil)
        assert(logContains("result=danger_reduced"))
    ''')


def test_death_world_and_missing_chunk_cancel_only_owned_escape(safety):
    safety.execute('''
        character(nil,-.5,.5,0,"IsoZombie"); fireTick(250)
        assert(queued(uuidA))
        squares["0:0:0"]=nil; fireTick(250)
        assert(queued(uuidA)==nil)
        worldName="another-world"; roster={}; fireTick(250)
        assert(E.getSurvivalState(uuidA)==nil)
    ''')


def test_dynamic_escape_edge_blocked_and_native_no_progress(safety):
    safety.execute('''
        character(nil,-.5,.5,0,"IsoZombie"); fireTick(250)
        local s=E.getState(uuidA); assert(s.currentLeg)
        squares[s.currentLeg.x..":"..s.currentLeg.y..":0"].blockAll=true
        fireTick(250)
        assert(queued(uuidA)==nil and E.getState(uuidA).result=="route_edge_blocked")
        fireTick(1000)
        assert(queued(uuidA))
        fireTick(1501)
        assert(queued(uuidA)==nil and logContains("result=sem progresso"))
    ''')


def test_roster_fairness_with_fixed_scan_budget(safety):
    safety.execute('''
        for i=3,5 do
            local id=string.format("%08d-1111-4111-8111-111111111111",i)
            roster[id]=character(id,10+i,10,0)
        end
        local observed={}; local calls=0; local original=ArayHuman.Perception.scanThreats
        ArayHuman.Perception.scanThreats=function(id) calls=calls+1; observed[id]=true; return original(id) end
        fireTick(1000); assert(calls==2)
        fireTick(250); assert(calls==4)
        fireTick(250); assert(calls==6)
        local count=0; for _ in pairs(observed) do count=count+1 end
        assert(count==5)
    ''')


def test_player_input_and_queue_are_untouched(safety):
    safety.execute('''
        player.pressedMovement=forbidden; player.pressedCancelAction=forbidden
        character(nil,-.5,.5,0,"IsoZombie"); fireTick(250)
        assert(queued(uuidA))
        queued(uuidA):update()
        assert(player.pathCancelled==0 and player.faced==0)
        assert(ISTimedActionQueue.queues[player]==nil)
        local obs=ArayHuman.Perception.scanThreats(nil)
        assert(not obs.active)
    ''')
