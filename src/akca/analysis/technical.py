from __future__ import annotations

from math import sqrt
from statistics import mean, pstdev

def _valid_prices(rows: list[dict]) -> list[dict]:
    valid = []
    for row in rows:
        value = row.get("adjusted_close") or row.get("close")
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if value > 0:
            valid.append({**row, "_price": value})
    return sorted(valid, key=lambda r: r["date"])

def _sma(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return mean(values[-window:])

def _ema(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    alpha = 2 / (window + 1)
    result = mean(values[:window])
    for value in values[window:]:
        result = alpha * value + (1 - alpha) * result
    return result

def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(change, 0.0) for change in changes]
    losses = [abs(min(change, 0.0)) for change in changes]

    average_gain = mean(gains[:period])
    average_loss = mean(losses[:period])
    for gain, loss in zip(gains[period:], losses[period:]):
        average_gain = ((average_gain * (period - 1)) + gain) / period
        average_loss = ((average_loss * (period - 1)) + loss) / period

    if average_loss == 0:
        return 100.0 if average_gain > 0 else 50.0
    relative_strength = average_gain / average_loss
    return 100 - 100 / (1 + relative_strength)

def _max_drawdown(values: list[float]) -> float | None:
    if not values:
        return None
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1)
    return worst * 100

def analyze_price_history(rows: list[dict]) -> dict:
    data = _valid_prices(rows)
    values = [r["_price"] for r in data]
    if len(values) < 2:
        return {
            "status": "insufficient_history",
            "observations": len(values),
            "indicators": {},
            "returns_pct": {},
            "risk": {},
        }
    def period_return(days: int) -> float | None:
        if len(values) <= days:
            return None
        return (values[-1] / values[-1 - days] - 1) * 100

    daily_returns = [
        values[i] / values[i - 1] - 1
        for i in range(1, len(values))
        if values[i - 1] > 0
    ]
    volatility = pstdev(daily_returns[-252:]) * sqrt(252) * 100 if len(daily_returns) > 1 else None
    sma50, sma200 = _sma(values, 50), _sma(values, 200)
    ema12, ema26 = _ema(values, 12), _ema(values, 26)
    macd = ema12 - ema26 if ema12 is not None and ema26 is not None else None
    latest = values[-1]
    high_52 = max(values[-min(252, len(values)):])
    low_52 = min(values[-min(252, len(values)):])
    returns = {
        "1m": period_return(21),
        "3m": period_return(63),
        "6m": period_return(126),
        "1y": period_return(252),
        "2y": period_return(504),
    }
    max_dd = _max_drawdown(values[-min(504, len(values)):])
    latest_rsi = _rsi(values)
    if sma50 is None or sma200 is None or latest_rsi is None:
        trend = "insufficient_history"
    elif latest > sma50 > sma200:
        trend = "bullish_alignment"
    elif latest < sma50 < sma200:
        trend = "bearish_alignment"
    else:
        trend = "mixed"
    return {
        "status": "ok",
        "observations": len(values),
        "as_of": data[-1]["date"],
        "currency": None,
        "last_price": latest,
        "indicators": {
            "sma_50": sma50,
            "sma_200": sma200,
            "ema_12": ema12,
            "ema_26": ema26,
            "macd_line": macd,
            "rsi_14": latest_rsi,
            "high_52w": high_52,
            "low_52w": low_52,
            "trend_state": trend,
        },
        "returns_pct": returns,
        "risk": {
            "annualized_volatility_pct": volatility,
            "max_drawdown_2y_pct": max_dd,
            "daily_return_observations": len(daily_returns),
        },
    }
