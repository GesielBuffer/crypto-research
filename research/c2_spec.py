# ============================================================
# C2 — FROZEN STRATEGY SPECIFICATION
#
# NÃO ALTERAR COM BASE EM AGOSTO/2026.
# Development:
# 2024-01-01 -> 2026-07-31
# ============================================================

C2_VERSION = "C2_FROZEN_DEV_2026_08_27"


# ============================================================
# MARKET / TIMEFRAME
# ============================================================

TIMEFRAME = "5m"

BAR_MINUTES = 5


# ============================================================
# FEATURE WINDOW
# ============================================================

LOOKBACK_DAYS = 7

BARS_PER_DAY = 288

LOOKBACK = (
    LOOKBACK_DAYS
    *
    BARS_PER_DAY
)

MIN_PERIODS = (
    3
    *
    BARS_PER_DAY
)


# ============================================================
# EXTREME EVENT
# ============================================================

EXTREME_UP_QUANTILE = 0.975

RETURN_Z_THRESHOLD = 4.0


# ============================================================
# FRESHNESS
#
# Nenhum EXTREME_UP nos 60 minutos anteriores.
# ============================================================

FRESH_LOOKBACK_BARS = 12

FRESH_LOOKBACK_MINUTES = (
    FRESH_LOOKBACK_BARS
    *
    BAR_MINUTES
)


# ============================================================
# TRADE
# ============================================================

SIDE = "LONG"

ENTRY_DELAY_BARS = 1

HOLD_BARS = 6

HOLD_MINUTES = (
    HOLD_BARS
    *
    BAR_MINUTES
)


# ============================================================
# COST MODEL
# ============================================================

BASE_COST = 0.0006

STRESS_COST = 0.0008


# ============================================================
# PAPER / TESTNET RISK BUDGET
# ============================================================

INITIAL_LEVERAGE = 1.0

POSITION_NOTIONAL_FRACTION = 0.25

MAX_OPEN_POSITIONS = 4

MAX_GROSS_EXPOSURE = 1.0


# ============================================================
# RESEARCH-ONLY STRESS
# ============================================================

SHADOW_LEVERAGE = 2.0

RESEARCH_STRESS_LEVERAGE = 3.0


# ============================================================
# EXITS
# ============================================================

USE_STOP_LOSS = False

USE_TAKE_PROFIT = False

TIME_EXIT_ONLY = True