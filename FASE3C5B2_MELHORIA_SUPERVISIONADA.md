# 3C.5B.2 — Melhoria supervisionada, avaliação e reprovação

Data: 28/10/2026. **Resultado final: REPROVADO.** A acurácia de decisões melhorou e a taxa de propostas inválidas caiu, mas não houve generalização suficiente para objetivos ordenados, planos compostos e todas as classes minoritárias. Não ativar a política nem iniciar automaticamente a 3C.5C.

## Preservação e escopo

Todos os arquivos da execução `ai/neural_artifacts/3c5b1-seed1729/` foram inventariados com SHA256 antes dos trabalhos. O teste de preservação confirmou os mesmos hashes depois dos experimentos. Corpus original, pesos, métricas, predições e benchmark anteriores foram preservados integralmente. Inventário: `ai/neural_experiments_v2/previous-artifacts.json`.

Nenhum pacote ou modelo novo instalado/baixado. Usados o venv existente, PyTorch CPU 2.15.0+cpu, SentenceTransformers 6.2.0 e o MiniLM local na revisão `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`. Fingerprint novamente verificado: `97473d94587537f61c5ee79a3f2ca82e0ccedede46ea6f34e6ee13000fda7fbb`. Versões e licenças continuam no registro da 3C.5B.1; referência com hash em `ai/neural_experiments_v2/integrity.json`.

Não houve leitura do antigo conjunto de teste para escolher arquitetura ou hiperparâmetros: sua métrica publicada é usada somente na comparação deste relatório. A verificação de preservação lê seus bytes exclusivamente para integridade.

## Auditoria da implementação

Foram revisados `NPCPolicy.forward`, construção dos targets, filtragem dos candidatos por ação, perda do ponteiro, retorno da GRU e `decode` autorregressivo.

- Não foi demonstrado erro de deslocamento de índice ação/target_id/candidato. Um novo teste inverte a lista de candidatos, reconstrói índices a partir dos IDs e verifica dois objetivos e a decodificação correta usando logits de referência. Isso é teste de alinhamento, não acurácia neural.
- O treino original usa a ação anterior correta por teacher forcing; a avaliação real usa a ação prevista anteriormente. Esse descompasso existe, mas não foi confirmado como causa principal: no checkpoint baseline selecionado, exatidão de planos na validação foi **28,49% tanto com teacher forcing quanto autorregressivamente**. Portanto, não seria correto atribuir toda a falha à propagação de erros da GRU.
- A perda de ponteiro original é somada e dividida pelo batch inteiro, enquanto sua supervisão só existe em exemplos/slots com destinos. Isso dilui sua contribuição em batches com poucas ações direcionadas. Foi testada normalização pelo número real de ponteiros e peso maior; é uma escolha de escala, não prova de índice incorreto.
- A cabeça de ações original não aplica máscara de capacidades antes do argmax; o ponteiro é filtrado por ação na decodificação e as propostas são recusadas pelos guardas. Isso foi preservado: aplicar as recusas de segurança antes da medição esconderia propostas inválidas. Nenhuma máscara do Executor foi relaxada.
- O token budget do encoder rejeitou um resumo de estado com 134 tokens durante a preparação, antes de qualquer atualização de pesos ou avaliação do teste. O registro foi mantido em `3c5b2-preflight-tokenbudget/`. Criado adaptador v2 que reduz campos inteiros mantendo JSON válido, respeita o limite por grupo e marca resumos como parciais. Features numéricas continuam calculadas da observação integral. O encoder e o runtime v1 não foram modificados.

Foi mantida a arquitetura `aray_multitask_gru_v1`, hidden 128, **335.552 parâmetros treináveis**, mesmo tamanho da 3C.5B.1. MiniLM congelado, sem fine-tuning. Não houve evidência que justificasse aumentar parâmetros nesta etapa.

## Corpus v2

Novo diretório: `ai/neural_supervised_data_v2/`. Dados autorais/sintéticos; não são experiências de jogo ou textos produzidos por Ollama. Não são usados como regras de interpretação em produção.

| Conjunto | Exemplos | Planos válidos de dois objetivos |
| --- | ---: | ---: |
| Treino | 792 | 312 |
| Validação | 556 | 76 |
| Novo teste | 572 | 92 |
| Total | 1.920 | 480 |

São 444 famílias declaradas, 33 famílias de contexto/variante e 937 mensagens normalizadas distintas, aproximadamente 3,4 vezes o total anterior. Há 144 formulações atômicas autorais (três por ação por partição), 180 falas autorais não atômicas e composição sistemática de pares de ações. Não se apresentam os 1.920 exemplos como 1.920 situações semanticamente independentes: parte é aumento controlado de contexto e construção de planos.

Cobertura: seis nomes, acentos opcionais, abreviações e alterações de digitação controladas; destinatários múltiplos; conversa, pergunta, informação, silêncio, esclarecimento e continuação; todas as 16 ações; prioridades manual/emergência, candidatos ausentes, capacidades indisponíveis, saúde, inventário e ameaças observadas variáveis. Informações declarativas sem pedido de reação foram rotuladas NO_RESPONSE; perguntas factuais e conversa pedem REQUEST_DIALOGUE. Essas são escolhas explícitas de supervisão, não uma semântica universal de toda frase PT-BR.

As construções atômicas foram atribuídas a partições antes de ampliar os contextos. Os pares não ordenados de ações são atribuídos por função determinística antes da geração das frases; ambas as ordens de um par ficam na mesma partição. Assim, o teste contém combinações de ações não usadas no treino. Auditoria recusa frases normalizadas ou IDs de famílias compartilhados entre partições. Labels executáveis foram verificados contra os mesmos guardas estruturais usados pelo runtime.

IDs de candidatos são opacos por exemplo, vinculados a UUID/mundo/observação; a lista é embaralhada. A seleção usa uma propriedade observada e textual (marca azul/vermelha), com dois candidatos por ação direcionada. Isso testa o alinhamento sem depender de índice fixo. É um problema artificial mais simples que distinguir objetos reais heterogêneos; não comprova domínio do inventário real.

### Balanceamento e limites dos dados

| Decisão | Treino | Validação | Teste |
| --- | ---: | ---: | ---: |
| EXECUTE_ACTION | 408 | 172 | 188 |
| WAIT | 96 | 96 | 96 |
| REQUEST_CLARIFICATION | 88 | 88 | 88 |
| REQUEST_DIALOGUE | 80 | 80 | 80 |
| NO_RESPONSE | 80 | 80 | 80 |
| CONTINUE_GOAL | 40 | 40 | 40 |

Cada classe minoritária CONVERSATION, QUESTION, INFORMATION e NO_RESPONSE tem **40 exemplos em cada conjunto**, contra 1–6 exemplos de treino na v1. O corpus está mais coberto, mas **não uniformemente balanceado**: planos compostos aumentam EXECUTE_ACTION e INSTRUCTION/ACTION_REQUEST. O experimento alternativo usa pesos de perda inversos à frequência para compensar isso. O baseline vencedor não transforma essa distribuição em uniforme.

Limitação importante da separação: IDs de cenário/mundo são disjuntos, mas as distribuições básicas de saúde, inventário e ameaça e a taxonomia de variantes são compartilhadas. As famílias declaradas são de construção lexical e combinação de ações; sua auditoria não prova independência semântica rigorosa entre todas as paráfrases nem um holdout de cenários físicos reais. Assim, a exigência de corpus plenamente balanceado e generalização semântica ampla **não pode ser declarada integralmente atendida** por esta versão. Não foram criadas milhares de paráfrases automáticas para ocultar essa limitação.

## Experimentos e protocolo

Antes do treino foram gravados configurações, gates, hashes do código e manifest do corpus em `ai/neural_artifacts/3c5b2/protocol-before-training.json`.

Ambos: seed 1729, batch 32, AdamW LR 0,002, weight decay 0,01, grad clipping 1, 150 épocas, duas threads CPU. Avaliação de validação nas épocas 1, 11, ..., 141 e 150. Melhoria estrita, sem consulta ao teste.

1. **baseline**: formulação original de perdas e teacher forcing; dados e adaptador textual v2.
2. **balanced_sequence**: BCE com pesos positivos por classe (limitados a 0,2–10), CE de decisões inversamente proporcional à frequência (máximo 5), perdas de ação e ponteiro com peso 2, ponteiro normalizado pelo número supervisionado. Teacher forcing nas primeiras 20 épocas; depois, batches alternam deterministicamente pela seed entre teacher forcing e feedback das próprias previsões, probabilidade 0,5. Nenhum parser ou regra fixa escolhe a intenção/ação.

Critério previamente fixado de seleção: decisão exata + intenção exata + plano exato + composto exato + F1 macro de intenções − taxa inválida, exclusivamente na validação. Esse critério não substitui os gates de aprovação, que continuam obrigatórios.

| Métrica na validação | baseline | balanced_sequence |
| --- | ---: | ---: |
| Época selecionada | 131 | 111 |
| Escore de seleção | 2,84010 | 2,71275 |
| Intenções exatas | 86,51% | 82,91% |
| Decisões corretas | 86,87% | 82,91% |
| Objetivos ordenados | 28,49% | 22,67% |
| Dois objetivos | 1,32% (1/76) | 1,32% (1/76) |
| Propostas inválidas | 3,42% | 1,98% |
| Cobertura ≥0,80 | 53,96% | 37,77% |
| Duração treino/seleção | 31,188 s | 31,562 s |

O experimento balanceado reduziu propostas inválidas, mas piorou o escore global e a cobertura. **Não foi promovido**. Nenhum ajuste posterior tentou fazê-lo vencer após olhar o teste.

Pesos baseline foram congelados antes do teste, conforme `selection-frozen-before-test.json`. Só então foi carregado/codificado o novo teste para um único forward final. O outro experimento não foi avaliado no teste. As análises e métricas detalhadas posteriores usam apenas as predições dessa passagem já salvas. Total da execução incluindo codificação/experimentos/avaliação: **74,860 s**, sem instalação/download.

## Comparação final e gates originais

Os testes v1 e v2 são diferentes; as colunas abaixo não constituem uma comparação pareada no mesmo benchmark. A v2 exige combinações novas e tem distribuição muito diferente. Não se deve interpretar as diferenças como efeito causal isolado de uma única mudança.

| Métrica | Gate mínimo original | Teste 3C.5B.1 | Teste 3C.5B.2 |
| --- | --- | ---: | ---: |
| Exemplos | ≥20 | 162 | 572 |
| Intenções multilabel exatas | ≥80% | 94,44% | 83,92% (480/572) |
| Acurácia das decisões | ≥85% | 75,93% | 86,01% (492/572) |
| Objetivos ordenados exatos | ≥80% | 21,05% | 20,74% (39/188) |
| Amostra de dois objetivos | ≥4 | 4 | 92 |
| Dois objetivos exatos | ≥80% | 0% | 0% (0/92) |
| Propostas inválidas antes dos guardas | 0% | 11,73% | 3,67% (21/572) |
| Cobertura de confiança ≥0,80 | ≥50% | 46,91% | 50,87% (291/572) |

A validação do selecionado também falhou nos gates de plano composto, plano ordenado e propostas inválidas. Todos os gates precisam passar em **ambos** os conjuntos. Nenhum foi relaxado.

Gates adicionais congelados: pelo menos 40 compostos em cada avaliação; suporte de pelo menos 20 positivos por intenção, recall e F1 ≥0,80 em todas as intenções; recall ≥0,80 para cada decisão; suporte ≥3 e plano exato ≥0,80 por ação. Lista integral das falhas por conjunto em `result.json`. Os requisitos adicionais também reprovaram.

### Intenções por classe no novo teste

| Classe | Suporte | Precisão | Recall | F1 |
| --- | ---: | ---: | ---: | ---: |
| CONVERSATION | 40 | 81,82% | 90,00% | 85,71% |
| QUESTION | 40 | 100,00% | 60,00% | 75,00% |
| INFORMATION | 40 | 100,00% | 42,50% | 59,65% |
| NO_RESPONSE | 40 | 89,47% | 85,00% | 87,18% |
| INSTRUCTION | 412 | 96,38% | 96,84% | 96,61% |
| ACTION_REQUEST | 372 | 95,54% | 92,20% | 93,84% |

As quatro classes antes não detectadas agora têm detecções reais; QUESTION e INFORMATION ainda falham claramente. Não declarar o problema das classes minoritárias resolvido.

Recall por decisão: EXECUTE_ACTION 83,51%, REQUEST_DIALOGUE 90%, CONTINUE_GOAL 95%, WAIT 100%, NO_RESPONSE 77,50%, REQUEST_CLARIFICATION 76,14%.

### Objetivos por ação e tipo

Métrica por ação abaixo: plano inteiro correto nos exemplos cujo plano esperado contém essa ação. Um erro na outra etapa também reprova o plano. Contagens por slot, ação correta e alvo condicionado à ação estão separadas em `diagnostics.json`.

| Ação | Planos com a ação | Planos inteiramente corretos |
| --- | ---: | ---: |
| STOP | 10 | 0,00% |
| FOLLOW_PLAYER | 14 | 21,43% |
| LOOK_AT_PLAYER | 14 | 14,29% |
| WALK | 26 | 7,69% |
| RUN | 18 | 0,00% |
| SNEAK | 26 | 7,69% |
| FACE_TARGET | 14 | 28,57% |
| OPEN_DOOR | 14 | 42,86% |
| CLOSE_DOOR | 18 | 11,11% |
| OPEN_WINDOW | 18 | 16,67% |
| CLIMB_WINDOW | 18 | 22,22% |
| CLIMB_FENCE | 22 | 18,18% |
| PICKUP_ITEM | 18 | 11,11% |
| LOOT_CONTAINER | 22 | 0,00% |
| TRANSFER_ITEM | 18 | 5,56% |
| BANDAGE | 10 | 40,00% |

Objetivo único: 39/96 = **40,63%**; composto: 0/92. Decomposição mutuamente exclusiva dos 188 pedidos executáveis: decisão errada 31, quantidade errada 29, ação/ordem errada 89, plano exato 39. Nenhum erro adicional exclusivamente de alvo quando decisão, quantidade e ações estavam corretas. Isso vale para o problema sintético de marcas, não garante seleção correta de itens reais.

### Matrizes de confusão das decisões

Linhas reais, colunas previstas, ambas na ordem EXECUTE_ACTION, REQUEST_DIALOGUE, CONTINUE_GOAL, WAIT, NO_RESPONSE, REQUEST_CLARIFICATION.

```text
Validação selecionada:
148  0  3  0  2 19
  2 71  0  0  1  6
  0  0 40  0  0  0
  0  0  0 96  0  0
  4  8  0  0 61  7
 16  0  2  0  3 67

Novo teste único:
157  0  0  0  4 27
  0 72  0  0  1  7
  0  0 38  0  0  2
  0  0  0 96  0  0
  0  9  0  0 62  9
 14  0  1  0  6 67
```

Matrizes TP/FP/FN/TN de todas as intenções, por conjunto, estão em `result.json` e nos manifests de cada experimento.

### Exemplos reais de erros desta passagem

- “Carlos e Tânia, estacione onde está”: esperado EXECUTE_ACTION/STOP; previsto REQUEST_CLARIFICATION, sem objetivo, confiança 0,6497.
- “Luísa, cola em mim no trajeto”: esperado FOLLOW_PLAYER; previsto EXECUTE_ACTION com lista vazia, confiança 0,5407. A proposta é inválida e não seria executada.
- “Beto, chegue devagar ao lugar Use os alvos com marca vermelha.”: esperado WALK; previsto SNEAK, confiança 0. O destino existe para a ação prevista, mas a ação não corresponde ao pedido.
- “Carlos, primeiro estacione onde está; depois faça a abertura da porta destravada Use os alvos com marca vermelha.”: esperado STOP → OPEN_DOOR; previsto OPEN_DOOR → SNEAK, confiança 0,5888. A ordem/ação é incorreta, apesar de o alvo da porta corresponder ao candidato observado.

Os textos acima são do corpus sintético, não logs de jogadores. Nenhum erro foi corrigido nos rótulos após consultar o novo teste.

## Confiança e desempenho CPU

Confiança não calibrada, limiar original 0,80 preservado. Teste: média 0,76887; 291 previsões de alta confiança, acurácia de decisão **95,53%** nesse subconjunto. Isso mede a classe de decisão, não sucesso do plano. Ao contrário da v1, a cobertura não contém somente WAIT: WAIT=96, EXECUTE_ACTION=54, REQUEST_DIALOGUE=38, NO_RESPONSE=33, CONTINUE_GOAL=30, REQUEST_CLARIFICATION=40. Não transformar essa cobertura em certificação de segurança.

Benchmark isolado após a regressão inicial, somente 30 observações da validação, duas threads CPU, encoder carregado localmente. Não houve nova inferência de teste.

| Custo | Média | P95 |
| --- | ---: | ---: |
| Cabeça + decode com tensores prontos | 0,571 ms | 0,621 ms |
| Completa, cache textual frio | 196,699 ms | 203,883 ms |
| Completa, cache textual aquecido | 1,481 ms | 1,622 ms |

Carregamento: 5,352 s. RSS após benchmark 1.206.312.960 bytes (~1,12 GiB); pico do processo 1.213.960.192 bytes (~1,13 GiB). O custo quente inclui compactação/tokenização, portanto é maior que na v1. Na v1 o custo frio era 185 ms e quente 0,68 ms em outro corpus. Não há prova de tempo real dentro do jogo; não inclui IPC, Lua ou Ollama.

## Artefatos, arquivos e reprodução

Raiz experimental: `ai/neural_artifacts/3c5b2/`.

- `baseline/` e `balanced_sequence/`: pesos, manifest versionado, histórico de validação, predições de validação. Cada manifest informa zero avaliações de teste para aquele experimento isolado.
- `protocol-before-training.json`: configurações, código e gates congelados antes dos experimentos.
- `selection-frozen-before-test.json`: escolha e hash congelados, antes de consultar teste; seu contador zero é o registro daquele instante.
- `result.json`: resultado final v2, `validated=false`, **test_evaluations=1**, métricas, gates e falhas; `game_integrated=false`.
- `test-predictions.json`, `diagnostics.json`, `benchmark.json`: passagem única preservada e análises sem inferência adicional de teste.

Checkpoint selecionado experimental: `ai/neural_artifacts/3c5b2/baseline/weights.pt`.
SHA256: `1b0e9f652d6ce0a42f64e75e6b2b4957c6088435cbb2361ee0d7760719edfe9a`.

Criados: `ai/neural_data_v2.py`, `ai/neural_inputs_v2.py`, `ai/train_neural_v2.py`, `ai/benchmark_neural_v2.py`, `ai/analyze_neural_v2.py`, `ai/test_neural_v2.py`, corpus v2, evidências em `ai/neural_experiments_v2/`, artefatos e este relatório. Nenhum código v1/produtivo foi alterado. Checkpoints e ambiente continuam ignorados pelo Git. Os manifests v2 experimentais não são promovidos pelo carregador v1.

Comando executado, em modo offline:

```powershell
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
& ./.venv-neural/Scripts/python.exe -B ai/train_neural_v2.py --encoder-path ai/neural_models/paraphrase-multilingual-MiniLM-L12-v2/e8f8c211226b894fcb81acc59f3b34ba3efd5f42
```

O trainer recusa sobrescrever a raiz já existente. Não apagar os artefatos para tentar obter outro resultado no mesmo teste. A preparação do corpus também recusa sobrescrita. Os hashes finais de fontes, corpus e resultados estão em `ai/neural_experiments_v2/integrity.json`.

## Testes e segurança

Regressão inicial: **980 testes aprovados**. Após acrescentar proteção dos gates minoritários e teste real de compactação/tokenização com MiniLM, regressão final: **982 aprovados, 0 pulados, 0 falhas**. JUnit e duração exata estão em `ai/neural_experiments_v2/regression.xml`.

Testes novos cobrem partições/famílias, pares inversos na mesma partição, rejeição de vazamento, rótulos/guardas, suporte minoritário, ordem/candidato/target_id após reordenação, compactação sem alterar fonte ou números, preservação byte a byte da 3C.5B.1, prioridades e ações UNSUPPORTED. O teste de logits de referência é explicitamente mecânico; somente os experimentos salvos medem aprendizagem.

Não há módulo v2 importado pelo pipeline ativo de chat/mailbox, Executor ou Lua. Destinatário obrigatório, UUID/mundo/sessão, revalidação de candidatos, prioridades e bloqueio de PUSH_ZOMBIE/CLIMB_STAIRS permanecem nos contratos existentes. Nenhuma previsão foi despachada como ação. Ollama não foi chamado; não participa da seleção neural. Não houve jogo/serviços, alteração de saves/SQLite real/JARs/executáveis/FBO/câmera/controles/balões/modelo Ollama, nem commit/push. RL não implementado.

## Conclusão técnica

Houve progresso verificável em decisões e detecção de classes raras, mas a parte central de composição de ações permanece insuficiente. A tentativa de balancear perdas e reduzir a diferença treino/inferência não resolveu isso nesta arquitetura/corpus. Não há evidência de que um simples ajuste de índice ou aumento de parâmetros resolveria o problema.

Para futura iteração, será necessário planejar separadamente corpus com maior diversidade autoral, balanceamento efetivo de decisões e cenários físicos, diagnóstico por slot e representação de ordem linguística. Essas são hipóteses para novo experimento, não correções já validadas. O teste v2 agora está consumido: qualquer nova seleção após esta análise exige **outro conjunto inédito**, congelado antes do próximo treino. Não reutilizar os testes v1/v2 para escolher hiperparâmetros ou relaxar gates.

Estado final: rede implementada e treinada offline; **não validada; não integrada ao jogo**. Aguardar instruções, sem iniciar 3C.5C.
