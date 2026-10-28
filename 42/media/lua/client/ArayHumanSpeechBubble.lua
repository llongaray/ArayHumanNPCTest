-- Baloes de fala ancorados no personagem, desenhados na camada de UI.
ArayHuman = ArayHuman or {}
ArayHuman.SpeechBubble = ArayHuman.SpeechBubble or {}

local activeBubbles = {}
local MAX_BUBBLE_WIDTH = 280
local CHAR_PER_SECOND = 15
local MIN_DURATION = 3000
local MAX_DURATION = 12000
local HEAD_Z = 0.85
local drawErrorLogged = false
local probed = false

local function nowMs()
    if getTimestampMs then return getTimestampMs() end
    return 0
end

local function speakerName(isPlayer)
    if isPlayer then return "PLAYER" end
    return "NPC"
end

local function speakerId(character)
    if not character then return "?" end
    if character.getOnlineID then
        local ok, id = pcall(function() return character:getOnlineID() end)
        if ok and id ~= nil then return tostring(id) end
    end
    return "?"
end

local function calculateDuration(text)
    local chars = #tostring(text or "")
    local duration = math.max(MIN_DURATION, chars / CHAR_PER_SECOND * 1000)
    return math.min(duration, MAX_DURATION)
end

local function wrapText(text, maxWidth)
    local font = UIFont.Small
    local manager = getTextManager and getTextManager() or nil
    local words = {}
    for word in tostring(text):gmatch("%S+") do
        table.insert(words, word)
    end
    if #words == 0 then
        return { tostring(text) }
    end
    if not manager or not manager.MeasureStringX then
        return { tostring(text) }
    end

    local lines = {}
    local currentLine = ""
    for _, word in ipairs(words) do
        local testLine = currentLine == "" and word or (currentLine .. " " .. word)
        local width = manager:MeasureStringX(font, testLine)
        if width <= maxWidth then
            currentLine = testLine
        else
            if currentLine ~= "" then
                table.insert(lines, currentLine)
            end
            currentLine = word
        end
    end
    if currentLine ~= "" then
        table.insert(lines, currentLine)
    end
    if #lines == 0 then
        return { tostring(text) }
    end
    return lines
end

local function activate(character, text, isPlayer, queue, durationOverride)
    local duration = durationOverride or calculateDuration(text)
    local bubble = {
        character = character,
        text = text,
        lines = wrapText(text, MAX_BUBBLE_WIDTH),
        isPlayer = isPlayer or false,
        createdAt = nowMs(),
        expiresAt = nowMs() + duration,
        queue = queue or {},
        loggedRender = false,
    }
    table.insert(activeBubbles, bubble)
    print("[ARAY] bubble create speaker=" .. speakerName(bubble.isPlayer)
        .. " id=" .. speakerId(character)
        .. " chars=" .. #tostring(text)
        .. " lines=" .. #bubble.lines
        .. " duration=" .. duration
        .. " queued=" .. #bubble.queue)
    return bubble
end

function ArayHuman.SpeechBubble.show(character, text, isPlayer, durationOverride)
    if not character or not text or text == "" then return end
    if character.isDead and character:isDead() then return end

    for _, bubble in ipairs(activeBubbles) do
        if bubble.character == character then
            table.insert(bubble.queue, { text = text, isPlayer = isPlayer or false, duration = durationOverride })
            print("[ARAY] bubble queue speaker=" .. speakerName(isPlayer)
                .. " id=" .. speakerId(character)
                .. " pending=" .. #bubble.queue)
            return
        end
    end
    activate(character, text, isPlayer, {}, durationOverride)
end

function ArayHuman.SpeechBubble.remove(character)
    if not character then return end
    for i = #activeBubbles, 1, -1 do
        if activeBubbles[i].character == character then
            table.remove(activeBubbles, i)
        end
    end
end

function ArayHuman.SpeechBubble.probe(character)
    if probed or not character then return end
    probed = true
    local sample = string.char(111, 108, 225)
    local bytes = {}
    for i = 1, #sample do
        bytes[#bytes + 1] = string.format("%02X", sample:byte(i))
    end
    print("[ARAY] utf8 probe visual speaker=NPC bytes=" .. table.concat(bytes, " ") .. " esperado=6F 6C E1")
    ArayHuman.SpeechBubble.show(character, sample, false, 1800)
end

local function screenPoint(character)
    local x = character:getX()
    local y = character:getY()
    local z = character:getZ()
    if isoToScreenX and isoToScreenY then
        local sx = isoToScreenX(0, x, y, z + HEAD_Z)
        local sy = isoToScreenY(0, x, y, z + HEAD_Z)
        if sx and sy then return sx, sy, "iso" end
    end
    if character.getScreenX and character.getScreenY then
        local sx = character:getScreenX()
        local sy = character:getScreenY()
        if sx and sy then return sx, sy - 80, "screen" end
    end
    return nil, nil, "none"
end

local function drawBubble(bubble)
    local character = bubble.character
    if not character or (character.isDead and character:isDead()) then
        return false
    end
    local sx, sy, mode = screenPoint(character)
    if not sx or not sy then
        return true
    end
    local screenW = getCore and getCore():getScreenWidth() or 1920
    local screenH = getCore and getCore():getScreenHeight() or 1080
    if sx < -40 or sy < -40 or sx > screenW + 40 or sy > screenH + 40 then
        return true
    end

    local manager = getTextManager and getTextManager() or nil
    if not manager or not manager.DrawString then
        return true
    end

    local font = UIFont.Small
    local lineH = 16
    if manager.MeasureStringY then
        lineH = manager:MeasureStringY(font, "Ag")
    end
    local totalH = #bubble.lines * lineH
    local top = sy - totalH

    if not bubble.loggedRender then
        bubble.loggedRender = true
        print(string.format(
            "[ARAY] bubble render speaker=%s id=%s mode=%s screenX=%.0f screenY=%.0f lines=%d",
            speakerName(bubble.isPlayer), speakerId(character), mode, sx, top, #bubble.lines))
    end

    local r, g, b = 1, 1, 1
    if not bubble.isPlayer then
        r, g, b = 0.85, 1, 0.75
    end

    for index, line in ipairs(bubble.lines) do
        local width = 0
        if manager.MeasureStringX then
            width = manager:MeasureStringX(font, line)
        end
        local x = sx - width / 2
        local y = top + (index - 1) * lineH
        manager:DrawString(font, x + 1, y + 1, line, 0, 0, 0, 0.9)
        manager:DrawString(font, x, y, line, r, g, b, 1)
    end
    return true
end

local function promote(bubble)
    local nextItem = table.remove(bubble.queue, 1)
    if not nextItem then return end
    activate(bubble.character, nextItem.text, nextItem.isPlayer, bubble.queue, nextItem.duration)
end

local function onUiDraw()
    if #activeBubbles == 0 then return end
    local now = nowMs()
    for i = #activeBubbles, 1, -1 do
        local bubble = activeBubbles[i]
        if now >= bubble.expiresAt then
            local elapsed = now - bubble.createdAt
            print("[ARAY] bubble expired speaker=" .. speakerName(bubble.isPlayer)
                .. " id=" .. speakerId(bubble.character)
                .. " elapsed=" .. tostring(elapsed))
            table.remove(activeBubbles, i)
            promote(bubble)
        else
            local ok, alive = pcall(drawBubble, bubble)
            if not ok then
                if not drawErrorLogged then
                    drawErrorLogged = true
                    print("[ARAY] bubble draw erro " .. tostring(alive))
                end
            elseif not alive then
                table.remove(activeBubbles, i)
            end
        end
    end
end

if Events and Events.OnPostUIDraw then
    Events.OnPostUIDraw.Add(onUiDraw)
else
    Events.OnPostRender.Add(onUiDraw)
    print("[ARAY] bubble aviso: OnPostUIDraw ausente, usando OnPostRender")
end

print("[ARAY] speech bubble carregado")
