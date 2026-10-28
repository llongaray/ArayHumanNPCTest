# 3C.5B — rede neural de interpretação e decisão

## Estado real da entrega

| Etapa | Situação |
|---|---|
| Arquitetura neural implementada | Código PyTorch real: camadas treináveis, múltiplas cabeças, decodificador GRU e ponteiro de candidatos. A execução numérica ainda não foi testada neste ambiente. |
| Dados supervisionados preparados | Sim: 243 treino, 162 validação, 162 teste; 168 famílias de frases. |
| Rede treinada | **Não. PyTorch/codificador ausentes; instalação e download dependem de autorização explícita.** |
| Rede validada estatisticamente | **Não. Não há checkpoint, acurácia neural ou matriz de confusão medida.** |
| Rede integrada ao jogo | **Não. Runtime offline/desativado e adaptador de pedidos preparados; pipeline atual preservado.** |

O comando de treinamento foi invocado e retornou `UNAVAILABLE/dependencies_unavailable`, `trained=false`, `validated=false`, `metrics=null`, sem criar pesos ou métricas fictícias. A fase não deve ser anunciada como concluída em treinamento/validação.

Regressão: **960 testes aprovados e 1 pulado** — os 914 anteriores, 46 regressões novas aprovadas e um teste numérico condicionado à disponibilidade do PyTorch. O teste pulado mede gradientes/formas do tensor/atualização de pesos; não é um benchmark de interpretação semântica.

## Infraestrutura e proposta de dependências

Ambiente auditado: Python 3.11.9 de 64 bits (`C:/Users/llongaray/AppData/Local/Programs/Python/Python311/python.exe`), Ryzen 7 5700X (8 núcleos/16 threads), 31,89 GiB de RAM total; aproximadamente 18,64 GiB livres no momento da inspeção. Não foram encontrados torch, sentence_transformers, transformers, numpy ou onnxruntime nesse runtime. Caches padrão Hugging Face/Torch consultados estavam ausentes. Isso não representa uma busca de todos os discos.

Proposta: PyTorch **CPU**, NumPy, SentenceTransformers e suas dependências em ambiente virtual separado; manter o Python/launcher atual até validação. Não são necessários torchvision, torchaudio, CUDA, Ollama como encoder ou mudança do modelo Ollama. A instalação CPU deve seguir o índice/seleção da [documentação oficial PyTorch](https://pytorch.org/get-started/locally/). Versões resolvidas deverão ser registradas após a instalação autorizada; ainda não existe um ambiente de ML homologado ou lock verificado.

Codificador proposto: [sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2), multilíngue, 384 dimensões, limite anunciado de 128 tokens e licença Apache-2.0. O [repositório oficial](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2/tree/main) lista `model.safetensors` de aproximadamente 471 MB, além dos arquivos de configuração/tokenização. Não é necessário baixar todas as variantes ONNX/OpenVINO/TensorFlow do repositório. A revisão precisa ser fixada antes de um download autorizado.

O loader implementado aceita apenas **diretório local existente**, `local_files_only=True`, `trust_remote_code=False`, safetensors e `device='cpu'`, conforme a [API oficial SentenceTransformer](https://www.sbert.net/docs/package_reference/sentence_transformer/model.html). Não há rotina de instalação/download nem fallback para um ID remoto. Texto que exceda o orçamento em bytes ou tokens é recusado, evitando perder silenciosamente o final de uma instrução composta.

## Arquitetura neural

`NPCPolicy` é um `torch.nn.Module` real, sem lookup de frases para inferência:

1. Codificador multilíngue pré-treinado **congelado** produz representações reais de mensagem, identidade/perfil, histórico/memória e estado observado. A política aprende sobre essas representações; não há hashes linguísticos, vetores semânticos de zeros ou embeddings simulados.
2. Dezesseis atributos numéricos documentados resumem saúde/indicadores de conhecimento, ameaça, quantidade/carga, prioridades, falhas anteriores e parcialidade. São atributos observados explícitos, não um substituto do aprendizado de linguagem. Valores ausentes possuem marcadores de disponibilidade.
3. Máscara das dezesseis ações iniciais do catálogo entra na fusão. O inventário/saúde/ameaças também têm representação textual codificada, além dos escalares. Resumos são reduzidos por campos/registros inteiros, com indicação de parcialidade; o estado original não é reescrito.
4. Fusão MLP com 128 unidades, ReLU e dropout de 0,1.
5. Cabeça multilabel com seis logits: CONVERSATION, QUESTION, INSTRUCTION, ACTION_REQUEST, INFORMATION, NO_RESPONSE. A ativação sigmoid permite mais de uma intenção.
6. Cabeça de seis decisões: EXECUTE_ACTION, REQUEST_DIALOGUE, CONTINUE_GOAL, WAIT, NO_RESPONSE, REQUEST_CLARIFICATION.
7. Cabeça de quantidade de objetivos (0, 1 ou 2) e GRUCell autorregressiva com embedding da ação anterior. Cada passo prediz uma ação; a ordem é saída aprendida, não uma separação por palavras-chave.
8. Ponteiro por atenção sobre até 32 candidatos: cada candidato é representado por descrição observada codificada e tipo de ação. A saída escolhe índice; o ID real vem da observação original. Não são geradas coordenadas, nomes de itens ou objetos.

A cabeça tem aproximadamente 336 mil parâmetros pelo dimensionamento do código; o total numérico ainda será conferido com PyTorch. O custo maior é do encoder congelado. Treinamento/inferência estão limitados a CPU e duas threads do Torch. Um cache limitado a 2.048 textos evita recodificar as mesmas descrições; guarda somente vetores realmente calculados pelo encoder. Não é armazenamento compartilhado de memórias de NPCs.

Limites iniciais: dois objetivos ordenados, 32 candidatos e entradas em português de escopo supervisionado restrito. Não é um planejador aberto nem um agente geral. Frases com três ou mais objetivos e variações fora do corpus não têm competência comprovada; devem passar pelo limiar de confiança/esclarecimento, nunca por uma garantia fictícia de entendimento.

## Corpus e separação dos conjuntos

Arquivos em `ai/neural_supervised_data/` contêm observações **sintéticas de ensino**, frases PT-BR e rótulos. O campo `provenance=authored_supervised_scenario_not_game_experience` impede confundi-las com experiências do jogo. Não foram coletadas partidas, lidos saves ou usados dados pessoais externos.

- Treino: 243 registros.
- Validação: 162 registros.
- Teste: 162 registros.
- Famílias de frases: 168, separadas antes das variantes de contexto.
- SHA-256 do corpus: `ae68cfa3de01197649f584f47ac7ead465b6fc4cd98a1a7d25d0295a4dd24cf8`.

Há variantes com prioridade manual, emergência e capacidade indisponível. Toda variante de uma mesma frase permanece no mesmo conjunto; auditoria recusa frase normalizada ou família repetida entre conjuntos. Nomes mudam entre treino/validação/teste, e os textos de validação/teste são formulações não vistas no treino. Ainda são exemplos autorais da mesma distribuição; isso **não prova** generalização para mensagens livres reais, cenários/mods ou perfis diversos.

O corpus cobre as dezesseis ações declaradas na cabeça: STOP, FOLLOW_PLAYER, LOOK_AT_PLAYER, FACE_TARGET, WALK/RUN/SNEAK, portas/janelas/cerca, coleta/transferência e BANDAGE. PUSH_ZOMBIE e CLIMB_STAIRS não são classes executáveis. NAVIGATE/SAY também não são atalhos gerados pela cabeça: a fala usa REQUEST_DIALOGUE e a composição usa objetivos limitados.

Há exemplos contrastivos para bandagem versus pregos e para as duas ordens:

- “pegue a bandagem e depois me siga” → PICKUP_ITEM → FOLLOW_PLAYER.
- “me siga e depois pegue a bandagem” → FOLLOW_PLAYER → PICKUP_ITEM.

Esses são **rótulos de supervisão**, não resultados já reconhecidos pela rede. O modelo deverá demonstrar essa capacidade em treino/teste reais antes de qualquer ativação. FOLLOW_PLAYER pode ser contínuo; a continuação do segundo objetivo depende de término/interrupção confirmados do primeiro, não apenas de ter começado a seguir.

Os rótulos e cenários precisam de revisão humana e futura ampliação. Não há treino específico de preferências estratégicas por profissão/traços; esses campos estão disponíveis à arquitetura, mas sua utilização correta não foi aprendida/comprovada nesta entrega.

## Treinamento supervisionado e métricas

`train_neural.py` implementa treinamento offline com AdamW, learning rate 0,002, weight decay 0,01, batch 32, gradient clipping 1, seed 1729 e 100 épocas por padrão. Pode-se definir entre 1 e 1.000 épocas. A perda combina BCE para intenções, entropia cruzada para decisão/quantidade/ações e perda de ponteiro para candidatos rotulados. Teacher forcing é usado no treino; avaliação é autorregressiva.

O trainer lê os JSONL exportados, verifica o digest e a separação dos conjuntos, codifica os textos reais com o encoder local e treina apenas a cabeça. Seleciona pesos pela validação; o teste é avaliado ao final, sem escolher épocas a partir dele.

Métricas implementadas, **ainda não medidas**:

- exatidão do conjunto de intenções e TP/FP/FN/TN por intenção;
- acurácia e matriz de confusão das seis decisões;
- exatidão dos objetivos ordenados, incluindo escolha do alvo;
- exatidão específica dos casos de dois objetivos;
- proporção de decisões de execução inválidas **antes** dos guardas;
- cobertura do limiar de confiança de 0,80.

Não se anuncia “0% de decisões inválidas” como desempenho de aprendizado apenas porque o Executor bloqueia a execução. A taxa medida no teste será da proposta bruta; os guardas permanecem uma camada de segurança separada.

Gates iniciais, deliberadamente explícitos e ainda sem resultado: cada conjunto de validação/teste deve ter pelo menos 20 amostras, intenção exata ≥0,80, decisão ≥0,85, objetivos ordenados ≥0,80, pelo menos quatro casos de dois objetivos com exatidão ≥0,80, taxa bruta inválida zero e cobertura ≥0,50. São critérios de engenharia sobre corpus pequeno, não prova estatística de segurança no jogo. A confiança é derivada das probabilidades das cabeças/ponteiro, sem calibração empírica comprovada; não deve ser descrita como probabilidade garantida de acerto.

Comando preparado, para **depois** da instalação/download autorizados e escolha de um novo diretório de execução:

```text
<python-do-ambiente-neural> -B ai/train_neural.py --encoder-path <diretorio-local-do-MiniLM> --output-dir ai/neural_artifacts/3c5b-initial --epochs 100
```

O destino precisa ser novo e estar dentro de `ai/neural_artifacts/`; não há sobrescrita de checkpoint aprovado. O trainer produz pesos, manifest, métricas e cópia do corpus usado. A execução atual, sem dependências, retornou somente indisponibilidade e não criou esse diretório.

## Checkpoints e ativação

`NeuralPolicy` inicia com `enabled=False`. Um caminho explicitamente habilitado exige manifest v1, arquitetura/dimensões/ordem de classes compatíveis, métricas que passem os gates, checkpoint com hash correspondente e fingerprint do encoder local. Tensor loading usa CPU, `weights_only=True` e `strict=True`. Arquivo ausente, corrompido, não validado, incompatível, sem dependências ou sem encoder produz `UNAVAILABLE/NO_RESPONSE`, sem ação.

Os hashes aqui servem somente à integridade de arquivos e correlação de IDs; **não** codificam significado nem são apresentados como embeddings/aprendizado.

Não existe checkpoint real neste workspace. Nenhum JSON de testes é um checkpoint neural ou comprovação de métricas; testes usam sentinelas claramente identificadas apenas para conferir rejeições de metadata/integridade. O teste numérico foi pulado por ausência de Torch.

## Segurança e ligação preparada

`compose_observation` combina o estado neural da 3C.5A com AgentState do mesmo UUID/mundo, acrescentando observation_id, controles atuais e candidatos. `check_observation` exige sessão, UUID canônico, mundo, roteamento explícito, snapshot de até 1.500 ms, prazo, orçamento de 32 KiB, candidatos vinculados à mesma observação e controles conhecidos. Identidade/memória de outro NPC é recusada quando os registros carregam o vínculo correspondente; registros de conversa exigem o UUID/mundo proprietário.

O uso operacional continua confiando nos snapshots de origem Lua, não em objetos arbitrários vindos de um modelo. Nenhuma regra Python substitui a revalidação nativa do Executor.

`safe_decision` aplica guardas externos ao aprendizado:

- prioridade manual ou emergência resulta em WAIT e nenhum objetivo executável;
- confiança baixa/inválida resulta em esclarecimento sem ações;
- ação indisponível/UNSUPPORTED, campo extra como código/coordenadas, alvo inventado ou candidato vencido é recusado;
- candidatos precisam de descrição observada para fundamentação semântica. **O AgentState atual nem sempre fornece essa descrição**. O adaptador preserva a ausência e exige esclarecimento; não inventa metadados para habilitar uma coleta/travessia;
- outputs do Ollama não entram em `predict`, `safe_decision` ou `prepare_dispatch` como comandos.

`prepare_dispatch` gera um pedido compatível com `Capabilities.request` (`origin=neural`, prioridade 0, UUID/mundo/observação/ID/prazo) somente para o **primeiro** objetivo. Objetivos restantes ficam como continuação pendente, exigindo resultado real e observação nova. CONTINUE_GOAL retorna referência à ação atual, sem iniciar outra caminhada. REQUEST_DIALOGUE prepara apenas uma solicitação verbal para a camada de conversa. O adaptador não chama Executor nem Ollama.

Não foi adicionado endpoint, OnTick, scheduler ou flag de ativação no serviço atual. A gramática fixa da 3C.5A e o caminho temporário de conversa permanecem até haver checkpoint validado e uma integração posterior deliberada. O antigo handler de decisões Ollama foi preservado por compatibilidade; a nova política não o consulta nem o usa como fallback de ações.

## Interface para RL futuro

`transition` prepara registro v1 com observação anterior, decisão, ação realmente executada, resultado, próxima observação e estado terminal. Exige o mesmo UUID/mundo/sessão, ordem temporal não regressiva e correspondência do ID/tipo da ação executada com o resultado/primeiro objetivo. O chamador futuro deverá vincular a sessão ao resultado real pelo ID do pedido; metadados não devem ser adivinhados.

Não há campo de recompensa, atualização de pesos online, replay buffer de RL, penalidade de morte ou alteração de atributos. Os registros não são gravados em SQLite real. A execução real precisará alimentar essa interface futuramente; ela não é anunciada como coleta de experiência já ativa no jogo.

## Arquivos e testes

Criados:

- `ai/neural_contract.py`: contratos, atributos, guardas, despacho preparado e transições.
- `ai/neural_model.py`: rede PyTorch treinável.
- `ai/neural_encoder.py`: encoder CPU estritamente local e cache limitado.
- `ai/neural_runtime.py`: composição de observações, tensores, inferência, checkpoints e estado indisponível.
- `ai/neural_data.py`: cenários/rotulagem explícita, separação/auditoria/carregamento do corpus.
- `ai/train_neural.py`: treinamento e avaliação offline.
- `ai/neural_supervised_data/{train,validation,test}.jsonl` e `manifest.json`: dados autorais e proveniência/digest.
- `ai/test_neural_policy.py`: testes de contratos e teste numérico condicional.
- Este relatório.

Nenhum arquivo de produção anterior foi modificado para ativar a rede. Regressão executada com `python -B -m pytest ai -q -p no:cacheprovider --tb=short`, usando runtime Lupa temporário no PYTHONPATH. Resultado final: **960 passed, 1 skipped**.

Os testes novos cobrem corpus sem vazamento, ordem de objetivos rotulados, plano com apenas a primeira ação, baixa confiança, prioridades, destinos/código/coordenadas inválidos, capacidades indisponíveis, nome/destinatário ausente, UUID/mundo/sessão/observação incorretos, expiração, memória privada, checkpoints rejeitados e transições sem recompensas. Esses testes comprovam contratos/segurança de código, **não** acurácia da rede.

## Próximo passo que exige autorização

Para treinar e medir de verdade, é necessária autorização para instalar PyTorch CPU/SentenceTransformers/NumPy e dependências em ambiente separado, além de baixar os arquivos estritamente necessários do MiniLM. Não alterará o modelo Ollama. Essa autorização é exigida pela restrição do usuário: “Não instalar pacotes nem baixar pesos sem autorização explícita”. Nenhuma autorização foi presumida.

Após autorização: instalar e registrar versões/revisão/licenças, executar o teste numérico, treinamento, validação/teste e revisão das matrizes/erros. Se os gates falharem, o checkpoint continua não validado/desativado; não haverá ativação automática nem declaração de êxito. Teste manual no jogo permanece uma etapa distinta e não foi autorizado/iniciado nesta entrega. Não avançar à 3C.5C.
