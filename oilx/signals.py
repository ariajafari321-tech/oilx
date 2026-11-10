"""The signals. Each one maps the panel to a score in [-1, +1] per day, where +1 means
"fully long crude" before risk scaling. Every score on day t uses only data available on
day t; the backtest then trades at the close of t and earns the return of t+1.

Keep each signal boring and explainable in one sentence - the edge claim lives in the
combination and the risk control, not in any single clever predictor.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Config


def _squash(z: pd.Series, scale: float) -> pd.Series:
    return np.tanh(z / scale)


def _zscore(x: pd.Series, window: int, min_periods: int | None = None) -> pd.Series:
    mp = min_periods or window // 2
    mean = x.rolling(window, min_periods=mp).mean()
    sd = x.rolling(window, min_periods=mp).std()
    return (x - mean) / sd


def sig_mom(panel: pd.DataFrame, cfg: Config) -> pd.Series:
    """Trend: vol-scaled 3-month and 12-month (skipping the latest month) returns.
    One sentence: oil trends; follow it at constant risk.

    GHR conditioning (2026-10-22): Gorton-Hayashi-Rouwenhorst show momentum premia
    concentrate in low-inventory states, and Fuertes-Miffre-Rallis's double-sort is the
    cross-sectional version of the same fact. Single-market analog: trend trades 1.25x
    when the inventory state agrees with it (tight + uptrend, glut + downtrend) and
    0.75x when it fights it. Theory-prescribed, not fitted; off via config."""
    px = panel["instr"]
    vol = panel["ret"].rolling(63, min_periods=40).std() * np.sqrt(252)
    r63 = px.pct_change(63)
    r252x21 = px.pct_change(252 - 21).shift(21)
    z = 0.5 * (r63 / (vol * np.sqrt(63 / 252)) + r252x21 / (vol * np.sqrt(231 / 252)))
    score = _squash(z, cfg.z_scale)
    if cfg.mom_inv_conditioning and "inv_level_z" in panel:
        tight = -panel["inv_level_z"]  # positive = stocks below seasonal = tight
        agree = np.sign(score) == np.sign(tight)
        scale = pd.Series(np.where(agree, 1.25, 0.75), index=score.index)
        scale[tight.isna()] = 1.0
        score = (score * scale).clip(-1, 1)
    return score.rename("mom")


def sig_crack(panel: pd.DataFrame, cfg: Config) -> pd.Series:
    """Refining margin: a rising 3-2-1 crack spread means refiners are being paid more
    to turn crude into fuel, which pulls crude demand; fade works the other way.
    Signal = 63-day z-score of the crack level."""
    z = _zscore(panel["crack"], 252, 126)
    return _squash(z, cfg.z_scale).rename("crack")


def sig_inv_level(panel: pd.DataFrame, cfg: Config) -> pd.Series:
    """Scarcity: inventories low versus the seasonal norm mean a tight prompt market
    (the same economics that puts the futures curve in backwardation). Long when stocks
    are below seasonal, short when they're above.

    GHR asymmetry (2026-10-22): the convenience yield is a decreasing, NON-LINEAR
    function of inventories - low stocks matter far more than high stocks. So the
    tight side (stocks below seasonal) counts in full and the glut side is dampened
    by `inv_glut_dampen`. Theory-prescribed, not fitted."""
    z = panel["inv_level_z"]
    tight_signal = -z  # positive = tight = long
    eff = tight_signal.where(tight_signal >= 0, tight_signal * cfg.inv_glut_dampen)
    return _squash(eff, cfg.z_scale).rename("inv_level")


def sig_inv_surprise(panel: pd.DataFrame, cfg: Config) -> pd.Series:
    """The Wednesday event: a bigger-than-seasonal draw is bullish, a surprise build is
    bearish. Active from the release until the next one (the weekly merge handles that),
    decayed by how stale the number is."""
    z = panel["inv_surprise_z"]
    score = _squash(-z, cfg.z_scale)
    # decay: full strength the week of release, half the next (staleness via value change)
    changed = panel["inv_stocks"].ne(panel["inv_stocks"].shift())
    age = changed.groupby(changed.cumsum()).cumcount()
    return (score * (0.5 ** (age / 5.0))).rename("inv_surprise")


def sig_cot(panel: pd.DataFrame, cfg: Config) -> pd.Series:
    """Positioning: when speculators are crowded long versus their own three-year norm,
    the marginal buyer is already in; fade the extreme (and vice versa). Dead zone inside
    |z| <= 1 because moderate positioning says nothing."""
    z = panel["cot_z"]
    excess = np.sign(z) * np.maximum(z.abs() - cfg.cot_dead_zone, 0.0)
    return _squash(-excess, cfg.z_scale).rename("cot")


SIGNALS = {
    "mom": sig_mom,
    "crack": sig_crack,
    "inv_level": sig_inv_level,
    "inv_surprise": sig_inv_surprise,
    "cot": sig_cot,
}


def compute_all(panel: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    out = pd.DataFrame(index=panel.index)
    for name in cfg.active:
        out[name] = SIGNALS[name](panel, cfg)
    return out
