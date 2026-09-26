# Indice de contexto do projeto

Atualizado em: 2026-09-26  
Branch operacional: `main`  
Ultimo estado consolidado: commit `ce0ddbe`

Este arquivo e o ponto de entrada para retomar o projeto. Ele indexa o estado;
os documentos e resultados vinculados continuam sendo a fonte detalhada.

## Leitura obrigatoria na retomada

1. `AGENTS.md` — regras de seguranca, pesquisa e versionamento.
2. `docs/CONTEXTO_ATUAL.md` — estado e proximo passo.
3. `deployment/readiness.toml` — gates operacionais vigentes.
4. `docs/AUDITORIA_CRITERIOS.md` — interpretacao de `REJECT`,
   `RESEARCH_CANDIDATE` e `HOLDOUT_READY`.
5. `experiments/TRIAL_LEDGER.md` — inventario de todas as tentativas.
6. `docs/PROGRAMA_ESTRATEGIAS.md` — familias, fontes e conclusoes.

## Estado executivo

- Repositorio privado: `GesielBuffer/crypto-research`.
- Codigo, protocolos, manifestos e resultados pequenos estao na branch `main`.
- Dados brutos permanecem locais em `data/` e sao reproduziveis por endpoints
  publicos; nao entram no Git.
- Runtime seguro, protecao de posicao, reconciliacao, recovery, kill switch,
  paper exchange e adaptador restrito ao Binance Testnet estao implementados.
- Suite atual: 142 testes unitarios aprovados; `pip check` sem conflitos.
- Nenhuma estrategia esta aprovada para paper trading ou capital real.
- `real_trading_enabled = false`; nenhum comando deve alterar isso por inferencia.

## Ultima candidata

`CROSS_SECTIONAL_FUNDING_CARRY_V3`:

- universo: 16 perpetuos USD-M selecionados por liquidez do primeiro trimestre
  de 2024;
- sinal: long menor funding e short maior funding;
- media: 3 settlements;
- rebalance: 3 settlements;
- carteira: histerese; entrada nos quartis e saida ao cruzar a mediana;
- estrategia V3 identica a V2; somente os criterios de dependencia foram
  auditados antes da abertura do holdout.

### Evidencia ate julho de 2026

- PF desenvolvimento: 1,204 base / 1,110 stress;
- PF validacao: 1,537 base / 1,408 stress;
- PF confirmacao: 1,188 base / 1,060 stress;
- PF agregado V2: 1,339;
- drawdown agregado: 11,34%;
- bootstrap agregado positivo: 99,95%;
- leave-one-asset-out: PF minimo 1,209 e drawdown maximo 16,27%.

### Extensao e holdout

- Agosto de 2026, estresse aberto: PF 1,195 base / 1,078 stress.
- Setembro de 2026, holdout `[2026-09-01, 2026-09-26)`:
  24 periodos, PF 0,992 base, PF 0,930 stress, media liquida base negativa e
  drawdown 4,82%.
- Decisao congelada: `FAIL_HOLDOUT`.
- Setembro foi aberto uma vez e nunca pode voltar a ser tratado como holdout.
- Relatorio canonico:
  `results/cross_sectional_funding_carry_v3_decision.json`.
- SHA-256 canonico:
  `44c81b89807494794689a27c7f4ababfb14591118e7a4ceb2cf8ffc6081f9480`.

## O que a auditoria de criterios concluiu

O antigo `PASS/FAIL` binario era insuficiente para orientar pesquisa. A nova
taxonomia encontrou carry transversal promissor e impediu que um proxy ruim de
amplitude descartasse a hipotese sem diagnostico. Entretanto, depois de a
estrategia ser congelada, o holdout novo falhou. Portanto:

- havia problema de classificacao cientifica;
- nao havia justificativa para reduzir o gate de capital;
- o holdout confirmou que a estrategia ainda nao possui edge operacional
  demonstrado depois de custos.

## Familias concluidas

- C2 / fresh impulse: `FAIL_HOLDOUT`.
- Medium trend event: `FAIL`.
- Politica de breakeven C2: `FAIL`.
- Hourly breakout: `FAIL`.
- Carry delta-neutro absoluto: `FAIL` por quebra de regime/amostra.
- Carry adaptativo: `FAIL_DISCOVERY`.
- Momentum transversal: `FAIL_DISCOVERY`, com uma configuracao proxima dos gates.
- Trend lento: `FAIL_DISCOVERY` por instabilidade e drawdown.
- Valor residual: `FAIL_DISCOVERY` por instabilidade temporal.
- Carry transversal V1: `RESEARCH_CANDIDATE`.
- Carry transversal V2: rejeitado pelo protocolo original, mas originou a V3.
- Carry transversal V3: `FAIL_HOLDOUT`.

Detalhes e contagem de configuracoes: `experiments/TRIAL_LEDGER.md`.

## Proximo passo correto

Nao retunar Binance usando setembro. O proximo ciclo deve buscar evidencia
independente do mesmo mecanismo em outras venues, prioritariamente OKX e Bybit:

1. congelar regra de contratos comparaveis, custos e periodos antes do download;
2. adquirir candles e funding por endpoints publicos;
3. reproduzir primeiro a estrategia V3 sem mudancas;
4. medir persistencia cross-exchange e diferenca de microestrutura;
5. somente uma hipotese que passe dados independentes recebe novo holdout;
6. paper/Testnet continuam bloqueados ate essa aprovacao.

## Comandos seguros

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests/unit -p "test_*.py" -q
.\.venv\Scripts\python.exe -m compileall -q research execution tests
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m execution.app
```

O ultimo comando apenas mostra readiness. Nao executar `main.py`, nao habilitar
modo real e nao usar credenciais reais.

## Mapa de evidencias

- Estado operacional: `deployment/readiness.toml`.
- Readiness detalhado: `docs/PRODUCTION_READINESS.md`.
- Auditoria dos backtests: `docs/AUDITORIA_BACKTESTS.md`.
- Auditoria dos gates: `docs/AUDITORIA_CRITERIOS.md`.
- Programa e fontes: `docs/PROGRAMA_ESTRATEGIAS.md`.
- Plano operacional: `docs/PLANO_28_DIAS.md`.
- Manifesto de precos ampliado: `manifests/cross_sectional_momentum_v1.json`.
- Manifesto de funding: `manifests/cross_sectional_funding_carry_v1.json`.
- Manifesto agosto/setembro: `manifests/cross_sectional_funding_carry_v3.json`.
- Resultado final V3: `results/cross_sectional_funding_carry_v3_decision.json`.
- Robustez leave-one-out: `results/cross_sectional_funding_carry_v3_leave_one_out.csv`.

## Regra de continuidade

Ao retomar, conferir `git status`, ler este indice e continuar do proximo passo
registrado. Nao repetir experimentos concluidos, nao apagar resultados negativos
e nao promover uma estrategia apenas porque ela foi positiva em subconjuntos.
