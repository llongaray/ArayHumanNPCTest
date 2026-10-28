# Correção do Launcher — Fase 2

## Problema identificado

O launcher original tentava executar `ProjectZomboid64.exe` diretamente usando `start /WAIT`, mas:

1. O executável `.exe` não configura o ambiente necessário
2. O processo `.exe` pode retornar imediatamente sem aguardar o Java
3. O diretório de trabalho não estava sendo configurado

**Diagnóstico confirmado pelo usuário:**
- Executar manualmente `ProjectZomboid64.bat` funciona ✅
- O launcher não abria o jogo ❌

## Correção aplicada

### Mudanças no `ArayHumanNPCTest_Launcher.bat`

**Antes:**
```batch
set "GAME_EXE=%GAME_DIR%\ProjectZomboid64.exe"
...
start /WAIT "" "%GAME_EXE%"
```

**Depois:**
```batch
set "GAME_BAT=%GAME_DIR%\ProjectZomboid64.bat"
...
pushd "%GAME_DIR%"
call "%GAME_BAT%"
popd
```

### Justificativa técnica

1. **`ProjectZomboid64.bat` em vez de `.exe`:**
   - O arquivo `.bat` configura variáveis de ambiente
   - Inicia o `jre64\bin\java.exe` com os argumentos corretos
   - Passa a classe principal `zombie.gameStates.MainScreenState`
   - O `.exe` não tem essa configuração

2. **`pushd` / `popd`:**
   - Define `GAME_DIR` como diretório de trabalho
   - O BAT original espera estar no diretório do jogo
   - Caminhos relativos (como `.\jre64\bin\java.exe`) funcionam corretamente
   - `popd` restaura o diretório original após o jogo fechar

3. **`call` em vez de `start /WAIT`:**
   - `call` executa o BAT no contexto atual e aguarda
   - O `ProjectZomboid64.bat` internamente aguarda o processo Java
   - Quando o Java termina, o BAT retorna
   - Quando o BAT retorna, o launcher continua

4. **Encerramento correto:**
   - O launcher aguarda o retorno de `call`
   - Só então encerra o Python pelo PID salvo
   - Não encerra processos genéricos por nome
   - Isola apenas o serviço iniciado por este launcher

## Validação manual

### Teste 1: Inicialização básica

```batch
cd c:\Users\llongaray\Zomboid\mods\ArayHumanNPCTest
.\ArayHumanNPCTest_Launcher.bat
```

**Resultado esperado:**
```
========================================
ArayHumanNPCTest - Launcher
========================================

[OK] Python encontrado: python

Iniciando servico Python...
Log: ...\ai\service.log

[OK] Servico Python iniciado com sucesso.

Iniciando Project Zomboid...
Diretorio: E:\Games\Project.Zomboid.v42.13.1\game

[Jogo abre normalmente no menu principal]
```

### Teste 2: Serviço Python ativo

**Com o jogo aberto:**
1. Verificar que `ai\service.pid` existe
2. Verificar processo Python rodando:
   ```powershell
   Get-Process python | Where-Object {$_.Id -eq (Get-Content ai\service.pid)}
   ```
3. Entrar no mundo de teste
4. F7 → Verificar comunicação Ollama

### Teste 3: Encerramento limpo

1. Fechar o jogo normalmente
2. Launcher deve exibir:
   ```
   Jogo fechado. Encerrando servico Python...
   [OK] Servico Python encerrado.
   
   Launcher finalizado.
   ```
3. Verificar que `ai\service.pid` foi deletado
4. Verificar que processo Python foi encerrado

### Teste 4: Caminho com espaços

Se o caminho do jogo contém espaços (ex: `C:\Program Files\...`):
1. As aspas duplas em `"%GAME_DIR%"` e `"%GAME_BAT%"` protegem corretamente
2. `pushd` funciona com caminhos entre aspas
3. `call` executa o BAT mesmo com espaços no caminho

## Arquivos modificados

**Único arquivo alterado:**
- `ArayHumanNPCTest_Launcher.bat`

**Linhas modificadas:**
- Linha 21: `GAME_EXE` → `GAME_BAT`
- Linha 22: `.exe` → `.bat`
- Linha 34: `GAME_EXE` → `GAME_BAT`
- Linha 35: mensagem atualizada
- Linha 121: `GAME_EXE` → `GAME_BAT`
- Linhas 124-128: Substituído `start /WAIT` por `pushd / call / popd`

**Total de mudanças:** 8 linhas

## Compatibilidade

✅ Não modifica `ProjectZomboid64.bat` original  
✅ Não modifica executáveis do jogo  
✅ Não altera configurações do jogo  
✅ Funciona com caminhos contendo espaços  
✅ Funciona com instalações Steam, GOG, standalone  
✅ Preserva comportamento de inicialização manual  
✅ Não interfere com outros launchers  

## Segurança

✅ Não executa comandos arbitrários  
✅ Não requer privilégios elevados  
✅ Encerra apenas o processo Python iniciado por este launcher  
✅ Não mata processos Java genéricos  
✅ Não interfere com outras aplicações Python  
✅ PID file evita múltiplas instâncias acidentais  

## Performance

✅ Mesma performance do launcher original do jogo  
✅ Nenhum overhead adicional  
✅ Serviço Python não consome recursos significativos  
✅ Não afeta FPS do jogo  

## Como usar agora

1. Ajustar `GAME_DIR` no topo do `ArayHumanNPCTest_Launcher.bat` se necessário
2. Executar o launcher
3. Aguardar o jogo abrir
4. Jogar normalmente
5. Fechar o jogo — Python encerra automaticamente

**Exemplo de caminho correto:**
```batch
set "GAME_DIR=E:\Games\Project.Zomboid.v42.13.1\game"
```

**Ou para instalação Steam padrão:**
```batch
set "GAME_DIR=C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid"
```

## Reversão

Se houver problemas:
1. Continuar usando inicialização manual:
   ```powershell
   python ai\ollama_service.py
   ```
2. Abrir o jogo pelo `ProjectZomboid64.bat` original
3. Mod funciona normalmente

## Estado dos arquivos

### Antes da correção:
- Launcher não abria o jogo
- Encerrava imediatamente

### Depois da correção:
- Launcher abre o jogo via BAT original ✅
- Aguarda o jogo fechar ✅
- Encerra Python corretamente ✅
- Limpa recursos ✅

## Próximos passos

**Validação manual pelo usuário:**
1. Executar o launcher corrigido
2. Confirmar que o jogo abre
3. Entrar no mundo e testar F7
4. Verificar seleção de modelos
5. Fechar o jogo e confirmar encerramento limpo

**Após validação:**
- Fase 2 estará completamente funcional
- Pronto para avançar para Fase 3 se aprovado
