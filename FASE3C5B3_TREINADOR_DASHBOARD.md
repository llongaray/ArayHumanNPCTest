# 3C.5B.3 — Treinador PowerShell e dashboard Flask

Implementado um fluxo independente de Codex, ChatGPT, Ollama e Project Zomboid. O usuário inicia os processos manualmente. Treino e painel são processos separados; fechar o navegador ou encerrar o dashboard não interrompe um treino iniciado em outro terminal.

## Como usar

Abra o PowerShell na raiz do projeto:

```powershell
Set-Location 'C:\Users\llongaray\Zomboid\mods\ArayHumanNPCTest'
```

Em uma janela, inicie o dashboard:

```powershell
& .\.venv-neural\Scripts\python.exe -B -m ai.neural_trainer dashboard
```

Abra **http://127.0.0.1:8766** no navegador. Em outra janela, na mesma pasta, inicie o treinamento:

```powershell
& .\.venv-neural\Scripts\python.exe -B -m ai.neural_trainer train --epochs 200
```

Não é necessário ativar o venv nem mudar políticas de execução do PowerShell. Usar o caminho explícito acima evita executar o Python global por engano. O comando abre somente o processo solicitado; o dashboard não inicia treino e o treino não inicia servidor.

Outros comandos:

```powershell
& .\.venv-neural\Scripts\python.exe -B -m ai.neural_trainer status
& .\.venv-neural\Scripts\python.exe -B -m ai.neural_trainer checkpoints
& .\.venv-neural\Scripts\python.exe -B -m ai.neural_trainer compare
```

`status` lista estados das execuções manuais; `checkpoints` e `compare` apresentam os checkpoints conhecidos com métricas de validação, hashes, época e situação dos gates, em JSON comparável. A tabela do navegador apresenta os mesmos modelos lado a lado.

Personalização suportada:

```powershell
& .\.venv-neural\Scripts\python.exe -B -m ai.neural_trainer train --epochs 200 --batch-size 32 --learning-rate 0.002 --seed 1729 --variant balanced_sequence
```

Também existem `--encoder-path` e `--output-dir`. O encoder padrão é o MiniLM local já instalado, revisão `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`. Diretórios explícitos de saída precisam ser **novos e estar dentro de `ai/neural_artifacts/`**; se já existem, são recusados e preservados. Não há resume/sobrescrita implícita. Sem `--output-dir`, é gerada uma pasta com timestamp UTC e UUID aleatório, com criação exclusiva e proteção contra colisão.

O ponto de entrada antigo também funciona:

```powershell
& .\.venv-neural\Scripts\python.exe -B ai/train_neural_v2.py --epochs 200
```

Ele agora encaminha ao fluxo manual seguro, sem tentar recriar `3c5b2/`. O erro `new_experiment_root_required` deixa de ocorrer no uso normal sem diretório explícito. Uma execução nova nunca apaga ou sobrescreve a anterior.

## Política de treino e aprovação

Este fluxo usa **somente treino e validação do corpus v2**. Não carrega, codifica ou avalia `test.jsonl`; não existe opção web para repetir o teste final consumido. Ele continua consumido, conforme a 3C.5B.2. Escolher mais épocas ou hiperparâmetros não torna uma execução validada.

Cada execução grava protocolo, parâmetros, hashes das entradas/fontes, fingerprint do encoder, journal, estado, históricos, checkpoints de melhoria e manifest. A melhor época é escolhida pelo critério de validação já existente. Todos os novos manifests permanecem `validated=false`, `test_evaluations=0`; aprovação completa exige futuro teste inédito e revisão específica. O painel pode reconhecer checkpoints v1 realmente aprovados pelo verificador existente, mas não promove modelos por conta própria. Os checkpoints atuais continuam experimentais/reprovados.

São registradas losses reais de treino e validação, além das métricas autorregressivas. Loss de validação usa avaliação sem teacher forcing; no treino, a variante escolhida determina seu uso. Os gráficos não são curvas inventadas ou recompensas de RL. A validação ocorre a cada época no fluxo manual, portanto seu custo é maior que o da antiga avaliação a cada dez épocas. A arquitetura e o número de parâmetros não aumentaram.

## Dashboard

- Aguardando/carregando, treinando, concluído, interrompido ou falhou.
- ID, arquitetura/versão, dataset, época/total, tempo decorrido, estimativa restante após começar a otimização, CPU/RAM e melhor época/checkpoint.
- Gráficos de loss de treino, loss de validação, decisão, intenção exata, objetivos ordenados, compostos, propostas inválidas, cobertura e learning rate.
- Histórico de execuções e comparação de checkpoints com gates de validação; logs de falha acessíveis nos detalhes.
- Polling HTTP a cada dois segundos; sem WebSocket, CDN ou dependência de serviços externos.

CPU é o percentual do **processo**, podendo superar 100% quando usa vários núcleos. RAM é RSS do processo. São amostras registradas pelo treinador, não métricas do jogo. Durante carregamento/codificação, métricas indisponíveis não são inventadas. A estimativa restante é aproximada, baseada nas épocas concluídas, e não inclui previsão artificial do tempo inicial de carregamento.

Estado em `state.json` é escrito via arquivo temporário exclusivo, flush/fsync e substituição atômica. `metrics.jsonl` é append-only por execução. O leitor ignora linha final incompleta e limita sua leitura à cauda recente (até 4 MiB/1.500 registros); o arquivo histórico completo permanece no disco. Não há locks de leitura prendendo o treinamento. Checkpoints de melhoria têm nomes por época e não são sobrescritos por outra execução.

Ctrl+C é tratado e registra interrupção, preservando o que foi salvo. Não há retomada automática de otimizador/época. Se o processo é encerrado à força, o painel reconhece a ausência do PID e seu horário de criação, exibindo interrupção sem confundir um PID reutilizado. Logs de exceção ficam em `error.log` da execução.

## Laboratório Neural

Escolha um checkpoint real na lista, um cenário sintético versionado e digite a mensagem. Para reproduzir o modelo selecionado na fase anterior, escolha **`3c5b2/baseline`**, que continua reprovado. O checkpoint de uma época criado apenas para teste de funcionamento não é uma política melhor ou aprovada.

Destinatários de laboratório: Carlos e Tania/Tânia; múltiplos nomes com “e” ou chamadas coletivas “vocês”, “pessoal”, “todos”, antes de vírgula/dois-pontos. Sem nome, nome desconhecido ou prefixo misturado com nome desconhecido, nenhuma inferência é feita. Esse catálogo fechado é somente dos dois NPCs sintéticos do laboratório; não substitui o roteador Lua do jogo nem interpreta o significado das mensagens.

Exemplos de entrada:

```text
Carlos, me siga.
Tania, procure uma bandagem.
Carlos, pegue a bandagem e depois me siga.
Carlos, como está sua saúde?
```

São exibidos destinatário/UUID/mundo sintético, intenções previstas, confiança, decisão bruta, dois objetivos, candidatos/capacidades/estado observados sintéticos, ações bloqueadas, motivos dos guardas e tempo de inferência. O painel separa previsão bruta, resultado dos guardas e resultado esperado do cenário. Mensagens livres não recebem um rótulo correto inventado; no cenário de prioridade emergencial, apenas o resultado esperado do guarda (WAIT) é conhecido.

O fluxo visual é **Mensagem → MiniLM → Embedding → Política Neural → Intenções/objetivos → Guardas**. As barras mostram os primeiros 12 componentes do embedding real de 384 dimensões, com sinal e valor no tooltip; não simulam atividade de neurônios ou avanço do aprendizado. Os gráficos do treino usam o journal real.

Usa `NPCPolicy`, MiniLM CPU/local, `trust_remote_code=False`, safetensors para o encoder e `torch.load(weights_only=True)` para a política. Hash do checkpoint e fingerprint do encoder são conferidos. Somente um pedido de inferência por vez é admitido por processo; concorrência adicional recebe “laboratory_busy”. Modelos/encoder ficam em cache limitado ao modelo selecionado e ao encoder existente.

**Nenhuma ação é executada**, mesmo se o resultado dos guardas permitir EXECUTE_ACTION. A resposta sempre registra `DISABLED_SYNTHETIC_ONLY`. Executor, Capabilities, mailbox, NPCs reais e Ollama não são chamados. PUSH_ZOMBIE e CLIMB_STAIRS permanecem bloqueados pelos contratos existentes.

## Interface local e dependências

Flask inicia somente por comando manual em `127.0.0.1`, porta padrão 8766; não existe argumento de host público. Debugger e reloader desativados. Host e origem local são verificados; POST de laboratório exige token gerado no processo. Não há endpoints para executar comandos, iniciar/parar treinamento, receber caminhos arbitrários de checkpoint ou alterar arquivos do jogo. Textos são renderizados como texto, sem inserir mensagens do usuário como HTML.

Flask 3.1.3, Werkzeug 3.1.9, blinker 1.9.0 e itsdangerous 2.2.0 foram instalados **somente em `.venv-neural`**. Versões, relatório de instalação, textos de licença e snapshot completo das dependências estão em `ai/neural_experiments_v3/`. Python global e launcher existentes não foram alterados. `pip check`: sem dependências quebradas. A implementação segue as orientações oficiais do [Flask](https://flask.palletsprojects.com/en/stable/quickstart/) quanto a binding local e debugger desligado.

## Verificação executada

- Regressão completa: **1.002 aprovados, 0 pulados, 0 falhas**, 47,08 s. Duas advertências já conhecidas sobre o nome obsoleto de um método do SentenceTransformers.
- Após os ajustes finais do catálogo, os 20 testes específicos do dashboard passaram novamente. Uma nova regressão final foi registrada no mesmo diretório de evidências.
- Testes Flask usam `test_client`, sem socket de escuta ou servidor iniciado.
- Treinamento real de uma época pelo novo CLI, sem teste final: ID `71571e1e34f7435caa04f16a1e16e6ac`, status concluído, loss treino **8,96777**, loss validação **6,16451**, `test_evaluations=0`. Trata-se somente de teste de funcionamento, não melhoria validada da rede.
- O estado e journal desse treino foram recuperados pelo endpoint de detalhes com HTTP 200 no cliente de testes. Evidência: `ai/neural_experiments_v3/manual-smoke.json`.
- Inferência real CPU/MiniLM/checkpoint anterior no laboratório, incluindo guarda emergencial e nenhum despacho de ação.
- Diretórios/IDs concorrentes, saída existente preservada, caminho fora da área recusado, journal parcial, processo morto, destinatários, origem/host remoto, token ausente, campos indevidos e Ctrl+C cobertos.
- Sintaxe JavaScript verificada pelo Node; nenhum framework/CDN necessário.

**Validação visual no navegador e teste manual prolongado permanecem pendentes.** Não foi iniciado servidor para declarar que esses testes já aconteceram. O usuário deve iniciar o dashboard pelos comandos acima e conferir polling/gráficos no navegador. Fechar o navegador não encerra o processo de treino; Ctrl+C no terminal do treino encerra esse processo. O servidor Flask é uma ferramenta local de desenvolvimento, não um serviço publicado.

## Arquivos

Criados: `ai/neural_trainer/{__init__,__main__,cli,store,lab,web}.py`, template HTML, CSS/JavaScript locais, `ai/test_neural_dashboard.py`, evidências/dependências em `ai/neural_experiments_v3/` e este relatório. Modificado: `ai/train_neural_v2.py` para CLI reutilizável, parâmetros, observador, losses e checkpoints de melhoria. Artefatos anteriores da 3C.5B.1/3C.5B.2 e respectivos corpora foram preservados; hashes conferidos em `ai/neural_experiments_v3/integrity.json`.

Não houve jogo, Ollama ou servidor Flask iniciado, alteração de saves/SQLite real/JARs/executáveis/FBO/câmera/controles/balões/modelo Ollama, commit/push ou ativação da RN. Não implementado RL. Não iniciado 3C.5C.
