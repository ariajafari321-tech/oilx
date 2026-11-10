"""Desk-note tests: sizing honesty, exposure-map correctness, state handling."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from oilx import recommend
from tests.test_oilx import make_cfg


def toy_panel(score_tilt: float, n: int = 400, seed: int = 2):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    ret = pd.Series(rng.normal(score_tilt * 1e-3, 0.02, n), index=idx)
    px = 94 * (1 + ret).cumprod()
    pnl = pd.DataFrame({"instr": px, "ret": ret, "cl": px}, index=idx)
    pnl["crack"] = 20 + np.cumsum(rng.normal(score_tilt * 0.05, 0.3, n))
    pnl["inv_level_z"] = -score_tilt * 1.0
    pnl["inv_surprise_z"] = -score_tilt * 1.0
    pnl["inv_stocks"] = 400000 + (np.arange(n) // 5)
    pnl["cot_z"] = 0.0
    pnl["ovx"] = 45.0
    return pnl


def test_note_long_state(tmp_path, monkeypatch):
    cfg = make_cfg(tmp_path, active=["mom", "crack", "inv_level", "inv_surprise", "cot"])
    monkeypatch.setattr(recommend, "live_curve", lambda cl: None)
    note = recommend.build_note(cfg, toy_panel(+3), nav=100_000)
    assert "lean bullish" in note and "Buy" in note
    assert "Not investment advice" in note.replace("not investment advice", "Not investment advice")


def test_note_flat_state_recommends_nothing(tmp_path, monkeypatch):
    cfg = make_cfg(tmp_path, active=["cot"])  # cot_z=0 -> dead zone -> flat
    monkeypatch.setattr(recommend, "live_curve", lambda cl: None)
    note = recommend.build_note(cfg, toy_panel(0), nav=100_000)
    assert "no trade today" in note or "Flat book" in note


def test_small_nav_warns_below_one_contract(tmp_path, monkeypatch):
    cfg = make_cfg(tmp_path, active=["mom", "crack", "inv_level", "inv_surprise", "cot"])
    monkeypatch.setattr(recommend, "live_curve", lambda cl: None)
    note = recommend.build_note(cfg, toy_panel(+3), nav=2_000)
    assert "below one micro contract" in note


def test_curve_agreement_changes_wording(tmp_path, monkeypatch):
    cfg = make_cfg(tmp_path, active=["mom", "crack", "inv_level", "inv_surprise", "cot"])
    back = {"m1": 95.0, "m2": 93.0, "ticks": ["CLX26.NYM", "CLZ26.NYM"],
            "carry_ann": 0.25, "shape": "backwardation"}
    monkeypatch.setattr(recommend, "live_curve", lambda cl: back)
    note = recommend.build_note(cfg, toy_panel(+3), nav=100_000)
    assert "Curve agrees" in note
    cont = dict(back, m1=93.0, m2=95.0, carry_ann=-0.25, shape="contango")
    monkeypatch.setattr(recommend, "live_curve", lambda cl: cont)
    note = recommend.build_note(cfg, toy_panel(+3), nav=100_000)
    assert "Curve disagrees" in note


def test_exposure_map_facts():
    buckets = {t: b for t, b, _ in recommend.EXPOSURE_MAP}
    assert buckets["MPC"] == "Refiner"            # Marathon Petroleum is NOT a crude play
    assert "pure play" in buckets["FANG"]
    assert "MRO" in recommend.RETIRED[0][0]       # the retired-name warning exists
    note_text = " ".join(d for _, _, d in recommend.EXPOSURE_MAP)
    assert "crack spread" in note_text            # refiner driver stated correctly
