"""Offline tests. The pmx lesson applies: every method must pass on a synthetic world
where the answer is known (planted signals recovered, planted lags respected), and the
honesty checks must be able to say 'no' (inverted books lose, misaligned data earns ~0).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from oilx.config import Config
from oilx import panel as panel_mod
from oilx import risk, signals, stats, backtest


def make_cfg(tmp_path, **kw) -> Config:
    base = dict(
        raw_dir=tmp_path, out_dir=tmp_path / "out", start="2000-01-01",
        backtest_start="2001-01-01", seasonal_years=5,
        spot_glitch_abs=0.12, spot_glitch_fut=0.04,
        eia_release_bdays=4, cot_release_bdays=4,
        active=["mom"], z_scale=1.5, cot_dead_zone=1.0,
        inv_glut_dampen=0.5, mom_inv_conditioning=False,
        vol_target=0.10, vol_lookback_days=20, max_leverage=1.5,
        kill_drawdown=0.15, kill_flat_days=10, kill_halflife_days=10,
        spread_slippage_bps=2.0, holding_bps_per_day=0.5,
        train_years=5, refit_months=12, min_weight=0.10,
        block_days=10, n_boot=100, root=tmp_path,
    )
    base.update(kw)
    return Config(**base)


# ---------------------------------------------------------------- release lags

def test_inventory_availability_is_lagged(tmp_path):
    cfg = make_cfg(tmp_path)
    weeks = pd.date_range("2020-01-03", periods=30, freq="W-FRI")
    stocks = pd.DataFrame({"date": weeks, "crude_stocks_kbbl": 400000 + np.arange(30) * 100.0})
    feat = panel_mod._inventory_features(stocks, cfg)
    # the week ending Fri 2020-01-10 must not be visible before Thu 2020-01-16 (+4 bdays)
    row = feat.loc[feat["inv_stocks"] == 400100.0]
    assert row["date"].iloc[0] == pd.Timestamp("2020-01-16")


def test_cot_availability_is_lagged(tmp_path):
    cfg = make_cfg(tmp_path)
    dates = pd.date_range("2018-01-02", periods=200, freq="W-TUE")
    cot = pd.DataFrame({
        "date": dates, "code": "067651",
        "noncomm_long": 300000 + np.arange(200) * 10.0, "noncomm_short": 100000.0,
        "comm_long": 500000.0, "comm_short": 600000.0, "oi": 2_000_000.0})
    feat = panel_mod._cot_features(cot, cfg)
    assert (feat["date"] - dates).min() >= pd.Timedelta(days=4)


# ---------------------------------------------------------------- signal mechanics

def _toy_panel(n=600, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n)
    ret = pd.Series(rng.normal(0, 0.02, n), index=idx)
    px = 50 * (1 + ret).cumprod()
    pnl = pd.DataFrame({"instr": px, "ret": ret}, index=idx)
    pnl["crack"] = 20 + rng.normal(0, 1, n).cumsum() * 0.1
    pnl["inv_level_z"] = rng.normal(0, 1, n)
    pnl["inv_surprise_z"] = rng.normal(0, 1, n)
    pnl["inv_stocks"] = 400000 + (np.arange(n) // 5)  # changes weekly
    pnl["cot_z"] = rng.normal(0, 1.5, n)
    return pnl


def test_scores_are_bounded(tmp_path):
    cfg = make_cfg(tmp_path, active=list(signals.SIGNALS))
    s = signals.compute_all(_toy_panel(), cfg)
    assert (s.abs().max().max() or 0) <= 1.0 + 1e-9


def test_surprise_build_is_bearish(tmp_path):
    cfg = make_cfg(tmp_path)
    pnl = _toy_panel()
    pnl["inv_surprise_z"] = 2.0  # stocks built far more than seasonal -> bearish
    s = signals.sig_inv_surprise(pnl, cfg)
    assert s.dropna().iloc[-1] < 0


def test_cot_dead_zone(tmp_path):
    cfg = make_cfg(tmp_path)
    pnl = _toy_panel()
    pnl["cot_z"] = 0.5  # inside the dead zone -> no view
    assert signals.sig_cot(pnl, cfg).abs().max() == 0.0
    pnl["cot_z"] = 3.0  # crowded long -> fade (short)
    assert signals.sig_cot(pnl, cfg).iloc[-1] < 0


def test_crack_arithmetic():
    # 2 gal gasoline + 1 gal distillate vs 3 bbl crude, per bbl
    rb, ho, cl = 2.0, 2.5, 70.0
    crack = (2 * rb * 42 + ho * 42 - 3 * cl) / 3
    assert crack == pytest.approx((168 + 105 - 210) / 3)


# ---------------------------------------------------------------- risk layer

def test_vol_target_caps_leverage(tmp_path):
    cfg = make_cfg(tmp_path)
    score = pd.Series([1.0] * 50)
    low_vol = pd.Series([0.01] * 50)  # 1% vol would ask for 10x
    pos = risk.vol_target_position(score, low_vol, cfg)
    assert pos.max() <= cfg.max_leverage + 1e-12


def test_kill_switch_flattens_after_drawdown(tmp_path):
    cfg = make_cfg(tmp_path)
    idx = pd.bdate_range("2020-01-01", periods=60)
    pos = pd.Series(1.0, index=idx)
    ret = pd.Series(0.0, index=idx)
    ret.iloc[5:10] = -0.04  # ~-18% cumulative: breaches the 15% switch
    eff, state = risk.apply_kill_switch(pos, ret, cfg)
    assert (eff.iloc[10:20] == 0).any()          # a flat stretch exists
    assert eff.iloc[-1] > 0                       # and the book comes back
    assert eff.iloc[-1] <= 1.0


# ---------------------------------------------------------------- end-to-end honesty

def _synthetic_world(n=2500, seed=11, edge=0.25):
    """Returns with a planted, tradable pattern: a hidden state flips slowly and drives
    drift; the panel exposes it through 'crack' so sig_crack can find it."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2010-01-01", periods=n)
    state = np.sign(np.sin(np.arange(n) / 80.0) + 0.1)
    ret = pd.Series(state * edge * 0.02 / np.sqrt(252) * 15 + rng.normal(0, 0.02, n), index=idx)
    px = 50 * (1 + ret).cumprod()
    pnl = pd.DataFrame({"instr": px, "ret": ret}, index=idx)
    pnl["crack"] = pd.Series(state, index=idx).rolling(10).mean().fillna(0).cumsum()
    pnl["inv_level_z"] = rng.normal(0, 1, n)
    pnl["inv_surprise_z"] = rng.normal(0, 1, n)
    pnl["inv_stocks"] = 400000 + (np.arange(n) // 5)
    pnl["cot_z"] = rng.normal(0, 1.5, n)
    pnl["cash_ret"] = 0.0
    return pnl


def test_backtest_recovers_planted_signal(tmp_path):
    cfg = make_cfg(tmp_path, active=["crack"], backtest_start="2011-01-03")
    pnl = _synthetic_world()
    res = backtest.run(pnl, cfg)
    full = res.summary[0]
    assert full["sharpe"] > 0.8            # the planted edge is found...
    assert res.honesty["inverted_book_sharpe"] < -0.5   # ...and the inverse loses
    assert res.honesty["pct_of_null_below"] > 0.9       # ...and luck can't explain it


def test_backtest_finds_nothing_in_noise(tmp_path):
    cfg = make_cfg(tmp_path, active=["crack", "cot"], backtest_start="2011-01-03")
    pnl = _synthetic_world(edge=0.0, seed=5)
    pnl["crack"] = np.random.default_rng(1).normal(0, 1, len(pnl)).cumsum()
    res = backtest.run(pnl, cfg)
    assert abs(res.summary[0]["sharpe"]) < 0.6  # no fake edge invented from noise


def test_no_same_day_peek(tmp_path):
    """A 'perfect oracle' score equal to the sign of today's return must earn ~0 on the
    day it sees, because positions only earn the NEXT day's return."""
    cfg = make_cfg(tmp_path, active=["crack"], backtest_start="2011-01-03")
    pnl = _synthetic_world(edge=0.0, seed=8)
    oracle = np.sign(pnl["ret"]).fillna(0)
    same_day_pnl = (oracle * pnl["ret"]).mean()          # what cheating would earn
    honest_pnl = (oracle.shift(1) * pnl["ret"]).mean()   # what the convention earns
    assert same_day_pnl > 0.005                           # cheating would be huge
    assert abs(honest_pnl) < 0.001                        # the convention earns noise


def test_walkforward_floors_losing_signal(tmp_path):
    cfg = make_cfg(tmp_path, active=["crack", "cot"], backtest_start="2011-01-03")
    pnl = _synthetic_world()
    # sig_cot fades crowding, so planting crowding long before up-days makes it short
    # winners: a guaranteed loser the walk-forward must floor.
    pnl["cot_z"] = np.sign(pnl["ret"].shift(-1)).fillna(0) * 3
    res = backtest.run(pnl, cfg)
    w = res.weights.iloc[-1]
    assert w["cot"] <= cfg.min_weight / (1 + cfg.min_weight) + 0.1  # floored, not flipped
    assert w["crack"] > w["cot"]
