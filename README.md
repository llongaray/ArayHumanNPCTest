# Aray Human NPC Test

Mod experimental de NPC humano nativo para Project Zomboid Build 42.13.1.

## Objetivo

Investigar a criacao e inicializacao de `IsoSurvivor` sem converter `IsoZombie`, com testes isolados em mundos descartaveis.

## Estado atual

- O jogo reconhece o mod `ArayHumanNPCTest`.
- Um teste anterior conseguiu instanciar `IsoSurvivor`.
- O teste falhou durante a atualizacao de `IsoGameCharacter`, pois `getBodyDamage()` retornou `null`.
- A inicializacao segura da entidade ainda precisa ser validada.

## Estrutura de instalacao (Build 42)

```text
ArayHumanNPCTest/
  42/
    mod.info
    media/
      lua/
        client/
```

## Desenvolvimento

O codigo Lua existente na instalacao local ainda nao foi importado para este repositorio. Antes de substituir os arquivos locais por `git pull`, sincronize a versao local ou forneca o ZIP do mod para revisao. Nao teste em saves importantes.

## Ambiente

- Project Zomboid: 42.13.1
- Mod ID: `ArayHumanNPCTest`
- Repositorio: `llongaray/ArayHumanNPCTest`
