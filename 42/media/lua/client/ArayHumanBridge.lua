-- Ponte de arquivos Lua -> Python. Sem Ollama, sem ordem, sem autonomia.
ArayHuman = ArayHuman or {}
ArayHuman.Bridge = ArayHuman.Bridge or {}
require "ArayHumanJson"

local ROOT = "ArayHumanNPCTest"
local POLL_MS = 1000
local TIMEOUT_MS = 10000
local MAX_TRIES = 3

local seq = 0
local pending = nil
local tries = 0
local finished = false
local lastPoll = 0
local writeLimit = false
local readLimit = false

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

local function worldIdentity()
    local name = "unknown"
    local mode = "unknown"
    local world = getWorld()
    if world and world.getWorld then
        name = tostring(world:getWorld() or "unknown")
    end
    if getCore then
        local core = getCore()
        if core and core.getGameMode then
            mode = tostring(core:getGameMode() or "unknown")
        end
    end
    return mode .. "/" .. name, name, mode
end

local function writeFile(rel, text)
    if not getFileWriter then return false, "getFileWriter" end
    local writer, err = nil, nil
    local ok = pcall(function()
        writer = getFileWriter(rel, true, false)
        if not writer then
            err = "nil"
            return
        end
        writer:write(text)
        writer:close()
    end)
    if not ok then return false, "excecao" end
    if err then return false, err end
    return true
end

local function publishRequest(id, payload)
    local tmp = ROOT .. "/to_py/" .. id .. ".json.tmp"
    local okMark = ROOT .. "/to_py/" .. id .. ".ok"
    local ok, reason = writeFile(tmp, payload)
    if not ok then return false, reason end
    return writeFile(okMark, id)
end

local function readFile(rel)
    if not getFileReader then return nil, "no_reader" end
    local chunks, reader, reason = {}, nil, nil
    local ok = pcall(function()
        reader = getFileReader(rel, false)
        if not reader then reason="not_ready"; return end
        local bytes=0
        local line = reader:readLine()
        while line do
            if type(line)~="string" then reason="invalid_read"; return end
            bytes=bytes+#line
            if bytes>65536 then reason="read_budget"; return end
            chunks[#chunks + 1] = line
            line = reader:readLine()
        end
    end)
    if reader then pcall(function() reader:close() end) end
    if not ok then return nil,"temporarily_unavailable" end
    if reason then return nil,reason end
    if #chunks == 0 then return "" end
    return table.concat(chunks, "")
end

local function sendPing(extraFields)
    if finished or pending then return end
    if tries >= MAX_TRIES then
        finished = true
        print("[ARAY] ponte sem servico")
        return
    end
    seq = seq + 1
    local id = tostring(nowMs()) .. "-" .. tostring(seq)
    local worldId, worldName, gameMode = worldIdentity()
    local payload = "{"
        .. "\"id\":\"" .. esc(id) .. "\","
        .. "\"kind\":\"ping\","
        .. "\"world_id\":\"" .. esc(worldId) .. "\","
        .. "\"world_name\":\"" .. esc(worldName) .. "\","
        .. "\"game_mode\":\"" .. esc(gameMode) .. "\""
    
    if extraFields then
        payload = payload .. "," .. extraFields
    end
    
    payload = payload .. "}"
    
    local ok, reason = publishRequest(id, payload)
    if not ok then
        if not writeLimit then
            writeLimit = true
            print("[ARAY] ponte escrita falhou " .. tostring(reason))
        end
        return
    end
    tries = tries + 1
    pending = { id = id, sent = nowMs() }
    print("[ARAY] ponte ping id=" .. id .. " world_id=" .. worldId)
end

function ArayHuman.Bridge.sendModelSelection(modelName)
    if not modelName or modelName == "" then return end
    -- Reset pending to allow immediate send
    pending = nil
    finished = false
    tries = 0
    local extraFields = "\"set_model\":\"" .. esc(modelName) .. "\""
    sendPing(extraFields)
end

local function acceptPong(json)
    local data=ArayHuman.Json.decode(json)
    if type(data)~="table" or not pending or data.id~=pending.id or data.kind~="pong" or data.ok~=true or data.action~=nil then
        return -- Partial/invalid/unrelated files never consume the pending request.
    end
    print("[ARAY] ponte pong recebido id=" .. data.id)
    pending = nil
    finished = true
    
    -- Update Ollama state if available
    if ArayHuman.Ollama and ArayHuman.Ollama.update then
        ArayHuman.Ollama.update(json)
    end
end

local function pollPong()
    if not pending then return end
    local rel = ROOT .. "/to_lua/" .. pending.id .. ".json"
    local json, err = readFile(rel)
    if json == nil then
        -- Arquivo pode não existir ainda, normal durante polling
        return
    end
    if json == "" then
        return
    end
    acceptPong(json)
end

local function onTick()
    if finished then return end
    if not getSpecificPlayer(0) or not getWorld then return end
    if not getWorld() then return end
    local t = nowMs()
    if not pending then
        sendPing()
        lastPoll = t
        return
    end
    if t - lastPoll < POLL_MS then return end
    lastPoll = t
    pollPong()
    if pending and t - pending.sent >= TIMEOUT_MS then
        print("[ARAY] ponte timeout id=" .. pending.id)
        pending = nil
    end
end

Events.OnTick.Add(onTick)
print("[ARAY] ponte carregada")
