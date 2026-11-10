"""Kalshi oil markets vs an options-style fair value - the pmx scanner, new underlying.

A Kalshi market "WTI above $94.49 at 2:30pm" is a digital option on the CL front-month
settle. pmx priced Kalshi's crypto digitals off Deribit's full implied-vol surface; oil
has no free options chain, so the model here is deliberately simpler and says so:

    P(S_T > K) = N(d2)  with  sigma = OVX / 100  (Cboe's 30-day oil implied vol)

- No skew (OVX is one number, not a smile). pmx showed the skew correction matters for
  far strikes, so far-from-the-money "edges" from this model are treated as model error
  first, and the suspect guard caps what the scanner will believe.
- The forward is the live CL front quote, cross-checked against the strip itself: the
  strike where the market's own prices cross 50c is the market-implied forward. If the
  quote and the implied forward disagree by more than half a short-horizon standard
  deviation, every signal is marked stale_underlying and nothing is tradable. Stale
  quotes manufacture fake edges; this is the pmx "price from the book" rule, automated.

Every emitted signal is logged with a timestamp so `kalshi-score` can grade it after
settlement: realized P&L per contract and Brier score of the model vs Kalshi's own mid,
with distinct settlement times as the honest sample size (pmx's `pmx score`, verbatim).
"""
from __future__ import annotations

import json
import logging
import math
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

import requests

log = logging.getLogger("oilx.kalshi")

PROD_BASE = "https://api.elections.kalshi.com/trade-api/v2"
UA = {"User-Agent": "oilx/0.1 (student research; read-only)"}
SERIES = ["KXWTI", "KXWTIW", "KXWTIMONTHLY"]  # daily / weekly / monthly WTI price
YEAR_SEC = 365.0 * 86400


def norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def digital_above(fwd: float, k: float, sigma: float, t_years: float) -> float:
    """Black digital P(S_T > K), flat vol (no skew - see module docstring)."""
    t = max(t_years, 1e-8)
    sd = max(sigma, 1e-6) * math.sqrt(t)
    d2 = (math.log(fwd / k) - 0.5 * sd * sd) / sd
    return norm_cdf(d2)


def kalshi_taker_fee(price: float, contracts: int = 1, rate: float = 0.07) -> float:
    """Kalshi's fee: ceil to the cent of rate * C * P * (1-P), per fill (pmx fees.py)."""
    raw = rate * contracts * price * (1 - price)
    return math.ceil(round(raw * 100, 6)) / 100.0  # round first: float dust must not add a cent


@dataclass(slots=True)
class Signal:
    ts: str                  # scan timestamp (UTC iso)
    ticker: str
    close_time: str
    strike: float
    side: str                # "yes" or "no"
    price: float             # ask paid for that side
    fee: float
    model_p: float           # model probability the BOUGHT side pays out
    edge: float              # model_p - price - fee
    kalshi_mid: float        # market mid for YES (for Brier comparison later)
    fwd: float
    sigma: float
    t_hours: float
    oi: float
    flags: str               # "", "suspect", "stale_underlying", ...
    tier: str = "main"       # "main" (full size) or "probe" (tiny size, calibration data)
    underlying: str = "WTI"  # which forward priced this signal (WTI or BRENT)


# ---------------------------------------------------------------- data access

def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def normalize_market(m: dict) -> dict:
    """Map any generation of Kalshi's market payload onto the names the scanner uses:
    yes_bid / yes_ask in dollars [0, 1] and open_interest in contracts.

    Kalshi migrated to fixed-point STRING fields (yes_bid_dollars, yes_ask_dollars,
    open_interest_fp) and removed the legacy integer-cent fields. The scanner read the
    legacy names, silently got the defaults (bid 0, ask 1, OI 0), and rejected every
    market on the open-interest floor for its whole first month live (found 2026-11-09
    by looking at a raw payload). Legacy ints are cents; legacy floats are dollars."""
    out = dict(m)
    for name in ("yes_bid", "yes_ask"):
        d = _num(m.get(name + "_dollars"))
        if d is None and name in m:
            v = m[name]
            d = v / 100 if isinstance(v, int) and not isinstance(v, bool) else _num(v)
        if d is not None:
            out[name] = d
    oi = _num(m.get("open_interest_fp"))
    if oi is None:
        oi = _num(m.get("open_interest"))
    if oi is not None:
        out["open_interest"] = oi
    return out


def quote_health(markets: list[dict]) -> dict:
    """The schema-drift canary: how many markets carry a usable two-sided quote and
    any open interest. A populated series where NONE do is a parsing failure, not a
    quiet market - the caller must shout, not shrug."""
    n = len(markets)
    two_sided = sum(1 for m in markets
                    if 0 < float(m.get("yes_bid", 0) or 0) and float(m.get("yes_ask", 1) or 1) < 1)
    with_oi = sum(1 for m in markets if float(m.get("open_interest", 0) or 0) > 0)
    return {"markets": n, "two_sided": two_sided, "with_oi": with_oi,
            "suspect_schema": n >= 5 and two_sided == 0 and with_oi == 0}


def fetch_markets(series: str, base: str = PROD_BASE, status: str = "open") -> list[dict]:
    out, cursor = [], None
    for _ in range(20):
        params = {"series_ticker": series, "status": status, "limit": 200}
        if cursor:
            params["cursor"] = cursor
        r = requests.get(f"{base}/markets", params=params, headers=UA, timeout=30)
        r.raise_for_status()
        j = r.json()
        out.extend(normalize_market(m) for m in j.get("markets", []))
        cursor = j.get("cursor")
        if not cursor:
            break
        time.sleep(0.2)
    return out


def load_snapshot(path: Path) -> list[dict]:
    """Offline mode: a saved {"markets": [...]} file instead of the live API."""
    return [normalize_market(m) for m in json.loads(path.read_text())["markets"]]


# ---------------------------------------------------------------- the scan

def implied_forward_from_ranges(markets: list[dict]) -> tuple[float, float] | None:
    """Fallback forward for strips of 'between' (range) markets with no one-sided
    strikes: the midpoint of the bucket the market prices highest, plus the bucket
    half-width as the extra tolerance the stale check should allow."""
    best = None
    for m in markets:
        if m.get("strike_type") != "between":
            continue
        lo, hi = m.get("floor_strike"), m.get("cap_strike")
        yb, ya = m.get("yes_bid", 0), m.get("yes_ask", 1)
        if lo is None or hi is None or yb <= 0 or ya >= 1:
            continue
        mid = (yb + ya) / 2
        if best is None or mid > best[0]:
            best = (mid, (float(lo) + float(hi)) / 2, (float(hi) - float(lo)) / 2)
    return (best[1], best[2]) if best else None


def implied_forward(markets: list[dict]) -> float | None:
    """The strike where the market's own YES mid crosses 0.5, linearly interpolated.
    Only 'greater' markets with a two-sided quote count."""
    pts = []
    for m in markets:
        if m.get("strike_type") not in (None, "greater"):
            continue
        k = m.get("floor_strike")
        yb, ya = m.get("yes_bid", 0), m.get("yes_ask", 1)
        if k is None or yb <= 0 or ya >= 1 or ya - yb > 0.10:
            continue
        pts.append((float(k), (yb + ya) / 2))
    pts.sort()
    for (k0, p0), (k1, p1) in zip(pts, pts[1:]):
        if p0 >= 0.5 >= p1:
            if p0 == p1:
                return (k0 + k1) / 2
            w = (p0 - 0.5) / (p0 - p1)
            return k0 + w * (k1 - k0)
    return None


def _strip_is_stale(strip: list[dict], fwd: float, sigma: float, t_years: float,
                    stale_sd_frac: float) -> bool:
    """Quote vs the strip's own implied forward; range strips get the max-mid-bucket
    fallback with the bucket half-width added to the tolerance."""
    sd_px = fwd * sigma * math.sqrt(max(t_years, 1e-8))
    tol = stale_sd_frac * max(sd_px, 0.10)
    imp = implied_forward(strip)
    if imp is None:
        rng = implied_forward_from_ranges(strip)
        if rng is not None:
            imp, halfwidth = rng
            tol += halfwidth
    return imp is not None and abs(fwd - imp) > tol


def _fair_yes(m: dict, fwd: float, sigma: float, t_years: float) -> float | None:
    """Model P(YES pays) for one market, or None for structures we can't parse."""
    st = m.get("strike_type") or "greater"
    lo, hi = m.get("floor_strike"), m.get("cap_strike")
    if st == "greater" and lo is not None:
        return digital_above(fwd, float(lo), sigma, t_years)
    if st == "less" and (hi is not None or lo is not None):
        return 1.0 - digital_above(fwd, float(hi if hi is not None else lo), sigma, t_years)
    if st == "between" and lo is not None and hi is not None:
        return digital_above(fwd, float(lo), sigma, t_years) \
            - digital_above(fwd, float(hi), sigma, t_years)
    return None


def moneyness_z(m: dict, fwd: float, sigma: float, t_years: float) -> float | None:
    """How many settlement-horizon standard deviations the market's strike sits from
    the forward (range buckets: their midpoint). The flat-vol model is only trusted
    near the money: on the live 2026-11-09 daily strip it matched the market within
    ~1c for |z| < 0.7 and was 2-4c too cheap in BOTH wings (a volatility smile the
    model does not have). Outside the trusted band the model's "edge" is the smile."""
    st = m.get("strike_type") or "greater"
    lo, hi = m.get("floor_strike"), m.get("cap_strike")
    if st == "between" and lo is not None and hi is not None:
        k = (float(lo) + float(hi)) / 2
    elif st == "less":
        k = hi if hi is not None else lo
    else:
        k = lo
    if k is None or fwd <= 0 or sigma <= 0:
        return None
    sd = sigma * math.sqrt(max(t_years, 1e-8))
    return math.log(float(k) / fwd) / sd


def scan(markets_by_series: dict[str, list[dict]], fwd: float, sigma: float,
         *, now: float | None = None, min_edge: float = 0.05, suspect_edge: float = 0.25,
         min_hours: float = 2.0, max_days: float = 45.0, min_oi: float = 100.0,
         taker_rate: float = 0.07, stale_sd_frac: float = 0.1,
         probe_edge: float | None = None, underlying: str = "WTI",
         wing_z: float = 0.7, distrust_forward: bool = False) -> list[Signal]:
    """probe_edge, if set below min_edge, emits a second tier of signals in
    [probe_edge, min_edge) tagged tier="probe" - tiny-size calibration trades whose whole
    purpose is to measure empirically whether sub-threshold edges are real. They are
    logged and scored separately and never counted as conviction."""
    emit_floor = min(min_edge, probe_edge) if probe_edge is not None else min_edge
    now = now or time.time()
    ts = datetime.fromtimestamp(now, tz=timezone.utc).isoformat(timespec="seconds")
    signals: list[Signal] = []

    for series, markets in markets_by_series.items():
        # group one strip per close time, so staleness is judged per strip
        strips: dict[str, list[dict]] = {}
        for m in markets:
            strips.setdefault(m.get("close_time", ""), []).append(m)

        for close_time, strip in strips.items():
            try:
                t_close = datetime.fromisoformat(close_time.replace("Z", "+00:00")).timestamp()
            except ValueError:
                continue
            t_hours = (t_close - now) / 3600
            if t_hours < min_hours or t_hours > max_days * 24:
                continue
            t_years = (t_close - now) / YEAR_SEC

            # distrust_forward: the caller found this underlying's quote disagreeing with
            # its most precise strip, so NO strip priced off that quote can be trusted -
            # longer strips would otherwise slip through on their wider dollar tolerance.
            flags_strip = "stale_underlying" if distrust_forward or _strip_is_stale(
                strip, fwd, sigma, t_years, stale_sd_frac) else ""

            for m in strip:
                lo, hi = m.get("floor_strike"), m.get("cap_strike")
                yb, ya = float(m.get("yes_bid", 0)), float(m.get("yes_ask", 1))
                oi = float(m.get("open_interest", 0) or 0)
                if oi < min_oi:
                    continue
                p = _fair_yes(m, fwd, sigma, t_years)
                if p is None:
                    continue  # unknown structure: never price what we can't parse
                mid = (yb + ya) / 2 if (yb > 0 or ya < 1) else None

                for side, price, model_p in (("yes", ya, p), ("no", 1 - yb, 1 - p)):
                    if price <= 0.01 or price >= 0.99:
                        continue
                    fee = kalshi_taker_fee(price, 1, taker_rate)
                    edge = model_p - price - fee
                    if edge < emit_floor:
                        continue
                    flags = flags_strip
                    if edge > suspect_edge:
                        flags = (flags + ",suspect").strip(",")
                    z = moneyness_z(m, fwd, sigma, t_years)
                    if z is not None and abs(z) > wing_z:
                        # logged (so wing "edges" can be graded later) but never traded
                        flags = (flags + ",wing").strip(",")
                    signals.append(Signal(
                        ts=ts, ticker=m["ticker"], close_time=close_time,
                        strike=float(lo if lo is not None else hi),
                        side=side, price=round(price, 4), fee=fee, model_p=round(model_p, 4),
                        edge=round(edge, 4), kalshi_mid=round(mid, 4) if mid is not None else -1,
                        fwd=fwd, sigma=sigma, t_hours=round(t_hours, 2), oi=oi, flags=flags,
                        tier="main" if edge >= min_edge else "probe", underlying=underlying))
    signals.sort(key=lambda s: (s.flags != "", s.tier != "main", -s.edge))
    return signals


# ---------------------------------------------------------------- strip view

def strip_view(markets: list[dict], fwd: float, sigma: float, *, now: float | None = None,
               wing_z: float = 0.7) -> dict | None:
    """Model-vs-market for the nearest threshold strip: one row per strike with the
    live bid/ask, the model's fair value and the strike's moneyness. This is the
    picture that shows where the flat-vol model can be trusted (near the money) and
    where the market prices a smile it lacks (the wings)."""
    now = now or time.time()
    strips: dict[str, list[dict]] = {}
    for m in markets:
        if (m.get("strike_type") or "greater") == "greater" and m.get("floor_strike") is not None:
            strips.setdefault(m.get("close_time", ""), []).append(m)
    best = None
    for ct, strip in strips.items():
        try:
            t_close = datetime.fromisoformat(ct.replace("Z", "+00:00")).timestamp()
        except ValueError:
            continue
        if t_close <= now or len(strip) < 5:
            continue
        if best is None or t_close < best[0]:
            best = (t_close, ct, strip)
    if best is None:
        return None
    t_close, ct, strip = best
    t_years = (t_close - now) / YEAR_SEC
    rows = []
    for m in sorted(strip, key=lambda x: float(x["floor_strike"])):
        yb, ya = float(m.get("yes_bid", 0) or 0), float(m.get("yes_ask", 1) or 1)
        rows.append({"k": float(m["floor_strike"]), "bid": round(yb, 4), "ask": round(ya, 4),
                     "fair": round(_fair_yes(m, fwd, sigma, t_years), 4),
                     "z": round(moneyness_z(m, fwd, sigma, t_years), 3),
                     "oi": float(m.get("open_interest", 0) or 0)})
    return {"close_time": ct, "t_hours": round((t_close - now) / 3600, 1), "fwd": fwd,
            "sigma": sigma, "implied_fwd": implied_forward(strip), "wing_z": wing_z,
            "rows": rows}


# ---------------------------------------------------------------- maker quotes

def shadow_fills(prev_quotes: list[dict], markets: list[dict], ts: str) -> list[dict]:
    """Paper fills for last cycle's passive quotes, judged against the PRODUCTION book.

    Demo-exchange fills prove the order plumbing, not the strategy: the demo book for
    these markets is nearly empty, so a resting bid there can sit forever. Shadow fills
    answer the real question - would this quote have traded on the real exchange? - with
    a deliberately conservative rule: a bid at price P counts as filled only if, by the
    next scan, the best ASK on that side has come down to or through P (someone was
    willing to sell at our price). Merely becoming the best bid is not a fill.

    Adverse selection is therefore built in, not assumed away: by construction these
    fills happen exactly when the market moved against the quote. Rows are returned in
    the signal-log shape (tier="maker_shadow", fee 0 - makers pay none) so kalshi-score
    grades them at settlement alongside everything else."""
    by = {m.get("ticker"): m for m in markets}
    fills = []
    for q in prev_quotes:
        m = by.get(q.get("ticker"))
        if not m:
            continue  # market closed or vanished: no fill
        yb, ya = float(m.get("yes_bid", 0) or 0), float(m.get("yes_ask", 1) or 1)
        ask = ya if q["side"] == "yes" else 1 - yb
        if ask <= q["price"] + 1e-9 and 0 < ask < 1:
            fills.append({
                "ts": ts, "ticker": q["ticker"], "close_time": q.get("close_time", ""),
                "strike": 0.0, "side": q["side"], "price": q["price"], "fee": 0.0,
                "model_p": q["fair"], "edge": round(q["fair"] - q["price"], 4),
                "kalshi_mid": q.get("mid", -1), "fwd": q.get("fwd", 0), "sigma": q.get("sigma", 0),
                "t_hours": q.get("t_hours", 0), "oi": q.get("oi", 0), "flags": "",
                "tier": "maker_shadow", "underlying": q.get("underlying", "WTI")})
    return fills


def maker_quotes(markets_by_series: dict[str, list[dict]], fwd: float, sigma: float,
                 *, now: float | None = None, margin: float = 0.02, min_oi: float = 500.0,
                 max_quotes: int = 6, min_hours: float = 2.0, max_days: float = 45.0,
                 stale_sd_frac: float = 0.1, underlying: str = "WTI",
                 max_depth: float = 0.06,
                 reject_counts: dict | None = None, wing_z: float = 0.7,
                 distrust_forward: bool = False) -> list[dict]:
    """Passive resting bids at model fair minus a margin, on liquid, non-stale strips.

    The taker scan asks "is the displayed price wrong by more than the fee?" - almost
    always no. This asks the maker question instead: "at what price would I be happy to
    be filled?" and rests there. On Kalshi the maker side pays no trading fee, so a fill
    at fair - margin is positive expected value by construction. pmx's trader study
    found exactly this asymmetry: makers earned roughly what takers lost.

    Rules: one quote per market (yes side preferred), price = fair - margin, capped at
    ask - 1c so it always rests (never crosses), floored at the current bid (no deep
    quotes that can't fill), only in markets with open interest >= min_oi, never on a
    stale strip, biggest-oi markets first, at most max_quotes. The caller cancels and
    reposts every cycle so nothing stale ever rests.
    """
    now = now or time.time()
    rej = reject_counts if reject_counts is not None else {}
    rej.update({k: rej.get(k, 0) for k in
                ("window", "stale_strip", "low_oi", "unparsable", "wing", "price_bounds")})

    def _rej(k):
        rej[k] += 1

    cands: list[dict] = []
    for series, markets in markets_by_series.items():
        strips: dict[str, list[dict]] = {}
        for m in markets:
            strips.setdefault(m.get("close_time", ""), []).append(m)
        for close_time, strip in strips.items():
            try:
                t_close = datetime.fromisoformat(close_time.replace("Z", "+00:00")).timestamp()
            except ValueError:
                continue
            t_hours = (t_close - now) / 3600
            if t_hours < min_hours or t_hours > max_days * 24:
                rej["window"] += len(strip)
                continue
            t_years = (t_close - now) / YEAR_SEC
            if distrust_forward or _strip_is_stale(strip, fwd, sigma, t_years, stale_sd_frac):
                rej["stale_strip"] += len(strip)
                continue
            for m in strip:
                oi = float(m.get("open_interest", 0) or 0)
                if oi < min_oi:
                    _rej("low_oi")
                    continue
                p = _fair_yes(m, fwd, sigma, t_years)
                if p is None:
                    _rej("unparsable")
                    continue
                z = moneyness_z(m, fwd, sigma, t_years)
                if z is not None and abs(z) > wing_z:
                    _rej("wing")   # never quote where the flat-vol model is known wrong
                    continue
                yb, ya = float(m.get("yes_bid", 0)), float(m.get("yes_ask", 1))
                for side, fair, bid, ask in (("yes", p, yb, ya),
                                             ("no", 1 - p, 1 - ya, 1 - yb)):
                    px = math.floor((fair - margin) * 100) / 100
                    px = min(px, round(ask - 0.01, 2))      # always rests, never crosses
                    # Resting BELOW the current bid is allowed - that is what passive
                    # means: the quote fills when the market trades down to it, and the
                    # margin is the payment for that adverse selection. (v1 required
                    # joining the bid, which in tight books is above fair - margin, so
                    # 35 straight cycles staged zero quotes. Depth is bounded so capital
                    # never parks far off-market.)
                    if px < max(bid - max_depth, 0.02) or px > 0.97:
                        if side == "no":  # count the market once, after both sides failed
                            _rej("price_bounds")
                        continue
                    cands.append({"ticker": m["ticker"], "side": side, "price": round(px, 2),
                                  "fair": round(fair, 4), "oi": oi, "close_time": close_time,
                                  "mid": round((yb + ya) / 2, 4), "fwd": fwd, "sigma": sigma,
                                  "book_bid": round(bid, 4), "book_ask": round(ask, 4),
                                  "t_hours": round(t_hours, 2), "underlying": underlying})
                    break  # one side per market
    cands.sort(key=lambda c: -c["oi"])
    return cands[:max_quotes]


def save_signals(signals: list[Signal], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "kalshi_scan_latest.json"
    path.write_text(json.dumps([asdict(s) for s in signals], indent=1))
    logp = out_dir / "kalshi_signals_log.jsonl"
    with logp.open("a") as f:
        for s in signals:
            f.write(json.dumps(asdict(s)) + "\n")
    return path


def render(signals: list[Signal], fwd: float, sigma: float) -> str:
    lines = [f"kalshi oil scan  (fwd {fwd:.2f}, sigma {sigma:.0%})", "-" * 78]
    if not signals:
        lines.append("no signals above the edge threshold - which is the usual, honest answer")
    clean = [s for s in signals if not s.flags]
    flagged = [s for s in signals if s.flags]
    for s in clean:
        tag = "" if s.tier == "main" else f" [{s.tier}]"
        lines.append(f"{s.ticker:>28} {s.side:>3} @{s.price:.2f}+{s.fee:.2f} fee  "
                     f"model {s.model_p:.2f}  edge {s.edge:+.2f}  {s.t_hours:7.1f}h  "
                     f"oi {s.oi:,.0f}{tag}")
    if flagged:
        lines.append(f"-- {len(flagged)} flagged (not tradable) --")
        for s in flagged[:10]:
            lines.append(f"{s.ticker:>28} {s.side:>3} edge {s.edge:+.2f}  [{s.flags}]")
    return "\n".join(lines)


# ---------------------------------------------------------------- scoring (pmx style)

def fetch_result(ticker: str, base: str = PROD_BASE) -> str | None:
    r = requests.get(f"{base}/markets/{ticker}", headers=UA, timeout=30)
    if r.status_code != 200:
        return None
    return (r.json().get("market") or {}).get("result") or None


def score(log_path: Path, base: str = PROD_BASE) -> str:
    """Grade every logged signal whose market has settled: realized P&L per contract,
    and Brier of the model vs Kalshi's own mid. Distinct close times = honest N."""
    if not log_path.exists():
        return "no signals logged yet - run kalshi-scan first"
    rows = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
    results: dict[str, str | None] = {}
    graded, pnl_sum, brier_model, brier_kalshi, events = 0, 0.0, [], [], set()
    by_tier: dict[str, list[float]] = {}
    for r_ in rows:
        t = r_["ticker"]
        if t not in results:
            results[t] = fetch_result(t)
            time.sleep(0.15)
        res = results[t]
        if res not in ("yes", "no"):
            continue
        won = 1.0 if res == r_["side"] else 0.0
        pnl = won - r_["price"] - r_["fee"]
        pnl_sum += pnl
        graded += 1
        events.add(r_["close_time"])
        by_tier.setdefault(r_.get("tier", "main"), []).append(pnl)
        # Brier on the YES outcome, model vs the market mid it traded against
        yes_won = 1.0 if res == "yes" else 0.0
        p_model_yes = r_["model_p"] if r_["side"] == "yes" else 1 - r_["model_p"]
        brier_model.append((p_model_yes - yes_won) ** 2)
        if r_["kalshi_mid"] >= 0:
            brier_kalshi.append((r_["kalshi_mid"] - yes_won) ** 2)
    if not graded:
        return "no logged signals have settled yet"
    bm = sum(brier_model) / len(brier_model)
    bk = sum(brier_kalshi) / len(brier_kalshi) if brier_kalshi else float("nan")
    verdict = "model beats Kalshi's price" if bm < bk else "Kalshi's price beats the model"
    tier_lines = "".join(
        f"  {t:>5}: {sum(v)/len(v):+.3f}/contract over {len(v)} signals\n"
        for t, v in sorted(by_tier.items()))
    return (f"{graded} signals settled across {len(events)} distinct events\n"
            f"realized P&L: {pnl_sum / graded:+.3f} per contract (sum {pnl_sum:+.2f})\n"
            f"by tier (probe = calibration spend, graded separately on purpose):\n{tier_lines}"
            f"Brier: model {bm:.3f} vs Kalshi mid {bk:.3f} -> {verdict}\n"
            f"(distinct events is the honest sample size; dozens are needed before this means anything)")
