# Crypto Research

Laboratorio quantitativo em Python para pesquisar, testar e validar estrategias de criptomoedas com dados historicos da Binance. O projeto separa deliberadamente **pesquisa** de **execucao real**:

```text
dados historicos -> indicadores/features -> hipotese -> backtest
-> custos e robustez -> validacao fora da amostra -> paper trading
-> somente entao, producao
```

> **Aviso de seguranca:** `main.py` e um bot legado capaz de operar Binance Futures e atualmente contem `TESTNET = False` e `DRY_RUN = False`. Nao execute esse arquivo. Nenhuma estrategia deste repositorio esta aprovada para dinheiro real.

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
|-- data/           cache historico local; nao versionado
|-- results/        resultados e decisoes; eventos brutos grandes nao versionados
|-- test_*.py       experimentos historicos e testes de hipoteses
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
```

Cada execucao valida o resultado congelado e grava em `results/runs/` um
relatorio com parametros, commit do codigo e checksums de todos os arquivos de
entrada. `PASS_REGRESSION` significa apenas que o resultado foi reproduzido; a
decisao cientifica da C2 no holdout continua sendo `FAIL`.

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
.\.venv\Scripts\python.exe test_download.py
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
.\.venv\Scripts\python.exe test_indicators.py
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

Os arquivos chamados `test_*.py` sao majoritariamente experimentos executaveis, nao uma suite pytest convencional. Alguns fazem downloads extensos ou geram centenas de megabytes; leia o cabecalho e confirme periodo, custo e arquivos de saida antes de executa-los.

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
