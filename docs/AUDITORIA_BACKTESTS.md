# Auditoria dos backtests e direcao do projeto

Data da auditoria: 2026-09-11

## Estado da consolidacao em 2026-09-12

Os principais vazios identificados nesta auditoria ja comecaram a ser corrigidos:

- `research/backtest.py` passou a ser a fonte canonica para custos aditivos e simulacao de horizonte fixo com entrada em `t+1`;
- o mesmo motor agora modela stop, alvo, gaps e breakeven com uma politica
  intrabar conservadora e explicitamente testada;
- `research/signals.py` regenera os sinais congelados da C2 sem lookahead;
- `research/metrics.py` centraliza as metricas basicas;
- `experiments/registry.toml` registra os replays de desenvolvimento e holdout;
- `research/run_research.py` executa experimentos por ID, valida o registro e grava commit e checksums nos relatorios;
- `manifests/c2_candles.json` fixa origem, cobertura, tamanho, linhas e SHA-256 dos 128 caches usados pela C2;
- o holdout C2 deixou de ter duas implementacoes ativas: `test_c2_august_holdout.py` agora e apenas um ponto de entrada para o motor consolidado;
- a sensibilidade a custos trend-short tambem foi migrada e preserva explicitamente a convencao historica de retorno short;
- os demais scripts exploratorios foram isolados em `experiments/legacy/`; nenhum deles pertence ao runtime operacional ou pode promover uma estrategia;
- testes unitarios e de regressao reproduzem a C2 desde os candles publicos em cache;
- a CI valida o nucleo offline em cada push e pull request.

Essa consolidacao melhora a reprodutibilidade, mas nao altera a decisao cientifica: a C2 continua reprovada no holdout e nenhuma estrategia esta autorizada para paper trading ou producao. Permanecem como proximos marcos a migracao gradual dos demais experimentos monoliticos e um protocolo novo de holdout.

## Resposta executiva

Nem tudo o que foi feito era necessario na forma em que foi implementado.

A exploracao de hipoteses foi util: ela eliminou varias ideias que pareciam plausiveis, mas nao sobreviveram a custos e estabilidade. Porem, a criacao de dezenas de scripts independentes, cada um repetindo download, alinhamento, estatisticas, custos e relatorios, aumentou muito a superficie de erro e tornou a pesquisa dificil de reproduzir.

O projeto ainda nao possui uma estrategia aprovada para paper trading ou producao. A candidata C2 foi positiva no desenvolvimento e falhou no holdout de agosto de 2026. As familias posteriores examinadas nos resultados tambem falharam nos gates de estabilidade. Portanto, um bot real totalmente autonomo agora automatizaria uma estrategia sem edge demonstrado.

## Evidencia principal

### Candidata C2

No desenvolvimento, o resumo canonico registrou:

| Custo | Amostra | Retorno medio | Win rate | Profit factor |
|---:|---:|---:|---:|---:|
| 0,04% | 1.259 | 0,081% | 49,64% | 1,288 |
| 0,06% | 1.259 | 0,061% | 47,66% | 1,209 |
| 0,08% | 1.259 | 0,041% | 46,39% | 1,135 |

No holdout de agosto de 2026, com custo de 0,06%:

| Amostra | Retorno medio | Mediana | Win rate | Profit factor | Drawdown maximo |
|---:|---:|---:|---:|---:|---:|
| 47 | -0,080% | -0,160% | 29,79% | 0,714 | -1,71% |

Decisao gravada pelo proprio experimento: `FAIL — holdout nao confirmou o edge`.

O numero reduzido de operacoes no holdout aumenta a incerteza, mas nao autoriza ignorar o resultado. A estrategia deve ser rejeitada ou voltar a pesquisa com uma hipotese nova; nao deve ser reajustada usando agosto e apresentada novamente como se agosto ainda fosse fora da amostra.

## O que os experimentos posteriores mostram

Os arquivos de estabilidade disponiveis registram gates negativos para familias como:

- BTC lead-lag;
- compressao/expansao;
- esforco versus resultado;
- persistencia de fluxo;
- absorcao preco/fluxo;
- funding crowding;
- premium/basis;
- mark price versus index price;
- posicao no range;
- extremos em multiplos timeframes;
- session handoff;
- divergencia e lead-lag spot/futuros;
- aceleracao de tendencia;
- robustez `low24h` e `low narrow`.

Alguns arquivos globais apresentam PF acima de 1 em subconjuntos ou custos favoraveis. Isso nao contradiz os fails: o melhor recorte global, escolhido entre muitas combinacoes, sofre selecao multipla. O que importa para promocao e estabilidade predefinida por periodo e ativo, seguida de holdout intocado.

## O que foi necessario

- Separar laboratorio e bot real.
- Baixar e cachear dados historicos publicos.
- Implementar indicadores e features sem lookahead.
- Considerar entrada em `t+1`, custos e amostras nao sobrepostas.
- Avaliar multiplos ativos, anos, meses e cenarios de custo.
- Congelar uma candidata antes do holdout.
- Manter resultados negativos: eles impedem repetir ideias descartadas.
- Testar risco de execucao e sobreposicao de sinais antes de producao.

## O que foi excessivo ou precisa ser refeito

- Dezenas de `test_*.py` monoliticos repetem funcoes de HTTP, calendario, `profit_factor`, resumo, bootstrap e exportacao.
- Os arquivos com prefixo `test_` sao experimentos executaveis, nao testes automatizados com assercoes.
- O registro central agora cobre a C2; os demais experimentos ainda precisam ser migrados gradualmente.
- Muitos resultados podem ser sobrescritos pelo mesmo nome sem vinculo criptografico com codigo e dados.
- `requirements.txt` usa apenas limites minimos, prejudicando reprodutibilidade futura.
- A C2 agora possui manifesto de dados; as demais familias ainda precisam receber manifestos durante a migracao.
- O teste de muitas combinacoes nao possui controle explicito de multiple testing/false discovery.
- O simulador canonico ja cobre fees, slippage, funding, entrada defasada e sobreposicao; latencia variavel, fills parciais, lot size, tick size e liquidacao ainda nao foram incorporados.
- `backtest.py`, `signals.py`, `metrics.py` e `run_research.py` agora formam o primeiro caminho consolidado, mas a logica antiga continua duplicada nos experimentos ainda nao migrados.
- `main.py` mistura estrategia, acesso a exchange, risco e loop operacional em um unico arquivo e nao deve ser a base da nova arquitetura.
- A integracao `chatgpt_connection.py` e o pacote `openai` nao sao necessarios para o Codex desenvolver o repositorio pelo VS Code.

## Arquitetura-alvo

```text
research/
  data/          fontes, cache, schema, cobertura e checksums
  features/      transformacoes puras e testaveis
  strategies/    sinais sem conhecer exchange ou carteira
  engine/        simulador unico de execucao e portfolio
  validation/    splits temporais, walk-forward, bootstrap e gates
  reporting/     metricas e artefatos reproduziveis

execution/
  exchange/      adaptador Binance testnet/real
  orders/        maquina de estados e idempotencia
  risk/          limites, exposicao, drawdown e kill switch
  monitoring/    logs, alertas, reconciliacao e heartbeat

experiments/
  registry.yaml  hipotese, parametros, periodos e gate predefinido
  run.py         executor unico por ID

tests/
  unit/          indicadores, fees, sizing e ausencia de lookahead
  integration/   Binance testnet e falhas de rede
  regression/    resultados pequenos congelados
```

## Pipeline de promocao

Uma ideia somente avanca quando passa todas as etapas:

1. Hipotese economica escrita antes do teste.
2. Baseline simples e criterios de sucesso congelados.
3. Desenvolvimento temporal com custos realistas.
4. Robustez por ativo, regime e periodo.
5. Correcao para selecao multipla quando muitas variantes forem testadas.
6. Walk-forward com parametros escolhidos apenas no passado.
7. Novo holdout realmente intocado.
8. Paper trading com dados ao vivo e simulacao de fills.
9. Testnet com reconciliacao de ordens e falhas de rede.
10. Capital real minimo, limites rigidos e kill switch.

Falhar em qualquer etapa devolve a hipotese para pesquisa ou a encerra. O agente nao pode mudar o gate depois de ver o resultado.

## O que significa "autonomo e dinamico"

Autonomia segura nao significa permitir que o bot mude sua estrategia e opere imediatamente. O sistema pode ser dinamico em tres niveis separados:

- **Pesquisa autonoma:** propor hipoteses, executar experimentos, rejeitar fails e produzir relatorios.
- **Selecao controlada:** escolher entre estrategias previamente aprovadas conforme regime, dentro de limites congelados.
- **Execucao autonoma:** enviar e reconciliar ordens de uma estrategia ja aprovada, sem alterar sua propria politica de risco.

O sistema nunca deve promover sozinho codigo recem-gerado diretamente para dinheiro real. Pesquisa e producao precisam de repositorios/modulos, credenciais e permissoes separados.

## Proxima decisao recomendada

Parar de abrir novas branches de indicadores por enquanto. Primeiro consolidar o motor de backtest e o registro de experimentos, reproduzir a C2 e alguns fails como testes de regressao, definir um novo protocolo de holdout e somente entao retomar hipoteses novas.

O proximo marco nao e "mais um indicador". E conseguir executar qualquer experimento por ID e reproduzir, a partir do Git e de um manifesto de dados, exatamente o mesmo resultado.
