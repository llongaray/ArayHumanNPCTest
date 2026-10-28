"""Fractional native motion and bounded recovery; real Lua 5.1/5.4 modules."""
from test_survival import safety, lua


def test_long_native_leg_and_fractional_motion(safety):
    safety.execute('''
        character(nil,-.5,.5,0,"IsoZombie"); fireTick(250)
        local old=queued(uuidA); local s=E.getState(uuidA)
        assert(s.currentLeg.y < -1) -- no one-tile waypoint conveyor
        place(roster[uuidA],.73,.13,0); fireTick(250)
        assert(queued(uuidA)==old and E.getState(uuidA).state=="RUNNING")
        local m=ArayHuman.Walking.getState(uuidA)
        assert(m.actualX==.73 and m.speed>0 and m.travelled>0 and m.queued)
        assert(not m.done and logContains("event=escape_progress"))
    ''')


def test_diagonal_segment_does_not_call_nonadjacent_edge(safety):
    safety.execute('''
        local a=squares["0:0:0"]; local b=squares["1:1:0"]
        assert(ArayHuman.Perception.edgePassable(a,b)==false)
        assert(ArayHuman.EscapePlanner.segmentPassable(.9,.8,1.6,1.7,0,roster[uuidA]))
    ''')


def test_corner_wall_and_unknown_are_not_bypassed(safety):
    safety.execute('''
        local p=ArayHuman.EscapePlanner
        squares["1:0:0"].blockAll=true
        local ok,detail=p.segmentPassable(.5,.5,1.5,1.5,0,roster[uuidA])
        assert(not ok and detail:find("api=isBlockedTo",1,true))
        assert(detail:find("from=0,0,0",1,true) and detail:find("direction=1,0",1,true))
        squares["1:0:0"].blockAll=false
        squares["1:0:0"].isBlockedTo=nil
        assert(not p.segmentPassable(.5,.5,1.5,1.5,0,roster[uuidA]))
    ''')


def test_dynamic_block_replans_from_real_position_and_stale_callback(safety):
    safety.execute('''
        character(nil,-.5,.5,0,"IsoZombie"); fireTick(250)
        local old=queued(uuidA); local first=E.getState(uuidA)
        place(roster[uuidA],.6,.15,0)
        squares["0:-1:0"].blockAll=true; fireTick(250)
        assert(queued(uuidA)==nil and logContains("api=isBlockedTo"))
        fireTick(1000)
        local replacement=queued(uuidA); local s=E.getState(uuidA)
        assert(replacement and s.actionId~=first.actionId)
        assert(s.destination.target_id~=first.destination.target_id)
        old:stop(); old:perform(); old.onCompleteFunc()
        assert(queued(uuidA)==replacement)
        assert(s.startedAt==clock)
    ''')


def test_persistent_threat_recovers_but_has_finite_budget(safety):
    safety.execute('''
        E.survivalConfig.recoveryMs=3000
        character(nil,-.5,.5,0,"IsoZombie")
        for _,xy in ipairs({{1,0},{0,1},{0,-1}}) do squares[xy[1]..":"..xy[2]..":0"].blocked=true end
        for i=1,50 do fireTick(1000) end
        local ep=E.getSurvivalState(uuidA)
        assert(ep.attempts==3 and ep.recoveries==2 and queued(uuidA)==nil)
        assert(logContains("event=controlled_recovery"))
        local at=ep.nextAttemptAt
        for i=1,20 do fireTick(1000) end
        assert(E.getSurvivalState(uuidA).nextAttemptAt==at and added==0)
    ''')


def test_recovery_after_obstacle_removed(safety):
    safety.execute('''
        E.survivalConfig.recoveryMs=3000
        character(nil,-.5,.5,0,"IsoZombie")
        for _,xy in ipairs({{1,0},{0,1},{0,-1}}) do squares[xy[1]..":"..xy[2]..":0"].blocked=true end
        fireTick(250); fireTick(1000); fireTick(1000)
        assert(E.getSurvivalState(uuidA).attempts==3 and not queued(uuidA))
        squares["0:-1:0"].blocked=false
        fireTick(3000)
        assert(queued(uuidA) and E.getSurvivalState(uuidA).recoveries==1)
        assert(E.getState(uuidA).state=="RUNNING") -- started is not completed
    ''')
