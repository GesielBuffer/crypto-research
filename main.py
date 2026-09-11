import time
import hmac
import hashlib
from decimal import Decimal, ROUND_DOWN
from urllib.parse import urlencode


import requests
import pandas as pd


# ============================================================
#                 CREDENCIAIS BINANCE
# ============================================================

# IMPORTANTE:
# NÃO coloque aqui as credenciais que foram expostas.
# Gere uma NOVA API KEY e um NOVO API SECRET na Binance.
#
# Você pode colocar as novas credenciais aqui:
API_KEY = "importe do arquivo .env"
API_SECRET = "importe do arquivo .env"


# ============================================================
#                 CONFIGURAÇÕES
# ============================================================

# True = Binance Futures Testnet
# False = Binance Futures REAL
TESTNET = False

# True = apenas simula
# False = envia ordens reais
DRY_RUN = False

# Capital utilizado como margem
RISK_USD = Decimal("7.0")

# Alavancagem
LEVERAGE = 15

# Lucro alvo
LUCRO_FIXO_USD = Decimal("1.0")

# Buffer para taxas/slippage
PROFIT_BUFFER_USD = Decimal("0.30")

# Stop Loss = 70% da distância do TP
SL_RATIO = Decimal("0.70")

# Volume mínimo 24h em USDT
MIN_VOLUME_24H = Decimal("1000000")

# Quantidade máxima de moedas analisadas
TOP_SYMBOLS = 100

# Quantidade máxima de posições abertas
MAX_OPEN_POSITIONS = 5

# Candle
INTERVAL = "1m"
KLINE_LIMIT = 60

# Intervalo entre scans
SCAN_INTERVAL = 10

# Tempo mínimo entre entradas
ENTRY_COOLDOWN = 60

# Timeout das requisições
HTTP_TIMEOUT = 10

# recvWindow Binance
RECV_WINDOW = 5000


# ============================================================
#                 URL BINANCE
# ============================================================

if TESTNET:
    BASE_URL = "https://testnet.binancefuture.com"
else:
    BASE_URL = "https://fapi.binance.com"


# ============================================================
#                 VALIDAÇÃO
# ============================================================

if (
    not API_KEY
    or API_KEY == "COLOQUE_SUA_NOVA_API_KEY_AQUI"
):
    raise RuntimeError(
        "Coloque uma NOVA BINANCE API KEY."
    )

if (
    not API_SECRET
    or API_SECRET == "COLOQUE_SEU_NOVO_API_SECRET_AQUI"
):
    raise RuntimeError(
        "Coloque um NOVO BINANCE API SECRET."
    )


# ============================================================
#                 CLIENTE BINANCE
# ============================================================

class BinanceClient:

    def __init__(
        self,
        api_key,
        api_secret,
        base_url,
    ):

        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url

        self.session = requests.Session()

        self.session.headers.update(
            {
                "X-MBX-APIKEY": self.api_key
            }
        )

        self.time_offset = 0

    # --------------------------------------------------------
    # SINCRONIZA RELÓGIO
    # --------------------------------------------------------

    def sync_time(self):

        response = self.session.get(
            self.base_url + "/fapi/v1/time",
            timeout=HTTP_TIMEOUT,
        )

        response.raise_for_status()

        server_time = int(
            response.json()["serverTime"]
        )

        local_time = int(
            time.time() * 1000
        )

        self.time_offset = (
            server_time - local_time
        )

    # --------------------------------------------------------
    # TIMESTAMP
    # --------------------------------------------------------

    def timestamp(self):

        return (
            int(time.time() * 1000)
            + self.time_offset
        )

    # --------------------------------------------------------
    # GET PÚBLICO
    # --------------------------------------------------------

    def public_get(
        self,
        endpoint,
        params=None,
    ):

        response = self.session.get(
            self.base_url + endpoint,
            params=params or {},
            timeout=HTTP_TIMEOUT,
        )

        if response.status_code >= 400:

            raise RuntimeError(
                response.text
            )

        return response.json()

    # --------------------------------------------------------
    # REQUEST ASSINADA
    # --------------------------------------------------------

    def signed_request(
        self,
        method,
        endpoint,
        params=None,
    ):

        params = dict(params or {})

        params["timestamp"] = (
            self.timestamp()
        )

        params["recvWindow"] = (
            RECV_WINDOW
        )

        query_string = urlencode(
            params
        )

        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        params["signature"] = signature

        url = (
            self.base_url
            + endpoint
        )

        method = method.upper()

        if method == "GET":

            response = self.session.get(
                url,
                params=params,
                timeout=HTTP_TIMEOUT,
            )

        elif method == "POST":

            response = self.session.post(
                url,
                data=params,
                timeout=HTTP_TIMEOUT,
            )

        elif method == "DELETE":

            response = self.session.delete(
                url,
                params=params,
                timeout=HTTP_TIMEOUT,
            )

        else:

            raise ValueError(
                "Método HTTP inválido."
            )

        try:

            data = response.json()

        except Exception:

            data = {
                "raw": response.text
            }

        if response.status_code >= 400:

            raise RuntimeError(
                f"Binance HTTP "
                f"{response.status_code}: "
                f"{data}"
            )

        if (
            isinstance(data, dict)
            and "code" in data
            and data["code"] < 0
        ):

            raise RuntimeError(
                f"Binance API "
                f"{data['code']}: "
                f"{data.get('msg')}"
            )

        return data

    # --------------------------------------------------------
    # SALDO
    # --------------------------------------------------------

    def get_balance(self):

        data = self.signed_request(
            "GET",
            "/fapi/v3/balance",
        )

        for item in data:

            if item["asset"] == "USDT":

                return Decimal(
                    item["balance"]
                )

        return Decimal("0")

    # --------------------------------------------------------
    # POSIÇÕES
    # --------------------------------------------------------

    def get_positions(self):

        return self.signed_request(
            "GET",
            "/fapi/v3/positionRisk",
        )

    # --------------------------------------------------------
    # POSIÇÕES ABERTAS
    # --------------------------------------------------------

    def get_open_positions(self):

        positions = self.get_positions()

        result = []

        for position in positions:

            amount = Decimal(
                position["positionAmt"]
            )

            if amount != 0:

                result.append(
                    position
                )

        return result

    # --------------------------------------------------------
    # POSIÇÃO DE UM SÍMBOLO
    # --------------------------------------------------------

    def get_position(
        self,
        symbol,
    ):

        positions = self.get_positions()

        for position in positions:

            if position["symbol"] == symbol:

                return position

        return None

    # --------------------------------------------------------
    # EXCHANGE INFO
    # --------------------------------------------------------

    def get_exchange_info(self):

        return self.public_get(
            "/fapi/v1/exchangeInfo"
        )

    # --------------------------------------------------------
    # TICKERS
    # --------------------------------------------------------

    def get_tickers(self):

        return self.public_get(
            "/fapi/v1/ticker/24hr"
        )

    # --------------------------------------------------------
    # KLINES
    # --------------------------------------------------------

    def get_klines(
        self,
        symbol,
        interval,
        limit,
    ):

        data = self.public_get(
            "/fapi/v1/klines",
            {
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
            },
        )

        columns = [
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_volume",
            "trades",
            "taker_buy_base",
            "taker_buy_quote",
            "ignore",
        ]

        df = pd.DataFrame(
            data,
            columns=columns,
        )

        numeric_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_volume",
        ]

        for column in numeric_columns:

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )

        df = df.sort_values(
            "open_time"
        )

        return df.reset_index(
            drop=True
        )

    # --------------------------------------------------------
    # PREÇO MARK
    # --------------------------------------------------------

    def get_mark_price(
        self,
        symbol,
    ):

        data = self.public_get(
            "/fapi/v1/premiumIndex",
            {
                "symbol": symbol
            },
        )

        return Decimal(
            data["markPrice"]
        )

    # --------------------------------------------------------
    # ALAVANCAGEM
    # --------------------------------------------------------

    def set_leverage(
        self,
        symbol,
        leverage,
    ):

        return self.signed_request(
            "POST",
            "/fapi/v1/leverage",
            {
                "symbol": symbol,
                "leverage": leverage,
            },
        )

    # --------------------------------------------------------
    # MARGIN TYPE
    # --------------------------------------------------------

    def set_margin_type(
        self,
        symbol,
    ):

        try:

            return self.signed_request(
                "POST",
                "/fapi/v1/marginType",
                {
                    "symbol": symbol,
                    "marginType": "ISOLATED",
                },
            )

        except RuntimeError as e:

            if "-4046" in str(e):

                return None

            raise

    # --------------------------------------------------------
    # ORDEM NORMAL
    # --------------------------------------------------------

    def new_order(
        self,
        **params,
    ):

        return self.signed_request(
            "POST",
            "/fapi/v1/order",
            params,
        )

    # --------------------------------------------------------
    # NOVA ALGO ORDER
    #
    # Usada para:
    # STOP_MARKET
    # TAKE_PROFIT_MARKET
    #
    # A Binance migrou essas ordens para o
    # Algo Service.
    # --------------------------------------------------------

    def new_algo_order(
        self,
        **params,
    ):

        return self.signed_request(
            "POST",
            "/fapi/v1/algoOrder",
            params,
        )

    # --------------------------------------------------------
    # ALGO ORDERS ABERTAS
    # --------------------------------------------------------

    def get_open_algo_orders(
        self,
        symbol=None,
    ):

        params = {}

        if symbol:

            params["symbol"] = symbol

        return self.signed_request(
            "GET",
            "/fapi/v1/openAlgoOrders",
            params,
        )

    # --------------------------------------------------------
    # CANCELAR ALGO ORDER
    # --------------------------------------------------------

    def cancel_algo_order(
        self,
        symbol,
        algo_id,
    ):

        return self.signed_request(
            "DELETE",
            "/fapi/v1/algoOrder",
            {
                "symbol": symbol,
                "algoId": algo_id,
            },
        )

    # --------------------------------------------------------
    # CANCELAR TODAS AS ALGO ORDERS
    # --------------------------------------------------------

    def cancel_all_algo_orders(
        self,
        symbol,
    ):

        return self.signed_request(
            "DELETE",
            "/fapi/v1/algoOpenOrders",
            {
                "symbol": symbol
            },
        )

    # --------------------------------------------------------
    # ORDENS ABERTAS NORMAIS
    # --------------------------------------------------------

    def get_open_orders(
        self,
        symbol=None,
    ):

        params = {}

        if symbol:

            params["symbol"] = symbol

        return self.signed_request(
            "GET",
            "/fapi/v1/openOrders",
            params,
        )

    # --------------------------------------------------------
    # CANCELAR ORDENS NORMAIS
    # --------------------------------------------------------

    def cancel_all_orders(
        self,
        symbol,
    ):

        return self.signed_request(
            "DELETE",
            "/fapi/v1/allOpenOrders",
            {
                "symbol": symbol
            },
        )


# ============================================================
#                 DECIMAL
# ============================================================

def floor_step(
    value,
    step,
):

    value = Decimal(
        str(value)
    )

    step = Decimal(
        str(step)
    )

    return (
        value / step
    ).to_integral_value(
        rounding=ROUND_DOWN
    ) * step


def decimal_string(
    value,
):

    text = format(
        Decimal(value),
        "f",
    )

    if "." in text:

        text = (
            text
            .rstrip("0")
            .rstrip(".")
        )

    return text


# ============================================================
#                 INFORMAÇÕES DOS SÍMBOLOS
# ============================================================

SYMBOL_INFO = {}


def load_symbols(client):

    global SYMBOL_INFO

    data = client.get_exchange_info()

    for symbol in data["symbols"]:

        if symbol["status"] != "TRADING":
            continue

        if symbol["contractType"] != "PERPETUAL":
            continue

        if symbol["quoteAsset"] != "USDT":
            continue

        filters = {
            f["filterType"]: f
            for f in symbol["filters"]
        }

        price_filter = filters.get(
            "PRICE_FILTER"
        )

        lot_filter = filters.get(
            "LOT_SIZE"
        )

        min_notional_filter = (
            filters.get(
                "MIN_NOTIONAL"
            )
        )

        if (
            not price_filter
            or not lot_filter
        ):
            continue

        SYMBOL_INFO[
            symbol["symbol"]
        ] = {

            "tick_size": Decimal(
                price_filter["tickSize"]
            ),

            "step_size": Decimal(
                lot_filter["stepSize"]
            ),

            "min_qty": Decimal(
                lot_filter["minQty"]
            ),

            "max_qty": Decimal(
                lot_filter["maxQty"]
            ),

            "min_notional": (
                Decimal(
                    min_notional_filter[
                        "notional"
                    ]
                )
                if min_notional_filter
                else Decimal("0")
            ),
        }

    print(
        f"Símbolos carregados: "
        f"{len(SYMBOL_INFO)}"
    )


# ============================================================
#                 TOP SYMBOLS
# ============================================================

def get_top_symbols(
    client,
):

    tickers = client.get_tickers()

    valid = []

    for ticker in tickers:

        symbol = ticker["symbol"]

        if symbol not in SYMBOL_INFO:
            continue

        try:

            volume = Decimal(
                ticker["quoteVolume"]
            )

        except Exception:

            continue

        if volume < MIN_VOLUME_24H:
            continue

        valid.append(
            (
                symbol,
                volume,
            )
        )

    valid.sort(
        key=lambda x: x[1],
        reverse=True,
    )

    return [
        x[0]
        for x in valid[:TOP_SYMBOLS]
    ]


# ============================================================
#                 INDICADORES
# ============================================================

def calculate_indicators(
    df,
):

    if (
        df is None
        or len(df) < 40
    ):

        return None

    df = df.copy()

    close = df["close"]

    df["ema9"] = (
        close.ewm(
            span=9,
            adjust=False,
        ).mean()
    )

    df["ema21"] = (
        close.ewm(
            span=21,
            adjust=False,
        ).mean()
    )

    df["ema35"] = (
        close.ewm(
            span=35,
            adjust=False,
        ).mean()
    )

    ema12 = (
        close.ewm(
            span=12,
            adjust=False,
        ).mean()
    )

    ema26 = (
        close.ewm(
            span=26,
            adjust=False,
        ).mean()
    )

    df["macd"] = (
        ema12 - ema26
    )

    df["signal"] = (
        df["macd"]
        .ewm(
            span=9,
            adjust=False,
        )
        .mean()
    )

    df["hist"] = (
        df["macd"]
        - df["signal"]
    )

    return df


# ============================================================
#                 SINAL
# ============================================================

def check_signal(
    client,
    symbol,
):

    try:

        df = client.get_klines(
            symbol,
            INTERVAL,
            KLINE_LIMIT,
        )

        if len(df) < 40:
            return None

        # Remove candle ainda aberta
        df = df.iloc[:-1].copy()

        df = calculate_indicators(df)

        if df is None:
            return None

        last = df.iloc[-1]
        previous = df.iloc[-2]

        bullish = (
            last["ema9"]
            > last["ema21"]
            > last["ema35"]
            and last["hist"]
            > previous["hist"]
        )

        bearish = (
            last["ema9"]
            < last["ema21"]
            < last["ema35"]
            and last["hist"]
            < previous["hist"]
        )

        if bullish:
            return "BUY"

        if bearish:
            return "SELL"

        return None

    except Exception as e:

        print(
            f"\nErro no sinal "
            f"{symbol}: {e}"
        )

        return None


# ============================================================
#                 QUANTIDADE
# ============================================================

def calculate_quantity(
    symbol,
    price,
    balance,
):

    info = SYMBOL_INFO[symbol]

    investment = min(
        RISK_USD,
        balance * Decimal("0.40"),
    )

    if investment <= 0:
        return Decimal("0")

    notional = (
        investment
        * Decimal(LEVERAGE)
    )

    quantity = (
        notional / price
    )

    quantity = floor_step(
        quantity,
        info["step_size"],
    )

    if quantity < info["min_qty"]:

        quantity = info["min_qty"]

    if (
        quantity * price
        < info["min_notional"]
    ):

        quantity = (
            info["min_notional"]
            / price
        )

        quantity = floor_step(
            quantity,
            info["step_size"],
        )

        if quantity < info["min_qty"]:

            quantity = info["min_qty"]

    if quantity > info["max_qty"]:

        quantity = info["max_qty"]

    return quantity


# ============================================================
#                 PREÇO
# ============================================================

def normalize_price(
    symbol,
    price,
):

    tick = SYMBOL_INFO[
        symbol
    ]["tick_size"]

    return floor_step(
        price,
        tick,
    )


# ============================================================
#                 FECHAR POSIÇÃO
# ============================================================

def close_position(
    client,
    symbol,
):

    try:

        position = client.get_position(
            symbol
        )

        if not position:
            return True

        amount = Decimal(
            position["positionAmt"]
        )

        if amount == 0:

            return True

        if amount > 0:

            side = "SELL"

        else:

            side = "BUY"

        quantity = abs(amount)

        print(
            f"\n⚠️ FECHANDO POSIÇÃO "
            f"DE EMERGÊNCIA"
        )

        print(
            f"Symbol: {symbol}"
        )

        print(
            f"Side: {side}"
        )

        print(
            f"Qty: "
            f"{decimal_string(quantity)}"
        )

        client.new_order(
            symbol=symbol,
            side=side,
            type="MARKET",
            quantity=decimal_string(
                quantity
            ),
            reduceOnly="true",
        )

        time.sleep(0.5)

        position = client.get_position(
            symbol
        )

        if position:

            remaining = Decimal(
                position["positionAmt"]
            )

            if remaining == 0:

                print(
                    "✅ Posição fechada."
                )

                return True

            print(
                f"🚨 Ainda existe "
                f"posição aberta: "
                f"{remaining}"
            )

            return False

        return True

    except Exception as e:

        print(
            f"🚨 ERRO AO FECHAR "
            f"{symbol}: {e}"
        )

        return False


# ============================================================
#                 CRIAR TP
# ============================================================

def create_take_profit(
    client,
    symbol,
    exit_side,
    tp,
):

    return client.new_algo_order(

        algoType="CONDITIONAL",

        symbol=symbol,

        side=exit_side,

        type="TAKE_PROFIT_MARKET",

        triggerPrice=decimal_string(tp),

        closePosition="true",

        workingType="MARK_PRICE",
    )


# ============================================================
#                 CRIAR SL
# ============================================================

def create_stop_loss(
    client,
    symbol,
    exit_side,
    sl,
):

    return client.new_algo_order(

        algoType="CONDITIONAL",

        symbol=symbol,

        side=exit_side,

        type="STOP_MARKET",

        triggerPrice=decimal_string(sl),

        closePosition="true",

        workingType="MARK_PRICE",
    )


# ============================================================
#                 VERIFICAR PROTEÇÃO
# ============================================================

def protection_exists(
    client,
    symbol,
):

    try:

        orders = (
            client.get_open_algo_orders(
                symbol
            )
        )

        tp_found = False
        sl_found = False

        for order in orders:

            order_type = order.get(
                "orderType",
                order.get(
                    "type",
                    ""
                ),
            )

            if order_type == "TAKE_PROFIT_MARKET":
                tp_found = True

            if order_type == "STOP_MARKET":
                sl_found = True

        return (
            tp_found,
            sl_found,
        )

    except Exception as e:

        print(
            f"⚠️ Não foi possível "
            f"confirmar proteção: "
            f"{e}"
        )

        return False, False


# ============================================================
#                 ABRIR POSIÇÃO
# ============================================================

def open_position(
    client,
    symbol,
    side,
):

    try:

        balance = (
            client.get_balance()
        )

        investment = min(
            RISK_USD,
            balance * Decimal("0.40"),
        )

        if investment < Decimal("1"):

            print(
                f"\nSaldo insuficiente: "
                f"${decimal_string(balance)}"
            )

            return False

        mark_price = (
            client.get_mark_price(
                symbol
            )
        )

        quantity = (
            calculate_quantity(
                symbol,
                mark_price,
                balance,
            )
        )

        if quantity <= 0:

            return False

        print(
            f"\n"
            f"🎯 SINAL {side} "
            f"{symbol}\n"
            f"Preço: "
            f"{decimal_string(mark_price)}\n"
            f"Quantidade: "
            f"{decimal_string(quantity)}\n"
            f"Margem: "
            f"${decimal_string(investment)}"
        )

        # ----------------------------------------------------
        # DRY RUN
        # ----------------------------------------------------

        if DRY_RUN:

            print(
                "🧪 DRY_RUN = TRUE"
            )

            print(
                "Nenhuma ordem será enviada."
            )

            return True

        # ----------------------------------------------------
        # LEVERAGE
        # ----------------------------------------------------

        try:

            client.set_leverage(
                symbol,
                LEVERAGE,
            )

        except Exception as e:

            print(
                f"Erro leverage: {e}"
            )

            return False

        # ----------------------------------------------------
        # ISOLATED
        # ----------------------------------------------------

        try:

            client.set_margin_type(
                symbol
            )

        except Exception as e:

            print(
                f"Aviso margin type: {e}"
            )

        # ----------------------------------------------------
        # MARKET
        # ----------------------------------------------------

        order = client.new_order(
            symbol=symbol,
            side=side,
            type="MARKET",
            quantity=decimal_string(
                quantity
            ),
            newOrderRespType="RESULT",
        )

        executed_qty = Decimal(
            order.get(
                "executedQty",
                "0",
            )
        )

        entry_price = Decimal(
            order.get(
                "avgPrice",
                "0",
            )
        )

        # ----------------------------------------------------
        # FALLBACK ENTRY PRICE
        # ----------------------------------------------------

        if entry_price <= 0:

            positions = (
                client.get_positions()
            )

            for position in positions:

                if (
                    position["symbol"]
                    == symbol
                ):

                    entry_price = Decimal(
                        position["entryPrice"]
                    )

                    break

        if (
            executed_qty <= 0
            or entry_price <= 0
        ):

            raise RuntimeError(
                "Não foi possível "
                "determinar execução."
            )

        # ----------------------------------------------------
        # TP / SL
        # ----------------------------------------------------

        tp_distance = (
            LUCRO_FIXO_USD
            + PROFIT_BUFFER_USD
        ) / executed_qty

        sl_distance = (
            tp_distance
            * SL_RATIO
        )

        if side == "BUY":

            exit_side = "SELL"

            tp = (
                entry_price
                + tp_distance
            )

            sl = (
                entry_price
                - sl_distance
            )

        else:

            exit_side = "BUY"

            tp = (
                entry_price
                - tp_distance
            )

            sl = (
                entry_price
                + sl_distance
            )

        tp = normalize_price(
            symbol,
            tp,
        )

        sl = normalize_price(
            symbol,
            sl,
        )

        print(
            f"\n"
            f"✅ ENTRADA EXECUTADA\n"
            f"Symbol: {symbol}\n"
            f"Side: {side}\n"
            f"Qty: "
            f"{decimal_string(executed_qty)}\n"
            f"Entry: "
            f"{decimal_string(entry_price)}\n"
            f"TP: "
            f"{decimal_string(tp)}\n"
            f"SL: "
            f"{decimal_string(sl)}"
        )

        # ----------------------------------------------------
        # TAKE PROFIT - ALGO ORDER
        # ----------------------------------------------------

        try:

            tp_order = create_take_profit(
                client,
                symbol,
                exit_side,
                tp,
            )

            print(
                "✅ TAKE PROFIT criado."
            )

            print(
                f"Algo ID TP: "
                f"{tp_order.get('algoId', 'N/A')}"
            )

        except Exception as e:

            print(
                f"🚨 ERRO NO TP: {e}"
            )

            print(
                "🚨 Proteção incompleta."
            )

            # NÃO procura outra moeda.
            # Tenta fechar imediatamente.
            close_position(
                client,
                symbol,
            )

            return False

        # ----------------------------------------------------
        # STOP LOSS - ALGO ORDER
        # ----------------------------------------------------

        try:

            sl_order = create_stop_loss(
                client,
                symbol,
                exit_side,
                sl,
            )

            print(
                "✅ STOP LOSS criado."
            )

            print(
                f"Algo ID SL: "
                f"{sl_order.get('algoId', 'N/A')}"
            )

        except Exception as e:

            print(
                f"🚨 ERRO NO SL: {e}"
            )

            print(
                "🚨 Cancelando TP..."
            )

            try:

                client.cancel_all_algo_orders(
                    symbol
                )

            except Exception as cancel_error:

                print(
                    f"Erro ao cancelar "
                    f"TP: {cancel_error}"
                )

            print(
                "🚨 Fechando posição "
                "por segurança..."
            )

            closed = close_position(
                client,
                symbol,
            )

            if not closed:

                print(
                    "\n"
                    "🚨🚨🚨 ATENÇÃO 🚨🚨🚨\n"
                    f"A posição {symbol} "
                    "PODE AINDA ESTAR ABERTA.\n"
                    "Verifique a Binance "
                    "imediatamente."
                )

            return False

        # ----------------------------------------------------
        # CONFIRMA PROTEÇÃO
        # ----------------------------------------------------

        time.sleep(0.5)

        tp_found, sl_found = (
            protection_exists(
                client,
                symbol,
            )
        )

        if not tp_found or not sl_found:

            print(
                "\n"
                "🚨 PROTEÇÃO NÃO "
                "CONFIRMADA!"
            )

            print(
                f"TP confirmado: "
                f"{tp_found}"
            )

            print(
                f"SL confirmado: "
                f"{sl_found}"
            )

            try:

                client.cancel_all_algo_orders(
                    symbol
                )

            except Exception:
                pass

            close_position(
                client,
                symbol,
            )

            return False

        print(
            "\n"
            "🟢 OPERAÇÃO PROTEGIDA "
            "POR TP + SL"
        )

        return True

    except Exception as e:

        print(
            f"\n❌ ERRO AO ABRIR "
            f"{symbol}: {e}"
        )

        # Segurança adicional:
        # se uma entrada tiver ocorrido,
        # tenta descobrir e fechar a posição.

        try:

            position = client.get_position(
                symbol
            )

            if position:

                amount = Decimal(
                    position["positionAmt"]
                )

                if amount != 0:

                    print(
                        f"🚨 Posição detectada "
                        f"após erro: {amount}"
                    )

                    close_position(
                        client,
                        symbol,
                    )

        except Exception as close_error:

            print(
                f"🚨 Não foi possível "
                f"verificar/fechar "
                f"{symbol}: "
                f"{close_error}"
            )

        return False


# ============================================================
#                 PROGRAMA PRINCIPAL
# ============================================================

def main():

    print("=" * 50)

    print(
        "🚀 BINANCE FUTURES SNIPER"
    )

    print("=" * 50)

    print(
        "Ambiente: "
        + (
            "TESTNET"
            if TESTNET
            else "PRODUÇÃO"
        )
    )

    print(
        "DRY RUN: "
        + str(DRY_RUN)
    )

    print(
        f"Alavancagem: {LEVERAGE}x"
    )

    print(
        f"Risco por operação: "
        f"${decimal_string(RISK_USD)}"
    )

    print("=" * 50)

    client = BinanceClient(
        API_KEY,
        API_SECRET,
        BASE_URL,
    )

    # --------------------------------------------------------
    # SINCRONIZA HORÁRIO
    # --------------------------------------------------------

    print(
        "Sincronizando horário..."
    )

    client.sync_time()

    print(
        "✅ Horário sincronizado."
    )

    # --------------------------------------------------------
    # CARREGA SÍMBOLOS
    # --------------------------------------------------------

    print(
        "Carregando contratos..."
    )

    load_symbols(client)

    print(
        "✅ Contratos carregados."
    )

    # --------------------------------------------------------
    # LOOP
    # --------------------------------------------------------

    last_entry = 0

    while True:

        try:

            balance = (
                client.get_balance()
            )

            positions = (
                client.get_open_positions()
            )

            print(
                f"\n"
                f"[{time.strftime('%H:%M:%S')}] "
                f"Saldo: "
                f"${decimal_string(balance)} "
                f"| Posições: "
                f"{len(positions)}"
            )

            # ------------------------------------------------
            # LIMITE DE POSIÇÕES
            # ------------------------------------------------

            if (
                len(positions)
                >= MAX_OPEN_POSITIONS
            ):

                print(
                    "⏳ Posição existente. "
                    "Aguardando..."
                )

                time.sleep(
                    SCAN_INTERVAL
                )

                continue

            # ------------------------------------------------
            # COOLDOWN
            # ------------------------------------------------

            if (
                time.time()
                - last_entry
                < ENTRY_COOLDOWN
            ):

                time.sleep(
                    SCAN_INTERVAL
                )

                continue

            # ------------------------------------------------
            # TOP MOEDAS
            # ------------------------------------------------

            symbols = (
                get_top_symbols(
                    client
                )
            )

            print(
                f"🔎 Analisando "
                f"{len(symbols)} ativos..."
            )

            # ------------------------------------------------
            # SCAN
            # ------------------------------------------------

            for symbol in symbols:

                try:

                    # Segurança:
                    # antes de cada entrada,
                    # verifica se existe alguma posição.

                    current_positions = (
                        client.get_open_positions()
                    )

                    if current_positions:

                        print(
                            "⏳ Posição aberta "
                            "detectada. "
                            "Parando scan."
                        )

                        break

                    signal = (
                        check_signal(
                            client,
                            symbol,
                        )
                    )

                    if signal is None:
                        continue

                    print(
                        f"\n🔥 SINAL "
                        f"{signal} "
                        f"→ {symbol}"
                    )

                    success = (
                        open_position(
                            client,
                            symbol,
                            signal,
                        )
                    )

                    if success:

                        last_entry = (
                            time.time()
                        )

                        break

                    # Depois de uma tentativa de entrada,
                    # verifica novamente se existe posição.

                    current_positions = (
                        client.get_open_positions()
                    )

                    if current_positions:

                        print(
                            "\n"
                            "🚨 POSIÇÃO "
                            "DETECTADA.\n"
                            "O scanner será "
                            "interrompido."
                        )

                        break

                    time.sleep(0.3)

                except Exception as e:

                    print(
                        f"\nErro "
                        f"{symbol}: {e}"
                    )

                    continue

            time.sleep(
                SCAN_INTERVAL
            )

        except KeyboardInterrupt:

            print(
                "\n\n🛑 Bot encerrado."
            )

            break

        except Exception as e:

            print(
                f"\n⚠️ Erro geral: "
                f"{e}"
            )

            print(
                "Tentando novamente..."
            )

            try:

                client.sync_time()

            except Exception:
                pass

            time.sleep(10)


# ============================================================
#                 START
# ============================================================

if __name__ == "__main__":

    main()