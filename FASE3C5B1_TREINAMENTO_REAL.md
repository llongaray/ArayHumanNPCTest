# 3C.5B.1 — Instalação isolada e treinamento real

Data: 28/10/2026. Resultado: **rede treinada, checkpoint experimental reprovado; não validada e não integrada ao jogo**. Não recomendo iniciar a integração da 3C.5C com este checkpoint.

## Ambiente instalado

Venv exclusivo: `.venv-neural/`, ignorado pelo Git, criado com Python 3.11.9 AMD64. Nenhuma alteração no Python global, launcher ou serviço do projeto. `pip check`: sem dependências quebradas. Torch informa `cuda_available=false` e sufixo `+cpu`.

| Componente | Versão instalada | Licença registrada |
| --- | --- | --- |
| PyTorch | 2.15.0+cpu | Expressão composta Apache/BSD/MIT/ISC/Zlib/BSL e exceção LLVM, conforme wheel; licenças incluídas preservadas |
| SentenceTransformers | 6.2.0 | Apache-2.0 |
| Transformers | 5.21.0 | Apache-2.0 |
| NumPy | 2.4.6 | BSD-3-Clause e licenças dos componentes incluídos |
| Tokenizers | 0.23.3 | Apache-2.0; licença obtida do tag oficial porque o wheel não a incluiu |
| Safetensors | 0.8.0 | Texto de licença Apache preservado do pacote |
| Hugging Face Hub | 2.3.0 | Apache-2.0 |
| pytest / psutil | 9.2.0 / 7.2.2 | MIT / BSD-3-Clause |

Todas as **51 distribuições**, versões, metadados de licença e caminhos dos textos disponíveis estão em `ai/neural_environment/environment.json` e `licenses/`. Licença Python copiada do interpretador base. A complementação do Tokenizers está em `license-supplement.json`, com origem e SHA256. Isso registra as licenças encontradas; não reduz bibliotecas compostas a uma licença única.

PyTorch instalado exclusivamente pelo índice oficial `https://download.pytorch.org/whl/cpu`. Os relatórios `torch-install.json` e `dependencies-install.json` conservam URLs e hashes dos pacotes. `requirements-lock.txt` contém todas as versões; `requirements-without-torch.txt` permite separar o índice CPU do restante da instalação.

Máquina observada: Windows AMD64, 8 núcleos físicos / 16 lógicos, RAM física 34.240.733.184 bytes. Treino e benchmarks limitados a duas threads Torch.

## Encoder e integridade

Modelo autorizado: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.

- Revisão imutável: `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`.
- Diretório: `ai/neural_models/paraphrase-multilingual-MiniLM-L12-v2/e8f8c211226b894fcb81acc59f3b34ba3efd5f42/`.
- Pesos: somente `model.safetensors`, 470.641.600 bytes. Nenhum peso pickle/bin, ONNX, OpenVINO ou TensorFlow baixado.
- Tokenizer, configurações, pooling e README da revisão preservados. Lista completa, tamanho e SHA256 de cada arquivo: `ai/neural_environment/encoder-download.json`.
- Licença declarada no card da revisão: Apache-2.0; README local preservado.
- Fingerprint agregado dos arquivos: `97473d94587537f61c5ee79a3f2ca82e0ccedede46ea6f34e6ee13000fda7fbb`.
- Carregamento real: CPU, caminho local, `local_files_only=True`, `trust_remote_code=False`, `use_safetensors=True`; treinamento e benchmark com HF/Transformers em modo offline.

O download inicial resolveu a revisão pública e a registrou antes de buscar os arquivos. O downloader entregue fixa diretamente essa mesma revisão para reprodução. Não houve envio de observações, conversas ou identidade de NPCs para serviços externos. O cache de download separado também está ignorado pelo Git.

## Protocolo e auditoria dos dados

`ai/neural_environment/training-protocol.json` foi registrado antes do treino: hashes do código original, hiperparâmetros, auditoria e gates. Não houve modificação de rótulos, arquitetura, encoder, guardas ou hiperparâmetros. O trainer recebeu apenas instrumentação de progresso/evidências e adiamento da codificação do teste para depois de congelar os pesos selecionados.

Corpus autoral/sintético, **não experiência real do jogo**: 243 exemplos de treino, 162 de validação e 162 de teste; 168 famílias de frases. Auditoria passou sem frases normalizadas ou famílias compartilhadas entre conjuntos, incluindo normalização do vocativo. Digest do corpus: `ae68cfa3de01197649f584f47ac7ead465b6fc4cd98a1a7d25d0295a4dd24cf8`.

As situações, catálogo e estrutura dos snapshots são compartilhados entre conjuntos por projeto. Ausência de duplicação não prova independência semântica completa nem generalização para situações reais. O nome varia por conjunto (Carlos/Tania/João), outra limitação do desenho experimental.

Desequilíbrio confirmado **sem correção nesta execução**: no treino, INSTRUCTION e ACTION_REQUEST aparecem em 231/243 exemplos cada; CONVERSATION=3, QUESTION=1, INFORMATION=6 e NO_RESPONSE=3. Decisões: WAIT=114, CLARIFICATION=60, EXECUTE=57, DIALOGUE=6, CONTINUE=3, NO_RESPONSE=3. Distribuições detalhadas estão em `data-diagnostics.json`.

## Treinamento executado

- Rede PyTorch real `NPCPolicy`, arquitetura já implementada `aray_multitask_gru_v1`; MiniLM pré-treinado congelado como encoder, sem fine-tuning do encoder.
- Seed Torch/Python: 1729; 100 épocas; batch 32; AdamW LR 0,002; weight decay 0,01; clipping 1; duas threads; hidden 128 e embeddings 384.
- Seleção exclusivamente pela soma `decision_accuracy + intent_exact + ordered_goal_exact` da validação, melhoria estrita. Avaliações nas épocas 1, 6, ..., 96 e 100, conforme implementação original.
- Época selecionada: **86**, escore de seleção 2,0519818064. Histórico completo em `validation-history.json`.
- Otimização e seleção: **5,562 s**. Execução do trainer incluindo carregamento/codificação/avaliação e gravação de predições: **16,938 s**, sem instalações e download.
- Pesos selecionados gravados e hash fixado **antes** da avaliação do teste. Teste avaliado **uma única vez**, após a seleção. Predições dessa passagem foram preservadas; análises posteriores apenas leram esses registros, sem novo forward sobre teste.
- Nenhum retreino ou ajuste baseado no teste foi executado. Reprodutibilidade numérica bit a bit entre máquinas/versões não é garantida somente pela seed; ambiente e dados foram registrados para reprodução controlada.

## Gates congelados e resultados

Todos os critérios precisam passar em validação **e** teste.

| Métrica | Gate original | Validação | Teste | Resultado |
| --- | --- | --- | --- | --- |
| Amostras | ≥20 | 162 | 162 | passou |
| Intenções multilabel, conjunto exato | ≥80% | 95,06% (154/162) | 94,44% (153/162) | passou |
| Acurácia das decisões | ≥85% | 75,93% (123/162) | 75,93% (123/162) | falhou |
| Objetivos ordenados exatos | ≥80% | 34,21% (13/38) | 21,05% (8/38) | falhou |
| Casos com dois objetivos | ≥4 | 4 | 4 | passou |
| Dois objetivos exatos | ≥80% | 25% (1/4) | 0% (0/4) | falhou |
| Decisões inválidas antes dos guardas | 0% | 9,88% (16/162) | 11,73% (19/162) | falhou |
| Cobertura com confiança ≥0,80 | ≥50% | 46,91% (76/162) | 46,91% (76/162) | falhou |

Objetivos são comparados incluindo ordem, ação e target_id; denominador apenas exemplos com objetivos esperados. A taxa inválida preserva a definição original: EXECUTE_ACTION bruto que seria recusado pelos guardas estruturais/prioridade com limiar de confiança zero, dividido por todas as amostras. Entre pedidos EXECUTE brutos, foram 16/35 inválidos na validação e 19/29 no teste. Não houve despacho ao jogo.

Intenção exata elevada é enganosa neste corpus desbalanceado: nenhuma das classes CONVERSATION, QUESTION, INFORMATION e NO_RESPONSE foi detectada no teste. Os valores não autorizam chamar o modelo de interpretador geral aprovado.

### Matrizes e confiança

Ordem das linhas reais e colunas previstas: EXECUTE_ACTION, REQUEST_DIALOGUE, CONTINUE_GOAL, WAIT, NO_RESPONSE, REQUEST_CLARIFICATION.

```text
Validação:
20 0 0  0 0 18
 1 0 0  0 0  3
 0 0 0  0 0  2
 0 0 0 76 0  0
 0 0 0  0 1  1
14 0 0  0 0 26

Teste único:
17 0 0  0 0 21
 0 0 0  0 0  4
 0 0 1  0 0  1
 0 0 0 76 0  0
 0 0 0  0 1  1
12 0 0  0 0 28
```

Confusão multilabel no teste, formato TP/FP/FN/TN:

| Intenção | TP | FP | FN | TN |
| --- | --- | --- | --- | --- |
| CONVERSATION | 0 | 0 | 2 | 160 |
| QUESTION | 0 | 0 | 2 | 160 |
| INSTRUCTION | 153 | 8 | 0 | 1 |
| ACTION_REQUEST | 153 | 8 | 0 | 1 |
| INFORMATION | 0 | 0 | 4 | 158 |
| NO_RESPONSE | 0 | 0 | 2 | 160 |

Matrizes completas de ambos os conjuntos estão no manifest. Confiança média: validação 0,72274, teste 0,72833. No teste: faixa <0,5 tem 36 casos e 47,22% de acerto de decisão; 0,5–0,8 tem 50 casos e 60%; 0,8–0,9 não tem casos; ≥0,9 tem 76 casos e 100% de acerto, **todos WAIT**. Não houve ação de alta confiança. Confiança não calibrada; nenhuma calibração ou alteração de limiar usando teste.

## Custo em CPU

Benchmark final isolado após a suíte, 30 observações **somente da validação**, uma observação por chamada, duas threads. O benchmark inicial concorrente com a regressão foi substituído por esta medição sem essa concorrência. Nenhuma segunda avaliação do teste; os resumos de confiança usam as predições salvas.

| Medição | Média | Mediana | P95 |
| --- | --- | --- | --- |
| Cabeça neural + decode, tensores previamente codificados | 0,469 ms | 0,436 ms | 0,618 ms |
| Completa com cache textual frio | 185,231 ms | 184,941 ms | 193,076 ms |
| Completa com cache textual aquecido | 0,683 ms | 0,670 ms | 0,725 ms |

Carregamento encoder/cabeça: 5,314 s. RSS antes: 205.860.864 bytes; depois: 1.186.377.728 bytes (~1,10 GiB); pico do working set do processo: 1.213.804.544 bytes (~1,13 GiB). São medições reais do processo de inferência, não pico instrumentado do treinamento. Não incluem IPC, Lua, navegação ou Ollama. Cache aquecido pressupõe textos repetidos; snapshots reais variáveis podem aproximar o custo frio. Não é benchmark dentro do jogo.

## Artefatos e alterações

Checkpoint experimental: `ai/neural_artifacts/3c5b1-seed1729/weights.pt`, 1.348.458 bytes.

SHA256: `fdf321f7a663bce5399463d28dd42f1b94a2137cd194d6f1ff6873d449a3121b`.

No mesmo diretório: `manifest.json` (`trained=true`, `validated=false`, `game_validated=false`, `test_evaluations=1`), corpus exato usado, `validation-history.json`, `validation-predictions.json`, `test-predictions.json`, `benchmark.json` e `data-diagnostics.json`. Manifest e hashes não transformam o checkpoint reprovado em validado. O runtime recusa sua ativação com `checkpoint_not_validated`, confirmado por teste.

Arquivos criados nesta fase: `ai/download_neural_encoder.py`, `ai/benchmark_neural.py`, `ai/record_neural_environment.py`, `ai/test_neural_training_evidence.py`, registros em `ai/neural_environment/` e este relatório. Modificados: `.gitignore` (ambiente/modelos/artefatos/cache ignorados) e `ai/train_neural.py` (instrumentação; teste adiado até seleção e pesos congelados).

Sem alterações nos módulos Lua, arquitetura, dados autorais, runtime/guardas, launcher ou integração de chat. Arquivos preexistentes modificados/não rastreados no workspace foram preservados; não representam alterações desta fase.

## Regressão

Teste numérico anteriormente pulado: executado com Torch real e aprovado, incluindo forward, backward e atualização dos pesos. Primeiro, todos os **961 testes anteriores** passaram. Depois dos nove testes adicionais de evidências, regressão completa: **970 aprovados, 0 pulados, 0 falhas**, 38,38 s. JUnit em `ai/neural_environment/regression.xml`.

Comando usado (runtime Lua simulado já existente):

```powershell
$env:PYTHONPATH="$env:TEMP/aray-perception-test-runtime"
& ./.venv-neural/Scripts/python.exe -B -m pytest ai -q -p no:cacheprovider --tb=short --junitxml=ai/neural_environment/regression.xml
```

Os testes simulados Lua/Python e numéricos não demonstram integração real no jogo. O runtime Lupa externo da regressão não foi instalado no Python global ou incluído como dependência produtiva do venv ML.

## Reprodução controlada

Em checkout novo, com Python 3.11.9 AMD64 e acesso às versões registradas:

```powershell
python -m venv .venv-neural
& ./.venv-neural/Scripts/python.exe -m pip install torch==2.15.0+cpu --index-url https://download.pytorch.org/whl/cpu
& ./.venv-neural/Scripts/python.exe -m pip install -r ai/neural_environment/requirements-without-torch.txt
& ./.venv-neural/Scripts/python.exe -m pip check
& ./.venv-neural/Scripts/python.exe -B ai/download_neural_encoder.py
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
```

O downloader recusa sobrescrever o manifest de download existente; o payload original já está disponível nesta máquina. Uma reprodução deve usar ambiente/diretório novo e verificar hashes registrados. Não apagar artefatos desta execução. Wheels não foram arquivados integralmente; sua disponibilidade futura é uma dependência externa, apesar das versões/URLs/hashes preservados.

O comando de treino original foi:

```powershell
& ./.venv-neural/Scripts/python.exe -B ai/train_neural.py --encoder-path ai/neural_models/paraphrase-multilingual-MiniLM-L12-v2/e8f8c211226b894fcb81acc59f3b34ba3efd5f42 --output-dir ai/neural_artifacts/3c5b1-seed1729 --epochs 100
```

Esse diretório já existe e o trainer recusa sobrescrita. Não executar novo treinamento para tentar melhorar este teste. A reprodução técnica não cria um novo teste estatisticamente independente.

## Recomendação e limitações

Não iniciar a 3C.5C com esta política. Antes de futura aprovação, é necessário planejar novo experimento: corpus maior e balanceado com conversas/perguntas, estados e candidatos diversos, mais objetivos compostos, avaliação por classe e por ação, e seleção/calibração exclusivamente em treino/validação. Reservar **novo conjunto de teste não consultado**: este já foi consumido e suas falhas agora são conhecidas. Essas são propostas para futura autorização, não mudanças realizadas nesta fase. Não relaxar os gates para aprovar este checkpoint.

A implementação e o gradiente numérico funcionam; a qualidade aprendida é insuficiente. Preservam-se também as limitações anteriores de descrições de candidatos nem sempre disponíveis no AgentState e validação nativa pendente. Não houve ativação neural, RL, jogo, Ollama ou serviços iniciados, nem alteração de saves/SQLite real/JARs/executáveis/FBO/câmera/controles/balões/modelo Ollama. Nenhum commit ou push. Aguardar instruções.

Referências de licença: [Tokenizers v0.23.3](https://github.com/huggingface/tokenizers/blob/v0.23.3/LICENSE) e [card do MiniLM na revisão fixada](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2/tree/e8f8c211226b894fcb81acc59f3b34ba3efd5f42), com evidência local preservada nos manifests e textos.
