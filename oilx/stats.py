"""Evaluation statistics, pmx-style: every headline number ships with its luck yardstick.

- Sharpe with its standard error (Lo 2002 approximation).
- Newey-West t-statistic on mean daily return (autocorrelation-robust).
- A circular block bootstrap null: scramble the *returns* in blocks against the real
  position series. If the strategy's Sharpe sits inside what misaligned data produces,
  the result is luck, whatever the point estimate says.
- The both-tails rule from the pmx trader study: always also report the inverted book.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ann_return(r: pd.Series) -> float:
    r = r.dropna()
    return float(r.mean() * 252)


def ann_vol(r: pd.Series) -> float:
    r = r.dropna()
    return float(r.std(ddof=1) * np.sqrt(252))


def sharpe(r: pd.Series) -> float:
    v = ann_vol(r)
    return float(ann_return(r) / v) if v > 0 else float("nan")


def sharpe_se(r: pd.Series) -> float:
    """Lo (2002) iid-ish standard error of the annualized Sharpe."""
    r = r.dropna()
    n = len(r)
    if n < 30:
        return float("nan")
    sr_d = r.mean() / r.std(ddof=1) if r.std(ddof=1) > 0 else 0.0
    return float(np.sqrt((1 + 0.5 * sr_d ** 2) / n) * np.sqrt(252))


def newey_west_t(r: pd.Series, lags: int = 10) -> float:
    r = r.dropna().to_numpy()
    n = len(r)
    if n < 30:
        return float("nan")
    mu = r.mean()
    e = r - mu
    s = e @ e / n
    for k in range(1, lags + 1):
        w = 1 - k / (lags + 1)
        s += 2 * w * (e[k:] @ e[:-k]) / n
    se = np.sqrt(s / n)
    return float(mu / se) if se > 0 else float("nan")


def max_drawdown(nav: pd.Series) -> float:
    peak = nav.cummax()
    return float((nav / peak - 1).min())


def block_bootstrap_null(position: pd.Series, ret: pd.Series, cost: pd.Series,
                         n_boot: int = 500, block: int = 10, seed: int = 7) -> np.ndarray:
    """Sharpe distribution when the same positions trade block-scrambled returns.

    The position series (with all its autocorrelation and leverage habits) is kept as it
    is; the instrument's returns are resampled in circular blocks, which preserves their
    own clustering but destroys any alignment with the positions. Costs stay as charged.
    """
    rng = np.random.default_rng(seed)
    pos = position.fillna(0.0).to_numpy()
    r = ret.fillna(0.0).to_numpy()
    c = cost.fillna(0.0).to_numpy()
    n = len(r)
    out = np.empty(n_boot)
    for b in range(n_boot):
        idx = np.empty(n, dtype=int)
        k = 0
        while k < n:
            s = rng.integers(0, n)
            m = min(block, n - k)
            idx[k:k + m] = (s + np.arange(m)) % n
            k += m
        pnl = pos * r[idx] - c
        sd = pnl.std(ddof=1)
        out[b] = (pnl.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0
    return out


def summarize(net: pd.Series, nav: pd.Series, label: str) -> dict:
    return {
        "period": label,
        "days": int(net.dropna().shape[0]),
        "ann_return": round(ann_return(net), 4),
        "ann_vol": round(ann_vol(net), 4),
        "sharpe": round(sharpe(net), 2),
        "sharpe_se": round(sharpe_se(net), 2),
        "nw_t": round(newey_west_t(net), 2),
        "max_drawdown": round(max_drawdown(nav), 4),
    }
