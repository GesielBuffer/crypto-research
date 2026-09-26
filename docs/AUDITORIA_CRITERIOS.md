# Auditoria dos criterios de avaliacao

Data: 2026-09-26

## Conclusao

Os criterios existentes nao sao incorretos para promocao de capital, mas o
rotulo binario `PASS/FAIL` perde informacao cientifica. Ele mistura duas
perguntas diferentes:

1. a estrategia esta pronta para consumir um holdout e possivelmente operar?;
2. a hipotese mostrou evidencia suficiente para merecer uma proxima versao?

O projeto passa a responder essas perguntas separadamente. Resultados antigos
nao serao recalculados para transforma-los retroativamente em aprovados.

## Diagnostico dos resultados recentes

- `CROSS_SECTIONAL_MOMENTUM_V1`, 28 dias/diario: PF 1,108 no desenvolvimento,
  1,093 na validacao e 1,052 na confirmacao. Foi uma reprovacao marginal nos
  PFs, mas o drawdown agregado de 17,7% tambem excedeu o gate de 15%. E uma linha
  de pesquisa promissora, nao uma estrategia aprovada.
- `SLOW_TREND_V1`: os drawdowns de 43,9% a 61,4% e PF abaixo de 1 em periodos
  relevantes caracterizam reprovacao economica, nao apenas um gate rigoroso.
- `RESIDUAL_VALUE_V1`: a reversao apareceu em 2025, mas nao em 2024/2026; os
  drawdowns de 28,2% a 47,5% confirmam instabilidade temporal.
- Carry V1/V2: a queda estrutural do funding e a ausencia de amostra/retorno em
  2025/2026 invalidaram os sinais absolutos e relativos testados.

## Nova taxonomia prospectiva

### `REJECT`

Evidencia contraria ao mecanismo: PF abaixo de 1 em mais de um split, retorno
liquido negativo persistente, amplitude insuficiente ou risco muito acima do
limite. A familia e encerrada, salvo hipotese economicamente diferente.

### `RESEARCH_CANDIDATE`

Nenhum split pode ter PF-base abaixo de 1; o PF agregado deve ser pelo menos
1,08, drawdown no maximo 20%, amplitude minima de metade do universo e amostra
suficiente. Autoriza diagnostico e uma nova versao pre-registrada. Nao autoriza
abrir holdout, paper trading ou ordens.

### `HOLDOUT_READY`

Mantem o gate conservador: PF-base minimo de 1,10 em cada split, PF de estresse
minimo de 1 em cada split, drawdown maximo de 15%, amplitude minima de 10 dos 16
ativos e amostra suficiente. Somente uma configuracao congelada nesse nivel
pode consumir setembro.

### Promocao posterior

Mesmo `HOLDOUT_READY` nao aprova trading. Depois de um holdout positivo ainda
sao obrigatorios paper/shadow, Testnet, custos e funding completos, reconciliacao
operacional e autorizacao humana especifica.

## Metricas complementares

Profit factor continua util, mas nao sera usado sozinho. Os relatorios futuros
devem mostrar retorno medio e mediano, turnover, drawdown, estabilidade temporal,
amplitude por ativo e exposicao ao fator de mercado. Quando houver uma candidata,
bootstrap, Deflated Sharpe Ratio e inventario total de tentativas serao usados
antes da promocao.

O V2 de carry transversal inaugura o bootstrap em blocos como metrica adicional.
Ele reportara a probabilidade empirica de retorno medio liquido positivo, com
semente, tamanho de bloco e numero de reamostragens congelados no protocolo.
