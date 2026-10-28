# Como usar o Launcher Automático

## Por que usar o launcher?

O mod **ArayHumanNPCTest** precisa de um serviço Python rodando em segundo plano para funcionar. Por padrão, você precisa abrir um PowerShell e executar manualmente:

```powershell
python ai\ollama_service.py
```

O **launcher automático** elimina essa necessidade: ele inicia o Python e o jogo automaticamente, e encerra tudo corretamente ao sair.

## Primeira vez: configurar o launcher

1. Abrir `ArayHumanNPCTest_Launcher.bat` em um editor de texto
2. Localizar a linha `set "GAME_DIR=E:\Games\Project.Zomboid.v42.13.1\game"`
3. Ajustar para o caminho onde seu Project Zomboid está instalado
4. **IMPORTANTE:** O caminho deve apontar para a pasta `game` onde está o `ProjectZomboid64.bat`
5. Salvar e fechar

**Exemplo para instalação Steam padrão:**
```batch
set "GAME_DIR=C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid"
```

**Exemplo para instalação GOG:**
```batch
set "GAME_DIR=C:\GOG Games\Project Zomboid"
```

**Como verificar o caminho correto:**
- Navegue até a pasta de instalação do Project Zomboid
- Confirme que existe o arquivo `ProjectZomboid64.bat` nessa pasta
- Use esse caminho completo no `GAME_DIR`

## Como usar

### Iniciar o jogo com o mod:
1. Fechar o jogo se estiver aberto
2. Executar `ArayHumanNPCTest_Launcher.bat`
3. Aguardar o jogo abrir automaticamente

**Você verá:**
```
========================================
ArayHumanNPCTest - Launcher
========================================

[OK] Python encontrado: python

Iniciando servico Python...
Log: C:\Users\...\ai\service.log

[OK] Servico Python iniciado com sucesso.

Iniciando Project Zomboid...
```

### Ao sair do jogo:
- O serviço Python será **encerrado automaticamente**
- Não precisa fazer nada manualmente

## Se algo der errado

### "ERRO: Python nao encontrado"

**Causa:** Python não está instalado ou não está no PATH.

**Solução:**
1. Instalar Python 3.10+ de [python.org](https://www.python.org/downloads/)
2. Durante a instalação, marcar "Add Python to PATH"
3. Reiniciar o launcher

### "AVISO: Arquivo PID encontrado"

**Causa:** O launcher detectou um serviço Python anterior que pode não ter sido encerrado corretamente.

**Solução:**
- Digitar `S` para encerrar o serviço antigo automaticamente
- O launcher limpará o PID e continuará normalmente

### "AVISO: Launcher do jogo nao encontrado"

**Causa:** O arquivo `ProjectZomboid64.bat` não foi encontrado no caminho configurado.

**Solução:**
1. Abrir `ArayHumanNPCTest_Launcher.bat` em um editor
2. Verificar a linha `set "GAME_DIR=..."`
3. Confirmar que o caminho está correto
4. Verificar que existe `ProjectZomboid64.bat` nessa pasta
5. Salvar e executar novamente

### "ERRO: Servico Python nao encontrado"

**Causa:** O arquivo `ai\ollama_service.py` não existe.

**Solução:**
- Verificar se você extraiu o mod corretamente
- O arquivo deve estar em `mods\ArayHumanNPCTest\ai\ollama_service.py`

### O serviço Python não inicia

**Verificar:**
1. Abrir o log: `ai\service.log`
2. Procurar por mensagens de erro
3. Verificar se o `requests` está instalado: `pip install requests`

### O jogo não abre

**Verificar:**
1. Caminho `GAME_DIR` está correto no `.bat`
2. O arquivo `ProjectZomboid64.bat` existe no caminho
3. Você tem permissão de execução na pasta do jogo

**Alternativa:**
- Iniciar o serviço Python pelo launcher
- Quando perguntar "Continuar apenas com o servico Python? (S/N)", digitar `S`
- Abrir o jogo manualmente pelo `ProjectZomboid64.bat` original
- O mod funcionará normalmente

**Nota técnica:**
O launcher utiliza o `ProjectZomboid64.bat` original do jogo, não o `.exe` diretamente. Isso garante que todas as configurações de ambiente e caminhos do Java sejam carregadas corretamente.

## Ainda prefiro inicialização manual?

**Sem problemas!** O método manual continua funcionando:

```powershell
cd c:\Users\llongaray\Zomboid\mods\ArayHumanNPCTest
python ai\ollama_service.py
```

Então abrir o jogo normalmente. Ao sair, pressionar `Ctrl+C` no PowerShell.

## Arquivos gerados

### `ai/service.pid`
- Armazena o PID do processo Python
- Usado pelo launcher para encerrar corretamente
- Deletado automaticamente ao encerrar
- **Se o jogo travar:** delete este arquivo manualmente antes de reiniciar

### `ai/service.log`
- Log completo do serviço Python
- Útil para debug
- Sobrescrito a cada execução do launcher

## Desinstalar

Para voltar ao método manual:
1. Deletar `ArayHumanNPCTest_Launcher.bat`
2. Continuar usando `python ai\ollama_service.py` manualmente

## Suporte

Se encontrar problemas:
1. Verificar `ai\service.log`
2. Verificar console do jogo (`C:\Users\<seu_usuario>\Zomboid\console.txt`)
3. Relatar com os dois logs
