-- Seta só quando a projeção do NPC cai fora da tela do jogador.
require "ISUI/ISPanel"

ArayHuman = ArayHuman or {}

local panel = nil
local warned = false

local function screenOf(playerNum, character)
    return isoToScreenX(playerNum, character:getX(), character:getY(), character:getZ()),
        isoToScreenY(playerNum, character:getX(), character:getY(), character:getZ())
end

local function ensurePanel()
    if panel then return panel end
    panel = ISPanel:new(0, 0, 72, 44)
    panel.background = false
    panel.backgroundColor = {r = 0, g = 0, b = 0, a = 0}
    panel.borderColor = {r = 0, g = 0, b = 0, a = 0}
    panel:initialise()
    panel:instantiate()
    panel:setCapture(false)
    panel:setAlwaysOnTop(true)
    panel:addToUIManager()
    panel:setVisible(false)
    panel.arrowTex = getTexture("media/ui/LootableMaps/map_arrownorth.png")
    panel.arrowAngle = 0
    panel.arrowText = ""
    panel.render = function(self)
        if not self.arrowTex then return end
        self:DrawTextureAngle(self.arrowTex, 36, 14, self.arrowAngle or 0)
        self:drawTextCentre(self.arrowText or "", 36, 26, 1, 1, 1, 0.9, UIFont.Small)
    end
    return panel
end

local function hideArrow()
    if panel then panel:setVisible(false) end
end

local function updateArrow()
    if not isoToScreenX or not isoToScreenY or not getPlayerScreenWidth then
        if not warned then
            warned = true
            print("[ARAY] limite: conversao mundo-tela indisponivel")
        end
        hideArrow()
        return
    end

    local player = getSpecificPlayer(0)
    local npc = ArayHuman.getNpc and ArayHuman.getNpc() or nil
    if not player or player:isDead() or not npc or npc:isDead() then
        hideArrow()
        return
    end
    if math.floor(player:getZ()) ~= math.floor(npc:getZ()) then
        hideArrow()
        return
    end

    local playerNum = player:getPlayerNum()
    local sx, sy = screenOf(playerNum, npc)
    local left = getPlayerScreenLeft(playerNum)
    local top = getPlayerScreenTop(playerNum)
    local right = left + getPlayerScreenWidth(playerNum)
    local bottom = top + getPlayerScreenHeight(playerNum)
    local margin = 28
    if sx >= left + margin and sx <= right - margin and sy >= top + margin and sy <= bottom - margin then
        hideArrow()
        return
    end

    local cx = (left + right) / 2
    local cy = (top + bottom) / 2
    local vx = sx - cx
    local vy = sy - cy
    if vx == 0 and vy == 0 then
        hideArrow()
        return
    end
    local halfW = (right - left) / 2 - 48
    local halfH = (bottom - top) / 2 - 48
    local scaleX = math.abs(vx) > 0.001 and (halfW / math.abs(vx)) or 1000
    local scaleY = math.abs(vy) > 0.001 and (halfH / math.abs(vy)) or 1000
    local scale = math.min(scaleX, scaleY)
    local ax = cx + vx * scale
    local ay = cy + vy * scale

    local dx = npc:getX() - player:getX()
    local dy = npc:getY() - player:getY()
    local tiles = math.floor(math.sqrt(dx * dx + dy * dy) + 0.5)
    local ui = ensurePanel()
    if not ui.arrowTex then
        hideArrow()
        return
    end
    ui.arrowAngle = math.deg(math.atan2(vx, -vy))
    ui.arrowText = tostring(tiles) .. " tiles"
    ui:setX(ax - 36)
    ui:setY(ay - 14)
    ui:setVisible(true)
end

Events.OnTick.Add(updateArrow)
