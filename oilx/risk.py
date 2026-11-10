"""Risk layer: the part a desk actually cares about.

Order of operations each day:
1. combine signal scores with the current walk-forward weights -> raw score in [-1, 1]
2. volatility targeting: position = score * (vol_target / realized vol), capped
3. kill switch: if the trailing drawdown breaches the limit, go flat for a cooling-off
   period, then re-enter at half size and recover geometrically.

The kill switch is deliberately dumb. It exists so one broken signal or one regime
change cannot spend the whole risk budget, and its cost shows up honestly in the
backtest instead of being assumed away.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Config


def realized_vol(ret: pd.Series, lookback: int) -> pd.Series:
    """Annualized EWMA volatility of the instrument, lagged one day (no same-day peek)."""
    var = ret.pow(2).ewm(span=lookback, min_periods=max(5, lookback // 2)).mean()
    return (np.sqrt(var * 252)).shift(1)


def combine(scores: pd.DataFrame, weights: pd.DataFrame) -> pd.Series:
    """Weighted sum of signal scores, weights normalized to sum to 1 per day, then the
    combined score is rescaled by its own trailing RMS so diversification across signals
    doesn't quietly de-lever the book (that's what makes the vol target actually bind)."""
    w = weights.reindex(scores.index).ffill()
    w = w.div(w.sum(axis=1), axis=0)
    raw = (scores * w).sum(axis=1, min_count=1)
    rms = raw.pow(2).rolling(252, min_periods=60).mean().pow(0.5).shift(1).clip(lower=0.05)
    return (raw / rms).clip(-1.5, 1.5) / 1.5


def vol_target_position(score: pd.Series, inst_vol: pd.Series, cfg: Config) -> pd.Series:
    scalar = (cfg.vol_target / inst_vol).clip(upper=cfg.max_leverage)
    return (score * scalar).clip(-cfg.max_leverage, cfg.max_leverage)


def apply_kill_switch(position: pd.Series, net_ret_preview: pd.Series, cfg: Config) -> tuple[pd.Series, pd.Series]:
    """Walk the equity curve; when trailing drawdown breaches `kill_drawdown`, flatten for
    `kill_flat_days` trading days, then scale back in. Returns (position, kill_state).

    The preview returns are what the book would earn with no kill switch; the switch is
    path-dependent so it has to be a loop, and the final P&L is recomputed afterwards
    from the adjusted positions by the backtest (so costs of the extra trading count).
    """
    pos = position.copy().fillna(0.0)
    state = pd.Series(0.0, index=pos.index)  # 1 = fully on, 0 = killed
    nav, peak = 1.0, 1.0
    flat_left = 0
    scale = 1.0
    out = np.empty(len(pos))
    for i, (p, r) in enumerate(zip(pos.to_numpy(), net_ret_preview.fillna(0.0).to_numpy())):
        if flat_left > 0:
            flat_left -= 1
            eff = 0.0
            if flat_left == 0:
                scale = 0.5
                nav, peak = 1.0, 1.0  # restart the drawdown clock on re-entry
        else:
            eff = p * scale
            nav *= (1 + r * scale)
            peak = max(peak, nav)
            if scale < 1.0:
                scale = min(1.0, scale * 2 ** (1 / cfg.kill_halflife_days))
            if peak > 0 and nav / peak - 1 < -cfg.kill_drawdown:
                flat_left = cfg.kill_flat_days
                eff = 0.0
        out[i] = eff
        state.iloc[i] = scale if flat_left == 0 else 0.0
    return pd.Series(out, index=pos.index), state
