"""Kalshi module tests: pricing sanity, fee math, the guards, scoring, demo safety."""
from __future__ import annotations

import json
import math

import pytest

from oilx import kalshi
from oilx.kalshi_demo import DemoClient


# ---------------------------------------------------------------- pricing

def test_digital_monotone_in_strike():
    ps = [kalshi.digital_above(94.0, k, 0.5, 30 / 365) for k in (80, 90, 94, 100, 115)]
    assert all(a > b for a, b in zip(ps, ps[1:]))


def test_digital_at_the_money_near_half():
    p = kalshi.digital_above(94.0, 94.0, 0.5, 1 / 365)
    assert abs(p - 0.5) < 0.02  # tiny lognormal drift aside


def test_digital_converges_to_indicator():
    assert kalshi.digital_above(94.0, 90.0, 0.5, 1e-9) > 0.999
    assert kalshi.digital_above(94.0, 98.0, 0.5, 1e-9) < 0.001


def test_fee_rounds_up_to_the_cent():
    assert kalshi.kalshi_taker_fee(0.50) == 0.02     # 0.0175 -> 0.02
    assert kalshi.kalshi_taker_fee(0.05) == 0.01     # 0.0033 -> 0.01
    assert kalshi.kalshi_taker_fee(0.50, contracts=100) == pytest.approx(1.75)


# ---------------------------------------------------------------- forward + guards

def mk(k, yb, ya, oi=1000.0, close="2026-10-15T18:30:00Z", st="greater"):
    return {"ticker": f"T-{k}", "strike_type": st, "floor_strike": k,
            "yes_bid": yb, "yes_ask": ya, "open_interest": oi, "close_time": close}


def test_implied_forward_interpolates():
    strip = [mk(93.0, 0.78, 0.80), mk(94.0, 0.58, 0.60), mk(95.0, 0.38, 0.40)]
    f = kalshi.implied_forward(strip)
    assert 94.0 < f < 95.0  # mid crosses 0.5 between 94 and 95
    assert f == pytest.approx(94.0 + (0.59 - 0.5) / (0.59 - 0.39), abs=0.01)


NOW = 1792060000.0  # 2026-10-15 ~10:26 ET


def test_stale_guard_flags_everything():
    strip = [mk(93.0, 0.75, 0.77), mk(94.0, 0.55, 0.57), mk(95.0, 0.30, 0.32)]
    # quote 5 dollars away from the strip's implied forward -> every signal flagged
    sigs = kalshi.scan({"KXWTI": strip}, fwd=89.0, sigma=0.5, now=NOW, min_edge=0.02)
    assert sigs and all("stale_underlying" in s.flags for s in sigs)


def test_suspect_guard():
    strip = [mk(94.0, 0.05, 0.07), mk(93.0, 0.10, 0.12), mk(95.0, 0.03, 0.05)]  # absurdly cheap
    sigs = kalshi.scan({"KXWTI": strip}, fwd=94.0, sigma=0.5, now=NOW, min_edge=0.02)
    big = [s for s in sigs if s.edge > 0.25]
    assert big and all("suspect" in s.flags for s in big)


def test_min_oi_and_min_edge_filter():
    strip = [mk(94.0, 0.48, 0.50, oi=5.0)]  # dead market
    assert kalshi.scan({"KXWTI": strip}, fwd=94.0, sigma=0.5, now=NOW) == []
    strip = [mk(94.0, 0.48, 0.52)]          # fair price -> no edge
    assert kalshi.scan({"KXWTI": strip}, fwd=94.0, sigma=0.5, now=NOW) == []


def test_near_expiry_skipped():
    strip = [mk(94.0, 0.30, 0.32, close="2026-10-15T11:30:00Z")]  # ~1h away
    assert kalshi.scan({"KXWTI": strip}, fwd=95.5, sigma=0.5, now=NOW, min_hours=2.0) == []


# ---------------------------------------------------------------- scoring

def test_score_math(tmp_path, monkeypatch):
    log = tmp_path / "log.jsonl"
    rows = [
        {"ticker": "A", "side": "yes", "price": 0.40, "fee": 0.02, "model_p": 0.60,
         "kalshi_mid": 0.42, "close_time": "c1"},
        {"ticker": "B", "side": "no", "price": 0.30, "fee": 0.02, "model_p": 0.70,
         "kalshi_mid": 0.72, "close_time": "c2"},
    ]
    log.write_text("\n".join(json.dumps(r) for r in rows))
    monkeypatch.setattr(kalshi, "fetch_result", lambda t, base=None: {"A": "yes", "B": "yes"}[t])
    out = kalshi.score(log)
    # A: won yes -> 1-0.40-0.02 = +0.58 ; B: bought no, yes resolved -> -0.32
    assert "2 signals settled across 2 distinct events" in out
    assert "+0.130 per contract" in out


# ---------------------------------------------------------------- demo safety

def test_demo_client_refuses_production(tmp_path):
    with pytest.raises(ValueError):
        DemoClient(tmp_path, base="https://api.elections.kalshi.com/trade-api/v2")


def test_demo_client_requires_secrets(tmp_path):
    with pytest.raises(FileNotFoundError):
        DemoClient(tmp_path)  # demo base, but no credential files


# ---------------------------------------------------------------- probe tier

def test_probe_tier_tags_and_floors():
    # ask such that edge lands between probe (0.03) and main (0.05) thresholds
    strip = [mk(94.0, 0.40, 0.44), mk(93.0, 0.52, 0.60)]
    sigs = kalshi.scan({"KXWTI": strip}, fwd=94.0, sigma=0.5, now=NOW,
                       min_edge=0.05, probe_edge=0.03)
    assert sigs, "expected at least one signal across the two tiers"
    for s in sigs:
        assert s.tier in ("main", "probe")
        assert s.edge >= (0.05 if s.tier == "main" else 0.03)
        if s.tier == "probe":
            assert s.edge < 0.05
    # without probe_edge the same scan emits strictly fewer-or-equal, all main
    base = kalshi.scan({"KXWTI": strip}, fwd=94.0, sigma=0.5, now=NOW, min_edge=0.05)
    assert all(s.tier == "main" for s in base)
    assert len(base) <= len(sigs)


def test_probe_signals_sort_after_main():
    strip = [mk(94.0, 0.30, 0.34), mk(93.0, 0.40, 0.50)]
    sigs = kalshi.scan({"KXWTI": strip}, fwd=95.0, sigma=0.5, now=NOW,
                       min_edge=0.05, probe_edge=0.03)
    tiers = [s.tier for s in sigs if not s.flags]
    assert tiers == sorted(tiers, key=lambda t: t != "main")


def test_underlying_is_carried():
    strip = [mk(94.0, 0.30, 0.34)]
    sigs = kalshi.scan({"KXBRENTW": strip}, fwd=95.5, sigma=0.5, now=NOW,
                       min_edge=0.03, underlying="BRENT")
    assert sigs and all(s.underlying == "BRENT" for s in sigs)


# ---------------------------------------------------------------- maker quotes

def test_maker_quote_rests_below_fair_and_inside_depth():
    strip = [mk(94.0, 0.45, 0.55, oi=2000), mk(93.0, 0.60, 0.70, oi=800)]
    qs = kalshi.maker_quotes({"KXWTI": strip}, fwd=94.0, sigma=0.5, now=NOW,
                             margin=0.02, min_oi=500)
    assert qs, "liquid fairly-priced strip should attract passive quotes"
    for q in qs:
        assert q["price"] <= q["fair"] - 0.02 + 1e-9   # margin honored
        m = next(x for x in strip if x["ticker"] == q["ticker"])
        bid, ask = ((m["yes_bid"], m["yes_ask"]) if q["side"] == "yes"
                    else (1 - m["yes_ask"], 1 - m["yes_bid"]))
        assert bid - 0.06 - 1e-9 <= q["price"] <= ask - 0.01 + 1e-9  # bounded depth, never crosses


def test_maker_quotes_tight_books_below_the_bid():
    # the v1 bug: when the bid sits at or above fair - margin (any tight or slightly
    # rich book), requiring join-the-bid staged zero quotes for 35 straight cycles.
    # Here fair ~ 0.50 and the book is 0.52 / 0.54 -> the passive price (0.47) must
    # rest BELOW the bid, bounded by max_depth.
    strip = [mk(94.0, 0.52, 0.54, oi=5000)]
    qs = kalshi.maker_quotes({"KXWTI": strip}, fwd=94.0, sigma=0.5, now=NOW,
                             margin=0.02, min_oi=500, stale_sd_frac=99)
    assert qs, "tight liquid book must still attract a passive quote"
    assert qs[0]["price"] < 0.52                       # rests below the bid on purpose
    assert qs[0]["price"] >= 0.52 - 0.06 - 1e-9        # but never deeper than max_depth
    assert qs[0]["price"] <= qs[0]["fair"] - 0.02 + 1e-9


def test_maker_skips_stale_strips_and_dead_markets():
    strip = [mk(93.0, 0.75, 0.77), mk(94.0, 0.55, 0.57), mk(95.0, 0.30, 0.32)]
    # quote 5 dollars from the strip's implied forward -> no quotes at all
    assert kalshi.maker_quotes({"KXWTI": strip}, fwd=89.0, sigma=0.5, now=NOW) == []
    dead = [mk(94.0, 0.45, 0.55, oi=50)]
    assert kalshi.maker_quotes({"KXWTI": dead}, fwd=94.0, sigma=0.5, now=NOW) == []


def test_maker_caps_quote_count_biggest_oi_first():
    strip = [mk(90 + i, 0.30, 0.60, oi=1000 * (i + 1)) for i in range(8)]
    qs = kalshi.maker_quotes({"KXWTI": strip}, fwd=94.0, sigma=0.5, now=NOW,
                             max_quotes=3, stale_sd_frac=99, wing_z=99)  # disarm stale + wing guards
    assert len(qs) == 3
    assert [q["oi"] for q in qs] == sorted([q["oi"] for q in qs], reverse=True)


# ---------------------------------------------------------------- scoring by tier

def test_score_reports_tiers_separately(tmp_path, monkeypatch):
    log = tmp_path / "log.jsonl"
    rows = [
        {"ticker": "A", "side": "yes", "price": 0.40, "fee": 0.02, "model_p": 0.60,
         "kalshi_mid": 0.42, "close_time": "c1", "tier": "main"},
        {"ticker": "B", "side": "yes", "price": 0.50, "fee": 0.02, "model_p": 0.55,
         "kalshi_mid": 0.52, "close_time": "c2", "tier": "probe"},
    ]
    log.write_text("\n".join(json.dumps(r) for r in rows))
    monkeypatch.setattr(kalshi, "fetch_result", lambda t, base=None: "yes")
    out = kalshi.score(log)
    assert "main" in out and "probe" in out
    assert "+0.580" in out and "+0.480" in out  # per-tier P&L, not blended


# ---------------------------------------------------------------- demo trader tiers

class FakeClient:
    def __init__(self):
        self.orders, self.cancelled = [], []
        self._resting = [{"order_id": "old1", "ticker": "OLD", "side": "yes",
                          "count": 5, "remaining_count": 5}]

    def balance(self):
        return {"balance": 325000}

    def positions(self):
        return []

    def resting_orders(self):
        return self._resting

    def cancel_order(self, oid, ticker=None):
        self.cancelled.append(oid)
        return {}

    def create_order(self, ticker, side, count, price, **kw):
        self.kw = getattr(self, "kw", {}); self.kw[ticker] = kw
        self.orders.append((ticker, side, count, price))
        return {"order": {"status": "resting", "order_id": f"o{len(self.orders)}"}}


def _sig(ticker, edge, tier, flags=""):
    return {"ticker": ticker, "side": "yes", "price": 0.40, "fee": 0.02, "edge": edge,
            "flags": flags, "tier": tier, "underlying": "WTI"}


def test_demo_trader_sizes_by_tier_and_refreshes_makers(tmp_path, monkeypatch):
    from oilx import kalshi_demo
    fake = FakeClient()
    monkeypatch.setattr(kalshi_demo, "DemoClient", lambda *a, **k: fake)
    scan = tmp_path / "kalshi_scan_latest.json"
    scan.write_text(json.dumps([
        _sig("MAIN1", 0.08, "main"),
        _sig("PROBE1", 0.04, "probe"),
        _sig("PROBE2", 0.035, "probe"),
        _sig("FLAGGED", 0.30, "main", flags="suspect"),
    ]))
    (tmp_path / "kalshi_maker_quotes.json").write_text(json.dumps([
        {"ticker": "MK1", "side": "yes", "price": 0.44, "fair": 0.47, "oi": 900,
         "underlying": "WTI"},
        {"ticker": "MAIN1", "side": "yes", "price": 0.38, "fair": 0.41, "oi": 800,
         "underlying": "WTI"},  # just bought as taker -> must be skipped
    ]))
    monkeypatch.setattr(kalshi_demo.time, "sleep", lambda s: None)
    out = kalshi_demo.trade_signals(
        scan, tmp_path, max_contracts=10, max_orders=5, max_open_contracts=100,
        min_edge=0.05,
        probe={"enabled": True, "min_edge": 0.03, "max_contracts_per_order": 2,
               "max_orders_per_run": 3},
        maker={"enabled": True, "contracts_per_order": 5, "max_resting_orders": 6})
    sizes = {t: c for t, _, c, _ in fake.orders}
    assert sizes["MAIN1"] == 10 and sizes["PROBE1"] == 2 and sizes["PROBE2"] == 2
    assert "FLAGGED" not in sizes                      # flagged never trades, any tier
    assert fake.cancelled == ["old1"]                  # stale resting quote cancelled
    assert sizes.get("MK1") == 5 and "MAIN1" not in [t for t, *_ in fake.orders[-1:]]
    tracked = json.loads((tmp_path / "kalshi_open_orders.json").read_text())
    assert [o["ticker"] for o in tracked["orders"]] == ["MK1"]
    rows = [json.loads(l) for l in (tmp_path / "kalshi_orders.jsonl").read_text().splitlines()]
    assert {r["tier"] for r in rows} == {"main", "probe", "maker"}
    assert "placed [probe]" in out and "resting yes x5 MK1" in out
    assert fake.kw["MAIN1"] == {"tif": "immediate_or_cancel"}   # takers never rest
    assert fake.kw["MK1"] == {"post_only": True}                # makers can never cross


def test_demo_trader_kill_switch_blocks_everything(tmp_path, monkeypatch):
    from oilx import kalshi_demo
    monkeypatch.setattr(kalshi_demo, "DemoClient",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not construct")))
    (tmp_path / "KILL").write_text("")
    scan = tmp_path / "kalshi_scan_latest.json"
    scan.write_text("[]")
    out = kalshi_demo.trade_signals(scan, tmp_path, maker={"enabled": True})
    assert "KILL" in out


def test_maker_reject_counters_tell_the_story():
    rej = {}
    dead = [mk(94.0, 0.45, 0.55, oi=50)]          # dies on the OI floor
    assert kalshi.maker_quotes({"KXWTI": dead}, fwd=94.0, sigma=0.5, now=NOW,
                               reject_counts=rej, stale_sd_frac=99) == []
    assert rej["low_oi"] == 1 and rej["stale_strip"] == 0
    rej2 = {}
    stale = [mk(93.0, 0.75, 0.77, oi=900), mk(94.0, 0.55, 0.57, oi=900),
             mk(95.0, 0.30, 0.32, oi=900)]
    kalshi.maker_quotes({"KXWTI": stale}, fwd=89.0, sigma=0.5, now=NOW, reject_counts=rej2)
    assert rej2["stale_strip"] == 3                # whole strip counted, reason named


# ---------------------------------------------------------------- live-schema regression
# The scanner ran blind for its first month live: Kalshi had moved to fixed-point string
# fields and the parser read the legacy names. These tests run on a RAW payload captured
# 2026-11-09 so that failure can never be silent again.

from pathlib import Path as _P
LIVE = _P(__file__).parent / "fixtures" / "kxwti_live_20261109.json"
LIVE_NOW = 1794269400.0  # 2026-11-10T00:10Z, ~19h before the strip closed


def test_normalize_handles_every_schema_generation():
    new = kalshi.normalize_market({"yes_bid_dollars": "0.4900", "yes_ask_dollars": "0.5000",
                                   "open_interest_fp": "470.99"})
    assert (new["yes_bid"], new["yes_ask"], new["open_interest"]) == (0.49, 0.50, 470.99)
    legacy_cents = kalshi.normalize_market({"yes_bid": 49, "yes_ask": 50, "open_interest": 470})
    assert (legacy_cents["yes_bid"], legacy_cents["yes_ask"]) == (0.49, 0.50)
    dollars = kalshi.normalize_market({"yes_bid": 0.49, "yes_ask": 0.50, "open_interest": 470.0})
    assert (dollars["yes_bid"], dollars["yes_ask"]) == (0.49, 0.50)


def test_canary_flags_schema_drift():
    blind = [{"ticker": f"T{i}"} for i in range(10)]     # what the old parser effectively saw
    assert kalshi.quote_health(blind)["suspect_schema"] is True
    live = kalshi.load_snapshot(LIVE)
    h = kalshi.quote_health(live)
    assert h["suspect_schema"] is False and h["two_sided"] >= 15 and h["with_oi"] == 30


def test_live_strip_model_is_calibrated_at_the_money():
    live = kalshi.load_snapshot(LIVE)
    assert abs(kalshi.implied_forward(live) - 86.44) < 0.15   # strip agrees with CL quote
    t = (1794339000.0 - LIVE_NOW) / kalshi.YEAR_SEC
    for m in live:
        z = kalshi.moneyness_z(m, 86.44, 0.5737, t)
        if abs(z) <= 0.7 and m["yes_bid"] > 0:
            mid = (m["yes_bid"] + m["yes_ask"]) / 2
            assert abs(kalshi._fair_yes(m, 86.44, 0.5737, t) - mid) < 0.02, m["ticker"]


def test_live_strip_wings_are_guarded():
    live = kalshi.load_snapshot(LIVE)
    rej = {}
    qs = kalshi.maker_quotes({"KXWTI": live}, 86.44, 0.5737, now=LIVE_NOW, min_oi=300,
                             reject_counts=rej)
    assert qs, "a tight liquid strip must produce near-the-money maker quotes"
    assert rej["wing"] > 0
    t = (1794339000.0 - LIVE_NOW) / kalshi.YEAR_SEC
    by = {m["ticker"]: m for m in live}
    for q in qs:
        assert abs(kalshi.moneyness_z(by[q["ticker"]], 86.44, 0.5737, t)) <= 0.7
        assert q["price"] <= q["fair"] - 0.02 + 1e-9
    # and any signal the scan emits in the wings is flagged, never tradeable
    sigs = kalshi.scan({"KXWTI": live}, 86.44, 0.5737, now=LIVE_NOW, min_edge=0.02,
                       probe_edge=0.01)
    for s in sigs:
        z = kalshi.moneyness_z(by[s.ticker], 86.44, 0.5737, t)
        assert ("wing" in s.flags) == (abs(z) > 0.7)


def test_shadow_fill_requires_the_ask_to_come_through_the_quote():
    q = [{"ticker": "A", "side": "yes", "price": 0.46, "fair": 0.486, "mid": 0.495,
          "close_time": "c"},
         {"ticker": "B", "side": "yes", "price": 0.30, "fair": 0.32, "mid": 0.33, "close_time": "c"},
         {"ticker": "C", "side": "no", "price": 0.40, "fair": 0.43, "mid": 0.58, "close_time": "c"},
         {"ticker": "GONE", "side": "yes", "price": 0.50, "fair": 0.55, "close_time": "c"}]
    now_book = [
        {"ticker": "A", "yes_bid": 0.44, "yes_ask": 0.46},   # ask came down TO our bid -> fill
        {"ticker": "B", "yes_bid": 0.30, "yes_ask": 0.32},   # we are best bid, ask above -> no fill
        {"ticker": "C", "yes_bid": 0.61, "yes_ask": 0.63},   # no-ask = 1-0.61 = 0.39 <= 0.40 -> fill
    ]
    fills = kalshi.shadow_fills(q, now_book, "2026-11-10T01:00:00+00:00")
    assert [f["ticker"] for f in fills] == ["A", "C"]
    for f in fills:
        assert f["tier"] == "maker_shadow" and f["fee"] == 0.0
        assert f["edge"] > 0   # filled below fair-at-quote; settlement decides if it was good


def test_position_size_reads_every_schema_generation():
    from oilx.kalshi_demo import position_size
    assert position_size({"position_fp": "7.00"}) == 7       # current fixed-point string
    assert position_size({"position_fp": "-3.00"}) == -3
    assert position_size({"position": 5}) == 5                # legacy integer
    assert position_size({}) == 0


def test_strip_view_rows_carry_model_and_moneyness():
    live = kalshi.load_snapshot(LIVE)
    sv = kalshi.strip_view(live, 86.44, 0.5737, now=LIVE_NOW)
    assert sv and len(sv["rows"]) == 30 and abs(sv["implied_fwd"] - 86.44) < 0.15
    ks = [r["k"] for r in sv["rows"]]
    assert ks == sorted(ks)
    atm = min(sv["rows"], key=lambda r: abs(r["z"]))
    assert abs(atm["fair"] - 0.5) < 0.06 and abs(atm["fair"] - (atm["bid"] + atm["ask"]) / 2) < 0.02


def test_v2_order_body_quotes_everything_from_the_yes_side():
    from oilx.kalshi_demo import DemoClient
    yes = DemoClient.order_body("T", "yes", 5, 0.46, post_only=True)
    assert (yes["side"], yes["price"], yes["count"]) == ("bid", "0.4600", "5.00")
    assert yes["post_only"] is True and yes["time_in_force"] == "good_till_canceled"
    no = DemoClient.order_body("T", "no", 2, 0.40, tif="immediate_or_cancel")
    # buying NO at 40c is selling YES at 60c
    assert (no["side"], no["price"], no["count"]) == ("ask", "0.6000", "2.00")
    assert no["time_in_force"] == "immediate_or_cancel" and "post_only" not in no
    for body in (yes, no):
        assert body["self_trade_prevention_type"] == "taker_at_cross" and body["client_order_id"]
    import pytest as _pt
    with _pt.raises(ValueError):
        DemoClient.order_body("T", "maybe", 1, 0.5)
    with _pt.raises(ValueError):
        DemoClient.order_body("T", "yes", 1, 0.999)


def test_wrong_contract_forward_is_flagged_not_traded():
    """Live, 2026-11-09: Yahoo's Brent quote (92.41) sat $2 above the forward the Brent
    strip itself implied, and the scan printed four 10-13c 'edges' all pointing the same
    way. A forward mismatch must flag the strip; none of it may be tradeable."""
    close = "2026-11-13T22:00:00Z"
    now = 1794607200.0 - 93.3 * 3600          # 93.3h before that close
    strip = [{"ticker": f"KXBRENTW-T{k}", "strike_type": "greater", "floor_strike": k,
              "yes_bid_dollars": f"{a - 0.02:.4f}", "yes_ask_dollars": f"{a:.4f}",
              "open_interest_fp": "500.00", "close_time": close}
             for k, a in ((86.99, 0.72), (88.99, 0.59), (90.99, 0.45), (92.99, 0.30), (94.99, 0.19))]
    strip = [kalshi.normalize_market(m) for m in strip]
    imp = kalshi.implied_forward(strip)
    assert 89.5 < imp < 91.0                                   # the market's own forward
    sigs = kalshi.scan({"KXBRENTW": strip}, fwd=92.41, sigma=0.57, now=now, min_edge=0.05,
                       probe_edge=0.03, underlying="BRENT")
    assert sigs and all("stale_underlying" in s.flags for s in sigs)
    assert kalshi.maker_quotes({"KXBRENTW": strip}, 92.41, 0.57, now=now, min_oi=100) == []
    # priced off the strip's own forward instead, the "edges" vanish
    clean = [s for s in kalshi.scan({"KXBRENTW": strip}, fwd=imp, sigma=0.57, now=now,
                                    min_edge=0.05, underlying="BRENT") if not s.flags]
    assert clean == []


def test_distrusted_forward_blocks_every_strip_of_that_underlying():
    """Live, 2026-11-10 01:44Z: the weekly Brent strip was flagged for a bad forward, but
    five maker quotes still went out on MONTHLY Brent, whose wider dollar tolerance let
    the same wrong quote through. A distrusted quote must block all of its strips."""
    strip = [mk(94.0, 0.45, 0.55, oi=2000), mk(93.0, 0.60, 0.70, oi=800)]
    assert kalshi.maker_quotes({"X": strip}, fwd=94.0, sigma=0.5, now=NOW, min_oi=500)
    rej = {}
    assert kalshi.maker_quotes({"X": strip}, fwd=94.0, sigma=0.5, now=NOW, min_oi=500,
                               distrust_forward=True, reject_counts=rej) == []
    assert rej["stale_strip"] == 2
    cheap = [mk(94.0, 0.30, 0.34), mk(93.0, 0.40, 0.50)]
    sigs = kalshi.scan({"X": cheap}, fwd=95.0, sigma=0.5, now=NOW, min_edge=0.03,
                       distrust_forward=True, stale_sd_frac=99)
    assert sigs and all("stale_underlying" in s.flags for s in sigs)
