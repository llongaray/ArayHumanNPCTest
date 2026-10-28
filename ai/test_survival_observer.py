"""Real production Lua observer; Java getters simulated, all mutations forbidden."""
import pytest

from test_navigation import nav, physical, safety, lua


@pytest.fixture
def observer(nav):
    nav.execute('''
        S=ArayHuman.Survival; S.clearAll()
        CharacterStat={}; MoodleType={}
        for _,k in ipairs({"HUNGER","THIRST","FATIGUE","ENDURANCE","PAIN","PANIC","STRESS","TEMPERATURE"}) do CharacterStat[k]=k end
        for _,k in ipairs({"ENDURANCE","TIRED","HUNGRY","THIRST","PANIC","BLEEDING","INJURED","PAIN","STRESS","HEAVY_LOAD","HYPERTHERMIA","HYPOTHERMIA"}) do MoodleType[k]=k end
        function healthyPart()
            local p={hp=100,bleeding=false,scratched=false,bitten=false,isCut=false,isInfectedWound=false,
                bandaged=false,IsInfected=false,getFractureTime=0,getBurnTime=0,getDeepWoundTime=0,getStitchTime=0}
            local o={values=p}
            for k in pairs(p) do if k~="hp" then local name=k; o[name]=function() return p[name] end end end
            o.getHealth=function() return p.hp end
            for _,k in ipairs({"setHealth","setBleeding","setBandaged","SetInfected"}) do o[k]=forbidden end
            return o
        end
        function prepareObserver(c)
            c.hp=100; c.infected=false; c.asleep=false; c.knocked=false; c.parts={healthyPart(),healthyPart()}
            c.values={HUNGER=0,THIRST=0,FATIGUE=0,ENDURANCE=1,PAIN=0,PANIC=0,STRESS=0,TEMPERATURE=37}
            c.moodleValues={}; c.inventoryItems={}; c.weight=0; c.capacity=12; c.reads=0
            c.stats={get=function(_,key) c.reads=c.reads+1; return c.values[key] end,set=forbidden,add=forbidden,remove=forbidden}
            c.body={getHealth=function() return c.hp end,
                IsInfected=function() return c.infected end,getBodyParts=function() return list(c.parts) end,
                getNumPartsBleeding=function() local n=0; for _,p in ipairs(c.parts) do if p.values.bleeding then n=n+1 end end; return n end,
                getNumPartsScratched=function() return c.parts[1].values.scratched and 1 or 0 end,
                getNumPartsBitten=function() return c.parts[1].values.bitten and 1 or 0 end,
                setHealth=forbidden,Update=forbidden}
            function c:getStats() return self.stats end
            function c:getBodyDamage() return self.body end
            function c:getMoodles() return {getMoodleLevel=function(_,key) return self.moodleValues[key] or 0 end,Update=forbidden} end
            function c:getInventory() return {getItems=function() return list(self.inventoryItems) end,AddItem=forbidden} end
            function c:getInventoryWeight() return self.weight end
            function c:getMaxWeight() return self.capacity end
            function c:isAsleep() return self.asleep end
            function c:isKnockedDown() return self.knocked end
            c.setHealth=forbidden; c.setAsleep=forbidden; c.setNPC=forbidden
        end
        prepareObserver(roster[uuidA]); prepareObserver(roster[uuidB])
        player.getStats=forbidden; player.getBodyDamage=forbidden; player.getInventory=forbidden
        player.getInventoryWeight=forbidden
        function hasState(s,key) return s.states[key].known and s.states[key].value==true end
        function eventsOf(id,kind)
            local r={}; for _,e in ipairs(S.getEvents(id)) do if e.type==kind then r[#r+1]=e end end; return r
        end
        function sample(id,ms) clock=clock+(ms or 1000); return assert(S.updateSnapshot(id or uuidA)) end
    ''')
    return nav


def test_two_npcs_independent_zero_false_and_defensive_copies(observer):
    observer.execute('''
        roster[uuidB].hp=20; roster[uuidB].values.HUNGER=.8
        local a=S.getSnapshot(uuidA); local b=S.getSnapshot(uuidB)
        assert(a.uuid==uuidA and b.uuid==uuidB and a.world_id=="Sandbox/"..worldName)
        assert(a.health.value==100 and b.health.value==20 and hasState(a,"HEALTHY"))
        assert(hasState(b,"CRITICAL") and hasState(b,"INJURED") and hasState(b,"HUNGRY"))
        assert(a.needs.hunger.status=="known" and a.needs.hunger.value==0)
        assert(a.conditions.asleep.known and a.conditions.asleep.value==false)
        assert(a.conditions.alive.known and a.conditions.alive.value==true)
        a.health.value=-1; b.wounds.items[1].health.value=-1
        assert(S.getSnapshot(uuidA).health.value==100 and S.getSnapshot(uuidB).wounds.items[1].health.value==100)
    ''')


def test_simultaneous_conditions_and_native_moodles_are_separate(observer):
    observer.execute('''
        local c=roster[uuidA]; c.hp=24; c.values.HUNGER=.7; c.values.THIRST=.9
        c.values.FATIGUE=.9; c.values.ENDURANCE=.1; c.values.PAIN=55; c.values.PANIC=80
        c.values.STRESS=.6; c.values.TEMPERATURE=39; c.asleep=true; c.knocked=true
        c.parts[1].values.bleeding=true; c.parts[1].values.bitten=true; c.parts[1].values.isInfectedWound=true
        c.infected=true; c.moodleValues.HUNGRY=3; c.weight=15
        local s=sample()
        for _,k in ipairs({"INJURED","CRITICAL","EXHAUSTED","HUNGRY","THIRSTY"}) do assert(hasState(s,k)) end
        assert(not hasState(s,"HEALTHY") and not hasState(s,"DEAD"))
        assert(s.conditions.bleeding_parts.value==1 and s.conditions.infected.value)
        assert(s.conditions.incapacitated.value and s.conditions.incapacitated.scope=="dead_or_native_knocked_down_only")
        assert(s.needs.pain.value==55 and s.needs.panic.value==80 and s.needs.temperature.value==39)
        assert(s.moodles.HUNGRY.value==3 and s.inventory.carried_weight.value==15)
        assert(s.wounds.infected_wounds.value==1 and s.conditions.asleep.value)
    ''')


def test_missing_vs_failed_vs_invalid_getters_do_not_invent_zero(observer):
    observer.execute('''
        local c=roster[uuidA]; CharacterStat.THIRST=nil
        c.stats.get=function(_,k) if k=="HUNGER" then error("unavailable") elseif k=="FATIGUE" then return 0/0 else return c.values[k] end end
        c.body.getHealth=nil; c.getMoodles=nil
        local s=sample()
        assert(s.needs.thirst.status=="unavailable" and s.needs.thirst.value==nil)
        assert(s.needs.hunger.status=="unknown" and s.needs.hunger.reason=="api_error")
        assert(s.needs.fatigue.status=="unknown" and s.needs.fatigue.reason=="invalid_value")
        assert(s.health.status=="unavailable" and not s.states.HEALTHY.known)
        assert(s.moodles.HUNGRY.status=="unavailable")
        assert(not s.states.INJURED.known and not s.states.CRITICAL.known)
    ''')


def test_damage_recovery_events_duration_and_no_fake_recovery_after_api_gap(observer):
    observer.execute('''
        local c=roster[uuidA]; sample()
        c.hp=80; local s=sample(nil,1200)
        local e=eventsOf(uuidA,"DAMAGE"); assert(#e==1 and e[1].delta==-20 and e[1].duration_ms==1200)
        assert(e[1].uuid==uuidA and e[1].world_id==s.world_id and e[1].threat.known==false)
        c.hp=90; sample(nil,500)
        e=eventsOf(uuidA,"RECOVERY"); assert(#e==1 and e[1].delta==10 and e[1].duration_ms==500)
        c.body.getHealth=nil; sample()
        c.body.getHealth=function() return 100 end; sample()
        assert(#eventsOf(uuidA,"RECOVERY")==1)
        e[1].delta=999; assert(eventsOf(uuidA,"RECOVERY")[1].delta==10)
    ''')


def test_needs_wounds_inventory_and_state_duration_events(observer):
    observer.execute('''
        local c=roster[uuidA]; sample()
        c.values.HUNGER=.5; c.parts[1].values.getFractureTime=5; c.weight=3
        local s=sample(nil,2000)
        assert(hasState(s,"HUNGRY") and hasState(s,"INJURED") and s.state_duration_ms.HUNGRY==0)
        assert(#eventsOf(uuidA,"NEED_CHANGED")==1)
        local found=false
        for _,e in ipairs(eventsOf(uuidA,"CONDITION_CHANGED")) do
            if e.field=="wounds.0" and e.changes.getFractureTime.after.value==5 then found=true end
        end
        assert(found)
        s=sample(nil,1500); assert(s.state_duration_ms.HUNGRY==1500)
        local before=#eventsOf(uuidA,"NEED_CHANGED"); sample()
        assert(#eventsOf(uuidA,"NEED_CHANGED")==before)
        c.values.HUNGER=0; sample(); c.values.HUNGER=.5
        assert(sample().state_duration_ms.HUNGRY==0)
    ''')


def test_death_is_immediate_single_event_and_never_active(observer):
    observer.execute('''
        local c=roster[uuidA]; local s=S.getSnapshot(uuidA)
        c.dead=true; c.hp=0
        s=S.getSnapshot(uuidA) -- bypasses interval on actual death
        assert(hasState(s,"DEAD") and not s.active and not hasState(s,"HEALTHY"))
        assert(s.conditions.alive.known and s.conditions.alive.value==false)
        assert(#eventsOf(uuidA,"DEATH")==1)
        sample(); sample(); assert(#eventsOf(uuidA,"DEATH")==1)
        assert(not S.getSnapshot(uuidB).conditions.dead.value)
    ''')


def test_world_unavailable_and_world_switch_clear_old_events_and_threats(observer):
    observer.execute('''
        local c=roster[uuidA]; sample(); c.hp=70; sample()
        local oldWorld=worldName; worldName="new-conditions-world"
        local s=S.getSnapshot(uuidA)
        assert(s.world_id=="Sandbox/"..worldName and #eventsOf(uuidA,"DAMAGE")==0)
        local oldGet=getWorld; getWorld=function() return nil end
        local r,why=S.getSnapshot(uuidA); assert(not r and why=="world_unavailable")
        assert(#S.getEvents(uuidA)==0)
        getWorld=oldGet; worldName=oldWorld
        assert(S.getSnapshot(uuidA).health.value==70 and #eventsOf(uuidA,"DAMAGE")==0)
    ''')


def test_unloaded_chunk_and_return_do_not_infer_damage_across_gap(observer):
    observer.execute('''
        local c=roster[uuidA]; sample()
        local sq=squares["0:0:0"]; squares["0:0:0"]=nil
        local s=S.getSnapshot(uuidA)
        assert(not s.available and not s.active and s.reason=="chunk_unavailable")
        assert(not s.health.known and not s.needs.hunger.known and s.conditions.dead.known)
        c.hp=40; squares["0:0:0"]=sq
        s=S.getSnapshot(uuidA); assert(s.health.value==40 and #eventsOf(uuidA,"DAMAGE")==0)
    ''')


def test_replaced_instance_wrong_uuid_player_and_removed_roster_are_isolated(observer):
    observer.execute('''
        assert(not S.getSnapshot(nil) and not S.updateSnapshot(nil))
        assert(not S.getSnapshot("npc_1"))
        sample(); roster[uuidA].hp=50; sample()
        local replacement=character(uuidA,.5,.5,0); preparePhysical(replacement); prepareObserver(replacement)
        roster[uuidA]=replacement
        assert(S.getSnapshot(uuidA).health.value==100 and #eventsOf(uuidA,"DAMAGE")==0)
        replacement.md.ARAY_Uuid=uuidB; assert(not S.getSnapshot(uuidA))
        roster[uuidA]=player; assert(not S.getSnapshot(uuidA))
        roster[uuidA]=nil; assert(#S.getEvents(uuidA)==0)
    ''')


def test_cache_interval_clear_events_bound_and_sequence_filter(observer):
    observer.execute('''
        local c=roster[uuidA]; local s=S.getSnapshot(uuidA); local reads=c.reads
        c.hp=90; clock=clock+999
        assert(S.getSnapshot(uuidA).health.value==100 and c.reads==reads)
        clock=clock+1; assert(S.getSnapshot(uuidA).health.value==90 and c.reads>reads)
        S.config.maxEvents=4
        for i=1,10 do c.values.HUNGER=i/20; sample() end
        local e=S.getEvents(uuidA); assert(#e==4 and e[1].sequence<e[4].sequence)
        assert(#S.getEvents(uuidA,e[3].sequence)==1)
        S.clearSnapshot(uuidA); assert(#S.getEvents(uuidA)==1) -- new baseline only
        S.clearAll(); assert(#eventsOf(uuidA,"DAMAGE")==0)
    ''')


def test_bounded_body_parts_and_inventory_are_explicitly_incomplete(observer):
    observer.execute('''
        local c=roster[uuidA]; S.config.maxBodyParts=1; S.config.maxInventoryItems=1
        c.inventoryItems={1,2}; c.getInventoryWeight=forbidden
        local s=sample()
        assert(s.wounds.examined==1 and not s.wounds.complete and s.wounds.reason=="body_part_budget")
        assert(not s.wounds.wounded_parts.known and not s.states.HEALTHY.known)
        assert(not s.inventory.carried_weight.known and s.inventory.item_count.value==2)
        c.parts[1].bleeding=function() error("bad getter") end
        assert(sample().wounds.items[1].bleeding.status=="unknown")
    ''')


def test_existing_threat_monitor_supplies_context_without_second_scan(observer):
    observer.execute('''
        local c=roster[uuidA]; sample()
        character(nil,-.3,.5,0,"IsoZombie")
        local o=ArayHuman.Perception.scanThreats(uuidA)
        assert(S.getSnapshot(uuidA).threat.known and S.getSnapshot(uuidA).threat.level=="CONTACT")
        c.hp=80; local s=sample(nil,100)
        assert(eventsOf(uuidA,"DAMAGE")[1].threat.level=="CONTACT")
        clock=clock+1600
        assert(not S.getSnapshot(uuidA).threat.known and S.getSnapshot(uuidA).threat.reason=="stale")
        local wrong={uuid=uuidB,world_id=s.world_id,captured_at_ms=clock}
        assert(not S.recordThreat(uuidA,wrong))
        assert(not S.getSnapshot(uuidB).threat.known)
    ''')


def test_integration_metrics_executor_perception_and_future_catalog(observer):
    observer.execute('''
        local c=roster[uuidA]
        local p=ArayHuman.Perception.updateSnapshot(uuidA)
        assert(p.survival.uuid==uuidA and p.survival.health.value==100)
        local m=L.beginMetrics(c,uuidA)
        assert(m.survival_before.uuid==uuidA)
        assert(L.submit({uuid=uuidA,world_id="Sandbox/"..worldName,action="MOVE_TO",action_id="conditions-walk",source="manual",target_id="tile:3:0:0"}))
        assert(E.getState(uuidA).conditions.uuid==uuidA)
        c.hp=90; clock=clock+1000; L.endMetrics(m,c,uuidA,true)
        assert(m.survival_after.health.value==90 and m.damage_received.value==10)
        local cat=S.getCatalog()
        for _,name in ipairs({"EAT","DRINK","REST","BANDAGE","SEEK_SAFETY"}) do
            assert(cat.actions[name].executable==false)
            assert(not L.submit({uuid=uuidA,world_id="Sandbox/"..worldName,action=name,action_id=name,source="manual"}))
        end
        assert(F.unsupportedReason("PUSH_ZOMBIE")=="UNSUPPORTED_target_exclusive_native_shove")
        assert(F.unsupportedReason("CLIMB_STAIRS")=="UNSUPPORTED_STAIRS_VERTICAL_VALIDATION")
        assert(player.pathCancelled==0)
    ''')


def test_scheduler_observes_needs_without_choosing_or_executing_actions(observer):
    observer.execute('''
        S.clearAll(); roster[uuidA].values.HUNGER=.9; roster[uuidB].values.THIRST=.9
        fireTick(1000)
        assert(hasState(S.getSnapshot(uuidA),"HUNGRY") and hasState(S.getSnapshot(uuidB),"THIRSTY"))
        assert(not queued(uuidA) and not queued(uuidB) and nativeCalls==0 and added==0)
        assert(not E.getState(uuidA) and not E.getState(uuidB))
        assert(S.getSnapshot(uuidA).needs.hunger.value==.9)
    ''')


def test_partial_wound_positive_evidence_and_incapacitation_unknown(observer):
    observer.execute('''
        local c=roster[uuidA]; S.config.maxBodyParts=1
        c.parts[1].values.getFractureTime=10
        local s=sample()
        assert(not s.wounds.complete and s.wounds.wounded_parts.observed_minimum==1)
        assert(hasState(s,"INJURED") and not hasState(s,"HEALTHY"))
        assert(s.conditions.knocked_down.known and s.conditions.knocked_down.value==false)
        assert(not s.conditions.incapacitated.known)
        c.knocked=true; s=sample(); assert(s.conditions.incapacitated.known and s.conditions.incapacitated.value)
    ''')


def test_initial_dead_actor_and_clock_rollback_never_invent_damage(observer):
    observer.execute('''
        local c=roster[uuidA]; c.dead=true; c.hp=0
        assert(hasState(S.getSnapshot(uuidA),"DEAD") and #eventsOf(uuidA,"DEATH")==1)
        c.dead=false; c.hp=100; sample()
        clock=clock-5000; c.hp=20
        local s=S.getSnapshot(uuidA)
        assert(s.health.value==20 and #eventsOf(uuidA,"DAMAGE")==0)
        assert(s.state_duration_ms.CRITICAL==0)
    ''')


def test_many_wounds_keep_damage_event_and_group_changes_by_part(observer):
    observer.execute('''
        local c=roster[uuidA]; c.parts={}
        for i=1,32 do c.parts[i]=healthyPart() end
        sample(); c.hp=50
        for _,p in ipairs(c.parts) do
            p.values.hp=80; p.values.bleeding=true; p.values.scratched=true
            p.values.bitten=true; p.values.isCut=true; p.values.getBurnTime=10
        end
        sample()
        assert(#eventsOf(uuidA,"DAMAGE")==1)
        local parts=0
        for _,e in ipairs(eventsOf(uuidA,"CONDITION_CHANGED")) do if e.changes then parts=parts+1 end end
        assert(parts==32 and #S.getEvents(uuidA)<128)
    ''')


def test_invalid_budgets_thresholds_and_configurable_scheduler_do_not_starve(observer):
    observer.execute('''
        S.clearAll(); S.config.maxPerTick=1; S.config.criticalHealth="invalid"
        S.config.epsilon=0/0; S.config.hunger="invalid"
        roster[uuidA].hp=10; roster[uuidA].values.HUNGER=.5
        fireTick(1000); fireTick(1)
        assert(hasState(S.getSnapshot(uuidA),"CRITICAL") and hasState(S.getSnapshot(uuidA),"HUNGRY"))
        assert(S.getSnapshot(uuidB).health.value==100)
        clock=clock-2000; fireTick(0)
        assert(S.getSnapshot(uuidA).captured_at_ms<=clock)
        assert(added==0 and nativeCalls==0)
    ''')


def test_small_real_need_changes_are_not_filtered_by_default(observer):
    observer.execute('''
        local c=roster[uuidA]; sample()
        c.values.HUNGER=.000001; sample()
        local events=eventsOf(uuidA,"NEED_CHANGED")
        assert(#events==1 and events[1].delta==.000001)
        assert(S.getSnapshot(uuidA).needs.hunger.value==.000001)
        assert(not hasState(S.getSnapshot(uuidA),"HUNGRY"))
    ''')
