# Crypto Research

Laboratorio quantitativo em Python para pesquisar, testar e validar estrategias de criptomoedas com dados historicos da Binance. O projeto separa deliberadamente **pesquisa** de **execucao real**:

```text
dados historicos -> indicadores/features -> hipotese -> backtest
-> custos e robustez -> validacao fora da amostra -> paper trading
-> somente entao, producao
```

> **Aviso de seguranca:** `main.py` e apenas um stub desativado; a implementacao
> legada capaz de operar Binance Futures permanece somente no historico Git.
> Nenhuma estrategia deste repositorio esta aprovada para dinheiro real.

## Estado atual

O laboratorio contem dezenas de experimentos sobre tendencia, reversao, extremos, fluxo, premium/basis, mark/index, lead-lag, regimes e robustez. A principal conclusao confirmada ate agora e negativa, mas valiosa:

- A candidata C2 apresentou PF aproximado de **1,21** no desenvolvimento, usando custo de 0,06%.
- No holdout de agosto de 2026, obteve apenas 47 operacoes, retorno medio negativo e PF aproximado de **0,71**.
- Decisao registrada: **FAIL — o holdout nao confirmou o edge**.

Isso significa que o projeto continua sendo um laboratorio de pesquisa. O volume de experimentos nao substitui validacao fora da amostra.

## Requisitos

- Python 3.14 no ambiente atual
- Git
- Conexao com a internet somente para baixar dependencias ou dados publicos

Crie o ambiente e instale as dependencias no Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

O pacote `openai` nao e necessario para os backtests nem para usar o Codex no VS Code. Ele foi separado como opcional para o utilitario legado `chatgpt_connection.py`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-openai.txt
```

No VS Code, selecione o interpretador:

```text
.venv\Scripts\python.exe
```

## Configuracao

Copie `.env.example` para `.env` somente se algum componente realmente precisar de credenciais. O laboratorio historico usa endpoints publicos da Binance e nao deve precisar de chave de trading.

O arquivo `.env` nunca entra no Git. Nao coloque segredos diretamente no codigo.

## Estrutura

```text
crypto_research/
|-- research/       modulos reutilizaveis de dados, indicadores e validacao
|-- manifests/      identidade, origem e cobertura dos datasets locais
|-- experiments/    registro declarativo dos experimentos reproduziveis
|-- execution/      runtime isolado, paper exchange e controles de risco
|-- deployment/     gates versionados de promocao operacional
|-- data/           cache historico local; nao versionado
|-- results/        resultados e decisoes; eventos brutos grandes nao versionados
|-- experiments/legacy/  arquivo dos experimentos monoliticos historicos
|-- main.py         bot legado de execucao real; nao executar
|-- AGENTS.md       regras permanentes para o Codex
|-- requirements.txt
`-- README.md
```

Alguns modulos centrais:

- `research/binance_data.py`: download, normalizacao, cache e leitura de candles.
- `research/indicators.py`: EMA, MACD, RSI, ATR, ADX e volume relativo.
- `research/features.py`: features derivadas de tendencia, momentum, volatilidade e pressao.
- `research/targets.py`: retornos futuros usados como alvos.
- `research/statistics.py`: estatisticas e profit factor.
- `research/validation.py`: experimentos e validacao com amostras nao sobrepostas.
- `research/regimes.py`: classificacao de regimes de mercado.
- `research/backtest.py`: modelo canonico e aditivo de custos por trade.
- `research/metrics.py`: metricas canonicas de retorno para experimentos.

O primeiro teste de regressao do motor reproduz os resumos congelados da C2 sem
baixar dados nem reabrir o holdout:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests/unit -p "test_*.py" -v
```

Quando os caches publicos mensais estao presentes em `data/`, execute tambem a
regressao pesada que reproduz sinais, entradas e retornos da C2 diretamente dos
candles. Testes sem o cache necessario sao marcados como ignorados; os dados
continuam fora do Git.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests/regression -p "test_*.py" -v
```

### Executar um experimento registrado

```powershell
.\.venv\Scripts\python.exe -m research.run_research --list
.\.venv\Scripts\python.exe -m research.run_research c2_development_replay
.\.venv\Scripts\python.exe -m research.run_research c2_august_holdout_replay
.\.venv\Scripts\python.exe -m research.run_research trend_short_cost_sensitivity
```

Cada execucao valida o resultado congelado e grava em `results/runs/` um
relatorio com parametros, commit do codigo e checksums de todos os arquivos de
entrada. `PASS_REGRESSION` significa apenas que o resultado foi reproduzido; a
decisao cientifica da C2 no holdout continua sendo `FAIL`.

A familia exploratoria `MEDIUM_TREND_EVENT_V1` foi pre-registrada antes da
execucao, usa entradas somente em `t+1` e tres divisoes temporais. Ela testou 16
conjuntos e todos falharam; os resumos pequenos foram preservados em `results/`
e nenhum parametro foi promovido. O motor de horizonte fixo foi vetorizado e
continua coberto pelas mesmas regressões historicas.

O motor tambem possui simulacao intrabar OHLC para stop, alvo e breakeven. A
convencao e deliberadamente conservadora: gaps saem no `open`, stop vence uma
ambiguidade stop/alvo no mesmo candle e um gatilho de breakeven so altera o
stop a partir do candle seguinte. O protocolo `C2_EXIT_POLICY_V1` compara regras
de breakeven com o respectivo baseline sem breakeven apenas nos antigos dados de
desenvolvimento; ele nao reabre o holdout de agosto nem pode promover a C2.

```powershell
.\.venv\Scripts\python.exe -m research.experiments.c2_exit_policy
```

O protocolo foi congelado no commit `d916347` antes da primeira execucao. O
resultado foi `FAIL`: nenhuma das oito regras de breakeven passou todos os
gates pareados de validacao, confirmacao, custos e amplitude por ativo. O melhor
caso isolado de confirmacao chegou a PF 1,002 com custo de 0,06%, mas caiu para
0,845 com custo de 0,10% e havia degradado fortemente a validacao. Portanto,
nenhum gatilho foi selecionado e a C2 continua reprovada.

Antes do replay, o executor confere cada cache contra o manifesto versionado em
`manifests/c2_candles.json`. O manifesto registra a origem publica, cobertura,
numero de linhas, tamanho e SHA-256, sem enviar os candles ao Git. Para
reconstrui-lo de forma deterministica depois de uma aquisicao deliberada de
dados:

```powershell
.\.venv\Scripts\python.exe -m research.data_manifest `
  --experiment c2_development_replay `
  --experiment c2_august_holdout_replay `
  --dataset-id c2-public-futures-5m-2024-01_2026-08 `
  --output manifests/c2_candles.json
```

O antigo `test_c2_august_holdout.py` foi reduzido a um ponto de entrada de
compatibilidade e agora delega ao executor registrado. A implementacao
monolitica anterior continua acessivel no historico Git.

O mesmo processo foi concluido para `test_cost_sensitivity.py`. A hipotese
trend-short usa explicitamente a convencao historica de retorno short inverso,
e o motor reproduz as 144 linhas detalhadas e as seis faixas de custo sem
divergencias. A decisao permanece `FAIL_COST_ROBUSTNESS`.

### Runtime operacional seguro

O novo runtime e separado de `main.py` e nasce em modo `paper`. Consulte
`docs/PRODUCTION_READINESS.md`, consulte o inventario em `docs/MIGRATION.md` e
verifique os gates sem conectar a uma exchange:

```powershell
.\.venv\Scripts\python.exe -m execution.app
```

Ordens passam obrigatoriamente por estrategia aprovada, limite de notional,
alavancagem, numero de posicoes, perda diaria, idade do dado e kill switch. Nao
existe adaptador de conta real habilitado enquanto os gates estiverem fechados.
O gateway Binance disponivel e restrito estruturalmente ao Testnet e nao e
instanciado pelo comando de readiness.

Retries e reinicios reconciliam tambem a quantidade assinada da posicao. Se o
fill historico existe mas a posicao ja esta zerada por stop ou alvo, o runtime
nao recria protecoes. Ele remove apenas os IDs condicionais pertencentes aquela
entrada, confirma a limpeza e registra o encerramento. Quantidade parcial,
invertida ou multiplas linhas de posicao falham fechadas para revisao.

`execution/recovery.py` reconstrui as intencoes completas do journal depois de
um reinicio e gera um relatorio por entrada. A recuperacao consulta primeiro a
exchange: pode restaurar protecoes de um fill confirmado, reconhecer uma
posicao encerrada ou bloquear divergencias, mas nunca envia uma nova entrada.

Execute o ensaio local, deterministico e sem credenciais para comprovar esses
casos e atualizar a evidencia JSON versionada:

```powershell
.\.venv\Scripts\python.exe -m execution.recovery_rehearsal
```

Cada intencao tambem contem stop-loss e take-profit obrigatorios. Depois do
fill, o runtime confirma as duas protecoes. Se a criacao ou consulta delas
falhar, tenta zerar a posicao imediatamente com uma ordem reduce-only e registra
o incidente no journal. Consulte o cronograma em `docs/PLANO_28_DIAS.md`.

O breakeven e opcional e nunca substitui o stop inicial. Quando habilitado, ele
so avanca o stop depois do ganho atingir o multiplo de risco configurado. O
preco protegido pode incluir uma estimativa explicita de taxas, slippage e
funding (`cost_buffer_rate`). No Testnet, o novo stop e criado e confirmado
antes do antigo ser cancelado, pois ordens condicionais Algo nao podem ser
alteradas diretamente.

```python
from decimal import Decimal
from execution.models import BreakEvenPolicy, PositionProtection

protection = PositionProtection(
    stop_loss_price=Decimal("49500"),
    take_profit_price=Decimal("51000"),
    break_even=BreakEvenPolicy(
        enabled=True,
        activation_r_multiple=Decimal("1"),
        cost_buffer_rate=Decimal("0.001"),
    ),
)
```

Depois de confirmar a entrada e as protecoes, o supervisor de mercado pode
consultar o mark price atual no adaptador e entregar uma observacao validada ao
servico. A chamada e idempotente: antes do gatilho retorna `None`; depois de
concluida retorna sempre a mesma protecao. Quotes obsoletos, futuros ou de outro
simbolo sao recusados.

```python
receipt = service.supervise_position(intent)
```

Este metodo nao autoriza uma estrategia nem inicia um loop de trading. A fonte
de mark price da Testnet e o arredondamento por `tickSize` ja estao integrados.
Antes de qualquer ordem de entrada, o adaptador tambem valida quantidade por
`MARKET_LOT_SIZE` (ou `LOT_SIZE`) e valida stop/alvo por `PRICE_FILTER`. Ainda
falta o ensaio completo no Testnet antes de promocao.

O loop reutilizavel em `execution/supervisor.py` supervisiona somente uma
posicao ja aberta e protegida. Ele possui polling, backoff exponencial, limite
de falhas transitorias, limite opcional de ciclos e encerramento cooperativo.
Nao existe comando que o inicie automaticamente.

```python
from threading import Event
from execution.supervisor import PositionSupervisor

shutdown = Event()
supervisor = PositionSupervisor(service)
result = supervisor.run(intent, should_stop=shutdown.is_set)
```

Para o preflight Testnet, crie chaves exclusivas da Testnet, preencha somente
`BINANCE_TESTNET_API_KEY` e `BINANCE_TESTNET_API_SECRET`, e altere
`BOT_MODE=testnet`. O comando abaixo faz apenas consultas GET: nao envia nem
cancela ordens.

```powershell
.\.venv\Scripts\python.exe -m execution.testnet_preflight
```

O preflight exige modo de posicao one-way, conta sem posicoes, sem ordens
comuns/condicionais pendentes e kill switch inativo. Nomes genericos de chaves
Binance nao sao aceitos pelo novo runtime, reduzindo o risco de usar uma chave
real por engano.

## Exemplos

### Baixar candles publicos

```python
from research.binance_data import fetch_klines

df = fetch_klines(
    symbol="BTCUSDT",
    interval="5m",
    start_date="2026-01-01",
    end_date="2026-01-02",
)

print(df[["open_time", "open", "high", "low", "close", "volume"]].head())
```

Executar o exemplo existente:

```powershell
.\.venv\Scripts\python.exe -m experiments.legacy.test_download
```

### Calcular todos os indicadores

```python
from research.binance_data import fetch_klines
from research.indicators import add_all_indicators

df = fetch_klines("BTCUSDT", "5m", "2026-01-01", "2026-01-02")
df = add_all_indicators(df)

print(df[[
    "close", "ema_9", "ema_21", "ema_35",
    "macd", "rsi", "atr", "adx", "volume_ratio",
]].tail())
```

Executar a validacao existente:

```powershell
.\.venv\Scripts\python.exe -m experiments.legacy.test_indicators
```

### Carregar um cache local

```python
from pathlib import Path
from research.binance_data import load_csv

df = load_csv(Path("data/BTCUSDT_5m.csv"))
print(len(df), df.open_time.min(), df.open_time.max())
```

Adapte o nome do arquivo ao cache existente em `data/`.

## Verificacoes seguras

Verificar imports e bytecode, sem operar e sem baixar dados:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q research
```

Os experimentos monoliticos historicos foram preservados em
`experiments/legacy/` e nao pertencem a suite automatizada. Alguns fazem
downloads extensos ou geram centenas de megabytes; execute-os apenas por modulo
e depois de revisar configuracao, custo e arquivos de saida.

## Politica de dados e GitHub

Entram no Git:

- codigo e configuracoes reproduziveis;
- README, auditorias e decisoes;
- resultados pequenos de resumo, estabilidade e holdout.

Nao entram no Git:

- `.env` e credenciais;
- `.venv`;
- candles e caches em `data/`;
- `results/*_events.csv`, que somam mais de 1 GB e incluem arquivos acima do limite individual do GitHub.

Dados brutos podem ser recriados a partir das fontes publicas. Se no futuro for necessario preserva-los remotamente, use armazenamento de artefatos, releases, DVC ou Git LFS com uma politica definida — nunca o repositorio Git comum.

## Direcao arquitetural

Antes de criar um bot autonomo, os scripts experimentais devem convergir para um pipeline configuravel:

```text
ingestao -> features -> estrategia -> simulador de execucao
-> metricas -> walk-forward/holdout -> decisao automatizada
```

O executor real deve ser um componente separado, com testnet, modo seco, idempotencia de ordens, reconciliacao apos falhas de rede, limites de risco e kill switch. Consulte `AGENTS.md` para as regras seguidas pelo agente de desenvolvimento.

## Disclaimer

Este repositorio e pesquisa de software e nao constitui recomendacao financeira. Backtests podem conter vieses, custos incompletos e resultados que nao se repetem no mercado real.
