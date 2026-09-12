# Estado da migracao

Data: 2026-09-12

## Caminho ativo consolidado

Tres experimentos sao executados por ID, com registro validado, manifesto de
dados e regressao contra resultados congelados:

- `c2_development_replay`;
- `c2_august_holdout_replay`;
- `trend_short_cost_sensitivity`.

As duas primeiras entradas reproduzem a candidata C2. A terceira substitui o
script monolitico de sensibilidade a custos e torna explicita a convencao de
retorno short usada pelo estudo original.

## Arquivo historico

Quarenta e sete scripts exploratorios foram movidos para
`experiments/legacy/`. Essa classificacao encerra sua participacao no caminho
ativo sem apagar evidencias negativas. Eles continuam versionados e podem ser
consultados, mas nao sao importados pelo runtime e nao podem promover uma
estrategia.

Uma familia arquivada so retorna ao caminho ativo mediante:

1. extracao de sinais puros para `research/`;
2. execucao pelo motor canonico;
3. registro declarativo por ID;
4. manifesto dos dados de entrada;
5. regressao contra o resultado historico;
6. hipotese e gates novos antes de qualquer dado futuro.

## Runtime operacional

O novo pacote `execution/` nao importa scripts legados nem `main.py`. Ele inclui
paper exchange, validacao central de risco, IDs idempotentes, journal append-only,
reconciliacao de submissao interrompida e kill switch.

`main.py` esta bloqueado no ponto de entrada e existe apenas como referencia do
legado. A promocao real segue os gates de `docs/PRODUCTION_READINESS.md`.
