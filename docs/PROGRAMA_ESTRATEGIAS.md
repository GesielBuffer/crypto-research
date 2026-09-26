# Programa de estrategias

Data da revisao: 2026-09-26

## Mudanca de abordagem

O projeto deixa de procurar uma unica regra tecnica vencedora e passa a
pesquisar um conjunto pequeno de premissas economicas independentes. Uma fonte
publicada nao e prova de rentabilidade local; ela serve como prior para uma
hipotese que ainda precisa sobreviver aos nossos dados, custos, ativos, splits e
holdout.

O historico completo de tentativas sera contado. Resultado negativo nao autoriza
ajustar a mesma familia ate ela passar. A selecao futura deve incorporar
correcao por multiplos testes, Deflated Sharpe Ratio e probabilidade de
overfitting sempre que houver retornos de portfolio suficientes.

## Motores priorizados

### 1. Carry delta-neutro spot/perpetuo

Comprar spot e vender o perpetuo quando somente informacao de funding ja
liquidado indicar carry positivo. O retorno inclui as duas pernas, funding
realmente recebido, variacao da base, taxas e slippage. A primeira versao nao
opera funding negativo porque isso exigiria emprestimo e venda a descoberto do
spot. E a prioridade imediata porque usa uma transferencia economica explicita
e reduz exposicao direcional.

Dados locais prontos: spot, perpetuo, funding, premium, mark e index para BTC,
ETH, BNB e SOL.

O primeiro protocolo, `DELTA_NEUTRAL_CARRY_V1`, confirmou carry liquido no
desenvolvimento, mas falhou por quebra de regime: o limiar anualizado absoluto
de 10% produziu apenas cinco operacoes na validacao e nenhuma na confirmacao.
A mediana movel de funding anualizado caiu de 8,58% em 2024 para 3,00% em 2025
e 1,05% em 2026. O V2 testou o estado relativo, com percentil calculado apenas
em observacoes anteriores, mas nenhum dos quatro conjuntos passou. A melhora
de 2024 nao persistiu em 2025/2026; o holdout de setembro permaneceu fechado.
O resultado encerra esta iteracao de carry em vez de iniciar novo ajuste de
limiar sobre os mesmos dados.

### 2. Momentum transversal em universo ampliado — proxima familia

Classificar um universo liquido de perpetuos, comprar vencedores e vender
perdedores com neutralizacao de beta e volatilidade. Quatro ativos sao
insuficientes para uma ordenacao transversal robusta; antes do teste, o universo
deve ser ampliado por regra de liquidez definida sem olhar retornos futuros.

O protocolo `CROSS_SECTIONAL_MOMENTUM_V1` foi congelado antes da aquisicao dos
novos dados. Ele parte de 24 contratos maduros, seleciona 16 apenas pela liquidez
de janeiro a marco de 2024 e testa quatro combinacoes de lookback/rebalance. A
carteira e long/short, com exposicao bruta simetrica, pesos por volatilidade e
custo aplicado ao turnover real.

Resultado: `FAIL_DISCOVERY`. O melhor perfil temporal foi lookback de 28 dias
com rebalance diario, mas os PFs de 1,108 / 1,093 / 1,052 ficaram abaixo dos
gates em desenvolvimento, validacao e confirmacao, e o drawdown agregado foi
17,7%. Nenhuma configuracao foi congelada e setembro nao foi aberto.

### 3. Trend following lento e multivelocidade

Combinar sinais de semanas, nao breakouts horarios, com dimensionamento por
volatilidade e diversificacao transversal. O breakout horario reprovado nao
invalida momentum de 1 a 8 semanas, que e uma familia economicamente e
estatisticamente diferente. O baseline sem sinal e com a mesma volatilidade sera
obrigatorio, pois parte do resultado atribuido a trend pode vir do volatility
scaling.

O protocolo `SLOW_TREND_V1` reutiliza o universo de 16 ativos congelado por
liquidez antes de seus retornos serem avaliados. Quatro conjuntos de velocidades
entre 1 e 12 semanas serao comparados, com rebalance diario, pesos por
volatilidade, limite por ativo e custo sobre o turnover efetivo.

Resultado: `FAIL_DISCOVERY`. Nenhum conjunto passou os tres periodos; os
drawdowns agregados ficaram entre 43,9% e 61,4%, contra limite de 15%. Setembro
permaneceu fechado e a familia nao foi ajustada depois do resultado.

### 4. Valor relativo residual

Remover o fator comum de mercado e negociar apenas desvios residuais entre
ativos cointegrados ou exposicoes spot/perpetuo. A composicao dos pares deve ser
formada somente no treino e testada em walk-forward. Redes neurais e
reinforcement learning nao entram antes de um baseline linear superar custos.

O protocolo `RESIDUAL_VALUE_V1` usa um baseline linear auditavel: beta movel
sem intercepto contra BTC, residual acumulado de 1 ou 3 dias e carteira
long/short dos quartis extremos. As janelas e gates foram congelados antes da
execucao.

Resultado: `FAIL_DISCOVERY`. A reversao apareceu em 2025, mas nao em 2024 nem
na confirmacao de 2026. Os drawdowns agregados ficaram entre 28,2% e 47,5%; o
holdout de setembro permaneceu fechado.

## Resultado do primeiro ciclo independente

As quatro familias priorizadas foram executadas sob protocolos congelados:
carry absoluto/adaptativo, momentum transversal, trend lento e valor residual.
Nenhuma passou todos os gates. A conclusao operacional permanece objetiva:
nao ha estrategia autorizada para paper trading ou capital real. O proximo
ciclo deve atacar as falhas observadas com uma hipotese nova e pre-registrada,
sem retirar ativos, inverter sinais ou relaxar gates depois dos resultados.

A auditoria em `docs/AUDITORIA_CRITERIOS.md` separou, prospectivamente,
continuidade de pesquisa e promocao. O segundo ciclo comeca por
`CROSS_SECTIONAL_FUNDING_CARRY_V1`: long nos contratos de menor funding e short
nos de maior funding, com preco, funding e turnover contabilizados em carteira
equilibrada. O protocolo foi congelado antes da aquisicao do funding ampliado.

Resultado V1: `RESEARCH_CANDIDATE`. Tres dos quatro conjuntos passaram o nivel
de continuidade cientifica e nenhum passou `HOLDOUT_READY`. O conjunto 3/3 teve
PF-base 1,121 / 1,320 / 1,138, PF agregado 1,205 e drawdown de 14,5%, mas falhou
no custo de estresse da confirmacao e teve somente 8 ativos positivos. Setembro
permaneceu fechado.

## Arquitetura final pretendida

Os motores aprovados nao serao somados por retorno historico maximo. O portfolio
usara risco aproximadamente igual por motor, limite de volatilidade, teto por
ativo, controle de correlacao, perda diaria e kill switch. Um regime pode reduzir
risco, mas nunca transformar uma estrategia reprovada em aprovada.

## O que nao sera pesquisado agora

- martingale, grid sem stop ou aumento de posicao apos perda;
- indicadores combinados sem mecanismo economico;
- market making sem livro de ofertas, fila, latencia e modelo de adverse selection;
- aprendizado por reforco antes de baselines simples e auditaveis;
- selecao de parametros usando agosto ou setembro de 2026;
- estrategias cuja vantagem desaparece antes de taxas e slippage realistas.

## Fontes primarias e profissionais

- Liu e Tsyvinski, *Risks and Returns of Cryptocurrency*: momentum temporal e
  atencao como preditores especificos de cripto:
  https://www.nber.org/papers/w24877
- Liu, Tsyvinski e Wu, *Common Risk Factors in Cryptocurrency*: fatores de
  mercado, tamanho e momentum transversal:
  https://www.nber.org/papers/w25882
- Moskowitz, Ooi e Pedersen, *Time Series Momentum*:
  https://doi.org/10.1016/j.jfineco.2011.11.003
- Hurst, Ooi e Pedersen, *A Century of Evidence on Trend-Following Investing*:
  https://www.aqr.com/insights/research/journal-article/a-century-of-evidence-on-trend-following-investing
- Kim, Tse e Wald, *Time Series Momentum and Volatility Scaling*: alerta de que
  parte do alpha atribuido a trend pode vir do escalonamento de volatilidade:
  https://doi.org/10.1016/j.finmar.2016.05.003
- Schmeling, Schrimpf e Todorov, *Crypto Carry*:
  https://doi.org/10.1287/mnsc.2024.05069
- Ackerer, Hugonnier e Jermann, *Perpetual Futures Pricing*:
  https://doi.org/10.2139/ssrn.4603820
- Bailey e Lopez de Prado, *The Deflated Sharpe Ratio*:
  https://doi.org/10.2139/ssrn.2460551
- Bailey, Borwein, Lopez de Prado e Zhu, *The Probability of Backtest
  Overfitting*:
  https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf
- Documentacao oficial Binance sobre funding, mark e index:
  https://developers.binance.com/docs/derivatives/coin-margined-futures/market-data/rest-api/Get-Funding-Info

As fontes incluem resultados favoraveis e criticas. Essa oposicao e
intencional: o projeto deve testar o mecanismo e tambem a explicacao alternativa.
