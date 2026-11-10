"""Daily backtest with walk-forward signal weights, costs, and the risk layer.

Timing convention (one place, so it can't drift): the score and position for day t are
set at the close of day t using data available by then; the position earns day t+1's
instrument return; trading costs are charged on day t+1 against the position *change*
made at t's close. Signals built from weekly releases enter the panel on their release
date via merge_asof, so nothing is seen early.

Walk-forward: once a year, each signal's weight is set from its own standalone gross
Sharpe over the trailing `train_years`, clipped at zero (a signal that lost money gets
the floor weight, never a flipped sign - sign-flipping is how backtests overfit), then
normalized. The first weights are equal, because there is no history to prefer one.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import risk, signals, stats
from .config import Config

log = logging.getLogger("oilx.backtest")


@dataclass
class Result:
    daily: pd.DataFrame          # scores, position, returns, nav
    weights: pd.DataFrame        # walk-forward weights by refit date
    summary: list[dict]          # period stats
    per_signal: list[dict]       # standalone stats per signal (full window, gross)
    honesty: dict                # bootstrap null, inverted book, buy & hold


def _walkforward_weights(scores: pd.DataFrame, ret: pd.Series, cfg: Config) -> pd.DataFrame:
    start = pd.Timestamp(cfg.backtest_start)
    refits = pd.date_range(start, scores.index.max(), freq=f"{cfg.refit_months}MS")
    rows = {}
    for t in refits:
        lo = t - pd.DateOffset(years=cfg.train_years)
        w = {}
        for name in scores.columns:
            s = scores[name].loc[lo:t - pd.Timedelta(days=1)]
            pnl = (s.shift(1) * ret).loc[lo:t - pd.Timedelta(days=1)]
            sr = stats.sharpe(pnl)
            w[name] = max(sr, 0.0) if np.isfinite(sr) else 0.0
        total = sum(w.values())
        if total <= 0:
            w = {k: 1.0 for k in w}
            total = len(w)
        w = {k: max(v / total, cfg.min_weight) for k, v in w.items()}
        norm = sum(w.values())
        rows[t] = {k: v / norm for k, v in w.items()}
    wdf = pd.DataFrame.from_dict(rows, orient="index").sort_index()
    wdf.loc[start - pd.Timedelta(days=1)] = 1.0 / len(scores.columns)  # equal until first refit
    return wdf.sort_index()


def run(panel: pd.DataFrame, cfg: Config) -> Result:
    scores = signals.compute_all(panel, cfg)
    ret = panel["ret"]
    bt_start = pd.Timestamp(cfg.backtest_start)

    weights = _walkforward_weights(scores, ret, cfg)
    score = risk.combine(scores, weights)
    inst_vol = risk.realized_vol(ret, cfg.vol_lookback_days)
    pos = risk.vol_target_position(score, inst_vol, cfg)
    pos = pos.loc[bt_start:].reindex(panel.index).fillna(0.0)
    pos.loc[:bt_start] = 0.0

    cost_rate = cfg.spread_slippage_bps / 1e4
    hold_rate = cfg.holding_bps_per_day / 1e4

    def pnl_of(p: pd.Series) -> tuple[pd.Series, pd.Series]:
        gross = p.shift(1) * ret
        costs = p.diff().abs().shift(1).fillna(0.0) * cost_rate + p.shift(1).abs() * hold_rate
        return gross, costs

    gross0, costs0 = pnl_of(pos)
    preview = (gross0 - costs0).loc[bt_start:]
    pos_k, kill_state = risk.apply_kill_switch(pos.loc[bt_start:], preview, cfg)
    pos_final = pos.copy()
    pos_final.loc[bt_start:] = pos_k

    gross, costs = pnl_of(pos_final)
    net = (gross - costs).loc[bt_start:]
    nav = (1 + net.fillna(0.0)).cumprod()

    daily = pd.DataFrame({
        "ret_instr": ret, "score": score, "position": pos_final,
        "gross": gross, "cost": costs, "net": net, "nav": nav,
        "kill_state": kill_state.reindex(panel.index),
    }).join(scores.add_prefix("s_"))
    daily = daily.loc[bt_start:]

    # ---- summaries
    periods = [("full", daily)]
    for lo, hi, lab in [("2007", "2016", "2007-2016"), ("2017", "2021", "2017-2021"),
                        ("2022", str(daily.index.max().year), "2022-now")]:
        chunk = daily.loc[lo:hi]
        if len(chunk) > 100:
            periods.append((lab, chunk))
    summary = []
    for lab, chunk in periods:
        nav_c = (1 + chunk["net"].fillna(0.0)).cumprod()
        summary.append(stats.summarize(chunk["net"], nav_c, lab))

    per_signal = []
    for name in scores.columns:
        s_pnl = (scores[name].shift(1) * ret).loc[bt_start:]
        per_signal.append({"signal": name, **{k: v for k, v in
                           stats.summarize(s_pnl, (1 + s_pnl.fillna(0)).cumprod(), name).items()
                           if k != "period"}})

    # ---- honesty checks
    null = stats.block_bootstrap_null(daily["position"], daily["ret_instr"], daily["cost"],
                                      n_boot=cfg.n_boot, block=cfg.block_days)
    realized_sr = stats.sharpe(net)
    pct = float((null < realized_sr).mean())
    inv_net = (-pos_final).shift(1) * ret - costs
    bh = ret.loc[bt_start:]
    honesty = {
        "realized_sharpe": round(realized_sr, 2),
        "bootstrap_null_mean": round(float(null.mean()), 2),
        "bootstrap_null_sd": round(float(null.std()), 2),
        "pct_of_null_below": round(pct, 3),
        "inverted_book_sharpe": round(stats.sharpe(inv_net.loc[bt_start:]), 2),
        "buy_hold_sharpe": round(stats.sharpe(bh), 2),
        "buy_hold_ann_return": round(stats.ann_return(bh), 4),
    }
    return Result(daily=daily, weights=weights, summary=summary,
                  per_signal=per_signal, honesty=honesty)


def save(res: Result, cfg: Config) -> None:
    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    res.daily.to_csv(cfg.out_dir / "backtest_daily.csv", float_format="%.6g")
    res.weights.to_csv(cfg.out_dir / "walkforward_weights.csv", float_format="%.4f")
    (cfg.out_dir / "backtest_summary.json").write_text(json.dumps({
        "summary": res.summary, "per_signal": res.per_signal, "honesty": res.honesty,
    }, indent=2))
    log.info("saved backtest outputs to %s", cfg.out_dir)
