Memória atualizada

Perfeito. Isso passa a ser nosso marco de continuidade do projeto. Vou tratar essa estrutura como a referência principal para não perdermos a linha de raciocínio.

🧠 NOTA MENTAL — CRYPTO RESEARCH / TRADING CHAMPIONSHIP
🎯 Objetivo original

Construir um sistema de trading de criptomoedas em Python para um campeonato, começando com capital muito pequeno e buscando evolução através de operações alavancadas.

Mas a estratégia não será simplesmente:

"criar um indicador → colocar no bot → operar."

A filosofia definida é:

Pesquisar → testar → medir → melhorar → validar → somente então operar.

1. PONTO DE PARTIDA

O usuário já possuía um bot Binance Futures.

Características principais do bot original:

Binance Futures
      ↓
Top moedas por volume
      ↓
EMA 9
EMA 21
EMA 35
      ↓
MACD
      ↓
BUY / SELL
      ↓
Alavancagem
      ↓
TP + SL
      ↓
Proteção da posição

O bot possui:

integração Binance Futures;
sincronização de horário;
API assinada;
seleção de contratos;
seleção por volume 24h;
candles;
EMA;
MACD;
alavancagem;
margem isolada;
entrada MARKET;
Take Profit;
Stop Loss;
verificação de proteção;
fechamento emergencial;
limite de posições;
cooldown.
2. DECISÃO ARQUITETURAL

Decidimos não evoluir diretamente o bot de produção.

Criamos primeiro um laboratório:

crypto_research

A função desse laboratório será descobrir:

O que realmente funciona estatisticamente?

Somente depois levaremos a estratégia vencedora para o bot.

3. ESTRUTURA ATUAL
crypto_research/
│
├── data/
│
├── results/
│
├── research/
│   ├── __init__.py
│   ├── backtest.py
│   ├── binance_data.py
│   ├── config.py
│   ├── features.py
│   ├── indicators.py
│   ├── metrics.py
│   ├── run_research.py
│   └── signals.py
│
├── .env.example
├── .gitignore
├── README.md
└── requirements.txt

Importante: nem todos esses arquivos já estão implementados.

Os arquivos que já trabalhamos são:

✅ config.py
✅ binance_data.py
⬜ indicators.py — código fornecido, teste ainda pendente
⬜ features.py
⬜ signals.py
⬜ backtest.py
⬜ metrics.py
⬜ run_research.py
4. AMBIENTE

Criamos:

.venv

E instalamos:

pandas
numpy
requests
python-dotenv
5. COLETA HISTÓRICA

Criamos:

research/binance_data.py

Ele acessa:

Binance Futures

através da API pública.

Importante

O laboratório de pesquisa não utiliza API KEY nem API SECRET.

Isso mantém a pesquisa separada do dinheiro real.

6. PRIMEIRO TESTE — CONCLUÍDO ✅

Testamos:

Ativo:
BTCUSDT

Timeframe:
5m

Período:
2026-01-01
até
2026-01-02

Resultado:

Quantidade de candles: 289

E os dados retornaram corretamente:

open
high
low
close
volume
quote_volume
trades
...
STATUS

🟢 COLETA HISTÓRICA FUNCIONANDO

Esse é um marco importante.

7. INDICADORES — IMPLEMENTAÇÃO INICIAL

Criamos research/indicators.py.

A primeira camada contém:

Tendência
EMA 9
EMA 21
EMA 35
Momentum
MACD
MACD Signal
MACD Histogram
RSI
Volatilidade
TR
ATR
Força da tendência
ADX
+DI
-DI
Volume
Volume MA
Volume Ratio
8. PONTO EXATO ONDE ESTAMOS

Criamos:

test_indicators.py

O próximo passo é executar:

python test_indicators.py

E confirmar que os indicadores estão sendo calculados corretamente.

Não pularemos essa etapa.

9. PRÓXIMA SEQUÊNCIA

Depois da validação dos indicadores:

ETAPA 3

Criar:

features.py

Aqui começa nossa parte proprietária.

Não queremos apenas:

RSI = 60
ADX = 25
EMA9 > EMA21

Queremos transformar os dados em informações mais inteligentes.

Exemplos que já definimos:

Aceleração da tendência
Momentum relativo
Pressão compradora/vendedora
Expansão de volatilidade
Distância entre médias
Mudança do volume
10. DEPOIS

Construiremos:

signals.py

para transformar as features em sinais.

Depois:

backtest.py

para simular operações historicamente.

Depois:

metrics.py

para medir:

Win Rate
Loss Rate
Profit Factor
Expectancy
Drawdown
retorno;
sequência de ganhos/perdas;
número de operações;
resultado por ativo;
resultado por timeframe;
resultado por horário;
resultado por regime de mercado.
11. PRINCÍPIO MAIS IMPORTANTE DO PROJETO

Não vamos dizer:

"ADX é bom."

Vamos perguntar:

"ADX melhora nossa expectativa quando adicionado à estratégia?"

Não vamos dizer:

"RSI funciona."

Vamos testar:

EMA + MACD

versus

EMA + MACD + RSI

Depois:

EMA + MACD + RSI + ADX

Depois:

EMA + MACD + RSI + ADX + Volume

E assim por diante.

12. NOSSO OBJETIVO FINAL

A arquitetura conceitual ficou:

                 HISTÓRICO BINANCE
                         │
                         ▼
                 ┌───────────────┐
                 │  INDICADORES  │
                 └───────┬───────┘
                         │
                         ▼
                 ┌───────────────┐
                 │    FEATURES   │
                 │   PRÓPRIAS    │
                 └───────┬───────┘
                         │
                         ▼
                 ┌───────────────┐
                 │    SINAIS     │
                 └───────┬───────┘
                         │
                         ▼
                 ┌───────────────┐
                 │   BACKTEST    │
                 └───────┬───────┘
                         │
                         ▼
                 ┌───────────────┐
                 │   MÉTRICAS    │
                 └───────┬───────┘
                         │
                         ▼
                    ROBUSTEZ
                         │
                         ▼
                   ESTRATÉGIA
                         │
                         ▼
                  PAPER TRADING
                         │
                         ▼
                   BOT REAL

E só depois:

BOT REAL
   ↓
CAPITAL PEQUENO
   ↓
CAMPEONATO
   ↓
EVOLUÇÃO
🔒 MARCO DE RETOMADA

Se em algum momento a conversa perder contexto, a frase de recuperação será:

"Retomar Crypto Research a partir do teste dos indicadores."

E o ponto será:

✅ Binance histórico funcionando
✅ BTCUSDT 5m testado — 289 candles
✅ config.py
✅ binance_data.py
✅ indicators.py criado
➡️ PRÓXIMO: executar test_indicators.py

A partir daí seguimos sem recomeçar o projeto e sem mudar a arquitetura original sem uma razão técnica clara.