-- Local spatial observations only. No actions, inference, persistence or camera checks.
require "ArayHumanSurvival"
ArayHuman = ArayHuman or {}
ArayHuman.Perception = ArayHuman.Perception or {}
local P = ArayHuman.Perception
P.config = { intervalMs = 1000, radius = 10, maxEntities = 128,
    maxObjects = 128, maxTiles = 400 }

local cache = {}
local worldSeen = nil
local scheduled = {}
local cursor = 1
local lastCycle = nil
local offsets = {}
local offsetRadius = nil
local threatHistory = {}
P.threatConfig = { radius = 6, maxTiles = 169, maxEntities = 96,
    contactDistance = 1.25, immediateDistance = 2.5, approachDistance = 3.5,
    maxConnectionNodes = 48, maxConnections = 8 }

local function call(object, method, ...)
    if not object then return nil end
    local args = { ... }
    local ok, value = pcall(function()
        if not object[method] then return nil end
        return object[method](object, unpack(args))
    end)
    if ok then return value end
    return nil
end

local function global(fn, ...)
    if not fn then return nil end
    local ok, value = pcall(fn, ...)
    if ok then return value end
    return nil
end

local function number(value)
    return type(value) == "number" and value == value
        and value ~= math.huge and value ~= -math.huge
end

local function limit(name, fallback, low, high)
    local value = P.config[name]
    if not number(value) then value = fallback end
    return math.max(low, math.min(high, math.floor(value)))
end

local function known(value)
    if value == nil then return { known = false } end
    return { known = true, value = value }
end

local function copy(value)
    if type(value) ~= "table" then return value end
    local result = {}
    for key, item in pairs(value) do result[key] = copy(item) end
    return result
end

local function worldId()
    local world = global(getWorld)
    local name = call(world, "getWorld")
    local mode = call(global(getCore), "getGameMode")
    if not name or name == "unknown" or not mode or mode == "unknown" then return nil end
    return tostring(mode) .. "/" .. tostring(name)
end

function P.clearAll()
    cache = {}
    scheduled = {}
    cursor = 1
    lastCycle = nil
    threatHistory = {}
end

local function checkWorld()
    local current = worldId()
    if current ~= worldSeen then
        P.clearAll()
        worldSeen = current
    end
    return current
end

local function identity(character)
    local md = call(character, "getModData")
    if md and md.ARAY_IsNPC and type(md.ARAY_Uuid) == "string" then
        return md.ARAY_Uuid
    end
    return nil
end

local function find(uuid)
    if type(uuid) ~= "string" or uuid == "" then return nil end
    local character = global(ArayHuman.getNpcByUuid, uuid)
    if identity(character) == uuid then return character end
    return nil
end

local function position(character)
    local x, y, z = call(character, "getX"), call(character, "getY"), call(character, "getZ")
    if not number(x) or not number(y) or not number(z) then return { known = false } end
    return { known = true, x = x, y = y, z = z }
end

local function loaded(character, cell, pos)
    if not pos.known then return false end
    local square = call(character, "getCurrentSquare")
    return square ~= nil and square == call(cell, "getGridSquare",
        math.floor(pos.x), math.floor(pos.y), math.floor(pos.z))
end

local function distance(a, b)
    if not a.known or not b.known then return nil end
    return math.sqrt((a.x - b.x)^2 + (a.y - b.y)^2)
end

local function isType(object, class)
    return global(instanceof, object, class) == true
end

-- Confirm only adjacent edges. isBlockedTo is not used as a long-distance ray cast.
function P.edgePassable(a, b)
    if not a or not b then return nil end
    local ax,ay,az=call(a,"getX"),call(a,"getY"),call(a,"getZ")
    local bx,by,bz=call(b,"getX"),call(b,"getY"),call(b,"getZ")
    if not (number(ax) and number(ay) and number(az) and number(bx) and number(by) and number(bz)) then return nil end
    if az~=bz or math.abs(ax-bx)+math.abs(ay-by)~=1 then return false end
    if call(a,"TreatAsSolidFloor")~=true or call(b,"TreatAsSolidFloor")~=true then return false end
    local forward,reverse=call(a,"isBlockedTo",b),call(b,"isBlockedTo",a)
    if forward==true or reverse==true then return false, "api=isBlockedTo obstacle=collision_or_closed_edge from="..ax..","..ay..","..az.." to="..bx..","..by..","..bz.." direction="..(bx-ax)..","..(by-ay).." forward="..tostring(forward).." reverse="..tostring(reverse) end
    if forward~=false or reverse~=false then return nil end
    return true
end

local function connection(cell, origin, target, budget)
    if origin==target then return true end
    local tx,ty,tz=call(target,"getX"),call(target,"getY"),call(target,"getZ")
    local ox,oy,oz=call(origin,"getX"),call(origin,"getY"),call(origin,"getZ")
    if not (number(tx) and number(ty) and number(tz) and number(ox) and number(oy)) or oz~=tz then return nil end
    local todo,head,visited={origin},1,{[origin]=true}
    local unknown=false
    while head<=#todo and head<=budget do
        local sq=todo[head]; head=head+1
        for _,d in ipairs({{1,0},{-1,0},{0,1},{0,-1}}) do
            local x,y=call(sq,"getX")+d[1],call(sq,"getY")+d[2]
            if math.abs(x-ox)<=4 and math.abs(y-oy)<=4 then
                local nextSquare=call(cell,"getGridSquare",x,y,tz)
                if not nextSquare then unknown=true
                elseif not visited[nextSquare] then
                    local pass=P.edgePassable(sq,nextSquare)
                    if pass==nil then unknown=true
                    elseif pass then
                        if nextSquare==target then return true end
                        visited[nextSquare]=true
                        todo[#todo+1]=nextSquare
                    end
                end
            end
        end
    end
    if head<=#todo or unknown then return nil end
    return false
end

-- Fast safety lane: fresh local occupants only; no object/door/needs/full-map scan.
-- Fractional NPC coordinates determine the search bounds, not tile-center inclusion.
function P.scanThreats(uuid, readOnly)
    local world=checkWorld()
    local c=find(uuid); local cell=global(getCell); local pos=position(c)
    local out={uuid=uuid,world_id=world,captured_at_ms=global(getTimestampMs),active=false,
        threats={},level="NONE",immediate=false,nearest=known(nil),health_drop=false,
        scan={tiles=0,entities=0,unavailable=0,truncated=false,unknown=false,connections=0}}
    if not world or not c or call(c,"isDead")~=false or not loaded(c,cell,pos) then
        out.reason="dead_or_unloaded"; if uuid~=nil and not readOnly then threatHistory[uuid]=nil end; return out
    end
    out.active=true; out.position=pos
    local cfg=P.threatConfig
    local radius=math.max(1,math.min(6,tonumber(cfg.radius) or 6))
    local tileBudget=math.max(1,math.min(169,tonumber(cfg.maxTiles) or 169))
    local entityBudget=math.max(1,math.min(128,tonumber(cfg.maxEntities) or 96))
    local previous=threatHistory[uuid]
    if previous and previous.character~=c then previous=nil end
    local health=call(call(c,"getBodyDamage"),"getHealth")
    out.health_drop=number(health) and previous and number(previous.health) and health<previous.health-.01 or false
    local samples,seen={},{}
    local tiles={}
    for x=math.floor(pos.x-radius),math.floor(pos.x+radius) do
        for y=math.floor(pos.y-radius),math.floor(pos.y+radius) do
            local dx=math.max(x-pos.x,0,pos.x-(x+1))
            local dy=math.max(y-pos.y,0,pos.y-(y+1))
            if dx*dx+dy*dy<=radius*radius then tiles[#tiles+1]={x=x,y=y,d=dx*dx+dy*dy} end
        end
    end
    table.sort(tiles,function(a,b) if a.d~=b.d then return a.d<b.d end; if a.x~=b.x then return a.x<b.x end; return a.y<b.y end)
    local observed={}
    for i,t in ipairs(tiles) do
        if i>tileBudget then out.scan.truncated=true; break end
        out.scan.tiles=out.scan.tiles+1
        local sq=call(cell,"getGridSquare",t.x,t.y,math.floor(pos.z))
        if not sq then out.scan.unavailable=out.scan.unavailable+1
        else
            local moving=call(sq,"getMovingObjects"); local count=call(moving,"size")
            if not number(count) then out.scan.unknown=true
            else
                for index=0,count-1 do
                    if out.scan.entities>=entityBudget then out.scan.truncated=true; break end
                    out.scan.entities=out.scan.entities+1
                    local obj=call(moving,"get",index)
                    if obj and not seen[obj] then
                        seen[obj]=true
                        if isType(obj,"IsoZombie") then
                            local alive=call(obj,"isDead"); local p=position(obj); local d=distance(pos,p)
                            if alive==nil then out.scan.unknown=true end
                            if alive==false and d and d<=radius and math.floor(p.z)==math.floor(pos.z) then
                                local old=previous and previous.samples[obj]
                                local closing=old and previous.at and out.captured_at_ms>previous.at
                                    and out.captured_at_ms-previous.at<=2000 and old-d>=.15 or false
                                samples[obj]=d
                                observed[#observed+1]={position=p,distance=d,closing=closing,
                                    square=sq,object=obj}
                            end
                        end
                    end
                end
            end
        end
    end
    table.sort(observed,function(a,b) return a.distance<b.distance end)
    local bestLevel=0
    for _,t in ipairs(observed) do
        local linked=nil
        if t.distance<=4 and out.scan.connections<math.min(8,cfg.maxConnections or 8) then
            out.scan.connections=out.scan.connections+1
            linked=connection(cell,call(c,"getCurrentSquare"),t.square,math.min(48,cfg.maxConnectionNodes or 48))
            if linked==nil then out.scan.connection_unknown=true end
        end
        local entry={position=t.position,distance=t.distance,closing=t.closing,connected=known(linked),level="NEARBY"}
        local level=1
        if linked==true then
            if t.distance<=cfg.contactDistance or (out.health_drop and t.distance<=3) then
                level=3; entry.level="CONTACT"; entry.immediate=true
                entry.evidence=out.health_drop and "health_drop_with_live_zombie" or "contact_distance"
            elseif t.distance<=cfg.immediateDistance or (t.closing and t.distance<=cfg.approachDistance) then
                level=2; entry.level="APPROACHING"; entry.immediate=true
                entry.evidence=t.closing and "closing_distance" or "dangerous_distance"
            elseif t.closing then level=2; entry.level="APPROACHING" end
        end
        if entry.immediate then
            out.immediate=true
            if not out.immediate_distance or t.distance<out.immediate_distance then out.immediate_distance=t.distance end
            out.evidence=entry.evidence
        end
        if level>bestLevel then bestLevel=level; out.level=entry.level end
        out.threats[#out.threats+1]=entry
    end
    if observed[1] then out.nearest=known(observed[1].distance) end
    out.scan.complete=not(out.scan.truncated or out.scan.unknown or out.scan.unavailable>0)
    if not readOnly then
        threatHistory[uuid]={character=c,samples=samples,health=health,at=out.captured_at_ms}
        if ArayHuman.Survival then ArayHuman.Survival.recordThreat(uuid,out) end
    end
    return out
end

-- Outcome collection must not consume closing/health-drop evidence from the safety monitor.
function P.observeThreats(uuid) return P.scanThreats(uuid,true) end

local function getOffsets(radius)
    if radius == offsetRadius then return offsets end
    offsets = {}
    for dx = -radius, radius do
        for dy = -radius, radius do
            if dx * dx + dy * dy <= radius * radius then
                offsets[#offsets + 1] = { x = dx, y = dy, d = dx * dx + dy * dy }
            end
        end
    end
    table.sort(offsets, function(a, b)
        if a.d ~= b.d then return a.d < b.d end
        if a.x ~= b.x then return a.x < b.x end
        return a.y < b.y
    end)
    offsetRadius = radius
    return offsets
end

local function environment(s, character, cell)
    local scan = s.scan
    local seen = {}
    local candidates = getOffsets(s.radius)
    for i = 1, math.min(#candidates, scan.tile_budget) do
        local offset = candidates[i]
        local x, y, z = math.floor(s.position.x) + offset.x,
            math.floor(s.position.y) + offset.y, math.floor(s.position.z)
        scan.tiles_examined = scan.tiles_examined + 1
        local square = call(cell, "getGridSquare", x, y, z)
        if (x + 0.5 - s.position.x)^2 + (y + 0.5 - s.position.y)^2 > s.radius^2 then
            -- A tile offset is only a candidate; respect the radius from the actual position.
        elseif not square then
            scan.unavailable_tiles = scan.unavailable_tiles + 1
        else
            local floor = call(square, "TreatAsSolidFloor")
            local free = call(square, "isFree", false)
            local tile = { x = x, y = y, z = z, solid_floor = known(floor),
                free = known(free), traversable_candidate = known(nil) }
            if type(floor) == "boolean" and type(free) == "boolean" then
                tile.traversable_candidate = known(floor and free)
            end
            s.tiles[#s.tiles + 1] = tile
            if floor == false or free == false then
                s.obstacles[#s.obstacles + 1] = { x = x, y = y, z = z,
                    reason = floor == false and "no_solid_floor" or "not_free" }
            end
            local moving = call(square, "getMovingObjects")
            local count = call(moving, "size")
            if not number(count) then
                scan.entity_api_unknown = true
            else
                for index = 0, count - 1 do
                    if scan.entities_examined >= scan.entity_budget then
                        scan.entities_truncated = true
                        break
                    end
                    scan.entities_examined = scan.entities_examined + 1
                    local other = call(moving, "get", index)
                    if other and other ~= character and not seen[other] then
                        seen[other] = true
                        local pos = position(other)
                        local dist = distance(s.position, pos)
                        if dist and dist <= s.radius and math.floor(pos.z) == z then
                            local uuid = identity(other)
                            local entry = { position = pos, distance = dist,
                                alive = known(nil) }
                            local dead = call(other, "isDead")
                            if type(dead) == "boolean" then entry.alive = known(not dead) end
                            if uuid then
                                entry.uuid = uuid
                                s.nearby_npcs[#s.nearby_npcs + 1] = entry
                            elseif isType(other, "IsoZombie") then
                                s.nearby_zombies[#s.nearby_zombies + 1] = entry
                            end
                        end
                    end
                end
            end
            local objects = call(square, "getObjects")
            local objectCount = call(objects, "size")
            if not number(objectCount) then
                scan.object_api_unknown = true
            else
                for index = 0, objectCount - 1 do
                    if scan.objects_examined >= scan.object_budget then
                        scan.objects_truncated = true
                        break
                    end
                    scan.objects_examined = scan.objects_examined + 1
                    local obj = call(objects, "get", index)
                    if isType(obj, "IsoDoor") or
                        (isType(obj, "IsoThumpable") and call(obj, "isDoor") == true) then
                        s.doors[#s.doors + 1] = { x = x, y = y, z = z,
                            open = known(call(obj, "IsOpen")) }
                    end
                end
            end
        end
    end
    scan.tiles_truncated = #candidates > scan.tile_budget
    scan.complete = not (scan.tiles_truncated or scan.entities_truncated
        or scan.objects_truncated or scan.entity_api_unknown or scan.object_api_unknown
        or scan.unavailable_tiles > 0)
end

function P.updateSnapshot(uuid)
    local world = checkWorld()
    if type(uuid) ~= "string" or uuid == "" then return nil end
    local character = find(uuid)
    local dead = call(character, "isDead")
    local pos = position(character)
    local cell = global(getCell)
    local s = { uuid = uuid, world_id = world, world_known = world ~= nil,
        captured_at_ms = global(getTimestampMs), active = false,
        alive = known(nil),
        position = { known = false }, direction = known(nil),
        player = { known = false }, movement = {}, order = { known = false },
        health = known(nil), needs = {}, nearby_npcs = {}, nearby_zombies = {},
        tiles = {}, doors = {}, obstacles = {}, radius = limit("radius", 10, 1, 20),
        observation = "spatial_candidates_same_floor_no_los_or_path_guarantee",
        scan = { tiles_examined = 0, entities_examined = 0, objects_examined = 0,
            unavailable_tiles = 0, complete = false,
            tile_budget = limit("maxTiles", 400, 1, 1500),
            entity_budget = limit("maxEntities", 128, 1, 1024),
            object_budget = limit("maxObjects", 128, 1, 1024) } }
    -- Lua's and/or idiom cannot represent a known false value.
    if type(dead) == "boolean" then s.alive = known(not dead) end
    if not world then s.reason = "world_unavailable"
    elseif not character then s.reason = "instance_unavailable"
    elseif dead == true then s.reason = "dead"
    elseif dead ~= false then s.reason = "alive_unknown"
    elseif not loaded(character, cell, pos) then s.reason = "chunk_or_square_unavailable"
    else
        s.active = true
        s.position = pos
        local dir = call(character, "getDir")
        s.direction = known(dir ~= nil and tostring(dir) or nil)
        local player = global(ArayHuman.getLocalPlayer)
        if player and player ~= character and not identity(player)
            and call(player, "isDead") == false then
            local playerPos = position(player)
            if loaded(player, cell, playerPos) then
                s.player = { known = true, position = playerPos,
                    distance = known(distance(pos, playerPos)),
                    same_floor = known(math.floor(pos.z) == math.floor(playerPos.z)) }
            end
        end
        s.movement.walking = known(call(character, "isWalking"))
        s.movement.action_state = known(call(character, "getCurrentActionContextStateName"))
        s.movement.walk_queued = known(global(ISTimedActionQueue and
            ISTimedActionQueue.hasActionType, character, "ISWalkToTimedAction"))
        -- The existing order has no UUID owner. Report it only as unattributed metadata.
        local scopedOrder = global(ArayHuman.getOrderForUuid, uuid)
        if type(scopedOrder) == "string" then
            s.order = known(scopedOrder)
        else
            s.order.reason = "legacy_global_order_not_attributed"
        end
        if not s.order.known and global(ArayHuman.getNpc) == character then
            s.order.reported_global_name = global(ArayHuman.getOrderName)
        end
        local health = call(call(character, "getBodyDamage"), "getHealth")
        if number(health) then s.health = known(health) end
        local stats = call(character, "getStats")
        for _, key in ipairs({ "HUNGER", "THIRST", "FATIGUE" }) do
            local value = nil
            if CharacterStat and CharacterStat[key] then value = call(stats, "get", CharacterStat[key]) end
            s.needs[string.lower(key)] = known(number(value) and value or nil)
        end
        environment(s, character, cell)
    end
    if ArayHuman.Survival then s.survival=ArayHuman.Survival.getSnapshot(uuid) end
    cache[uuid] = { snapshot = s, character = character,
        player = global(ArayHuman.getLocalPlayer) }
    return copy(s)
end

function P.getSnapshot(uuid)
    checkWorld()
    local entry = cache[uuid]
    if not entry then return nil end
    local character = find(uuid)
    local dead = call(character, "isDead")
    local alive = entry.snapshot.alive
    if character ~= entry.character or (alive.known and dead ~= (not alive.value))
        or (entry.snapshot.active and global(ArayHuman.getLocalPlayer) ~= entry.player)
        or (entry.snapshot.player.known and call(entry.player, "isDead") ~= false)
        or (entry.snapshot.active and not loaded(character, global(getCell), position(character))) then
        cache[uuid] = nil
        return nil
    end
    return copy(entry.snapshot)
end

function P.clearSnapshot(uuid)
    if uuid ~= nil then cache[uuid] = nil end
end

local function tick()
    if not checkWorld() then return end
    local now = global(getTimestampMs)
    if not number(now) then return end
    if lastCycle == nil or (cursor > #scheduled and
        now - lastCycle >= limit("intervalMs", 1000, 100, 60000)) then
        lastCycle = now
        scheduled = global(ArayHuman.rosterSnapshot) or {}
        cursor = 1
        local present = {}
        for _, entry in ipairs(scheduled) do if entry.uuid then present[entry.uuid] = true end end
        for uuid in pairs(cache) do if not present[uuid] then cache[uuid] = nil end end
    end
    -- Spread work across frames, never scan every NPC in one tick.
    local entry = scheduled[cursor]
    if entry then
        cursor = cursor + 1
        if entry.uuid then P.updateSnapshot(entry.uuid) end
    end
end

if Events and Events.OnTick then Events.OnTick.Add(tick) end
