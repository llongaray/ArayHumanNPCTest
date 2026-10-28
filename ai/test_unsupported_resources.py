"""Audited refusals are not successful shove/stairs simulations. Real Lua 5.1/5.4."""
from test_navigation import nav, physical, safety, lua


def test_capability_report_does_not_enable_present_attack_or_stair_apis(nav):
    nav.execute('''
        local c=roster[uuidA]
        c.NPCSetAttack=forbidden; c.setAuthorizeShoveStomp=forbidden; c.doStairs=forbidden
        local sq=c:getCurrentSquare()
        sq.HasStairs=function() return true end
        sq.HasStairTop=function() return false end
        sq.HasStairsBelow=function() return false end
        local r=assert(F.inspectCapabilities(uuidA))
        assert(r.uuid==uuidA and r.world_id=="Sandbox/"..worldName)
        assert(r.CLIMB_STAIRS.has_stairs.known and r.CLIMB_STAIRS.has_stairs.value)
        assert(r.CLIMB_STAIRS.has_stair_top.known and r.CLIMB_STAIRS.has_stair_top.value==false)
        assert(r.CLIMB_STAIRS.position.x==.5 and r.CLIMB_STAIRS.tile.x==0)
        assert(r.PUSH_ZOMBIE.api_present.NPCSetAttack and r.CLIMB_STAIRS.api_present.doStairs)
        assert(not r.PUSH_ZOMBIE.supported and not r.CLIMB_STAIRS.supported)
        r.PUSH_ZOMBIE.supported=true
        assert(not F.inspectCapabilities(uuidA).PUSH_ZOMBIE.supported)
        assert(nativeCalls==0)
    ''')


def test_missing_and_throwing_stair_apis_preserve_unknown(nav):
    nav.execute('''
        local sq=roster[uuidA]:getCurrentSquare()
        sq.HasStairs=function() error("unavailable") end
        sq.HasStairTop=nil
        local r=assert(F.inspectCapabilities(uuidA))
        assert(not r.CLIMB_STAIRS.has_stairs.known and r.CLIMB_STAIRS.has_stairs.value==nil)
        assert(not r.CLIMB_STAIRS.has_stair_top.known)
        assert(not r.CLIMB_STAIRS.api_present.doStairs)
        assert(not r.CLIMB_STAIRS.supported)
    ''')


def test_capabilities_reject_player_wrong_uuid_dead_or_unloaded_actor(nav):
    nav.execute('''
        assert(not F.inspectCapabilities("npc_1"))
        roster[uuidA].dead=true; assert(not F.inspectCapabilities(uuidA))
        roster[uuidA].dead=false
        squares["0:0:0"]=nil
        local r,why=F.inspectCapabilities(uuidA)
        assert(not r and why=="chunk_unavailable")
        roster[uuidA]=player
        assert(not F.inspectCapabilities(uuidA))
    ''')


def test_new_executor_actions_refuse_before_cancelling_existing_walk(nav):
    nav.execute('''
        assert(L.submit({uuid=uuidA,world_id="Sandbox/"..worldName,action="MOVE_TO",
            action_id="original",source="manual",target_id="tile:3:0:0"}))
        local before=L.getState(uuidA); local a=queued(uuidA)
        for _,kind in ipairs({"PUSH_ZOMBIE","CLIMB_STAIRS"}) do
            local ok,why=L.submit({uuid=uuidA,world_id="Sandbox/"..worldName,
                action=kind,action_id=kind,source="manual"})
            assert(not ok and why==F.unsupportedReason(kind))
            assert(L.getState(uuidA).action_id==before.action_id and queued(uuidA)==a)
        end
        assert(player.pathCancelled==0 and nativeCalls==0)
    ''')


def test_new_actions_still_validate_world_uuid_expiration_and_metadata(nav):
    nav.execute('''
        local req={uuid=uuidA,world_id="wrong",action="PUSH_ZOMBIE",action_id="test",source="manual"}
        local ok,why=L.submit(req); assert(not ok and why=="world_mismatch")
        req.world_id="Sandbox/"..worldName; req.uuid="npc_1"
        ok,why=L.submit(req); assert(not ok and why=="instance_unavailable")
        req.uuid=uuidA; req.expires_at_ms=getTimestampMs()-1
        ok,why=L.submit(req); assert(not ok and why=="expired")
        req.expires_at_ms=nil; req.action_id=nil
        ok,why=L.submit(req); assert(not ok and why=="action_id_invalid")
    ''')


def test_compound_plan_refuses_unsupported_step_before_starting_first_walk(nav):
    nav.execute('''
        for _,kind in ipairs({"PUSH_ZOMBIE","CLIMB_STAIRS","STAIRS"}) do
            local ok,why=N.submit(plan({{action="WALK",target_id="tile:3:0:0"},
                {action=kind,target_id="tile:1:0:1"}}))
            assert(not ok and why==F.unsupportedReason(kind))
            assert(not queued(uuidA) and not N.getState(uuidA))
        end
    ''')


def test_live_zombie_is_only_eligible_not_a_claimed_success(nav):
    nav.execute('''
        local z=character(nil,-.3,.5,0,"IsoZombie")
        z.Hit=forbidden; z.setX=forbidden; z.setZ=forbidden
        local c=roster[uuidA]; c.NPCSetAttack=forbidden; c.setAuthorizeShoveStomp=forbidden
        local ok,why=F.defensiveShove(uuidA,c,obs())
        assert(not ok and why==F.unsupportedReason("PUSH_ZOMBIE"))
        assert(not F.busy(uuidA) and not F.getResult(uuidA,"PUSH_ZOMBIE"))
        assert(logContains("executed=false") and nativeCalls==0)
    ''')


def test_no_player_or_allied_npc_target_from_forged_threat(nav):
    nav.execute('''
        place(player,.7,.5,0); place(roster[uuidB],.8,.5,0)
        local o={uuid=uuidA,world_id="Sandbox/"..worldName,active=true,immediate=true,
            captured_at_ms=getTimestampMs(),scan={complete=true},
            threats={{position={x=.7,y=.5,z=0}},{position={x=.8,y=.5,z=0}}}}
        local ok,why=F.defensiveShove(uuidA,roster[uuidA],o)
        assert(not ok and why=="shove_target_or_orientation_invalid")
        assert(not F.defensiveShove(uuidA,player,o) and nativeCalls==0)
    ''')


def test_shove_range_orientation_and_true_wall_are_rejected(nav):
    nav.execute('''
        local z=character(nil,-.3,.5,0,"IsoZombie"); local c=roster[uuidA]
        c.isFacingLocation=function() return false end
        local ok,why=F.defensiveShove(uuidA,c,obs())
        assert(not ok and why=="shove_target_or_orientation_invalid")
        c.isFacingLocation=function() return true end
        local beforeWall=obs(); c:getCurrentSquare().blockAll=true
        ok,why=F.defensiveShove(uuidA,c,beforeWall)
        assert(not ok and why=="shove_target_or_orientation_invalid")
        c:getCurrentSquare().blockAll=false; place(z,-1.3,.5,0)
        assert(not F.defensiveShove(uuidA,c,obs()) and nativeCalls==0)
    ''')


def test_malformed_unknown_or_stale_shove_evidence_is_safe(nav):
    nav.execute('''
        local c=roster[uuidA]; character(nil,-.3,.5,0,"IsoZombie")
        local o=obs(); o.scan=nil
        local ok,why=F.defensiveShove(uuidA,c,o)
        assert(not ok and why=="emergency_not_confirmed")
        o=obs(); o.captured_at_ms=getTimestampMs()-1001
        assert(not F.defensiveShove(uuidA,c,o))
        o=obs(); o.threats={{position={x=0/0,y=.5,z=0}},{}}
        ok,why=F.defensiveShove(uuidA,c,o)
        assert(not ok and why=="shove_target_or_orientation_invalid")
        o=obs(); o.threats[1].position.x=.5; o.threats[1].position.y=.5
        c:getCurrentSquare().getMovingObjects=function() error("unavailable") end
        ok,why=F.defensiveShove(uuidA,c,o)
        assert(not ok and why=="shove_scan_unavailable")
    ''')


def test_dead_or_moved_zombie_does_not_match_old_observation(nav):
    nav.execute('''
        local c=roster[uuidA]; local z=character(nil,-.3,.5,0,"IsoZombie"); local o=obs()
        z.dead=true
        local ok,why=F.defensiveShove(uuidA,c,o)
        assert(not ok and why=="shove_target_or_orientation_invalid")
        z.dead=false; z.z=1
        ok,why=F.defensiveShove(uuidA,c,o)
        assert(not ok and why=="shove_target_or_orientation_invalid")
    ''')


def test_shove_diagnostics_budget_and_two_independent_cooldowns(nav):
    nav.execute('''
        local a=roster[uuidA]; local b=roster[uuidB]
        character(nil,-.3,.5,0,"IsoZombie"); character(nil,19.7,10.5,0,"IsoZombie")
        assert(select(2,F.defensiveShove(uuidA,a,obs(uuidA)))==F.unsupportedReason("PUSH_ZOMBIE"))
        assert(select(2,F.defensiveShove(uuidB,b,obs(uuidB)))==F.unsupportedReason("PUSH_ZOMBIE"))
        assert(select(2,F.defensiveShove(uuidA,a,obs(uuidA)))=="shove_cooldown")
        worldName="another-world"
        assert(select(2,F.defensiveShove(uuidA,a,obs(uuidA)))==F.unsupportedReason("PUSH_ZOMBIE"))
        local o=obs(uuidB); o.threats={}
        for i=1,33 do o.threats[i]={position={x=100,y=100,z=0}} end
        assert(select(2,F.defensiveShove(uuidB,b,o))=="shove_scan_budget")
        assert(not F.busy(uuidA) and not F.busy(uuidB))
    ''')


def test_unsupported_request_during_animation_leaves_native_lock_intact(nav):
    nav.execute('''
        local w=obstacle("IsoWindow"); local token=assert(tokenFor(w))
        assert(interaction("OPEN_WINDOW",token,uuidA,"manual"))
        assert(untilTick(function() return roster[uuidA].state=="OpenWindowState" end))
        local old=F.getState(uuidA)
        local ok,why=interaction("PUSH_ZOMBIE",nil,uuidA,"manual")
        assert(not ok and why==F.unsupportedReason("PUSH_ZOMBIE"))
        assert(F.getState(uuidA).action_id==old.action_id and roster[uuidA].state=="OpenWindowState")
        E.cancel(uuidA,"manual_cancel")
        assert(F.busy(uuidA) and roster[uuidA].state=="OpenWindowState")
        finishNative(uuidA)
        assert(untilTick(function() return not F.busy(uuidA) end))
        assert(L.getState(uuidA).state=="CANCELLED" and nativeCalls==1)
    ''')


def test_stair_presence_never_causes_synthetic_z_or_success(nav):
    nav.execute('''
        local c=roster[uuidA]; c:getCurrentSquare().HasStairs=function() return true end
        c.doStairs=forbidden; c.setZ=forbidden
        local initialZ=c:getZ()
        local ok,why=interaction("CLIMB_STAIRS","tile:1:0:1",uuidA,"manual")
        assert(not ok and why=="UNSUPPORTED_STAIRS_VERTICAL_VALIDATION")
        assert(c:getZ()==initialZ and not queued(uuidA) and not F.busy(uuidA))
        assert(not F.actions.CLIMB_STAIRS and not F.actions.PUSH_ZOMBIE)
        assert(player.pathCancelled==0 and not ISTimedActionQueue.queues[player])
    ''')
