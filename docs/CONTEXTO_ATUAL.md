# Indice de contexto do projeto

Atualizado em: 2026-10-02
Branch operacional: `main`  
Ultimo estado consolidado: replicacao cross-exchange concluida

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
- Suite atual: 151 testes unitarios aprovados; `pip check` sem conflitos.
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
- Fechamento calendario `[2026-09-01, 2026-10-01)`: 29 periodos, PF 0,941
  base, PF 0,880 stress, media liquida negativa e drawdown 5,51%. Os quatro
  periodos adicionais tiveram PF 0,452 base e reforcaram o `FAIL`.
- Setembro foi aberto uma vez e nunca pode voltar a ser tratado como holdout.
- Relatorio canonico:
  `results/cross_sectional_funding_carry_v3_decision.json`.
- SHA-256 canonico:
  `44c81b89807494794689a27c7f4ababfb14591118e7a4ceb2cf8ffc6081f9480`.

### Replicacao externa posterior

- A V3 foi transferida sem alteracoes para Bybit e OKX em dados publicos de
  janeiro de 2024 a setembro de 2026.
- Bybit: 912 periodos, PF 1,325 base / 1,198 stress, drawdown 10,72%.
- OKX: 912 periodos, PF 1,336 base / 1,207 stress, drawdown 13,02%.
- As duas venues passaram os gates anuais e agregados: `REPLICATION_CONFIRMED`.
- Isso e evidencia independente de venue, nao um holdout temporal futuro; nao
  apaga setembro e ainda nao libera paper, Testnet promocional ou capital real.
- Relatorio: `results/cross_exchange_funding_replication_v1_decision.json`.
- SHA-256: `ecf3201f37e92a33720efc3b25a8d674cefd8591e960c881c6eeeddfa5c8773d`.

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
- Replicacao Bybit/OKX da regra V3: `REPLICATION_CONFIRMED`.

Detalhes e contagem de configuracoes: `experiments/TRIAL_LEDGER.md`.

## Proximo passo correto

Nao retunar Binance, Bybit ou OKX. Como a replicacao independente passou, o
proximo ciclo deve congelar a mesma regra para um holdout temporal futuro nas
tres venues. O periodo precisa comecar depois do registro, acumular a amostra
minima e ser aberto uma unica vez. Enquanto isso, engenharia e ensaios locais
podem avancar, mas paper promocional e capital real continuam bloqueados.

O protocolo V4 ja esta congelado em
`experiments/cross_venue_funding_holdout_v4.toml`: periodo
`[2026-10-03, 2026-11-03)`, minimo de 24 periodos por venue, Binance obrigatoria
e aprovacao de pelo menos duas das tres venues. Ele permanece `UNOPENED` e nao
pode ser consultado antes de 3 de novembro de 2026.

O observador `execution.shadow_funding` ja acompanha a regra V4 com endpoints
publicos, preserva a histerese em `runtime/` e produz pesos-alvo auditaveis. Ele
nao possui caminho de envio de ordem e declara `DISABLED_BY_DESIGN`.

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
- Fechamento mensal: `results/september_2026_month_close.json`.
- Manifesto cross-exchange: `manifests/cross_exchange_funding_replication_v1.json`.
- Decisao cross-exchange: `results/cross_exchange_funding_replication_v1_decision.json`.

## Regra de continuidade

Ao retomar, conferir `git status`, ler este indice e continuar do proximo passo
registrado. Nao repetir experimentos concluidos, nao apagar resultados negativos
e nao promover uma estrategia apenas porque ela foi positiva em subconjuntos.
