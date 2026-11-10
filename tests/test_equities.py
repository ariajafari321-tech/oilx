"""Equity desk tests: universe sanity, the news lexicon, picker routing, grading."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from oilx import equities
from oilx.equities import View


# ---------------------------------------------------------------- universe sanity

def test_universe_no_duplicates_and_no_mro():
    tickers = [u["ticker"] for u in equities.UNIVERSE]
    assert len(tickers) == len(set(tickers))
    assert "MRO" not in tickers  # absorbed by COP in 2024 - the classic stale-universe bug


def test_refiners_are_not_oil_exposure():
    # the classic interview mistake, encoded: refiners' crude beta must be <= 0
    for u in equities.UNIVERSE:
        if u["bucket"] == "refiner":
            assert u["crude_beta"] <= 0, f"{u['ticker']}: crude is a refiner's INPUT cost"
            assert u["crack_beta"] > 0
        if u["bucket"] == "upstream":
            assert u["crude_beta"] >= 0.9


def test_midstream_is_the_defensive_bucket():
    mids = [u for u in equities.UNIVERSE if u["bucket"] == "midstream"]
    others = [u for u in equities.UNIVERSE if u["bucket"] in ("upstream", "refiner")]
    assert min(u["defensive"] for u in mids) > max(u["defensive"] for u in others)


# ---------------------------------------------------------------- news lexicon

def test_news_tilt_direction():
    bull = ["OPEC+ extends cut through March", "Drone attack on Saudi export terminal",
            "Crude stockpiles fell sharply last week"]
    bear = ["OPEC+ agrees output hike", "Ceasefire talks progress in the Gulf",
            "Crude inventories rose; demand concern grows"]
    t_bull, m_bull = equities.news_tilt(bull)
    t_bear, m_bear = equities.news_tilt(bear)
    assert t_bull > 0 and len(m_bull) == 3
    assert t_bear < 0 and len(m_bear) == 3


def test_news_tilt_quiet_tape_and_dilution():
    assert equities.news_tilt(["Oil majors report earnings next week"]) == (0.0, [])
    # one scary headline among many quiet ones is a whisper, not a regime
    noisy = ["Nothing headline"] * 39 + ["Attack on tanker in the Red Sea"]
    tilt, m = equities.news_tilt(noisy)
    assert 0 < tilt < 0.1 and len(m) == 1


def test_news_tilt_is_clipped():
    tilt, _ = equities.news_tilt(["supply cuts deepen"] * 50)
    assert tilt == 1.0


# ---------------------------------------------------------------- picker routing

def test_bullish_crude_routes_to_high_beta_upstream():
    out = equities.pick(View(crude=0.8, crack=0.0, vol=0.30, tilt=0.0, kill=False))
    assert out["pick"]["action"] == "long"
    assert out["pick"]["bucket"] in ("upstream", "etf")
    assert out["ranked"][0]["ticker"] == "OXY"  # highest stated crude beta


def test_wide_crack_bearish_crude_routes_to_refiner():
    out = equities.pick(View(crude=-0.3, crack=0.8, vol=0.30, tilt=0.0, kill=False))
    assert out["pick"]["action"] == "long"
    assert out["pick"]["bucket"] == "refiner"
    # and the avoid side should be a high-crude-beta name
    assert out["avoid"]["ticker"] in ("OXY", "DVN", "FANG", "XOP", "USO", "EOG", "HAL")


def test_weak_view_means_no_trade():
    out = equities.pick(View(crude=0.03, crack=0.02, vol=0.30, tilt=0.0, kill=False))
    assert out["pick"]["action"] == "none"
    assert "cash" in out["pick"]["reason"]


def test_kill_switch_zeroes_the_desk():
    out = equities.pick(View(crude=0.9, crack=0.9, vol=0.30, tilt=0.9, kill=True))
    assert out["pick"]["action"] == "none"
    assert "kill" in out["pick"]["reason"].lower()


def test_high_vol_weak_view_prefers_midstream_in_ranking():
    rows = equities.rank(View(crude=0.0, crack=0.0, vol=0.70, tilt=0.0, kill=False))
    assert rows[0]["bucket"] == "midstream"


def test_news_tilt_tilts_but_never_dominates():
    base = equities.rank(View(crude=0.3, crack=0.0, vol=0.30, tilt=0.0, kill=False))
    tilted = equities.rank(View(crude=0.3, crack=0.0, vol=0.30, tilt=-1.0, kill=False))
    s0 = {r["ticker"]: r["score"] for r in base}
    s1 = {r["ticker"]: r["score"] for r in tilted}
    assert s1["OXY"] < s0["OXY"]                      # max bearish news drags scores...
    assert s1["OXY"] == s0["OXY"] - 0.5 * 1.3         # ...by exactly tilt * 0.5 * beta


# ---------------------------------------------------------------- grading

def test_equity_score_relative_to_xle(tmp_path):
    old = (datetime.now(timezone.utc) - timedelta(days=9)).isoformat(timespec="seconds")
    young = datetime.now(timezone.utc).isoformat(timespec="seconds")
    log = tmp_path / "equity_pick_log.jsonl"
    rows = [
        {"ts": old, "pick": {"action": "long", "ticker": "MPC"},
         "entry_quotes": {"MPC": 100.0, "XLE": 50.0}},
        {"ts": young, "pick": {"action": "long", "ticker": "EOG"},
         "entry_quotes": {"EOG": 100.0, "XLE": 50.0}},   # too young to grade
        {"ts": old, "pick": {"action": "none"}, "entry_quotes": {}},
    ]
    log.write_text("\n".join(json.dumps(r) for r in rows))
    quotes = {"MPC": 110.0, "XLE": 52.0}  # pick +10% vs sector +4% -> +6% relative
    out = equities.score(log, horizon_days=5, quotes_fn=lambda t: quotes[t])
    assert "1 picks graded" in out
    assert "+6.00%" in out and "1/1" in out


def test_equity_score_patience(tmp_path):
    log = tmp_path / "log.jsonl"
    log.write_text(json.dumps({
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pick": {"action": "long", "ticker": "EOG"},
        "entry_quotes": {"EOG": 100.0, "XLE": 50.0}}))
    assert "patience" in equities.score(log, horizon_days=5, quotes_fn=lambda t: 1.0)


# ---------------------------------------------------------------- gdelt fetch parsing

def test_fetch_gdelt_parses_and_writes(tmp_path, monkeypatch):
    from oilx import data

    class FakeResp:
        status_code = 200
        def __init__(self, mode):
            import datetime as _d
            rows = ["Date,Series,Value"]
            d0 = _d.date(2017, 1, 1)
            for i in range(400):
                day = d0 + _d.timedelta(days=i)
                v = -2.5 + 0.01 * (i % 7) if "tone" in mode else 100 + i % 50
                rows.append(f"{day.isoformat()}T00:00:00Z,Article Tone,{v}")
            self.text = "\n".join(rows)

    def fake_get(url, params=None, **kw):
        return FakeResp(params["mode"])

    monkeypatch.setattr(data.requests, "get", fake_get)
    monkeypatch.setattr(data, "datetime", __import__("datetime").datetime)
    import time as _t
    monkeypatch.setattr(_t, "sleep", lambda s: None)
    written = data.fetch_gdelt(tmp_path, start_year=2017)
    assert set(written) == {"gdelt_tone_crude.csv", "gdelt_vol_crude.csv"}
    import pandas as pd
    tone = pd.read_csv(tmp_path / "gdelt_tone_crude.csv")
    assert list(tone.columns) == ["date", "tone"] and len(tone) >= 300
    assert tone["date"].is_monotonic_increasing


def test_fetch_gdelt_rate_limit_raises_cleanly(tmp_path, monkeypatch):
    from oilx import data

    class Fake429:
        status_code = 429
        text = "Please limit requests"

    monkeypatch.setattr(data.requests, "get", lambda *a, **k: Fake429())
    import time as _t
    monkeypatch.setattr(_t, "sleep", lambda s: None)
    import pytest as _pt
    with _pt.raises(RuntimeError, match="rate-limited"):
        data.fetch_gdelt(tmp_path)


def test_negated_conflict_headlines_flip_bearish():
    # verbatim from the live log, 2026-11-09: scored bullish before the negation rule
    tilt, m = equities.news_tilt(["Oil Futures Slide as Trump Says New Strikes on Iran Unlikely"])
    assert tilt < 0 and m[0]["weight"] < 0 and "negated" in m[0]["pattern"]
    tilt2, m2 = equities.news_tilt(["Oil prices climb after U.S. strikes Iran's Qeshm Island"])
    assert tilt2 > 0                                    # a real strike still reads bullish
