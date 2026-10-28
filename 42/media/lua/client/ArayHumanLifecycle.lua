-- Fase 3B.2: restaura ajudantes existentes e cria outro so quando o jogador pede.
ArayHuman = ArayHuman or {}
ArayHuman.Lifecycle = ArayHuman.Lifecycle or {}

local START_DELAY_MS = 5000
local STEP_MS = 500
local SAVE_MS = 20000
local REQUEST_TIMEOUT_MS = 8000
local CREATE_TIMEOUT_MS = 90000
local SQUARE_WAIT_MS = 30000
local RETRY_MS = 3000
local MAX_TRIES = 3

local phase = "WAITING_WORLD"
local readyAt = 0
local tries = 0
local lastStep = 0
local lastPoll = 0
local lastSave = 0
local worldSeen = nil
local focusedId = nil
local records = {}
local queue = {}
local markedDead = {}
local lastConfirmedAt = nil
local creating = false

local function nowMs()
    if getTimestampMs then return getTimestampMs() end
    return 0
end

local function setPhase(nextPhase)
    if phase == nextPhase then return end
    phase = nextPhase
    print("[ARAY] persist lifecycle=" .. phase)
end

local DIRECTIONS = { "N", "NE", "E", "SE", "S", "SW", "W", "NW" }

local function directionOf(character)
    if not character or not character.getDir then return "S" end
    local ok, value = pcall(function() return character:getDir() end)
    if not ok or value == nil then return "S" end
    if IsoDirections then
        for i = 1, #DIRECTIONS do
            if value == IsoDirections[DIRECTIONS[i]] then return DIRECTIONS[i] end
        end
    end
    return tostring(value):match("([NSEW]+)$") or "S"
end

local function capture(character)
    return {
        x = character:getX(),
        y = character:getY(),
        z = character:getZ(),
        direction = directionOf(character),
    }
end

local function samePlace(a, b)
    if not a or not b then return false end
    return math.abs(a.x - b.x) < 0.05 and math.abs(a.y - b.y) < 0.05
        and math.abs(a.z - b.z) < 0.01 and a.direction == b.direction
end

local function send(op, extra)
    if not ArayHuman.Persist or not ArayHuman.Persist.request then return false end
    if ArayHuman.Persist.busy and ArayHuman.Persist.busy() then return false end
    return ArayHuman.Persist.request(op, extra)
end

local function rememberRecord(item)
    if type(item) ~= "table" or not item.npc_id then return end
    local current = records[item.npc_id] or {}
    current.uuid = item.npc_id
    current.name = item.name or current.name
    current.surname = item.surname or current.surname
    current.sex = item.sex or current.sex
    current.alive = item.alive
    if item.position_x then
        current.saved = {
            x = item.position_x,
            y = item.position_y,
            z = item.position_z or 0,
            direction = item.direction,
        }
        current.revision = item.state_version or current.revision or 0
    end
    if item.state_version then current.revision = item.state_version end
    records[item.npc_id] = current
    if not focusedId then focusedId = item.npc_id end
end

local function spawnRecord(record, square, reason)
    if not ArayHuman.spawnCarlos then return false end
    local visual
    if ArayHuman.Appearance then
        local why
        visual,why=ArayHuman.Appearance.get(record.uuid)
        if why=="appearance_pending" then return false,"appearance_pending" end
        if why~="found" and why~="missing" then
            if ArayHuman.setStatus then ArayHuman.setStatus("Aparência: "..tostring(why)) end
            return false
        end
        if why=="missing" and record.saved then
            local existing=ArayHuman.getNpcByUuid and ArayHuman.getNpcByUuid(record.uuid)
            if existing then ArayHuman.Appearance.saveInitial(existing,record.uuid)
            elseif ArayHuman.setStatus then ArayHuman.setStatus("Aparência legada ausente: migração necessária.") end
            if existing then return false,"appearance_pending" end
            return false,"appearance_migration_required"
        end
    end
    local config = {
        uuid = record.uuid,
        firstName = record.name,
        lastName = record.surname,
        sex = record.sex,
        square = square,
        direction = record.saved and record.saved.direction or nil,
        restoring = record.saved ~= nil,
        appearance = visual,
    }
    if reason == "pronto" and record.saved then
        config.exact = true
        config.x = record.saved.x
        config.y = record.saved.y
        config.z = record.saved.z
    end
    return ArayHuman.spawnCarlos(config) == true
end

local function restoreNext()
    if phase ~= "ACTIVE" and phase ~= "WAITING_SQUARE" and phase ~= "RESTORE_FAILED" and phase ~= "RESTORING_NPC" then
        return
    end
    local pendingSquare = false
    local failed = false
    for i = 1, #queue do
        local job = queue[i]
        if not job.done then
            local record = records[job.uuid]
            if not record or record.alive == false or markedDead[job.uuid] then
                job.done = true
            elseif not record.saved then
                local spawned,why = spawnRecord(record, nil, "criar")
                if spawned then
                    record.dirty = true
                    job.done = true
                elseif why == "appearance_pending" then
                    pendingSquare = true
                else
                    failed = true
                end
            elseif not ArayHuman.findRestoreSquare then
                failed = true
            else
                local square, reason = ArayHuman.findRestoreSquare(record.saved.x, record.saved.y, record.saved.z)
                if reason == "nao carregado" or reason == "sem cell" then
                    if not job.since then job.since = nowMs() end
                    if nowMs() - job.since > SQUARE_WAIT_MS then
                        if not job.logged then
                            print("[ARAY] persist quadrado indisponivel, posicao mantida")
                            job.logged = true
                        end
                        failed = true
                    else
                        pendingSquare = true
                    end
                elseif not square then
                    failed = true
                else
                    if not job.logged then
                        print("[ARAY] persist restore pos=" .. tostring(record.saved.x) .. "," .. tostring(record.saved.y)
                            .. " revision=" .. tostring(record.revision))
                        job.logged = true
                    end
                    setPhase("RESTORING_NPC")
                    local spawned,why = spawnRecord(record, square, reason)
                    if spawned then
                        if reason == "adjacente" then record.dirty = true end
                        job.done = true
                    elseif why == "appearance_pending" then
                        pendingSquare = true
                    elseif why == "appearance_migration_required" then
                        record.visualMigrationRequired = true
                        job.done = true
                    else
                        failed = true
                    end
                end
            end
        end
    end
    if pendingSquare then
        setPhase("WAITING_SQUARE")
    elseif failed then
        setPhase("RESTORE_FAILED")
    else
        setPhase("ACTIVE")
    end
end

local function onResult(result)
    if not result then return end
    if result.op == "create_npc" then
        creating = false
        if result.error == "timeout" or not result.ok then
            if ArayHuman.setStatus then
                ArayHuman.setStatus("Não foi possível criar o ajudante: " .. tostring(result.message or result.error))
            end
            setPhase("ACTIVE")
            return
        end
        local payload = result.payload or result
        rememberRecord(payload)
        local record = records[payload.npc_id]
        if record then
            focusedId = record.uuid
            queue[#queue + 1] = { uuid = record.uuid }
            print("[ARAY] persist npc encontrado uuid=" .. tostring(record.uuid))
        end
        setPhase("ACTIVE")
        return
    end
    if result.error == "timeout" then
        tries = tries + 1
        readyAt = nowMs()
        if tries >= MAX_TRIES then setPhase("PERSISTENCE_UNAVAILABLE") else setPhase("RETRY_WAIT") end
        return
    end
    if not result.ok then
        readyAt = nowMs()
        setPhase("RETRY_WAIT")
        return
    end
    tries = 0
    if result.op == "list_npcs" then
        local payload = result.payload or {}
        local npcs = payload.npcs or {}
        queue = {}
        local found = false
        for i = 1, #npcs do
            local item = npcs[i]
            rememberRecord(item)
            if item.alive == false then
                print("[ARAY] persist npc morto uuid=" .. tostring(item.npc_id))
            else
                found = true
                queue[#queue + 1] = { uuid = item.npc_id }
                print("[ARAY] persist npc encontrado uuid=" .. tostring(item.npc_id))
            end
        end
        if not found then
            setPhase("ACTIVE")
            return
        end
        setPhase("WAITING_SQUARE")
        return
    end
    if result.op == "save_state" or result.op == "save_npc_state" then
        local record = records[result.npc_id]
        if record then
            record.revision = result.state_version or record.revision
            record.dirty = false
            local snapshot = ArayHuman.rosterSnapshot and ArayHuman.rosterSnapshot() or {}
            for i = 1, #snapshot do
                if snapshot[i].uuid == record.uuid and not snapshot[i].dead then
                    record.saved = capture(snapshot[i].character)
                end
            end
        end
        lastConfirmedAt = result.last_saved_at or tostring(nowMs())
        print("[ARAY] persist save confirmed revision=" .. tostring(result.state_version))
        if ArayHuman.setStatus then
            ArayHuman.setStatus("Ajudante salvo, revisão " .. tostring(result.state_version))
        end
        setPhase("ACTIVE")
    end
end

local function saveOne(force)
    if ArayHuman.Persist.busy and ArayHuman.Persist.busy() then return end
    local snapshot = ArayHuman.rosterSnapshot and ArayHuman.rosterSnapshot() or {}
    for i = 1, #snapshot do
        local entry = snapshot[i]
        local record = records[entry.uuid]
        if entry.dead and record and not markedDead[entry.uuid] then
            if send("mark_npc_dead", { npcId = entry.uuid }) then
                markedDead[entry.uuid] = true
                record.alive = false
            end
            return
        end
        if record and not entry.dead then
            local place = capture(entry.character)
            local changed = record.dirty or not samePlace(place, record.saved)
            local due = force or (nowMs() - lastSave >= SAVE_MS and changed)
            if due and changed then
                local revision = (record.revision or 0) + 1
                print("[ARAY] persist save requested revision=" .. tostring(revision))
                if send("save_npc_state", { npcId = entry.uuid, state = {
                    x = place.x, y = place.y, z = place.z, direction = place.direction, revision = revision,
                } }) then
                    lastSave = nowMs()
                end
                return
            end
        end
    end
end

local function tick()
    local now = nowMs()
    local currentWorld = ArayHuman.Persist.worldId and ArayHuman.Persist.worldId() or nil
    if worldSeen and currentWorld and currentWorld ~= worldSeen and phase ~= "WAITING_WORLD" then
        records = {}
        queue = {}
        focusedId = nil
        markedDead = {}
        tries = 0
        creating = false
        setPhase("WAITING_WORLD")
    end
    if currentWorld then worldSeen = currentWorld end
    if now - lastPoll >= 75 then
        lastPoll = now
        local timeout = REQUEST_TIMEOUT_MS
        if ArayHuman.Persist.pendingOp and ArayHuman.Persist.pendingOp() == "create_npc" then
            timeout = CREATE_TIMEOUT_MS
        end
        local result = ArayHuman.Persist.poll and ArayHuman.Persist.poll(timeout) or nil
        if result and result.world_id and currentWorld and result.world_id ~= currentWorld then
            result = nil
        end
        if result then onResult(result) end
    end
    if now - lastStep < STEP_MS then return end
    lastStep = now
    if phase == "WAITING_WORLD" then
        if getWorld and getWorld() then setPhase("WAITING_PLAYER") end
        return
    end
    if phase == "WAITING_PLAYER" then
        if ArayHuman.getLocalPlayer and ArayHuman.getLocalPlayer() then
            readyAt = now
            setPhase("WAITING_BRIDGE")
        end
        return
    end
    if phase == "WAITING_BRIDGE" then
        if now - readyAt < START_DELAY_MS then return end
        if not getFileWriter then return end
        if tries >= MAX_TRIES then
            setPhase("PERSISTENCE_UNAVAILABLE")
            return
        end
        if send("list_npcs") then setPhase("LOADING_PERSISTENCE") end
        return
    end
    if phase == "RETRY_WAIT" then
        if now - readyAt > RETRY_MS then
            readyAt = now - START_DELAY_MS
            setPhase("WAITING_BRIDGE")
        end
        return
    end
    if phase == "CREATING" then return end
    restoreNext()
    if phase == "ACTIVE" then saveOne(false) end
end

function ArayHuman.Lifecycle.createNpc()
    if creating or (ArayHuman.Persist.busy and ArayHuman.Persist.busy()) then
        if ArayHuman.setStatus then ArayHuman.setStatus("Criação de ajudante já está em andamento.") end
        return
    end
    if phase ~= "ACTIVE" and phase ~= "RESTORE_FAILED" and phase ~= "PERSISTENCE_UNAVAILABLE" then
        if ArayHuman.setStatus then ArayHuman.setStatus("Aguarde a restauração dos ajudantes.") end
        return
    end
    creating = true
    setPhase("CREATING")
    if ArayHuman.setStatus then ArayHuman.setStatus("Gerando um novo ajudante...") end
    if not send("create_npc") then
        creating = false
        setPhase("ACTIVE")
        if ArayHuman.setStatus then ArayHuman.setStatus("Não foi possível pedir a criação.") end
    end
end

function ArayHuman.Lifecycle.manualSpawn()
    ArayHuman.Lifecycle.createNpc()
end

function ArayHuman.Lifecycle.markDirty()
    if focusedId and records[focusedId] then records[focusedId].dirty = true end
    saveOne(true)
end

function ArayHuman.Lifecycle.saveNow()
    if phase ~= "ACTIVE" then
        if ArayHuman.setStatus then ArayHuman.setStatus("Ainda não é possível salvar.") end
        return false
    end
    if ArayHuman.Persist.busy and ArayHuman.Persist.busy() then
        if ArayHuman.setStatus then ArayHuman.setStatus("Salvamento pendente.") end
        return false
    end
    if focusedId and records[focusedId] then records[focusedId].dirty = true end
    if ArayHuman.setStatus then ArayHuman.setStatus("Salvando ajudante...") end
    saveOne(true)
    return true
end

function ArayHuman.Lifecycle.statusLine()
    local shortId = focusedId and focusedId:sub(1, 8) or "-"
    local count, migrations = 0, 0
    for _,record in pairs(records) do
        count = count + 1
        if record.visualMigrationRequired then migrations = migrations + 1 end
    end
    return "Persistência " .. phase .. " npcs=" .. tostring(count) .. " uuid=" .. shortId .. " salvo=" .. tostring(lastConfirmedAt or "-") .. " visual_migration=" .. tostring(migrations)
end

local function onExitSave()
    if phase == "ACTIVE" then saveOne(true) end
end

Events.OnTick.Add(tick)
if Events.OnPostSave then Events.OnPostSave.Add(onExitSave) end
if Events.OnSave then Events.OnSave.Add(onExitSave) end
print("[ARAY] ciclo de vida carregado")
