"""Tests for the 2026-10-22 upgrades: range-market pricing, GHR asymmetry and
momentum-inventory conditioning, curve fallback guard."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from oilx import kalshi, signals
from tests.test_oilx import make_cfg, _toy_panel

NOW = 1792060000.0


def mk(st, lo, hi, yb, ya, oi=1000.0, close="2026-10-30T18:30:00Z", tick="T"):
    return {"ticker": f"{tick}-{lo}-{hi}", "strike_type": st, "floor_strike": lo,
            "cap_strike": hi, "yes_bid": yb, "yes_ask": ya, "open_interest": oi,
            "close_time": close}


# ---------------------------------------------------------------- range pricing

def test_between_equals_digital_difference():
    t_years = (pd.Timestamp("2026-10-30T18:30:00Z").timestamp() - NOW) / (365 * 86400)
    p_lo = kalshi.digital_above(94.0, 92.0, 0.5, t_years)
    p_hi = kalshi.digital_above(94.0, 96.0, 0.5, t_years)
    strip = [mk("between", 92.0, 96.0, 0.06, 0.08)]  # priced far below model fair
    sigs = kalshi.scan({"KXWTIW": strip}, fwd=94.0, sigma=0.5, now=NOW, min_edge=0.01)
    yes = [s for s in sigs if s.side == "yes"]
    assert yes and yes[0].model_p == pytest.approx(p_lo - p_hi, abs=1e-4)


def test_less_type_prices_complement():
    strip = [mk("less", None, 90.0, 0.05, 0.08)]
    sigs = kalshi.scan({"X": strip}, fwd=94.0, sigma=0.5, now=NOW, min_edge=0.0)
    p = 1 - kalshi.digital_above(94.0, 90.0, 0.5, (pd.Timestamp("2026-10-30T18:30:00Z").timestamp() - NOW) / (365 * 86400))
    yes = [s for s in sigs if s.side == "yes"]
    assert yes and yes[0].model_p == pytest.approx(p, abs=1e-3)


def test_unknown_structure_never_priced():
    strip = [mk("weird", 90.0, 95.0, 0.40, 0.45)]
    assert kalshi.scan({"X": strip}, fwd=94.0, sigma=0.5, now=NOW, min_edge=0.0) == []


def test_range_strip_stale_guard():
    # market prices the 88-90 bucket highest, but our quote says 94 -> stale
    strip = [mk("between", 88.0, 90.0, 0.55, 0.60),
             mk("between", 90.0, 92.0, 0.20, 0.25),
             mk("between", 92.0, 94.0, 0.05, 0.10)]
    imp = kalshi.implied_forward_from_ranges(strip)
    assert imp is not None and imp[0] == pytest.approx(89.0)
    sigs = kalshi.scan({"X": strip}, fwd=94.0, sigma=0.3, now=NOW, min_edge=0.01)
    assert sigs and all("stale_underlying" in s.flags for s in sigs)


# ---------------------------------------------------------------- GHR upgrades

def test_inventory_glut_side_is_dampened(tmp_path):
    cfg = make_cfg(tmp_path)
    pnl = _toy_panel()
    pnl["inv_level_z"] = -2.0  # tight
    tight_score = signals.sig_inv_level(pnl, cfg).iloc[-1]
    pnl["inv_level_z"] = 2.0   # glut
    glut_score = signals.sig_inv_level(pnl, cfg).iloc[-1]
    assert tight_score > 0 > glut_score
    assert abs(tight_score) > abs(glut_score)  # non-linear per GHR


def test_mom_conditioning_scales_by_agreement(tmp_path):
    base = make_cfg(tmp_path, mom_inv_conditioning=False)
    cond = make_cfg(tmp_path, mom_inv_conditioning=True)
    pnl = _toy_panel(seed=9)
    pnl["inv_level_z"] = -3.0  # very tight -> agrees with longs, fights shorts
    s0 = signals.sig_mom(pnl, base)
    s1 = signals.sig_mom(pnl, cond)
    longs = s0 > 0.1
    shorts = s0 < -0.1
    assert (s1[longs].abs() >= s0[longs].abs() - 1e-12).all()   # longs boosted (or clipped)
    assert (s1[shorts].abs() <= s0[shorts].abs() + 1e-12).all() # shorts cut
    assert s1.abs().max() <= 1.0 + 1e-9
