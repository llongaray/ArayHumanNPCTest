# Comandos de Teste — Fase 2

## Teste 1: Módulo de modelos por mundo (sem o jogo)

```powershell
cd c:\Users\llongaray\Zomboid\mods\ArayHumanNPCTest
python ai\test_world_models.py
```

**Resultado esperado:**
- Cria `Zomboid/Lua/ArayHumanNPCTest/world_models.json`
- Salva seleções de modelos por mundo
- Recarrega e valida persistência

✅ **Validado:** Teste passou com sucesso

---

## Teste 2: Serviço Python com PID tracking (sem o jogo)

```powershell
cd c:\Users\llongaray\Zomboid\mods\ArayHumanNPCTest
python ai\ollama_service.py
```

**Resultado esperado:**
```
[ARAY] servico PID=<numero> gravado em ...
[ARAY] servico ollama iniciado dir=...
[ARAY] ollama online version=0.21.0 models=3
```

**Verificar:**
1. Arquivo `ai/service.pid` foi criado com o PID
2. Pressionar `Ctrl+C` para encerrar
3. Verificar mensagem: `[ARAY] servico PID removido`
4. Arquivo `ai/service.pid` foi deletado automaticamente

---

## Teste 3: Launcher automático (com o jogo)

### Preparação:
1. Fechar o jogo se estiver aberto
2. Abrir `ArayHumanNPCTest_Launcher.bat` em um editor
3. Ajustar `GAME_DIR` para o caminho correto:
   ```batch
   set "GAME_DIR=E:\Games\Project.Zomboid.v42.13.1\game"
   ```
4. Salvar

### Execução:
1. Clicar duas vezes em `ArayHumanNPCTest_Launcher.bat`
2. Aguardar mensagens:
   ```
   [OK] Python encontrado: python
   [OK] Servico Python iniciado com sucesso.
   Iniciando Project Zomboid...
   ```
3. O jogo abrirá automaticamente
4. Entrar no mundo de teste
5. Pressionar **F7**
6. Verificar interface:
   ```
   Ollama: 0.21.0 | nenhum modelo selecionado
   
   Modelo:
   [Dropdown com 3 modelos]
   ```
7. Selecionar um modelo no dropdown
8. Verificar atualização: `Ollama: 0.21.0 | <modelo_selecionado>`

### Verificação no console do launcher:
```
[ARAY] ponte ping id=... world_id=sandbox/Riverside
[ARAY] modelo selecionado world=sandbox/Riverside model=...
[ARAY] ponte pong id=...
```

### Encerramento:
9. Fechar o jogo normalmente
10. Launcher encerra automaticamente:
    ```
    Jogo fechado. Encerrando servico Python...
    [OK] Servico Python encerrado.
    ```

---

## Teste 4: Persistência de seleção por mundo

1. Com o launcher/serviço rodando
2. Entrar no mundo de teste (ex: Riverside)
3. F7 → Selecionar modelo "llama3.2:latest"
4. **Sair do mundo** (voltar ao menu principal)
5. **Entrar novamente** no mesmo mundo
6. F7 → Verificar que "llama3.2:latest" está selecionado automaticamente
7. **Criar/entrar em outro mundo** (ex: Muldraugh)
8. F7 → Verificar que nenhum modelo está selecionado (mundo diferente)
9. Selecionar "mistral:latest"
10. Sair e entrar novamente
11. F7 → Verificar "mistral:latest" mantido
12. Voltar ao primeiro mundo (Riverside)
13. F7 → Verificar "llama3.2:latest" mantido

**Arquivo de persistência:**
```powershell
Get-Content "$env:USERPROFILE\Zomboid\Lua\ArayHumanNPCTest\world_models.json"
```

**Exemplo de conteúdo:**
```json
{
  "sandbox/Riverside": "llama3.2:latest",
  "survival/Muldraugh": "mistral:latest"
}
```

---

## Teste 5: Modelo removido do Ollama

**Cenário:** Testar comportamento quando modelo salvo não está mais disponível

1. Com o jogo **fechado**:
   ```powershell
   # Simular remoção editando world_models.json
   $json = Get-Content "$env:USERPROFILE\Zomboid\Lua\ArayHumanNPCTest\world_models.json" | ConvertFrom-Json
   $json.'sandbox/Riverside' = "modelo-inexistente:latest"
   $json | ConvertTo-Json | Set-Content "$env:USERPROFILE\Zomboid\Lua\ArayHumanNPCTest\world_models.json"
   ```

2. Iniciar launcher e jogo
3. Entrar no mundo
4. F7 → Verificar: `Ollama: 0.21.0 | nenhum modelo selecionado`
5. Dropdown continua funcional com os 3 modelos reais
6. Selecionar um modelo válido
7. Verificar que a seleção é salva corretamente

---

## Teste 6: Inicialização manual ainda funciona

1. **Não usar o launcher**
2. Abrir PowerShell:
   ```powershell
   cd c:\Users\llongaray\Zomboid\mods\ArayHumanNPCTest
   python ai\ollama_service.py
   ```
3. Abrir o jogo pelo executável original
4. Entrar no mundo
5. F7 → Tudo deve funcionar normalmente
6. Selecionar modelo
7. Verificar logs no PowerShell
8. Ao sair do jogo, encerrar PowerShell com `Ctrl+C`

---

## Teste 7: Múltiplas instâncias (proteção)

1. Iniciar o launcher
2. Jogo abre, **deixar rodando**
3. Em outro terminal, tentar:
   ```powershell
   cd c:\Users\llongaray\Zomboid\mods\ArayHumanNPCTest
   python ai\ollama_service.py
   ```
4. **Resultado esperado:** Ambas as instâncias criam PIDs separados
5. Ao fechar o jogo, launcher encerra **somente** o seu processo
6. A instância manual continua rodando até `Ctrl+C`

**Nota:** Se executar o launcher duas vezes, ele detecta o PID antigo e oferece encerrar.

---

## Teste 8: Launcher sem o jogo instalado no caminho padrão

1. Editar `ArayHumanNPCTest_Launcher.bat`
2. Mudar `GAME_DIR` para um caminho inválido
3. Executar launcher
4. **Resultado esperado:**
   ```
   AVISO: Executavel do jogo nao encontrado em:
   <caminho_invalido>
   
   Continuar apenas com o servico Python? (S/N):
   ```
5. Digitar `S`
6. Serviço Python inicia normalmente
7. Abrir jogo manualmente
8. Mod funciona normalmente

---

## Comandos úteis para debug

### Ver processo Python rodando:
```powershell
Get-Process python | Where-Object {$_.CommandLine -like "*ollama_service*"}
```

### Ver PID salvo:
```powershell
Get-Content "c:\Users\llongaray\Zomboid\mods\ArayHumanNPCTest\ai\service.pid"
```

### Ver log do serviço:
```powershell
Get-Content "c:\Users\llongaray\Zomboid\mods\ArayHumanNPCTest\ai\service.log"
```

### Ver seleções de modelos:
```powershell
Get-Content "$env:USERPROFILE\Zomboid\Lua\ArayHumanNPCTest\world_models.json" | ConvertFrom-Json | Format-List
```

### Limpar tudo e recomeçar:
```powershell
# Encerrar todos os processos Python
Get-Process python | Stop-Process -Force

# Deletar PIDs e logs
Remove-Item "c:\Users\llongaray\Zomboid\mods\ArayHumanNPCTest\ai\service.pid" -ErrorAction SilentlyContinue
Remove-Item "c:\Users\llongaray\Zomboid\mods\ArayHumanNPCTest\ai\service.log" -ErrorAction SilentlyContinue

# Deletar seleções de modelos (opcional)
Remove-Item "$env:USERPROFILE\Zomboid\Lua\ArayHumanNPCTest\world_models.json" -ErrorAction SilentlyContinue
```

---

## Checklist de validação completa

- [ ] Teste 1: `test_world_models.py` passou
- [ ] Teste 2: PID criado e deletado automaticamente
- [ ] Teste 3: Launcher inicia Python e jogo automaticamente
- [ ] F7 mostra dropdown com modelos
- [ ] Seleção de modelo atualiza a linha Ollama
- [ ] Console Python mostra `modelo selecionado`
- [ ] Teste 4: Modelo persiste ao reentrar no mundo
- [ ] Teste 4: Mundos diferentes têm seleções independentes
- [ ] Teste 5: Modelo inexistente não quebra a UI
- [ ] Teste 6: Inicialização manual continua funcionando
- [ ] Launcher encerra Python automaticamente ao fechar o jogo
- [ ] Arquivo `ai/service.pid` é deletado ao encerrar
- [ ] Não há processos Python órfãos após fechar o jogo
- [ ] 120 FPS mantido (nenhum lag adicionado)
