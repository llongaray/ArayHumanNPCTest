-- Menu F7. F2 a F6 continuam com os atalhos nativos do jogo.
require "ISUI/ISCollapsableWindow"
require "ISUI/ISButton"
require "ISUI/ISLabel"
require "ISUI/ISComboBox"

ArayHuman = ArayHuman or {}

local window = nil

-- Abrevia nomes de modelos Ollama para exibicao
-- Preserva o ID original para todas as operacoes internas
local function abbreviateModelName(fullName)
    if not fullName or fullName == "" or fullName == "(sem modelos)" then
        return fullName
    end
    
    -- Extrai nome do modelo e quantizacao de formatos comuns
    -- Exemplos:
    -- hf.co/PatrickPat/remnants-llm-v5-GGUF:Q4_K_M -> remnants-llm-v5 [Q4_K_M]
    -- llama3.2:latest -> llama3.2 [latest]
    -- mistral:7b-instruct-v0.2-q4_K_M -> mistral [7b-instruct-v0.2-q4_K_M]
    
    local name = fullName
    local tag = nil
    
    -- Separar tag (depois de ':')
    local colonPos = fullName:find(":")
    if colonPos then
        name = fullName:sub(1, colonPos - 1)
        tag = fullName:sub(colonPos + 1)
    end
    
    -- Remover prefixo de repositorio (hf.co/, etc)
    local slashPos = name:find("/[^/]*$")
    if slashPos then
        name = name:sub(slashPos + 1)
    end
    
    -- Remover sufixo -GGUF ou similar
    name = name:gsub("%-GGUF$", "")
    name = name:gsub("%-gguf$", "")
    
    -- Construir nome abreviado
    if tag and tag ~= "" then
        return name .. " [" .. tag .. "]"
    end
    
    return name
end

local function keyboardCaptured()
    local chat = ISChat and ISChat.instance
    if chat and chat.textEntry and chat.textEntry.isFocused and chat.textEntry:isFocused() then
        return true
    end
    return false
end

ArayNpcWindow = ISCollapsableWindow:derive("ArayNpcWindow")

function ArayNpcWindow:new(x, y, width, height)
    local o = ISCollapsableWindow:new(x, y, width, height)
    setmetatable(o, self)
    self.__index = self
    o.title = "Aray NPC — Gerenciador de Ajudantes"
    o.resizable = false
    o.ollamaUpdateTick = 0
    return o
end

function ArayNpcWindow:createChildren()
    ISCollapsableWindow.createChildren(self)
    
    -- Define button width once at the start
    local buttonW = self.width - 24
    
    local y = self:titleBarHeight() + 8
    self.statusLabel = ISLabel:new(12, y, 18, "Nenhum ajudante.", 1, 1, 1, 1, UIFont.Small, true)
    self.statusLabel:initialise()
    self.statusLabel:instantiate()
    self:addChild(self.statusLabel)

    y = y + 28
    self.ollamaLabel = ISLabel:new(12, y, 18, "Ollama: verificando...", 1, 1, 1, 1, UIFont.Small, true)
    self.ollamaLabel:initialise()
    self.ollamaLabel:instantiate()
    self:addChild(self.ollamaLabel)

    y = y + 28
    self.modelLabel = ISLabel:new(12, y, 18, "Modelo:", 1, 1, 1, 1, UIFont.Small, true)
    self.modelLabel:initialise()
    self.modelLabel:instantiate()
    self:addChild(self.modelLabel)

    y = y + 22
    self.modelCombo = ISComboBox:new(12, y, buttonW, 22, self, ArayNpcWindow.onModelSelect)
    self.modelCombo:initialise()
    self.modelCombo:instantiate()
    self.modelCombo:addOption("(sem modelos)")
    self.modelCombo.selected = 1
    self.modelCombo:setEnabled(false)
    self:addChild(self.modelCombo)

    y = y + 28
    self.spawnButton = ISButton:new(12, y, buttonW, 22, "Criar ajudante", self, ArayNpcWindow.onSpawn)
    self.spawnButton:initialise()
    self.spawnButton:instantiate()
    self:addChild(self.spawnButton)

    y = y + 28
    self.pullButton = ISButton:new(12, y, buttonW, 22, "Puxar ajudante para perto", self, ArayNpcWindow.onPull)
    self.pullButton:initialise()
    self.pullButton:instantiate()
    self:addChild(self.pullButton)

    y = y + 28
    self.walkButton = ISButton:new(12, y, buttonW, 22, "Testar caminhada (4 tiles)", self, ArayNpcWindow.onTestWalk)
    self.walkButton:initialise()
    self.walkButton:instantiate()
    self:addChild(self.walkButton)
    
    y = y + 28
    self.chatButton = ISButton:new(12, y, buttonW, 22, "Conversar com ajudante", self, ArayNpcWindow.onChat)
    self.chatButton:initialise()
    self.chatButton:instantiate()
    self:addChild(self.chatButton)

    y=y+28
    self.npcCombo=ISComboBox:new(12,y,buttonW,22,self,ArayNpcWindow.onNpcSelect)
    self.npcCombo:initialise(); self.npcCombo:instantiate(); self:addChild(self.npcCombo)
    self.npcIds={}
    for _,entry in ipairs(ArayHuman.rosterSnapshot and ArayHuman.rosterSnapshot() or {}) do
        if not entry.dead then
            self.npcIds[#self.npcIds+1]=entry.uuid
            self.npcCombo:addOption(tostring(entry.character:getModData().ARAY_Name or "NPC").." ["..entry.uuid:sub(1,8).."]")
        end
    end
    self.selectedUuid=self.npcIds[1]
    y=y+28
    self.inventoryButton=ISButton:new(12,y,buttonW,22,"Inventário do NPC selecionado",self,ArayNpcWindow.onInventory)
    self.inventoryButton:initialise(); self.inventoryButton:instantiate(); self:addChild(self.inventoryButton)

    y = y + 28
    self.persistLabel = ISLabel:new(12, y, 18, "Persistência: aguardando", 1, 1, 1, 1, UIFont.Small, true)
    self.persistLabel:initialise()
    self.persistLabel:instantiate()
    self:addChild(self.persistLabel)

    y = y + 22
    self.saveButton = ISButton:new(12, y, buttonW, 22, "Salvar ajudante agora", self, ArayNpcWindow.onSaveCarlos)
    self.saveButton:initialise()
    self.saveButton:instantiate()
    self:addChild(self.saveButton)
    
    self:setHeight(y + 28 + self:titleBarHeight())
end

function ArayNpcWindow:updateModelCombo()
    if not self.modelCombo or not ArayHuman.Ollama then return end
    
    local models = ArayHuman.Ollama.getModels() or {}
    local selectedModel = ArayHuman.Ollama.getSelectedModel()
    
    self.modelCombo:clear()
    
    if #models == 0 then
        self.modelCombo:addOption("(sem modelos)")
        self.modelCombo.selected = 1
        self.modelCombo:setEnabled(false)
        return
    end
    
    self.modelCombo:setEnabled(true)
    local selectedIndex = 1
    
    -- Armazenar mapeamento entre nome abreviado e ID completo
    self.modelCombo.modelMap = {}
    
    for i, model in ipairs(models) do
        local displayName = abbreviateModelName(model)
        self.modelCombo:addOption(displayName)
        self.modelCombo.modelMap[i] = model  -- ID completo original
        
        if model == selectedModel then
            selectedIndex = i
        end
    end
    
    self.modelCombo.selected = selectedIndex
end

function ArayNpcWindow:onModelSelect(box)
    if not box or box.selected <= 0 then return end
    
    -- Recuperar ID original do modelo a partir do mapa
    local originalModelId = box.modelMap and box.modelMap[box.selected]
    if not originalModelId then
        -- Fallback: usar o nome exibido (para compatibilidade)
        originalModelId = box.options[box.selected]
    end
    
    if not originalModelId or originalModelId == "(sem modelos)" then return end
    
    if ArayHuman.Ollama and ArayHuman.Ollama.selectModel then
        -- Sempre envia o ID completo original para o backend
        ArayHuman.Ollama.selectModel(originalModelId)
    end
end

function ArayNpcWindow:prerender()
    ISCollapsableWindow.prerender(self)
    if self.statusLabel and ArayHuman.getStatus then
        self.statusLabel:setName(ArayHuman.getStatus())
    end
    
    -- Update Ollama status every 60 frames (~2 seconds at 30 FPS)
    self.ollamaUpdateTick = (self.ollamaUpdateTick or 0) + 1
    if self.ollamaUpdateTick >= 60 then
        self.ollamaUpdateTick = 0
        if self.ollamaLabel and ArayHuman.Ollama and ArayHuman.Ollama.getStatus then
            self.ollamaLabel:setName(ArayHuman.Ollama.getStatus())
        end
        self:updateModelCombo()
        self:updateNpcCombo()
    end
    if self.persistLabel and ArayHuman.Lifecycle and ArayHuman.Lifecycle.statusLine then
        self.persistLabel:setName(ArayHuman.Lifecycle.statusLine())
    end
end

function ArayNpcWindow:onSaveCarlos()
    if ArayHuman.Lifecycle and ArayHuman.Lifecycle.saveNow then
        ArayHuman.Lifecycle.saveNow()
    end
end

function ArayNpcWindow:onSpawn()
    if ArayHuman.spawn then ArayHuman.spawn() end
end

function ArayNpcWindow:onPull()
    if ArayHuman.pull then ArayHuman.pull() end
end

function ArayNpcWindow:onTestWalk()
    if ArayHuman.testWalk then ArayHuman.testWalk() end
end

function ArayNpcWindow:onChat()
    -- Prioriza TalkBar (conversa presencial), fallback para janela antiga
    if ArayHuman.TalkBar and ArayHuman.TalkBar.open then
        ArayHuman.TalkBar.open(self.selectedUuid)
    elseif ArayHuman.ChatWindow and ArayHuman.ChatWindow.open then
        ArayHuman.ChatWindow.open(self.selectedUuid)
    end
end
function ArayNpcWindow:onNpcSelect(box) self.selectedUuid=self.npcIds[box.selected] end
function ArayNpcWindow:updateNpcCombo()
    if not self.npcCombo then return end
    local selected=self.selectedUuid; local found=false
    self.npcCombo:clear(); self.npcIds={}
    for _,entry in ipairs(ArayHuman.rosterSnapshot and ArayHuman.rosterSnapshot() or {}) do
        if not entry.dead and #self.npcIds<128 then
            self.npcIds[#self.npcIds+1]=entry.uuid
            self.npcCombo:addOption(tostring(entry.character:getModData().ARAY_Name or "NPC").." ["..entry.uuid:sub(1,8).."]")
            if entry.uuid==selected then self.npcCombo.selected=#self.npcIds; found=true end
        end
    end
    if not found then self.npcCombo.selected=1 end
    self.selectedUuid=self.npcIds[self.npcCombo.selected or 1]
end
function ArayNpcWindow:onInventory()
    require "ArayHumanInventoryWindow"
    if ArayHuman.InventoryWindow then
        local ok,why=ArayHuman.InventoryWindow.open(self.selectedUuid)
        if not ok and ArayHuman.setStatus then ArayHuman.setStatus("Inventário: "..tostring(why)) end
    end
end

function ArayNpcWindow:close()
    self:setVisible(false)
end

local function toggleWindow()
    if window and window:getIsVisible() then
        window:close()
        return
    end
    if not window then
        local width = 380
        local height = 238
        local x = getPlayerScreenLeft(0) + 24
        local y = getPlayerScreenTop(0) + 24
        window = ArayNpcWindow:new(x, y, width, height)
        window:initialise()
        window:instantiate()
        window:addToUIManager()
        window:setVisible(true)
        return
    end
    window:setVisible(true)
    window:addToUIManager()
end

local function onKeyPressed(key)
    if key ~= Keyboard.KEY_F7 then return end
    local player = getSpecificPlayer(0)
    if not player or player:isDead() then return end
    if keyboardCaptured() then return end
    toggleWindow()
end

Events.OnKeyPressed.Add(onKeyPressed)
