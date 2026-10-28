"""Safety-zone refusals; no mocked collision is presented as native shove success."""
import pytest

from test_navigation import nav, physical, safety, lua


@pytest.mark.parametrize("player_distance,reason", [
    (1.999, "shove_player_too_close"),
    (2.0, "shove_player_too_close"),
    (2.001, "UNSUPPORTED_target_exclusive_native_shove"),
])
def test_player_distance_is_strict_and_never_authorizes_collision(nav, player_distance, reason):
    nav.globals().testDistance = player_distance
    nav.globals().expectedReason = reason
    nav.execute('''
        local c=roster[uuidA]
        character(nil,-.3,.5,0,"IsoZombie")
        place(player,c:getX(),c:getY()+testDistance,0)
        c.NPCSetAttack=forbidden; c.NPCSetMelee=forbidden
        local ok,why=F.defensiveShove(uuidA,c,obs())
        assert(not ok and why==expectedReason)
        assert(not F.busy(uuidA) and nativeCalls==0 and player.pathCancelled==0)
    ''')


@pytest.mark.parametrize("target_distance,eligible", [(1.25, True), (1.251, False)])
def test_target_fractional_distance_boundary(nav, target_distance, eligible):
    nav.globals().targetDistance = target_distance
    nav.globals().eligible = eligible
    nav.execute('''
        local c=roster[uuidA]
        local z=character(nil,c:getX()-targetDistance,c:getY(),0,"IsoZombie")
        local ok,why=F.defensiveShove(uuidA,c,obs())
        assert(not ok)
        assert(why==(eligible and F.unsupportedReason("PUSH_ZOMBIE") or "shove_target_or_orientation_invalid"))
        assert(z:getX()==c:getX()-targetDistance and nativeCalls==0)
    ''')


def test_multiple_zombies_do_not_provide_a_target_exclusivity_guarantee(nav):
    nav.execute('''
        local c=roster[uuidA]
        local z1=character(nil,-.3,.5,0,"IsoZombie")
        local z2=character(nil,-.4,.5,0,"IsoZombie")
        z1.Hit=forbidden; z2.Hit=forbidden
        z1.setX=forbidden; z2.setX=forbidden
        local ok,why=F.defensiveShove(uuidA,c,obs())
        assert(not ok and why==F.unsupportedReason("PUSH_ZOMBIE"))
        assert(logContains("collision_zone=unknown") and not F.busy(uuidA))
    ''')


@pytest.mark.parametrize("ally_x,ally_y", [(.7, .5), (-.7, .5), (.5, 1.3)])
def test_ally_in_front_behind_or_lateral_never_receives_a_shove(nav, ally_x, ally_y):
    nav.globals().allyX, nav.globals().allyY = ally_x, ally_y
    nav.execute('''
        local c=roster[uuidA]; local ally=roster[uuidB]
        character(nil,-.3,.5,0,"IsoZombie"); place(ally,allyX,allyY,0)
        ally.Hit=forbidden; c.NPCSetAttack=forbidden; c.NPCSetMelee=forbidden
        local ok,why=F.defensiveShove(uuidA,c,obs())
        assert(not ok and why==F.unsupportedReason("PUSH_ZOMBIE"))
        assert(ally:getX()==allyX and ally:getY()==allyY and nativeCalls==0)
    ''')


def test_fresh_evidence_does_not_hide_player_movement_or_survivor_switch(nav):
    nav.execute('''
        local c=roster[uuidA]; character(nil,-.3,.5,0,"IsoZombie")
        local captured=obs()
        place(player,.5,2.4,0) -- moved into the exclusion distance after capture
        assert(select(2,F.defensiveShove(uuidA,c,captured))=="shove_player_too_close")
        local originalGetter=ArayHuman.getLocalPlayer
        local replacement=character(nil,.5,1.5,0,"IsoPlayer")
        player.dead=true
        ArayHuman.getLocalPlayer=function() return replacement end
        assert(select(2,F.defensiveShove(uuidA,c,captured))=="shove_player_too_close")
        replacement.dead=true
        assert(select(2,F.defensiveShove(uuidA,c,captured))=="shove_player_unavailable")
        ArayHuman.getLocalPlayer=originalGetter
    ''')


def test_incomplete_stale_future_or_mismatched_perception_never_reaches_attack(nav):
    nav.execute('''
        local c=roster[uuidA]; character(nil,-.3,.5,0,"IsoZombie")
        local variants={obs(),obs(),obs(),obs(),obs()}
        variants[1].scan.complete=false
        variants[2].captured_at_ms=getTimestampMs()-1001
        variants[3].captured_at_ms=getTimestampMs()+1
        variants[4].uuid=uuidB
        variants[5].world_id="wrong"
        for _,o in ipairs(variants) do
            assert(select(2,F.defensiveShove(uuidA,c,o))=="emergency_not_confirmed")
        end
        assert(not F.busy(uuidA) and nativeCalls==0)
    ''')


def test_empty_initial_zone_does_not_authorize_future_moving_allies(nav):
    nav.execute('''
        local c=roster[uuidA]; local ally=roster[uuidB]
        character(nil,-.3,.5,0,"IsoZombie")
        local captured=obs()
        assert(select(2,F.defensiveShove(uuidA,c,captured))==F.unsupportedReason("PUSH_ZOMBIE"))
        -- No shove animation was started. Crossing afterwards must not revive it.
        place(ally,.6,.5,0); place(player,.5,1.5,0)
        F.update(uuidA,obs()); F.cancel(uuidA,"cancel_during_collision_window")
        F.update(uuidA,obs())
        assert(not F.busy(uuidA) and nativeCalls==0 and not queued(uuidA))
        assert(c:getX()==.5 and ally:getX()==.6 and player.pathCancelled==0)
    ''')


def test_unowned_attack_animation_is_not_cancelled_or_restarted(nav):
    nav.execute('''
        local c=roster[uuidA]; character(nil,-.3,.5,0,"IsoZombie")
        c.isPerformingShoveAnimation=function() return true end
        c.changeState=forbidden; c.NPCSetAttack=forbidden; c.setDoShove=forbidden
        local ok,why=F.defensiveShove(uuidA,c,obs())
        assert(not ok and why=="physical_busy")
        F.cancel(uuidA,"cancel")
        assert(c:isPerformingShoveAnimation() and not F.busy(uuidA) and nativeCalls==0)
    ''')


def test_capability_reports_unknown_swept_zone_even_with_all_attack_apis(nav):
    nav.execute('''
        local c=roster[uuidA]
        for _,k in ipairs({"NPCSetAttack","NPCSetMelee","setDoShove","pressedAttack","setAuthorizeShoveStomp"}) do c[k]=forbidden end
        local r=F.inspectCapabilities(uuidA).PUSH_ZOMBIE
        local zone=r.safety_zone
        assert(not r.supported and r.api_present.NPCSetMelee)
        assert(zone.target_max_distance==1.25 and zone.player_distance_must_exceed==2)
        assert(not zone.collision_area.known and not zone.exclusion_during_animation.known)
        assert(zone.selection_can_occur_at_collision and zone.nonempty_hit_list_may_be_reused)
        assert(zone.native_collision_requires_local_player)
        zone.collision_area.known=true
        assert(not F.inspectCapabilities(uuidA).PUSH_ZOMBIE.safety_zone.collision_area.known)
    ''')
