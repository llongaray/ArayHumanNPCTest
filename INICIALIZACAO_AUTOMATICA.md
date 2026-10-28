# Investigação: Inicialização Automática do Serviço Python

## APIs verificadas na Build 42.13.1

### Lua do Project Zomboid

A sandbox Lua do Project Zomboid **não expõe**:
- `os.execute`
- `io.popen`
- `ProcessBuilder` (Java)
- `Runtime.exec` (Java)

O `LuaManager.GlobalObject` não fornece métodos para iniciar processos externos.

### Limitação confirmada

**O mod Lua não pode iniciar o serviço Python automaticamente.**

## Alternativas técnicas

### 1. Launcher batch (RECOMENDADO)

Criar `ArayHumanNPCTest_Launcher.bat` que:
1. Verifica se Python está disponível
2. Inicia `ollama_service.py` em segundo plano
3. Inicia o Project Zomboid
4. Ao fechar o jogo, encerra o serviço

**Vantagens:**
- Simples, seguro, sem modificar o jogo
- Processo Python encerrado junto com o jogo
- Funciona sem privilégios admin
- Fácil de reverter (usar o executável original)

**Desvantagens:**
- Requer iniciar o jogo pelo batch, não pelo executável direto
- Uma janela de console adicional (pode ser minimizada)

### 2. Serviço do Windows

Instalar o Python como serviço permanente do Windows.

**Desvantagens:**
- Requer privilégios de administrador
- Processo permanente consumindo recursos
- Complexo de desinstalar
- **NÃO RECOMENDADO** para um mod

### 3. Tarefa agendada no boot

Configurar uma tarefa do Windows para iniciar o serviço no boot.

**Desvantagens:**
- Requer configuração manual
- Processo permanente
- Não é automático para novos usuários
- **NÃO RECOMENDADO**

### 4. VSCode/Cursor task runner

Usuários que já usam Cursor/VSCode podem configurar uma task.

**Desvantagens:**
- Só funciona quando o editor está aberto
- Não é portável entre usuários
- **NÃO RECOMENDADO** como solução principal

## Recomendação

**Launcher batch** é a única solução viável que:
- Não modifica o jogo
- Não requer privilégios elevados
- Não cria processos permanentes
- É fácil de reverter

## Implementação proposta

1. Criar `ArayHumanNPCTest_Launcher.bat`
2. Detectar Python no PATH ou em localizações comuns
3. Iniciar `ollama_service.py` com `pythonw.exe` (sem janela)
4. Salvar PID do Python
5. Iniciar o jogo
6. Ao detectar que o jogo fechou, encerrar o Python pelo PID

## Documentação clara

O README deve explicar:
- Para inicialização automática: usar o launcher
- Para inicialização manual: continuar usando o PowerShell
- Ambas as opções funcionam igualmente bem
