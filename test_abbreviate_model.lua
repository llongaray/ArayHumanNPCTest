-- Teste estatico da funcao abbreviateModelName
-- Executar: lua test_abbreviate_model.lua

local function abbreviateModelName(fullName)
    if not fullName or fullName == "" or fullName == "(sem modelos)" then
        return fullName
    end
    
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

-- Testes
local tests = {
    {
        input = "hf.co/PatrickPat/remnants-llm-v5-GGUF:Q4_K_M",
        expected = "remnants-llm-v5 [Q4_K_M]",
    },
    {
        input = "llama3.2:latest",
        expected = "llama3.2 [latest]",
    },
    {
        input = "mistral:7b-instruct-v0.2-q4_K_M",
        expected = "mistral [7b-instruct-v0.2-q4_K_M]",
    },
    {
        input = "phi3:medium",
        expected = "phi3 [medium]",
    },
    {
        input = "llama3.2",
        expected = "llama3.2",
    },
    {
        input = "(sem modelos)",
        expected = "(sem modelos)",
    },
    {
        input = "",
        expected = "",
    },
    {
        input = nil,
        expected = nil,
    },
    {
        input = "hf.co/user/model-name-gguf:tag",
        expected = "model-name [tag]",
    },
}

print("=== Teste: abbreviateModelName ===\n")

local passed = 0
local failed = 0

for i, test in ipairs(tests) do
    local result = abbreviateModelName(test.input)
    local ok = (result == test.expected)
    
    if ok then
        passed = passed + 1
        print(string.format("✓ Teste %d: PASSOU", i))
    else
        failed = failed + 1
        print(string.format("✗ Teste %d: FALHOU", i))
        print(string.format("  Input:    %s", tostring(test.input)))
        print(string.format("  Esperado: %s", tostring(test.expected)))
        print(string.format("  Obtido:   %s", tostring(result)))
    end
end

print(string.format("\n=== Resultados: %d/%d passaram ===", passed, passed + failed))

if failed == 0 then
    print("\n✅ Todos os testes passaram!")
    os.exit(0)
else
    print(string.format("\n❌ %d teste(s) falharam", failed))
    os.exit(1)
end
