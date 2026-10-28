# Fase 1: Ponte Lua ↔ Python

**Status**: Implementado, aguardando teste.

## Arquivos criados

- `42/media/lua/client/ArayHumanBridge.lua` - ponte Lua
- `ai/bridge.py` - serviço Python

## O que faz

O Lua envia até 3 pings com `id`, `kind: ping`, `world_id`, `world_name` e `game_mode`. O Python responde com `pong` contendo o mesmo `id` e `ok: true`. Nenhuma ação é executada, nenhum Ollama é chamado.

**Protocolo de publicação atômica:**

- Lua: escreve `<id>.json.tmp`, fecha, depois escreve `<id>.ok`.
- Python: lê `.tmp` só quando `.ok` existe, publica resposta com `os.replace`.

## Teste

### 1. Sem o serviço Python

1. Inicie o jogo com o mod.
2. Carregue ou crie um save.
3. Aguarde até 30 segundos.
4. Console deve mostrar:
   ```
   [ARAY] ponte carregada
   [ARAY] ponte ping id=<timestamp>-1 world_id=<mode>/<world>
   [ARAY] ponte timeout id=<timestamp>-1
   [ARAY] ponte ping id=<timestamp>-2 world_id=<mode>/<world>
   [ARAY] ponte timeout id=<timestamp>-2
   [ARAY] ponte ping id=<timestamp>-3 world_id=<mode>/<world>
   [ARAY] ponte timeout id=<timestamp>-3
   [ARAY] ponte sem servico
   ```
5. O jogo continua jogável, sem travamento.

### 2. Com o serviço Python

1. No terminal (fora do jogo):
   ```powershell
   cd C:\Users\llongaray\Zomboid\mods\ArayHumanNPCTest
   python ai\bridge.py
   ```
   Deve mostrar:
   ```
   [ARAY] ponte servico iniciado dir=C:\Users\llongaray\Zomboid\Lua\ArayHumanNPCTest
   ```

2. Inicie o jogo com o mod.
3. Carregue ou crie um save.
4. Console do jogo deve mostrar:
   ```
   [ARAY] ponte carregada
   [ARAY] ponte ping id=<timestamp>-1 world_id=<mode>/<world>
   [ARAY] ponte pong id=<timestamp>-1
   ```

5. Console do Python deve mostrar:
   ```
   [ARAY] ponte ping id=<timestamp>-1 world_id=<mode>/<world>
   [ARAY] ponte pong id=<timestamp>-1
   ```

6. O mesmo `id` aparece nos dois lados. O jogo não trava.

## Arquivos criados em `Zomboid/Lua/ArayHumanNPCTest/`

- `to_py/<id>.json.tmp` e `to_py/<id>.ok` (temporários, apagados pelo Python)
- `to_lua/<id>.json` (resposta do Python)
- `seen_ids.txt` (últimos 32 IDs processados)

## Reversão

Se precisar desabilitar a ponte:

1. Renomeie `42/media/lua/client/ArayHumanBridge.lua` para `ArayHumanBridge.lua.disabled`.
2. Recarregue o Lua no jogo (menu Debug).

## Critério de aceite

✓ Jogo jogável com o Python desligado (timeout, sem travamento).  
✓ Console mostra o mesmo `id` no Lua e no Python quando o serviço está ligado.  
✓ Nenhuma exceção do mod.  
✓ Nenhum campo `action` nas mensagens.

## Próxima fase

Após aceite, implementar Fase 2: detecção do Ollama e exibição no F7.
