-- Janela de conversa com o ajudante
require "ISUI/ISCollapsableWindow"
require "ISUI/ISButton"
require "ISUI/ISTextEntryBox"
require "ISUI/ISRichTextPanel"

ArayHuman = ArayHuman or {}
ArayHuman.ChatWindow = ArayHuman.ChatWindow or {}

local chatWindow = nil

ArayChatWindow = ISCollapsableWindow:derive("ArayChatWindow")

function ArayChatWindow:new(x, y, width, height)
    local o = ISCollapsableWindow:new(x, y, width, height)
    setmetatable(o, self)
    self.__index = self
    o.title = "Conversa com " .. (ArayHuman.getNpcName and ArayHuman.getNpcName() or "Ajudante")
    o.resizable = false
    o.chatUpdateTick = 0
    return o
end

function ArayChatWindow:createChildren()
    ISCollapsableWindow.createChildren(self)
    
    local y = self:titleBarHeight() + 8
    local contentWidth = self.width - 24
    
    -- Área de histórico (rich text)
    local historyHeight = 300
    self.historyPanel = ISRichTextPanel:new(12, y, contentWidth, historyHeight)
    self.historyPanel:initialise()
    self.historyPanel:instantiate()
    self.historyPanel.autosetheight = false
    self.historyPanel.clip = true
    self.historyPanel:addScrollBars()
    self.historyPanel:setAnchorRight(true)
    self.historyPanel:setAnchorBottom(true)
    self:addChild(self.historyPanel)
    
    y = y + historyHeight + 8
    
    -- Campo de entrada
    self.inputBox = ISTextEntryBox:new("", 12, y, contentWidth, 25)
    self.inputBox:initialise()
    self.inputBox:instantiate()
    self.inputBox:setMaxTextLength(2000)
    self:addChild(self.inputBox)
    
    y = y + 30
    
    -- Botões
    local buttonWidth = (contentWidth - 8) / 2
    
    self.sendButton = ISButton:new(12, y, buttonWidth, 25, "Enviar", self, ArayChatWindow.onSend)
    self.sendButton:initialise()
    self.sendButton:instantiate()
    self:addChild(self.sendButton)
    
    self.clearButton = ISButton:new(12 + buttonWidth + 8, y, buttonWidth, 25, "Limpar", self, ArayChatWindow.onClear)
    self.clearButton:initialise()
    self.clearButton:instantiate()
    self:addChild(self.clearButton)
    
    y = y + 30
    
    -- Status
    self.statusText = ""
    
    self:setHeight(y + 8)
    
    -- Carrega histórico existente
    self:refreshHistory()
end

function ArayChatWindow:refreshHistory()
    if not self.historyPanel then return end
    
    self.historyPanel:clear()
    
    local history = ArayHuman.Chat and ArayHuman.Chat.getHistory(self.npcUuid) or {}
    
    if #history == 0 then
        self.historyPanel:setText("<RGB:0.7,0.7,0.7> (Nenhuma conversa ainda. Digite uma mensagem e clique Enviar.)")
    else
        local lines = {}
        for _, entry in ipairs(history) do
            if entry.role == "user" then
                table.insert(lines, "<RGB:0.5,0.8,1.0> Você: <LINE> <RGB:1,1,1> " .. entry.text)
            elseif entry.role == "assistant" then
                local actor=self.npcUuid and ArayHuman.getNpcByUuid(self.npcUuid)
                local npcName=actor and actor:getModData().ARAY_Name or "Ajudante"
                table.insert(lines, "<RGB:0.5,1.0,0.5> " .. npcName .. ": <LINE> <RGB:1,1,1> " .. entry.text)
            end
        end
        self.historyPanel:setText(table.concat(lines, " <LINE> <LINE> "))
    end
    
    -- Scroll para o final
    self.historyPanel:setYScroll(-999999)
end

function ArayChatWindow:onSend()
    if not self.inputBox then return end
    
    local message = self.inputBox:getInternalText()
    if not message or message == "" then
        return
    end
    
    -- Envia mensagem
    local success, errorOrId = ArayHuman.Chat.sendMessage(message,nil,nil,self.world_id)
    
    if success then
        self.inputBox:setText("")
        self.statusText = ArayHuman.Chat.isPending(self.npcUuid) and "Aguardando resposta verbal..." or "Mensagem roteada aos destinatários explícitos."
        self:refreshHistory()
    else
        self.statusText = "Erro: " .. tostring(errorOrId)
    end
end

function ArayChatWindow:onClear()
    if ArayHuman.Chat and ArayHuman.Chat.clearHistory then
        ArayHuman.Chat.clearHistory(self.npcUuid)
        self:refreshHistory()
        self.statusText = "Histórico limpo"
    end
end

function ArayChatWindow:prerender()
    ISCollapsableWindow.prerender(self)
    
    -- Polling movido para Events.OnTick em ArayHumanChat.lua
    
    -- Desenha status
    if self.statusText and self.statusText ~= "" then
        self:drawText(self.statusText, 12, self.height - 25, 0.7, 0.7, 0.7, 1, UIFont.Small)
    end
end

function ArayChatWindow:onKeyPress(key)
    if key == Keyboard.KEY_RETURN or key == Keyboard.KEY_NUMPADENTER then
        if self.inputBox and self.inputBox:isFocused() then
            self:onSend()
            return true
        end
    end
    return false
end

function ArayChatWindow:close()
    self:setVisible(false)
end

-- Callback chamado quando resposta chega
function ArayHuman.ChatWindow.onChatResponse(success, reply, error,uuid)
    if uuid and chatWindow and chatWindow.npcUuid~=uuid then return end
    if not chatWindow or not chatWindow:getIsVisible() then return end
    
    if success then
        chatWindow.statusText = ""
        chatWindow:refreshHistory()
    else
        chatWindow.statusText = "Erro: " .. tostring(error)
    end
end

-- API pública

function ArayHuman.ChatWindow.open(uuid)
    local player = getSpecificPlayer(0)
    if not player or player:isDead() then return end
    
    -- Verifica se NPC existe
    local npc
    if uuid then npc=ArayHuman.getNpcByUuid(uuid) else npc=ArayHuman.getNpc and ArayHuman.getNpc() end
    if not npc or npc:isDead() then
        print("[ARAY] chat window: nenhum ajudante disponivel")
        return
    end
    
    if chatWindow and chatWindow:getIsVisible() then
        chatWindow:close()
        return
    end
    
    if not chatWindow then
        local width = 500
        local height = 450
        local x = getPlayerScreenLeft(0) + (getPlayerScreenWidth(0) - width) / 2
        local y = getPlayerScreenTop(0) + 50
        chatWindow = ArayChatWindow:new(x, y, width, height)
        chatWindow.npcUuid=npc:getModData().ARAY_Uuid
        chatWindow.world_id=ArayHuman.Capabilities.world()
        chatWindow:initialise()
        chatWindow:instantiate()
        chatWindow:addToUIManager()
        chatWindow:setVisible(true)
        return
    end
    
    chatWindow.npcUuid=npc:getModData().ARAY_Uuid
        chatWindow.world_id=ArayHuman.Capabilities.world()
    chatWindow:setVisible(true)
    chatWindow:addToUIManager()
    chatWindow:refreshHistory()
end

function ArayHuman.ChatWindow.close()
    if chatWindow then
        chatWindow:close()
    end
end

function ArayHuman.ChatWindow.isOpen()
    return chatWindow and chatWindow:getIsVisible()
end

print("[ARAY] chat window carregada")
