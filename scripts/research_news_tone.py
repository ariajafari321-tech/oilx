"""Does news tone predict crude returns? The GDELT backtest the live tilt was waiting for.

The live news tilt (oilx/equities.py) is caged because headlines had no free archive.
GDELT's DOC API has one: daily average tone and article volume for a query, 2017->now.
This script grades the idea the same way every oilx signal is graded, before it is
allowed anywhere near position sizing.

Inputs (written by the fetch step into data/raw/):
    gdelt_tone_crude.csv    date,tone      daily avg article tone for "crude oil"
    gdelt_vol_crude.csv     date,volume    daily matching-article count (raw)

Tests, in order of increasing generosity to the idea:
    1. Contemporaneity check: does tone just TRACK same-day returns? (If corr(tone_t,
       ret_t) >> corr(tone_t, ret_{t+1}), the signal is a mirror, not a forecast.)
    2. Lead IC: rank-corr of tone_z (lagged 1 day, known at the close) vs next-day and
       next-5-day returns.
    3. Standalone signal: tanh(tone_z/1.5) traded with the full oilx risk layer and
       costs, 2018->now - the same harness as every real signal.
    4. Volume spike interaction: |returns| follow attention? (volume z vs |ret|.)

Verdict rules (written before running, pmx-style):
    - Lead IC t-stat > 2 AND standalone net Sharpe > 0.2 -> candidate for the stack
      (would still enter via walk-forward weights, never hand-weighted).
    - Contemporaneous-only -> the tilt stays caged at half-weight in the equity desk.
    - Nothing -> the tilt is retired. A signal that can't beat its own yardstick goes.

Run from oilx root:  python scripts/research_news_tone.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from oilx import config as cfg_mod, panel as panel_mod, risk  # noqa: E402

OUT = ROOT / "data" / "out" / "news_tone_study.txt"


def zscore(s: pd.Series, win: int = 60) -> pd.Series:
    m = s.rolling(win, min_periods=20).mean()
    sd = s.rolling(win, min_periods=20).std()
    return (s - m) / sd


def ic(x: pd.Series, y: pd.Series) -> tuple[float, float, int]:
    """Spearman rank IC with a crude t-stat (sqrt(n) scaling)."""
    df = pd.concat([x, y], axis=1).dropna()
    if len(df) < 50:
        return float("nan"), float("nan"), len(df)
    r = df.iloc[:, 0].rank().corr(df.iloc[:, 1].rank())
    return r, r * np.sqrt(len(df)), len(df)


def main() -> None:
    cfg = cfg_mod.load(ROOT / "config.toml")
    tone_p = cfg.raw_dir / "gdelt_tone_crude.csv"
    vol_p = cfg.raw_dir / "gdelt_vol_crude.csv"
    if not tone_p.exists():
        print(f"missing {tone_p} - run the GDELT fetch first")
        return
    tone = pd.read_csv(tone_p, parse_dates=["date"]).set_index("date")["tone"].sort_index()
    vol = (pd.read_csv(vol_p, parse_dates=["date"]).set_index("date")["volume"].sort_index()
           if vol_p.exists() else None)

    pnl = panel_mod.build(cfg)
    ret = pnl["ret"]
    # tone for calendar day t is known by that evening; trade at close t+1 -> lag 1
    tz = zscore(tone).reindex(ret.index).ffill(limit=3)
    tz_lag = tz.shift(1)

    lines = ["GDELT news-tone study (crude oil query, daily, 2017->now)", "=" * 64]

    # 1. mirror check
    c_same, t_same, n = ic(tz, ret)
    c_next, t_next, _ = ic(tz_lag, ret)
    ret5 = ret.rolling(5).sum().shift(-4)
    c_5d, t_5d, _ = ic(tz_lag, ret5)
    lines += [
        f"1. same-day   IC {c_same:+.3f} (t {t_same:+.1f}, n={n})   <- mirror, not skill",
        f"2. next-day   IC {c_next:+.3f} (t {t_next:+.1f})",
        f"   next-5-day IC {c_5d:+.3f} (t {t_5d:+.1f})",
    ]

    # 3. standalone backtest with the real risk layer + costs
    score = np.tanh(tz_lag / 1.5).fillna(0.0)
    vol_r = risk.realized_vol(ret, cfg.vol_lookback_days)
    lev = (cfg.vol_target / vol_r).clip(upper=cfg.max_leverage).shift(1)
    pos = (score * lev).fillna(0.0)
    costs = (pos.diff().abs().fillna(0) * cfg.spread_slippage_bps / 1e4
             + pos.abs() * cfg.holding_bps_per_day / 1e4)
    strat = (pos.shift(1) * ret - costs).loc["2018":]
    ann = strat.mean() * 252
    sd = strat.std() * np.sqrt(252)
    sharpe = ann / sd if sd > 0 else float("nan")
    eq = (1 + strat).cumprod()
    dd = (eq / eq.cummax() - 1).min()
    lines += [
        f"3. standalone net (2018->now): {ann:+.1%}/yr, Sharpe {sharpe:+.2f}, maxDD {dd:.1%}",
        f"   (same vol target, leverage cap, and costs as every oilx signal)",
    ]

    # 4. attention vs absolute moves
    if vol is not None:
        vz = zscore(vol).reindex(ret.index).ffill(limit=3)
        c_att, t_att, _ = ic(vz, ret.abs())
        c_att_lead, t_att_lead, _ = ic(vz.shift(1), ret.abs())
        lines += [
            f"4. attention: volume_z vs |ret| same-day IC {c_att:+.3f} (t {t_att:+.1f}); "
            f"lead IC {c_att_lead:+.3f} (t {t_att_lead:+.1f})",
        ]

    lines += [
        "",
        "verdict rules (fixed before running):",
        "  promote to stack  : lead-IC t > 2 AND standalone Sharpe > 0.2",
        "  keep caged        : contemporaneous only",
        "  retire the tilt   : neither",
    ]
    text = "\n".join(lines)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text)
    print(text)
    print(f"\nsaved: {OUT}")


if __name__ == "__main__":
    main()
