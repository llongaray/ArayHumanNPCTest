require "ArayHumanJson"
-- Fase 3B.2: pedidos de persistencia e leitura da resposta. Nao spawna sozinho.
ArayHuman = ArayHuman or {}
ArayHuman.Persist = ArayHuman.Persist or {}

local ROOT = "ArayHumanNPCTest"
local seq = 0
local pending = nil
local handled = {}

local function nowMs()
    if getTimestampMs then return getTimestampMs() end
    return 0
end

local function esc(value)
    local text = tostring(value or "")
    text = text:gsub("\\", "\\\\")
    text = text:gsub("\"", "\\\"")
    text = text:gsub("\r", "")
    text = text:gsub("\n", "\\n")
    return text
end

function ArayHuman.Persist.worldId()
    local name = "unknown"
    local mode = "unknown"
    local world = getWorld and getWorld() or nil
    if world and world.getWorld then
        name = tostring(world:getWorld() or "unknown")
    end
    if getCore then
        local core = getCore()
        if core and core.getGameMode then
            mode = tostring(core:getGameMode() or "unknown")
        end
    end
    return mode .. "/" .. name
end

local function writeFile(path, text)
    if not getFileWriter then return false end
    local ok = pcall(function()
        local writer = getFileWriter(path, true, false)
        if not writer then error("writer nil") end
        writer:write(text)
        writer:close()
    end)
    return ok == true
end

local function readFile(path)
    if not getFileReader then return nil end
    local ok, text = pcall(function()
        local reader = getFileReader(path, false)
        if not reader then return nil end
        local chunks = {}
        local line = reader:readLine()
        while line do
            chunks[#chunks + 1] = line
            line = reader:readLine()
        end
        reader:close()
        return table.concat(chunks, "")
    end)
    if not ok or type(text) ~= "string" or text == "" then return nil end
    return text
end

function ArayHuman.Persist.busy()
    return pending ~= nil
end

function ArayHuman.Persist.pendingOp()
    return pending and pending.op or nil
end

function ArayHuman.Persist.request(op, extra)
    if pending or type(op) ~= "string" or op == "" then return false end
    if not getFileWriter then return false end
    seq = seq + 1
    local id = tostring(nowMs()) .. "-persist-" .. tostring(seq)
    local payload = "{"
        .. "\"id\":\"" .. esc(id) .. "\","
        .. "\"kind\":\"persist\","
        .. "\"op\":\"" .. esc(op) .. "\","
        .. "\"world_id\":\"" .. esc(ArayHuman.Persist.worldId()) .. "\""
    if extra and extra.npcId then
        payload = payload .. ",\"npc_id\":\"" .. esc(extra.npcId) .. "\""
    end
    if extra and extra.state then
        local state = extra.state
        payload = payload .. ",\"state\":{"
            .. "\"position_x\":" .. tostring(state.x) .. ","
            .. "\"position_y\":" .. tostring(state.y) .. ","
            .. "\"position_z\":" .. tostring(state.z) .. ","
            .. "\"direction\":\"" .. esc(state.direction or "") .. "\","
            .. "\"state_version\":" .. tostring(state.revision)
            .. "}"
    end
    payload = payload .. "}"
    local tmp = ROOT .. "/to_py/" .. id .. ".json.tmp"
    local mark = ROOT .. "/to_py/" .. id .. ".ok"
    if not writeFile(tmp, payload) then return false end
    if not writeFile(mark, id) then return false end
    pending = { id = id, op = op, sent = nowMs(), revision = extra and extra.state and extra.state.revision or nil }
    print("[ARAY] persist pedido op=" .. op .. " id=" .. id)
    return true
end

local function parseJson(text)
    return ArayHuman.Json.decode(text)
end

function ArayHuman.Persist.poll(timeoutMs)
    if not pending then return nil end
    if handled[pending.id] then
        pending = nil
        return nil
    end
    local path = ROOT .. "/to_lua/" .. pending.id .. ".json"
    local json = readFile(path)
    if not json then
        if timeoutMs and nowMs() - pending.sent > timeoutMs then
            local expired = pending
            pending = nil
            return { ok = false, op = expired.op, error = "timeout", message = "timeout", id = expired.id }
        end
        return nil
    end
    local data = parseJson(json)
    if type(data) ~= "table" or data.id ~= pending.id then return nil end
    handled[pending.id] = true
    local current = pending
    pending = nil
    local payload = data.result
    local result = {
        id = data.id,
        op = data.op or current.op,
        ok = data.ok == true,
        error = data.error,
        message = data.message or data.error,
        world_id = data.world_id,
        payload = payload,
    }
    if type(payload) == "table" then
        result.npc_id = payload.npc_id
        result.alive = payload.alive
        result.position_x = payload.position_x
        result.position_y = payload.position_y
        result.position_z = payload.position_z
        result.direction = payload.direction
        result.state_version = payload.state_version
        result.last_saved_at = payload.last_saved_at
        result.name = payload.name
        result.surname = payload.surname
        result.sex = payload.sex
    end
    print("[ARAY] persist response id=" .. tostring(result.id) .. " success=" .. tostring(result.ok))
    if not result.ok then
        print("[ARAY] persist error code=" .. tostring(result.error) .. " message=" .. tostring(result.message))
    end
    return result
end

print("[ARAY] persistencia carregada")
