# Triagem de candidatas em 2026-09-13

## Decisao

Nenhum resultado historico existente atende aos requisitos para congelamento.
Esta triagem usa apenas relatorios ja produzidos. Ela nao reabre agosto como
conjunto de desenvolvimento e nao altera parametros.

| Hipotese | Evidencia favoravel | Falha decisiva | Decisao |
|---|---|---|---|
| C2 / fresh impulse | PF 1,170 no desenvolvimento a 0,06% | PF 0,714 no holdout de agosto | rejeitar |
| low24h reversal 60m | 8.899 amostras e PF global 1,110 | PF abaixo de 1 em 2025 e 2026; IC bootstrap inclui 1 | rejeitar |
| ATR contracting short | PF mediano 1,028 a 0,06% | somente 50% das janelas positivas; julho PF 0,220 | rejeitar |
| medium trend event V1 | grade pre-registrada, tres splits e 16 conjuntos | melhor minimo entre splits foi PF 0,899 a 0,06% | rejeitar |
| hourly breakout V1 | baixo giro, stop ATR, tres splits e custos ate 0,14% | melhor minimo foi PF 0,995 a 0,06%; validacao e estresse falharam | rejeitar |

## Consequencia para o plano

O prazo de congelamento continua em 2026-09-18, mas uma nova familia deve ser
avaliada no periodo de desenvolvimento anterior a agosto. Ajustar filtros das
tres hipoteses acima para reparar os meses ruins seria tuning retrospectivo e
nao produz uma candidata nova confiavel.

As proximas familias devem privilegiar menor giro e vantagem maior que o custo,
com criterios registrados antes da execucao. Se nenhuma passar ate 18 de
setembro, a decisao correta e NO-GO antecipado e o holdout nao comeca.

## Execucao da nova familia

`MEDIUM_TREND_EVENT_V1` foi registrada no Git antes do calculo e executada sem
alteracao da grade. Nenhum dos 16 conjuntos passou. O conjunto menos fraco
(EMA 24/192, ADX 20, hold 96 barras) apresentou PF 0,900 no desenvolvimento,
0,899 na validacao e 0,982 na confirmacao, todos com custo de 0,06%. A familia
foi encerrada sem tuning adicional.

`HOURLY_BREAKOUT_V1` tambem foi registrada e versionada antes do calculo. Os
oito conjuntos falharam sem que setembro de 2026 fosse lido. A familia foi
encerrada; seus resultados negativos permanecem versionados como evidencia.
