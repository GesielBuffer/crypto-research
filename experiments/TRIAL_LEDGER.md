# Ledger de familias testadas

Este arquivo conta tentativas, inclusive resultados negativos. Variantes dentro
de uma familia e estudos de politica de saida tambem permanecem registrados para
que a selecao futura nao trate o melhor backtest como uma descoberta isolada.

| Familia | Conjuntos | Decisao | Papel |
|---|---:|---|---|
| C2 / fresh impulse | historico legado | FAIL no holdout | direcional curto prazo |
| MEDIUM_TREND_EVENT_V1 | 16 | FAIL | tendencia media |
| C2_EXIT_POLICY_V1 | 8 | FAIL | politica de saida; nao e alpha independente |
| HOURLY_BREAKOUT_V1 | 8 | FAIL | breakout horario |
| DELTA_NEUTRAL_CARRY_V1 | 4 | FAIL: quebra de regime e amostra OOS insuficiente | carry estrutural delta-neutro |
| ADAPTIVE_CARRY_V2 | 4 | FAIL_DISCOVERY: nenhum conjunto passou 2024/2025/2026 | carry relativo; holdout de setembro permaneceu fechado |
| CROSS_SECTIONAL_MOMENTUM_V1 | 4 | PREREGISTERED | momentum relativo em universo ampliado |

O numero total de configuracoes e familias sera usado nas correcoes de selecao
quando houver uma candidata com serie de retornos de portfolio suficiente.

O V1 de carry mostrou edge no desenvolvimento, mas o limiar absoluto deixou de
gerar amostra: a mediana anualizada da media movel de 21 fundings caiu de 8,58%
em 2024 para 3,00% em 2025 e 1,05% em 2026. Esse diagnostico autoriza pesquisar
uma familia adaptativa nova; nao autoriza reduzir retroativamente o limiar do V1.

O V2 adaptativo tambem foi encerrado antes do holdout. Os quatro conjuntos
falharam: o desempenho positivo de 2024 nao persistiu em 2025 e 2026, inclusive
no custo-base. BNB concentrou perdas, mas sua exclusao seria uma selecao
pos-resultado e nao foi usada para promover ou reabrir a familia.
