-- Barra de conversa presencial (input discreto)
require "ISUI/ISPanel"
require "ISUI/ISTextEntryBox"
require "ISUI/ISButton"

ArayHuman = ArayHuman or {}
ArayHuman.TalkBar = ArayHuman.TalkBar or {}

local talkBar = nil

ArayTalkBar = ISPanel:derive("ArayTalkBar")

function ArayTalkBar:new(x, y, width, height)
    local o = ISPanel:new(x, y, width, height)
    setmetatable(o, self)
    self.__index = self
    o.backgroundColor = {r=0.1, g=0.1, b=0.1, a=0.8}
    o.borderColor = {r=0.4, g=0.4, b=0.4, a=1.0}
    o.npc = nil
    return o
end

function ArayTalkBar:createChildren()
    ISPanel.createChildren(self)
    
    local padding = 8
    local buttonWidth = 80
    
    -- Campo de texto
    self.inputBox = ISTextEntryBox:new("", padding, padding, self.width - buttonWidth - padding * 3, self.height - padding * 2)
    self.inputBox:initialise()
    self.inputBox:instantiate()
    self.inputBox:setMaxTextLength(500)
    self.inputBox.font = UIFont.Small
    self:addChild(self.inputBox)
    
    -- Botão enviar
    self.sendButton = ISButton:new(self.width - buttonWidth - padding, padding, buttonWidth, self.height - padding * 2, "Enviar", self, ArayTalkBar.onSend)
    self.sendButton:initialise()
    self.sendButton:instantiate()
    self.sendButton.borderColor = {r=0.4, g=0.6, b=0.4, a=1.0}
    self:addChild(self.sendButton)
    
    -- Auto-focus no input
    self.inputBox:focus()
end

function ArayTalkBar:prerender()
    ISPanel.prerender(self)
    
    local player=getSpecificPlayer(0)
    if not player or player:isDead() or self.world_id~=ArayHuman.Capabilities.world() then self:close() end

end

function ArayTalkBar:onSend()
    if self.world_id and (self.world_id~=ArayHuman.Capabilities.world()) then self:close(); return end
    if not self.inputBox then return end
    
    local message = self.inputBox:getInternalText()
    if not message or message == "" then
        return
    end
    
    -- Limpa campo
    self.inputBox:setText("")
    
    -- Verifica distância novamente
    local player = getSpecificPlayer(0)
    if not player then return end
    
    -- Mostra fala do jogador usando Say nativo (funciona corretamente para jogador)
    player:Say(message)
    
    -- Envia para o Ollama
    if ArayHuman.Chat and ArayHuman.Chat.sendMessage then
        local success, errorOrId = ArayHuman.Chat.sendMessage(message,nil,nil,self.world_id)
        if not success then
            print("[ARAY] talkbar erro: " .. tostring(errorOrId))
            player:Say("Não foi possível: "..tostring(errorOrId))
        end
    end
    
    -- Fecha a barra após enviar
    self:close()
end

function ArayTalkBar:onKeyPress(key)
    if key == Keyboard.KEY_RETURN or key == Keyboard.KEY_NUMPADENTER then
        self:onSend()
        return true
    elseif key == Keyboard.KEY_ESCAPE then
        self:close()
        return true
    end
    return false
end

function ArayTalkBar:close()
    self:setVisible(false)
    self:removeFromUIManager()
    talkBar = nil
end

-- API pública

function ArayHuman.TalkBar.open(uuid)
    local player = getSpecificPlayer(0)
    if not player or player:isDead() then return end
    
    local npc
    if uuid then npc=ArayHuman.getNpcByUuid and ArayHuman.getNpcByUuid(uuid)
    else npc=ArayHuman.getNpc and ArayHuman.getNpc() end
    -- Fecha existente se aberto
    if talkBar then
        talkBar:close()
    end
    
    -- Cria nova barra
    local screenWidth = getPlayerScreenWidth(0)
    local screenHeight = getPlayerScreenHeight(0)
    local width = 500
    local height = 40
    local x = (screenWidth - width) / 2
    local y = screenHeight - height - 100
    
    talkBar = ArayTalkBar:new(x, y, width, height)
    talkBar.npc = npc
    talkBar.world_id=ArayHuman.Capabilities.world()
    talkBar:initialise()
    talkBar:instantiate()
    talkBar:addToUIManager()
    talkBar:setVisible(true)
end

function ArayHuman.TalkBar.close()
    if talkBar then
        talkBar:close()
    end
end

function ArayHuman.TalkBar.isOpen()
    return talkBar and talkBar:getIsVisible()
end

print("[ARAY] talk bar carregado")
