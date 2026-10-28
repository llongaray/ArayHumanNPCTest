"""Production executor/walking/manual/perception and B42 native walk, simulated engine."""
import os
from pathlib import Path

import pytest

pytest.importorskip("lupa")
from lupa import lua51, lua54
from test_perception import MOCKS

CLIENT = Path(__file__).resolve().parents[1] / "42/media/lua/client"
NATIVE = Path(os.environ.get("ARAY_GAME_DIR", "E:/Games/Project.Zomboid.v42.13.1/game")) / "media/lua/client/TimedActions/WalkToTimedAction.lua"

ENGINE = r'''
clock=10000
require=function() return true end
handlers={}
Events.OnTick.Add=function(fn) table.insert(handlers,fn) end
Events.OnPlayerUpdate={Add=function() end}
Events.RenderOpaqueObjectsInWorld={Add=function() end}
for x=-25,35 do for y=-20,20 do square(x,y,0) end end
for _,sq in pairs(squares) do
    function sq:getX() return self.x end
    function sq:getY() return self.y end
    function sq:getZ() return self.z end
    function sq:isBlockedTo(other) return self.blockAll==true or other.blockAll==true end
    function sq:isFree() return not self.blocked end
end
uuidA="11111111-1111-4111-8111-111111111111"
uuidB="22222222-2222-4222-8222-222222222222"
roster={}
local function prepare(c)
    c.pathCancelled=0; c.faced=0
    c.behavior={cancel=function() c.pathCancelled=c.pathCancelled+1 end,
        pathToLocation=function(_,x,y,z) c.pathTarget={x=x,y=y,z=z} end,
        update=function() return BehaviorResult.Working end}
    function c:getPathFindBehavior2() return self.behavior end
    function c:setPath2(value) self.path=value end
    function c:getVehicle() return nil end
    function c:pressedMovement() return false end
    function c:pressedCancelAction() return false end
    function c:faceLocation(x,y) self.faced=self.faced+1 end
    return c
end
roster[uuidA]=prepare(character(uuidA,.5,.5,0))
roster[uuidB]=prepare(character(uuidB,2.5,.5,0))
player=prepare(character(nil,1.5,2.5,0))
local baseInstanceof=instanceof
instanceof=function(obj,class)
    if class=="IsoPlayer" then return obj and ((obj.md and obj.md.ARAY_IsNPC) or obj==player) or false end
    if class=="IsoGameCharacter" then
        return obj and (obj.class=="IsoZombie" or (obj.md and obj.md.ARAY_IsNPC) or obj==player) or false
    end
    return baseInstanceof(obj,class)
end
focus=roster[uuidA]
function getSpecificPlayer(index) assert(index==0); return player end
function getPlayer() return player end
function getGameSpeed() return 1 end
function place(c,x,y,z)
    if c.sq then for i=#c.sq.movers,1,-1 do if c.sq.movers[i]==c then table.remove(c.sq.movers,i) end end end
    c.x,c.y,c.z=x,y,z
    c.sq=squares[math.floor(x)..":"..math.floor(y)..":"..math.floor(z)]
    if c.sq then table.insert(c.sq.movers,c) end
end
BehaviorResult={Failed="Failed",Succeeded="Succeeded",Working="Working"}
nativeStops=0; added=0; bubbles={}
ISBaseTimedAction={}
function ISBaseTimedAction:derive(name)
    local cls={Type=name}; setmetatable(cls,{__index=self}); return cls
end
function ISBaseTimedAction:forceStop() self:stop() end
function ISBaseTimedAction:forceComplete() self:perform() end
function ISBaseTimedAction:stop()
    nativeStops=nativeStops+1
    local q=ISTimedActionQueue.queues[self.character]
    q.queue={}; q.current=nil
end
function ISBaseTimedAction:perform()
    local q=ISTimedActionQueue.queues[self.character]
    for i=#q.queue,1,-1 do if q.queue[i]==self then table.remove(q.queue,i) end end
    q.current=q.queue[1]
end
ISTimedActionQueue={queues={}}
function ISTimedActionQueue.hasActionType(c,t)
    local q=ISTimedActionQueue.queues[c]
    if q then for _,a in ipairs(q.queue) do if a.Type==t then return true end end end
    return false
end
function ISTimedActionQueue.add(a)
    assert(a.character~=player,"player queue touched")
    added=added+1
    if failAdd then error("native path failure") end
    local q=ISTimedActionQueue.queues[a.character] or {queue={}}
    ISTimedActionQueue.queues[a.character]=q
    table.insert(q.queue,a); q.current=q.queue[1]
    a.action={setPathfinding=function() end,setAllowedWhileDraggingCorpses=function() end}
    a:start()
end
function queued(uuid)
    local q=ISTimedActionQueue.queues[roster[uuid]]
    return q and q.queue[1]
end
function complete(uuid)
    local a=queued(uuid); assert(a)
    place(roster[uuid],a.location:getX()+.5,a.location:getY()+.5,a.location:getZ())
    a:perform()
end
function decision(uuid,action,params,seq)
    seq=seq or 1
    return {kind="decision_response",ok=true,executable=false,npc_id=uuid,world_id="Sandbox/"..worldName,
        id=uuid.."-"..tostring(seq),session_id="session-1",session_started_at_ms=9000,sequence=seq,
        issued_at_ms=clock,expires_at_ms=clock+10000,
        decision={action=action,parameters=params or {},reason="Observed context",priority=2}}
end
function move(uuid,id,seq) return ArayHuman.Executor.submit(decision(uuid,"MOVE_TO",{candidate_id=id},seq)) end
function advance(ms)
    clock=clock+ms
    ArayHuman.Walking.update()
    manualTick()
    ArayHuman.Executor.update()
end
'''


@pytest.fixture(params=[lua51.LuaRuntime, lua54.LuaRuntime], ids=["lua51", "lua54"])
def lua(request):
    if not NATIVE.is_file():
        pytest.skip("B42 native Lua source unavailable; set ARAY_GAME_DIR")
    r = request.param(unpack_returned_tuples=True)
    r.execute(MOCKS)
    r.execute(ENGINE)
    r.execute(NATIVE.read_text(encoding="utf-8"))
    r.execute((CLIENT / "ArayHumanLocomotion.lua").read_text(encoding="utf-8"))
    r.execute((CLIENT / "ArayHumanWalking.lua").read_text(encoding="utf-8"))
    r.execute((CLIENT / "ArayHumanTest.lua").read_text(encoding="utf-8"))
    r.execute("baselineTick=handlers[#handlers]")
    r.execute('''
        ArayHuman.getNpcByUuid=function(id) return roster[id] end
        ArayHuman.getNpc=function() return focus end
        ArayHuman.rosterSnapshot=function()
            local result={}
            for id,c in pairs(roster) do result[#result+1]={uuid=id,character=c,dead=c:isDead()} end
            return result
        end
        ArayHuman.SpeechBubble={show=function(c,text,isPlayer)
            assert(c~=player); bubbles[#bubbles+1]={character=c,text=text}
        end}
    ''')
    r.execute((CLIENT / "ArayHumanCommands.lua").read_text(encoding="utf-8"))
    r.execute("manualTick=handlers[#handlers]")
    r.execute((CLIENT / "ArayHumanSurvival.lua").read_text(encoding="utf-8"))
    r.execute((CLIENT / "ArayHumanPerception.lua").read_text(encoding="utf-8"))
    r.execute((CLIENT / "ArayHumanInventory.lua").read_text(encoding="utf-8"))
    r.execute((CLIENT / "ArayHumanPhysical.lua").read_text(encoding="utf-8"))
    r.execute((CLIENT / "ArayHumanEscapePlanner.lua").read_text(encoding="utf-8"))
    r.execute((CLIENT / "ArayHumanExecutor.lua").read_text(encoding="utf-8"))
    r.execute((CLIENT / "ArayHumanNavigation.lua").read_text(encoding="utf-8"))
    r.execute('E=ArayHuman.Executor; assert(E.beginSession("session-1",9000))')
    yield r
    assert r.eval("forbiddenCalls") == 0
    assert r.eval("ISTimedActionQueue.queues[player] == nil")


def test_no_automatic_execution(lua):
    lua.execute('advance(1000); advance(1000); assert(added==0 and E.getState(uuidA)==nil)')


def test_independent_walks_and_cancellation(lua):
    lua.execute('''
        assert(move(uuidA,"tile:4:0:0")); assert(move(uuidB,"tile:5:0:0"))
        local b=queued(uuidB); assert(queued(uuidA)~=b)
        assert(E.cancel(uuidA,"test")); assert(queued(uuidA)==nil and queued(uuidB)==b)
        complete(uuidB)
        assert(E.getState(uuidA).state=="CANCELLED")
        assert(E.getState(uuidB).state=="COMPLETED")
    ''')


def test_replace_and_late_native_callbacks(lua):
    lua.execute('''
        assert(move(uuidA,"tile:4:0:0"))
        local old=queued(uuidA); local oldId=E.getState(uuidA).actionId
        assert(move(uuidA,"tile:5:0:0",2))
        local current=queued(uuidA); local stops=nativeStops
        old:stop(); old:perform(); old:update(); old:start(); old.onCompleteFunc()
        assert(nativeStops==stops and queued(uuidA)==current)
        assert(E.getState(uuidA).actionId~=oldId and E.getState(uuidA).state=="RUNNING")
        complete(uuidA); assert(E.getState(uuidA).state=="COMPLETED")
    ''')


def test_blocked_and_non_candidate_destinations(lua):
    lua.execute('''
        squares["4:0:0"].blocked=true
        local ok,reason=move(uuidA,"tile:4:0:0")
        assert(not ok and reason=="destination_not_in_snapshot" and added==0)
        ok,reason=move(uuidA,"tile:30:0:0")
        assert(not ok and reason=="destination_not_in_snapshot")
        local d=decision(uuidA,"MOVE_TO",{x=4,y=0,z=0})
        assert(not E.submit(d))
        assert(move(uuidA,"tile:3:0:0"))
        squares["3:0:0"].blocked=true; advance(250)
        assert(E.getState(uuidA).state=="CANCELLED" and queued(uuidA)==nil)
    ''')


def test_death_unloaded_world_and_session(lua):
    lua.execute('''
        assert(move(uuidA,"tile:4:0:0")); roster[uuidA].dead=true; advance(250)
        assert(E.getState(uuidA).state=="CANCELLED" and queued(uuidA)==nil)
        assert(move(uuidB,"tile:5:0:0")); worldName="another"
        advance(250); assert(E.getState(uuidB).result=="world_changed" and queued(uuidB)==nil)
        assert(not E.submit(decision(uuidB,"IDLE")))
        assert(E.beginSession("session-1",9000))
        assert(move(uuidB,"tile:5:0:0",2))
        assert(E.beginSession("session-2",9500))
        assert(E.getState(uuidB).result=="session_changed")
    ''')


def test_distance_limit_ask_and_scoped_approval(lua):
    lua.execute('''
        place(player,.5,.5,0); place(roster[uuidA],11.5,.5,0)
        local ok,reason=move(uuidA,"tile:15:0:0")
        assert(not ok and reason=="permission_required" and added==0)
        local s=E.getState(uuidA)
        assert(s.state=="WAITING_PERMISSION" and s.permissionMode=="ASK")
        assert(not E.approve(uuidB,s.actionId))
        assert(not E.recordNotice(uuidA,s.actionId,"notice"))
        assert(E.approve(uuidA,s.actionId)); assert(added==1)
        assert(not E.approve(uuidA,s.actionId))
    ''')


def test_notify_requires_registered_notice(lua):
    lua.execute('''
        E.config.permissionMode="NOTIFY"
        place(player,.5,.5,0); place(roster[uuidA],11.5,.5,0)
        assert(not move(uuidA,"tile:15:0:0")); assert(added==0)
        local s=E.getState(uuidA)
        assert(not E.recordNotice(uuidA,s.actionId,""))
        assert(E.recordNotice(uuidA,s.actionId,"Player notified locally")); assert(added==1)
    ''')


def test_permission_revalidates_expiry_and_occupancy(lua):
    lua.execute('''
        place(player,.5,.5,0); place(roster[uuidA],11.5,.5,0)
        assert(not move(uuidA,"tile:15:0:0")); local id=E.getState(uuidA).actionId
        squares["15:0:0"].blocked=true
        assert(not E.approve(uuidA,id)); assert(added==0 and E.getState(uuidA).state=="FAILED")
        squares["15:0:0"].blocked=false
        assert(not move(uuidA,"tile:15:0:0",2)); id=E.getState(uuidA).actionId
        clock=clock+11000; assert(not E.approve(uuidA,id)); assert(added==0)
    ''')


def test_local_emergency_bypasses_distance_then_stops(lua):
    lua.execute('''
        place(player,.5,.5,0); place(roster[uuidA],11.5,.5,0)
        local z=character(nil,10.5,.5,0,"IsoZombie")
        assert(E.escape(uuidA))
        local s=E.getState(uuidA)
        assert(s.emergency and s.justification and s.destination.x>12)
        assert(added==1 and s.timeoutMs==6000)
        z.dead=true; advance(250)
        assert(E.getState(uuidA).result=="danger_reduced" and queued(uuidA)==nil)
    ''')


def test_emergency_requires_local_proof_and_clear_corridor(lua):
    lua.execute('''
        assert(not E.escape(uuidA) and added==0)
        local d=decision(uuidA,"MOVE_TO",{candidate_id="tile:4:0:0"})
        d.emergency=true; assert(not E.submit(d) and added==0)
        local z=character(nil,-.5,.5,0,"IsoZombie")
        roster[uuidA].sq.blockAll=true
        assert(not E.escape(uuidA) and added==0)
        roster[uuidA].sq.blockAll=false
        for _,xy in ipairs({{1,0},{-1,0},{0,1},{0,-1}}) do
            squares[xy[1]..":"..xy[2]..":0"].blocked=true
        end
        assert(not E.escape(uuidA) and added==0)
    ''')


def test_threat_interrupts_common_walk(lua):
    lua.execute('''
        assert(move(uuidA,"tile:4:0:0")); local old=queued(uuidA)
        character(nil,-.5,.5,0,"IsoZombie")
        ArayHuman.Perception.clearSnapshot(uuidA); advance(250)
        -- 3C.3.1 now requests the local escape, rather than stopping and awaiting an explicit call.
        assert(E.getState(uuidA).localSurvival and queued(uuidA)~=old)
        old:perform(); old:stop(); assert(E.getState(uuidA).emergency)
    ''')


def test_native_failure_timeout_and_no_progress(lua):
    lua.execute('''
        failAdd=true; assert(not move(uuidA,"tile:4:0:0"))
        assert(E.getState(uuidA).state=="FAILED")
        failAdd=false; assert(move(uuidA,"tile:4:0:0",2))
        queued(uuidA).result=BehaviorResult.Failed; advance(250)
        assert(E.getState(uuidA).result=="pathfinding_failed")
        assert(move(uuidA,"tile:4:0:0",3)); advance(5001)
        assert(E.getState(uuidA).result=="sem progresso")
        E.config.timeoutMs=500
        assert(move(uuidA,"tile:4:0:0",4)); advance(501)
        assert(E.getState(uuidA).result=="timeout")
    ''')


def test_manual_commands_preempt_only_their_uuid(lua):
    lua.execute('''
        assert(move(uuidA,"tile:4:0:0")); assert(move(uuidB,"tile:5:0:0"))
        local b=queued(uuidB)
        assert(ArayHuman.order({name="STAY"},uuidA))
        assert(E.getState(uuidA).result=="manual_command" and queued(uuidB)==b)
        local ok,reason=move(uuidA,"tile:3:0:0",2)
        assert(not ok and reason=="manual_priority")
        E.releaseManual(uuidA)
        assert(not move(uuidA,"tile:3:0:0",2)) -- issued in same millisecond as manual cutoff
        clock=clock+1; assert(move(uuidA,"tile:3:0:0",2))
    ''')


def test_f7_legacy_walk_and_manual_order_wrappers(lua):
    lua.execute('''
        assert(ArayHuman.order({name="MOVE_TO",x=4,y=0,z=0}))
        assert(ArayHuman.getOrderName()=="MOVE_TO")
        focus=roster[uuidB]
        assert(ArayHuman.order({name="MOVE_TO",x=5,y=0,z=0}))
        assert(ArayHuman.getOrderName(uuidA)=="MOVE_TO")
        ArayHuman.cancelWalk(true)
        assert(queued(uuidB)==nil and queued(uuidA)~=nil)
        focus=roster[uuidA]; complete(uuidA)
        assert(ArayHuman.getOrderName()=="STAY")
        -- F7's function closes over the actual registry focus. Bind the simulated spawn focus.
        for i=1,30 do
            local name=debug.getupvalue(ArayHuman.testWalk,i)
            if name=="npc" then debug.setupvalue(ArayHuman.testWalk,i,focus); break end
        end
        ArayHuman.testWalk(); assert(queued(uuidA) and E.getState(uuidA)==nil)
        assert(ArayHuman.Perception.updateSnapshot(uuidA).order.value=="STAY")
    ''')


def test_follow_throttles_and_player_replacement(lua):
    lua.execute('''
        place(player,6.5,.5,0)
        assert(E.submit(decision(uuidA,"FOLLOW_PLAYER")))
        local n=added
        for i=1,20 do advance(10) end
        assert(added==n)
        complete(uuidA); assert(E.getState(uuidA).state=="FOLLOWING")
        player.dead=true
        player=character(nil,7.5,2.5,0)
        advance(1000)
        assert(E.getState(uuidA).state~="FAILED")
    ''')


def test_idle_look_say_stop_and_duplicate_validation(lua):
    lua.execute('''
        assert(E.submit(decision(uuidA,"LOOK_AT_PLAYER")))
        assert(roster[uuidA].faced==1 and player.faced==0)
        assert(E.submit(decision(uuidA,"SAY",{text="Ola"},2)))
        assert(#bubbles==1 and bubbles[1].character==roster[uuidA])
        assert(E.submit(decision(uuidA,"IDLE",{},3)))
        assert(E.submit(decision(uuidA,"STOP",{},4)))
        assert(not E.submit(decision(uuidA,"STOP",{},4)))
        local d=decision(uuidA,"IDLE",{},5); d.session_id="old"; assert(not E.submit(d))
        d=decision(uuidA,"IDLE",{},5); d.expires_at_ms=clock-1; assert(not E.submit(d))
        d=decision(uuidA,"EXECUTE_LUA",{},5); assert(not E.submit(d))
        d=decision("npc_1","IDLE"); assert(not E.submit(d))
    ''')


def test_instance_unloaded_and_optional_walk_api_missing(lua):
    lua.execute('''
        assert(move(uuidA,"tile:4:0:0")); squares["0:0:0"]=nil
        advance(250)
        assert(queued(uuidA)==nil and E.getState(uuidA).state=="CANCELLED")
        ISWalkToTimedAction=nil
        local ok,reason=move(uuidB,"tile:5:0:0")
        assert(not ok and reason=="walking_api_unavailable")
    ''')


def test_revalidates_live_occupancy_after_snapshot(lua):
    lua.execute('''
        local original=ArayHuman.Perception.updateSnapshot
        ArayHuman.Perception.updateSnapshot=function(id)
            local s=original(id)
            squares["4:0:0"].blocked=true
            return s
        end
        local ok,reason=move(uuidA,"tile:4:0:0")
        assert(not ok and reason=="destination_blocked" and added==0)
    ''')


def test_emergency_replaces_walk_and_is_time_limited(lua):
    lua.execute('''
        assert(move(uuidA,"tile:4:0:0")); local old=queued(uuidA)
        character(nil,-.5,.5,0,"IsoZombie")
        E.config.emergencyDurationMs=400
        assert(E.escape(uuidA)); local current=queued(uuidA)
        assert(old~=current and E.getState(uuidA).emergency)
        old:perform(); old:stop(); assert(queued(uuidA)==current)
        advance(401)
        assert(queued(uuidA)==nil and E.getState(uuidA).result=="timeout")
    ''')


def test_emergency_safe_deviation_and_insufficient_perception(lua):
    lua.execute('''
        character(nil,-.5,.5,0,"IsoZombie")
        assert(E.escape(uuidA))
        place(roster[uuidA],1.5,1.5,0); advance(250)
        assert(E.getState(uuidA).state=="RUNNING" and queued(uuidA))
        E.cancel(uuidA,"test_reset")
        ArayHuman.Perception.threatConfig.maxEntities=1
        local ok=E.escape(uuidA)
        assert(not ok and queued(uuidA)==nil)
    ''')


def test_manual_follow_is_scoped_throttled_and_stops_on_world_change(lua):
    lua.execute('''
        place(player,6.5,.5,0)
        assert(ArayHuman.order({name="FOLLOW_PLAYER"},uuidA))
        assert(ArayHuman.order({name="FOLLOW_PLAYER"},uuidB))
        local n=added; assert(n==2)
        for i=1,20 do advance(10) end
        assert(added==n and queued(uuidA) and queued(uuidB))
        worldName="new-world"; advance(1000)
        assert(queued(uuidA)==nil and queued(uuidB)==nil and added==n)
    ''')


def test_state_copies_and_foreign_queue_are_preserved(lua):
    lua.execute('''
        local foreign={Type="OtherAction"}
        ISTimedActionQueue.queues[roster[uuidA]]={queue={foreign},current=foreign}
        local ok,reason=move(uuidA,"tile:4:0:0")
        assert(not ok and reason=="foreign_action_busy")
        assert(queued(uuidA)==foreign)
        assert(move(uuidB,"tile:5:0:0"))
        local s=E.getState(uuidB); s.destination.x=999
        assert(E.getState(uuidB).destination.x==5)
    ''')


def test_context_command_retains_original_uuid_after_focus_changes(lua):
    lua.execute('''
        Events.OnFillWorldObjectContextMenu={Add=function(fn) fillContext=fn end}
        options={}
        local menu={addOption=function(_,label,target,fn)
            options[label]={target=target,fn=fn}; return {}
        end}
        ISContextMenu={getNew=function() return menu end}
        context={addOption=function() return {} end,addSubMenu=function() end}
        isoToScreenX=function(_,x,y,z) return x*100 end
        isoToScreenY=function(_,x,y,z) return y*100 end
        getMouseX=function() return 50 end; getMouseY=function() return 0 end
        roster[uuidA].isOnScreen=function() return true end
    ''')
    lua.execute((CLIENT / "ArayHumanContext.lua").read_text(encoding="utf-8"))
    lua.execute('''
        assert(move(uuidA,"tile:4:0:0")); assert(move(uuidB,"tile:5:0:0"))
        local b=queued(uuidB)
        fillContext(0,context,{},false)
        focus=roster[uuidB]
        local stay=options["Ficar aqui"]; assert(stay and stay.target==uuidA)
        stay.fn(stay.target)
        assert(E.getState(uuidA).result=="manual_command" and queued(uuidB)==b)
        assert(options["Ir até..."].target==uuidA)
    ''')
