"""Execute the production Lua module with simulated B42 APIs (requires lupa)."""
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")
from lupa import lua51

SOURCE = Path(__file__).resolve().parents[1] / "42/media/lua/client/ArayHumanPerception.lua"

MOCKS = r'''
unpack = table.unpack or unpack
clock = 0
worldName = "test"
lookups = 0
forbiddenCalls = 0
forbidden = function() forbiddenCalls=forbiddenCalls+1; error("forbidden side effect") end
getFileWriter = forbidden
getFileReader = forbidden
IsoPlayer = { new = forbidden, setInstance = forbidden }
IsoCamera = { setCameraCharacter = forbidden }
Events = { OnTick = { Add = function(fn) tick = fn end } }
function getTimestampMs() return clock end
function getWorld() return { getWorld = function() return worldName end } end
function getCore() return { getGameMode = function() return "Sandbox" end } end
function instanceof(obj, class) return obj and obj.class == class end
function list(values)
    return { size = function() return #values end,
        get = function(_, index) return values[index + 1] end }
end
squares = {}
function square(x, y, z)
    local sq = { x=x, y=y, z=z, movers={}, objects={} }
    function sq:TreatAsSolidFloor() return true end
    function sq:isFree() return true end
    function sq:getMovingObjects() return list(self.movers) end
    function sq:getObjects() return list(self.objects) end
    squares[x .. ":" .. y .. ":" .. z] = sq
    return sq
end
cell = { getGridSquare = function(_, x,y,z)
    lookups = lookups + 1
    return squares[x .. ":" .. y .. ":" .. z]
end, getObjectList = forbidden, getZombieList = forbidden }
function getCell() return cell end
function character(id, x, y, z, class)
    local c = { id=id, x=x, y=y, z=z, dead=false, class=class,
        md={ ARAY_IsNPC=id ~= nil, ARAY_Uuid=id } }
    c.sq = squares[math.floor(x) .. ":" .. math.floor(y) .. ":" .. z]
    function c:getModData() return self.md end
    function c:getX() return self.x end
    function c:getY() return self.y end
    function c:getZ() return self.z end
    function c:isDead() return self.dead end
    function c:getCurrentSquare() return self.sq end
    function c:getDir() return "N" end
    function c:isWalking() return false end
    function c:getCurrentActionContextStateName() return "idle" end
    function c:getBodyDamage() return { getHealth=function() return 0 end } end
    function c:getStats() return { get=function() return 0 end } end
    c.teleportTo=forbidden; c.setX=forbidden; c.faceLocation=forbidden
    c.isOnScreen=forbidden; c.Say=forbidden
    if c.sq then table.insert(c.sq.movers, c) end
    return c
end
for x=-12,12 do for y=-12,12 do square(x,y,0) end end
roster = {}
roster.a = character("a",0.5,0.5,0)
roster.b = character("b",2.5,0.5,0)
player = character(nil,1.5,0.5,0)
CharacterStat = { HUNGER="hunger", THIRST="thirst", FATIGUE="fatigue" }
ISTimedActionQueue = { add=forbidden, clear=forbidden,
    hasActionType=function() return false end }
ArayHuman = { getNpcByUuid=function(id) return roster[id] end,
    getLocalPlayer=function() return player end,
    getNpc=function() return roster.a end,
    getOrderName=function() return "STAY" end,
    order=forbidden, walkTo=forbidden, Chat={sendMessage=forbidden},
    Persist={request=forbidden}, Bridge={sendModelSelection=forbidden},
    rosterSnapshot=function()
        local result={}
        for _,id in ipairs({"a","b"}) do
            if roster[id] then result[#result+1]={uuid=id, character=roster[id]} end
        end
        return result
    end }
'''


@pytest.fixture(params=[lua51.LuaRuntime, lupa.LuaRuntime], ids=["lua51", "default_lua"])
def lua(request):
    runtime = request.param(unpack_returned_tuples=True)
    runtime.execute(MOCKS)
    runtime.execute('package.preload["ArayHumanSurvival"]=function()\n' +
                    SOURCE.with_name("ArayHumanSurvival.lua").read_text(encoding="utf-8") +
                    '\nreturn ArayHuman.Survival end')
    runtime.execute(SOURCE.read_text(encoding="utf-8"))
    yield runtime
    assert runtime.eval("forbiddenCalls") == 0


def test_independent_snapshots_and_defensive_copy(lua):
    lua.execute('''
        local p=ArayHuman.Perception
        local a=p.updateSnapshot("a"); local b=p.updateSnapshot("b")
        assert(a.uuid=="a" and b.uuid=="b")
        assert(a.position.x==0.5 and b.position.x==2.5)
        assert(a.nearby_npcs[1].uuid=="b")
        assert(b.nearby_npcs[1].uuid=="a")
        a.position.x=999; a.nearby_npcs[1].uuid="wrong"
        assert(p.getSnapshot("a").position.x==0.5)
        assert(p.getSnapshot("a").nearby_npcs[1].uuid=="b")
        assert(p.getSnapshot("b").position.x==2.5)
        assert(not b.order.known and b.order.reported_global_name==nil)
        assert(not a.order.known and a.order.reported_global_name=="STAY")
    ''')


def test_current_survivor_and_death(lua):
    lua.execute('''
        local p=ArayHuman.Perception
        assert(p.updateSnapshot("a").player.distance.value==1)
        player.dead=true
        assert(p.getSnapshot("a")==nil)
        assert(not p.updateSnapshot("a").player.known)
        player=character(nil,5.5,0.5,0)
        assert(p.getSnapshot("a")==nil)
        assert(p.updateSnapshot("a").player.distance.value==5)
        roster.a.dead=true
        assert(p.getSnapshot("a")==nil)
        local a=p.updateSnapshot("a")
        assert(not a.active and a.alive.known and a.alive.value==false)
        assert(a.reason=="dead" and #a.tiles==0 and #a.nearby_npcs==0)
    ''')


def test_unloaded_instance_chunk_and_world(lua):
    lua.execute('''
        local p=ArayHuman.Perception
        p.updateSnapshot("a")
        squares["0:0:0"]=nil
        assert(p.getSnapshot("a")==nil)
        local a=p.updateSnapshot("a")
        assert(not a.active and not a.position.known and #a.tiles==0)
        assert(a.reason=="chunk_or_square_unavailable")
        local absent=p.updateSnapshot("missing")
        assert(not absent.active and not absent.alive.known)
        assert(absent.reason=="instance_unavailable")
        worldName="other"
        assert(p.getSnapshot("a")==nil and p.getSnapshot("missing")==nil)
        assert(p.updateSnapshot("b").world_id=="Sandbox/other")
        worldName=nil
        assert(p.getSnapshot("b")==nil)
        assert(p.updateSnapshot("b").reason=="world_unavailable")
    ''')


def test_radius_entities_and_object_budgets(lua):
    lua.execute('''
        local p=ArayHuman.Perception
        character(nil,9.5,0.5,0,"IsoZombie")
        character(nil,11.5,0.5,0,"IsoZombie")
        local a=p.updateSnapshot("a")
        assert(#a.nearby_zombies==1 and a.nearby_zombies[1].distance==9)
        assert(a.scan.tiles_examined<=400 and a.scan.entities_examined<=128)
        p.config.maxEntities=1; p.config.maxObjects=1; p.config.maxTiles=3
        for i=1,50 do character(nil,0.5,0.5,0,"IsoZombie") end
        squares["0:0:0"].objects={ {class="IsoDoor", IsOpen=function() return false end},
            {class="IsoDoor", IsOpen=function() return true end} }
        a=p.updateSnapshot("a")
        assert(a.scan.entities_examined==1 and a.scan.entities_truncated)
        assert(a.scan.objects_examined==1 and a.scan.objects_truncated)
        assert(a.scan.tiles_examined==3 and a.scan.tiles_truncated)
        assert(not a.scan.complete and #a.doors==1)
        assert(a.doors[1].open.known and a.doors[1].open.value==false)
    ''')


def test_optional_apis_and_zero(lua):
    lua.execute('''
        local p=ArayHuman.Perception
        local a=p.updateSnapshot("a")
        assert(a.health.known and a.health.value==0)
        assert(a.needs.hunger.known and a.needs.hunger.value==0)
        assert(a.movement.walking.known and a.movement.walking.value==false)
        roster.a.getBodyDamage=nil; roster.a.getStats=nil; roster.a.isWalking=nil
        roster.a.getDir=function() error("not exposed") end
        CharacterStat=nil; ISTimedActionQueue=nil
        a=p.updateSnapshot("a")
        assert(a.active and not a.health.known and not a.needs.hunger.known)
        assert(not a.direction.known and not a.movement.walking.known)
        assert(not a.movement.walk_queued.known)
        squares["1:0:0"]=nil
        a=p.updateSnapshot("a")
        assert(a.scan.unavailable_tiles==1 and not a.scan.complete)
        for _,tile in ipairs(a.tiles) do assert(not (tile.x==1 and tile.y==0)) end
    ''')


def test_cache_frequency_clear_and_no_side_effects(lua):
    lua.execute('''
        local p=ArayHuman.Perception
        assert(p.getSnapshot("a")==nil)
        tick(); tick()
        assert(p.getSnapshot("a") and p.getSnapshot("b"))
        local old=p.getSnapshot("a").captured_at_ms
        clock=999; tick(); assert(p.getSnapshot("a").captured_at_ms==old)
        clock=1000; tick(); assert(p.getSnapshot("a").captured_at_ms==1000)
        assert(p.getSnapshot("b").captured_at_ms==old)
        tick(); assert(p.getSnapshot("b").captured_at_ms==1000)
        p.clearSnapshot("a"); assert(p.getSnapshot("a")==nil)
        assert(p.getSnapshot("b"))
        p.clearAll(); assert(p.getSnapshot("b")==nil)
        -- Every mutating, global map, camera, rendering and inference API is a trap.
        -- The production module has run both scheduled and explicit scans above.
        assert(roster.a.x==0.5 and roster.b.x==2.5)
    ''')


def test_identity_mismatch_and_instance_replacement(lua):
    lua.execute('''
        local p=ArayHuman.Perception
        p.updateSnapshot("a")
        roster.a=character("a",3.5,0.5,0)
        assert(p.getSnapshot("a")==nil)
        assert(p.updateSnapshot("a").position.x==3.5)
        roster.a.md.ARAY_Uuid="b"
        assert(p.getSnapshot("a")==nil)
        assert(not p.updateSnapshot("a").active)
    ''')


def test_obstacles_unknown_tiles_and_config_limits(lua):
    lua.execute('''
        local p=ArayHuman.Perception
        p.config.radius=2
        squares["1:0:0"].isFree=function() return false end
        squares["0:1:0"].TreatAsSolidFloor=function() return false end
        squares["-1:0:0"].isFree=nil
        local a=p.updateSnapshot("a")
        assert(#a.obstacles==2)
        for _,tile in ipairs(a.tiles) do
            assert((tile.x+0.5-a.position.x)^2+(tile.y+0.5-a.position.y)^2<=4)
            if tile.x==-1 and tile.y==0 then
                assert(not tile.free.known and not tile.traversable_candidate.known)
            end
        end
        p.config.radius=0/0; p.config.maxEntities=-5
        p.config.maxTiles=999999; p.config.intervalMs="invalid"
        a=p.updateSnapshot("a")
        assert(a.radius==10 and a.scan.entity_budget==1 and a.scan.tile_budget==1500)
        assert(p.updateSnapshot(nil)==nil)
        p.clearSnapshot(nil)
    ''')


def test_scheduler_does_not_starve_later_npcs(lua):
    lua.execute('''
        local p=ArayHuman.Perception
        tick()
        clock=2000; tick()
        assert(p.getSnapshot("b").captured_at_ms==2000)
        roster.b=nil
        clock=3000; tick()
        assert(p.getSnapshot("b")==nil)
    ''')
