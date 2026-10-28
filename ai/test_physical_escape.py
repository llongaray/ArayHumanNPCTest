"""Native APIs are simulated, production planner/executor run in Lua 5.1 and 5.4."""
from pathlib import Path

import pytest

from test_survival import safety, lua
from test_executor import NATIVE


@pytest.fixture
def physical(safety):
    safety.execute(r'''
        F=ArayHuman.Physical
        IsoDirections={N="N",S="S",E="E",W="W"}
        IsoDoor={getDoubleDoorIndex=function() return -1 end,getGarageDoorIndex=function() return -1 end}
        edges={}; nativeCalls=0; results={}
        function edgeKey(a,b)
            local s=a.x..":"..a.y; local t=b.x..":"..b.y
            return s<t and s.."/"..t or t.."/"..s
        end
        for _,sq in pairs(squares) do
            function sq:getBrokenGlass() return self.glass end
            function sq:getDoorTo(b) local o=edges[edgeKey(self,b)]; return o and o.class=="IsoDoor" and o end
            function sq:getWindowTo(b) local o=edges[edgeKey(self,b)]; return o and o.class=="IsoWindow" and o end
            function sq:getHoppableTo(b) local o=edges[edgeKey(self,b)]; return o and o.class=="IsoObject" and o end
            function sq:isPlayerAbleToHopWallTo(dir,b) return not self.noHop end
            function sq:isBlockedTo(b)
                if self.y~=b.y or (self.y~=0 and self.y~=10) or self.x< -2 or b.x< -2 then return true end
                local o=edges[edgeKey(self,b)]
                if o then return o.class~="IsoDoor" or not o.open end
                return self.blockAll==true or b.blockAll==true
            end
        end
        function preparePhysical(c)
            c.state="IdleState"; c.contextPanic=0
            function c:isNPC() return self.md and self.md.ARAY_IsNPC==true end
            function c:getCurrentStateName() return self.state end
            function c:isClimbing() return self.state=="ClimbThroughWindowState" or self.state=="ClimbOverFenceState" end
            function c:isKnockedDown() return false end
            function c:isPerformingAttackAnimation() return false end
            function c:isPerformingShoveAnimation() return false end
            function c:faceDirection(dir) assert(self~=player); self.facing=dir end
            function c:shouldBeTurning() return self.turning==true end
            function c:isFacingLocation() return true end
            function c:isSafeToClimbOver() return not self.unsafeFence end
            function c:openWindow(o) nativeCalls=nativeCalls+1; self.state="OpenWindowState"; self.pending=o end
            function c:climbThroughWindow(o) nativeCalls=nativeCalls+1; self.state="ClimbThroughWindowState"; self.pending=o end
            function c:climbOverFence(dir)
                nativeCalls=nativeCalls+1; self.state="ClimbOverFenceState"; self.pendingDir=dir
            end
            c.DoAttack=forbidden; c.pressedAttack=forbidden; c.setDoShove=forbidden
        end
        preparePhysical(roster[uuidA]); preparePhysical(roster[uuidB])
        place(roster[uuidB],20.5,10.5,0)
        function obstacle(kind,y)
            y=y or 0
            local o={class=kind,open=false,smashed=false,removed=false,locked=false,sq=squares["1:"..y..":0"]}
            function o:getSquare() return self.sq end
            function o:getNorth() return false end
            function o:getObjectIndex() return 0 end
            function o:IsOpen() return self.open end
            function o:isSmashed() return self.smashed end
            function o:isGlassRemoved() return self.removed end
            function o:isBarricaded() return self.barricaded==true end
            function o:isLocked() return self.locked end
            function o:isLockedByKey() return false end
            function o:isPermaLocked() return false end
            function o:isInvincible() return false end
            function o:isObstructed() return false end
            function o:isTallHoppable() return self.tall==true end
            function o:canClimbThrough(c) return (self.open or self.smashed) and not self.barricaded end
            function o:ToggleDoor(c) assert(c~=player); nativeCalls=nativeCalls+1; self.open=not self.open end
            edges[edgeKey(squares["0:"..y..":0"],o.sq)]=o
            return o
        end
        function finishNative(id)
            local c=roster[id]
            if c.state=="OpenWindowState" then c.pending.open=true
            elseif c.state=="ClimbThroughWindowState" or c.state=="ClimbOverFenceState" then
                place(c,1.5,math.floor(c:getY())+.5,0)
            end
            c.state="IdleState"
        end
        function obs(id) return ArayHuman.Perception.scanThreats(id or uuidA) end
        function stepFor(o,kind,y)
            return {kind=kind,object=o,fromX=0,fromY=y or 0,x=1,y=y or 0,z=0,direction=IsoDirections.E}
        end
        function beginPhysical(o,kind,id,y)
            id=id or uuidA
            return F.start(id,roster[id],stepFor(o,kind,y),obs(id),1,function(result,g)
                results[id]={result=result,generation=g}
            end)
        end
    ''')
    return safety


def test_door_escape_fallback_opens_and_walks(physical):
    physical.execute('''
        local door=obstacle("IsoDoor")
        character(nil,-1.7,.5,0,"IsoZombie"); fireTick(250)
        assert(E.getState(uuidA).state=="INTERACTING" and not queued(uuidA))
        assert(F.busy(uuidA) and not door.open)
        fireTick(250); assert(door.open and nativeCalls==1)
        fireTick(250); fireTick(250)
        assert(queued(uuidA) and E.getState(uuidA).state=="RUNNING")
        complete(uuidA); assert(E.getState(uuidA).state=="COMPLETED")
    ''')


def test_closed_window_waits_for_both_native_animations(physical):
    physical.execute('''
        local w=obstacle("IsoWindow"); character(nil,-1.7,.5,0,"IsoZombie")
        fireTick(250); assert(E.getState(uuidA).transition=="OPEN_WINDOW")
        fireTick(250); assert(roster[uuidA].state=="OpenWindowState")
        fireTick(500); assert(F.busy(uuidA) and not queued(uuidA) and nativeCalls==1)
        finishNative(uuidA); fireTick(250); fireTick(250)
        assert(E.getState(uuidA).transition=="CLIMB_WINDOW")
        fireTick(250); assert(roster[uuidA]:isClimbing())
        fireTick(500); assert(not queued(uuidA) and F.busy(uuidA))
        finishNative(uuidA); fireTick(250); fireTick(250)
        assert(queued(uuidA) and nativeCalls==2)
    ''')


def test_open_and_clean_broken_window(physical):
    physical.execute('''
        local w=obstacle("IsoWindow"); w.open=true
        character(nil,-1.7,.5,0,"IsoZombie")
        assert(beginPhysical(w,"CLIMB_WINDOW")); F.update(uuidA,obs())
        assert(roster[uuidA]:isClimbing() and not results[uuidA])
        finishNative(uuidA); clock=clock+250; F.update(uuidA,obs())
        assert(results[uuidA].result=="success")
        place(roster[uuidA],.5,.5,0); w.open=false; w.smashed=true; w.removed=true
        assert(beginPhysical(w,"CLIMB_WINDOW"))
    ''')


def test_shards_barricade_locked_and_missing_api_rejected(physical):
    physical.execute('''
        local w=obstacle("IsoWindow"); w.smashed=true
        character(nil,-1.7,.5,0,"IsoZombie")
        assert(not beginPhysical(w,"CLIMB_WINDOW"))
        w.removed=true; squares["1:0:0"].glass={}
        assert(not beginPhysical(w,"CLIMB_WINDOW"))
        squares["1:0:0"].glass=nil; w.barricaded=true
        assert(not beginPhysical(w,"CLIMB_WINDOW"))
        w.barricaded=false; w.smashed=false; w.locked=true
        assert(not beginPhysical(w,"OPEN_WINDOW"))
        w.locked=false; roster[uuidA].openWindow=nil
        local ok,reason=beginPhysical(w,"OPEN_WINDOW")
        assert(not ok and reason=="UNSUPPORTED_window_state" and nativeCalls==0)
    ''')


def test_low_fence_native_and_high_fence_refused(physical):
    physical.execute('''
        local f=obstacle("IsoObject"); character(nil,-1.7,.5,0,"IsoZombie")
        assert(beginPhysical(f,"CLIMB_FENCE")); F.update(uuidA,obs())
        assert(roster[uuidA]:isClimbing() and nativeCalls==1)
        finishNative(uuidA); clock=clock+250; F.update(uuidA,obs())
        assert(results[uuidA].result=="success")
        place(roster[uuidA],.5,.5,0); f.tall=true
        assert(not beginPhysical(f,"CLIMB_FENCE"))
        f.tall=false; roster[uuidA].unsafeFence=true
        assert(not beginPhysical(f,"CLIMB_FENCE"))
    ''')


def test_enemy_other_side_and_enemy_blocking_landing(physical):
    physical.execute('''
        local w=obstacle("IsoWindow"); w.open=true
        character(nil,-1.7,.5,0,"IsoZombie")
        local z=character(nil,2.2,.5,0,"IsoZombie")
        local ok,reason=beginPhysical(w,"CLIMB_WINDOW")
        assert(not ok and reason=="interaction_threat_too_close")
        place(z,1.4,.5,0)
        assert(not beginPhysical(w,"CLIMB_WINDOW") and nativeCalls==0)
    ''')


def test_native_interruption_defers_and_stale_executor_does_not_resume(physical):
    physical.execute('''
        local w=obstacle("IsoWindow"); w.open=true
        character(nil,-1.7,.5,0,"IsoZombie"); fireTick(250); fireTick(250)
        assert(roster[uuidA]:isClimbing())
        local old=E.getState(uuidA).actionId
        assert(E.cancel(uuidA,"manual_command"))
        assert(F.busy(uuidA) and roster[uuidA]:isClimbing())
        assert(not ArayHuman.order({name="FACE_TARGET"},uuidA))
        assert(not ArayHuman.walkTo(squares["3:0:0"],"teste")) -- omitted UUID also guarded
        fireTick(8000); assert(F.busy(uuidA) and not queued(uuidA))
        finishNative(uuidA); fireTick(250)
        assert(not F.busy(uuidA) and E.getState(uuidA).actionId==old)
        assert(E.getState(uuidA).state=="CANCELLED" and not queued(uuidA))
    ''')


def test_approaching_threat_cancels_before_native_start(physical):
    physical.execute('''
        local w=obstacle("IsoWindow"); w.open=true
        local z=character(nil,-1.7,.5,0,"IsoZombie")
        roster[uuidA].turning=true
        assert(beginPhysical(w,"CLIMB_WINDOW"))
        place(z,-.4,.5,0); clock=clock+250; F.update(uuidA,obs())
        assert(not F.busy(uuidA) and results[uuidA].result=="interaction_threat_too_close")
        assert(nativeCalls==0)
    ''')


def test_two_npcs_independent_physical_locks(physical):
    physical.execute('''
        place(roster[uuidB],.5,10.5,0)
        local a=obstacle("IsoWindow"); a.open=true
        local b=obstacle("IsoWindow",10); b.open=true
        character(nil,-1.7,.5,0,"IsoZombie"); character(nil,-1.7,10.5,0,"IsoZombie")
        assert(beginPhysical(a,"CLIMB_WINDOW"))
        assert(beginPhysical(b,"CLIMB_WINDOW",uuidB,10))
        F.cancel(uuidA,"test"); F.update(uuidA,obs())
        F.update(uuidB,obs(uuidB))
        assert(not F.busy(uuidA) and F.busy(uuidB) and roster[uuidB]:isClimbing())
        assert(player.faced==0 and player.pathCancelled==0 and not ISTimedActionQueue.queues[player])
    ''')


def test_shove_is_explicitly_unsupported_never_attack(physical):
    physical.execute('''
        character(nil,-.3,.5,0,"IsoZombie")
        local ok,why=F.defensiveShove(uuidA,roster[uuidA],obs())
        assert(not ok and why=="UNSUPPORTED_target_exclusive_native_shove")
        assert(logContains("DEFENSIVE_SHOVE") and nativeCalls==0)
        ok,why=F.defensiveShove(uuidA,roster[uuidA],obs())
        assert(not ok and why=="shove_cooldown")
        assert(not F.defensiveShove(uuidA,player,obs()))
    ''')


def test_changed_obstacle_during_orientation_and_stale_world(physical):
    physical.execute('''
        local d=obstacle("IsoDoor"); character(nil,-1.7,.5,0,"IsoZombie")
        assert(beginPhysical(d,"OPEN_DOOR"))
        d.locked=true; F.update(uuidA,obs())
        assert(not F.busy(uuidA) and nativeCalls==0)
        d.locked=false
        local old=obs(); worldName="different"
        local ok,reason=F.start(uuidA,roster[uuidA],stepFor(d,"OPEN_DOOR"),old,2,function() end)
        assert(not ok and reason=="threat_not_confirmed")
    ''')


def test_free_route_is_preferred_over_opening_door(physical):
    physical.execute('''
        local d=obstacle("IsoDoor"); character(nil,-1.7,.5,0,"IsoZombie")
        for _,sq in pairs(squares) do
            function sq:isBlockedTo(b)
                local o=edges[edgeKey(self,b)]
                return o and not o.open or false
            end
        end
        fireTick(250)
        assert(queued(uuidA) and E.getState(uuidA).state=="RUNNING")
        assert(not F.busy(uuidA) and not d.open and nativeCalls==0)
    ''')


def test_threat_during_native_animation_waits_and_refuses_next_crossing(physical):
    physical.execute('''
        local w=obstacle("IsoWindow"); character(nil,-1.7,.5,0,"IsoZombie")
        fireTick(250); fireTick(250)
        assert(roster[uuidA].state=="OpenWindowState")
        character(nil,-.3,.5,0,"IsoZombie"); fireTick(250)
        assert(F.busy(uuidA) and roster[uuidA].state=="OpenWindowState")
        assert(logContains("policy=wait_native_safe"))
        finishNative(uuidA); fireTick(250); fireTick(250)
        assert(not F.busy(uuidA) and nativeCalls==1)
        assert(E.getState(uuidA).state=="FAILED")
        assert(E.getState(uuidA).result=="interaction_threat_too_close")
    ''')


def test_missing_geometry_api_and_uuid_observation_are_rejected(physical):
    physical.execute('''
        local d=obstacle("IsoDoor"); character(nil,-1.7,.5,0,"IsoZombie")
        IsoDoor.getDoubleDoorIndex=nil
        local ok,reason=beginPhysical(d,"OPEN_DOOR")
        assert(not ok and reason=="UNSUPPORTED_door_geometry")
        IsoDoor.getDoubleDoorIndex=function() return -1 end
        local wrong=obs(); wrong.uuid=uuidB
        ok,reason=F.start(uuidA,roster[uuidA],stepFor(d,"OPEN_DOOR"),wrong,1,function() end)
        assert(not ok and reason=="observation_uuid_mismatch")
        squares["1:0:0"].getBrokenGlass=function() error("API unavailable") end
        assert(not beginPhysical(d,"OPEN_DOOR") and nativeCalls==0)
    ''')


def test_native_lua_wrapper_does_not_wait_for_animation(physical):
    # Run the actual installed Lua wrappers, showing why queue completion is insufficient.
    root=NATIVE.parents[2]
    physical.execute('''
        function ISBaseTimedAction.new(self,c) return setmetatable({character=c},{__index=self}) end
    ''')
    physical.execute((root / "shared/TimedActions/ISOpenCloseWindow.lua").read_text())
    physical.execute((root / "client/TimedActions/ISClimbThroughWindow.lua").read_text())
    physical.execute((root / "client/TimedActions/ISClimbOverFence.lua").read_text())
    physical.execute('''
        local w=obstacle("IsoWindow"); w.open=true
        local c=roster[uuidA]
        local a=ISClimbThroughWindow:new(c,w,0)
        ISTimedActionQueue.queues[c]={queue={a}}
        a:perform()
        assert(c:isClimbing() and #ISTimedActionQueue.queues[c].queue==0)
        c.state="IdleState"; w.open=false
        local b=ISOpenCloseWindow:new(c,w)
        ISTimedActionQueue.queues[c]={queue={b}}
        b:perform()
        assert(c.state=="OpenWindowState" and not w.open)
        c.state="IdleState"
        local f=obstacle("IsoObject")
        local hop=ISClimbOverFence:new(c,f,IsoDirections.E)
        ISTimedActionQueue.queues[c]={queue={hop}}
        hop:perform()
        assert(c.state=="ClimbOverFenceState" and #ISTimedActionQueue.queues[c].queue==0)
    ''')

