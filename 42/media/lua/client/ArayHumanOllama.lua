-- Gerenciador de estado do Ollama. Fase 2.
ArayHuman = ArayHuman or {}
ArayHuman.Ollama = ArayHuman.Ollama or {}

local state = {
    online = false,
    version = nil,
    models = {},
    selectedModel = nil,
    lastUpdate = 0,
}

local function parseModels(json)
    local models = {}
    local inArray = false
    local current = ""
    
    for i = 1, #json do
        local c = json:sub(i, i)
        if c == "[" then
            inArray = true
        elseif c == "]" then
            if current ~= "" then
                table.insert(models, current)
            end
            break
        elseif inArray then
            if c == '"' then
                if current == "" then
                    -- Start of string
                    local endPos = json:find('"', i + 1)
                    if endPos then
                        current = json:sub(i + 1, endPos - 1)
                    end
                else
                    -- End of string
                    if current ~= "" then
                        table.insert(models, current)
                        current = ""
                    end
                end
            end
        end
    end
    
    return models
end

function ArayHuman.Ollama.update(pongJson)
    if not pongJson then return end
    
    -- Parse ollama section
    local ollamaStart = pongJson:find('"ollama"%s*:%s*{')
    if not ollamaStart then return end
    
    local ollamaEnd = pongJson:find("}", ollamaStart)
    if not ollamaEnd then return end
    
    local ollamaSection = pongJson:sub(ollamaStart, ollamaEnd)
    
    -- Parse online
    local onlineStr = ollamaSection:match('"online"%s*:%s*(%a+)')
    state.online = (onlineStr == "true")
    
    -- Parse version
    local version = ollamaSection:match('"version"%s*:%s*"([^"]*)"')
    state.version = version ~= "null" and version or nil
    
    -- Parse selected model
    local selected = ollamaSection:match('"selected_model"%s*:%s*"([^"]*)"')
    state.selectedModel = selected ~= "null" and selected or nil
    
    -- Parse models array
    local modelsStart = ollamaSection:find('"models"%s*:%s*%[')
    if modelsStart then
        local modelsEnd = ollamaSection:find("%]", modelsStart)
        if modelsEnd then
            local modelsSection = ollamaSection:sub(modelsStart, modelsEnd)
            state.models = parseModels(modelsSection)
        end
    else
        state.models = {}
    end
    
    state.lastUpdate = getTimestampMs and getTimestampMs() or 0
end

function ArayHuman.Ollama.isOnline()
    return state.online
end

function ArayHuman.Ollama.getVersion()
    return state.version
end

function ArayHuman.Ollama.getModels()
    return state.models
end

function ArayHuman.Ollama.getSelectedModel()
    return state.selectedModel
end

function ArayHuman.Ollama.getStatus()
    if not state.online then
        return "Ollama: offline"
    end
    local line = "Ollama: " .. (state.version or "online")
    if state.selectedModel then
        line = line .. " | " .. state.selectedModel
    else
        line = line .. " | nenhum modelo selecionado"
    end
    return line
end

function ArayHuman.Ollama.selectModel(modelName)
    if not modelName or modelName == "" or modelName == "(sem modelos)" then return end
    
    -- Send model selection via bridge
    if ArayHuman.Bridge and ArayHuman.Bridge.sendModelSelection then
        ArayHuman.Bridge.sendModelSelection(modelName)
        print("[ARAY] ollama modelo selecionado via UI name=" .. modelName)
    end
end

print("[ARAY] ollama gerenciador carregado")
