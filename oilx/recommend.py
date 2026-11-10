"""The desk note: turn today's signal state into ranked PAPER expressions.

This is the "what would you actually do about it" layer a sales & trading desk asks for.
It never places anything; it writes a briefing: direction and size from the risk layer,
then the menu of instruments ranked by fit to the current state - futures, the curve,
the ETF, Kalshi binaries (if the scanner emitted clean signals), and equities by exposure
type. Every expression carries its honest caveat, and the note leads with plain English.

Not investment advice: this is a student research framework grading itself on paper.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path

import pandas as pd

from . import data as dlib
from . import risk, signals
from .config import Config

log = logging.getLogger("oilx.recommend")

# ---- exposure map: what each listed name is ACTUALLY exposed to. Educational reference;
# weights drift with M&A, so verify before leaning on any single name.
EXPOSURE_MAP = [
    # ticker, bucket, one-line driver
    ("FANG", "E&P (crude pure play)", "Permian producer (post-Endeavor); closest large-cap US crude beta"),
    ("DVN",  "E&P (crude pure play)", "Multi-basin US shale producer; high crude torque"),
    ("PR",   "E&P (crude pure play)", "Permian pure play, smaller; higher beta, higher idiosyncratic risk"),
    ("OXY",  "E&P (leveraged)",       "Crude beta plus balance-sheet leverage; moves harder both ways"),
    ("APA",  "E&P (international)",   "US + Egypt/North Sea; crude beta with geopolitical basis"),
    ("CNQ",  "E&P (Canadian)",        "Oil sands; exposed to WCS-WTI differential, not just WTI"),
    ("XOM",  "Integrated",            "Upstream + refining + chemicals; diluted, steadier crude beta"),
    ("CVX",  "Integrated",            "Same; integrateds hedge you against crack/crude mix shifts"),
    ("MPC",  "Refiner",               "Marathon Petroleum REFINES crude: paid the crack spread, not the"
                                      " crude price - wide cracks good, crude cost is an input"),
    ("VLO",  "Refiner",               "Largest independent refiner; crack-spread exposure like MPC"),
    ("PSX",  "Refiner + midstream",   "Refining plus pipelines; midstream softens the crack swings"),
    ("SLB",  "Oil services",          "Paid by producers' capex; lags price, rig-count sensitive"),
    ("HAL",  "Oil services",          "North-America-weighted services; same lagged capex exposure"),
    ("FRO",  "Tanker",                "Freight rates, not oil price; spikes on disruption/rerouting"),
    ("STNG", "Tanker (products)",     "Product-tanker rates; the 2026 Hormuz regime's big winner class"),
    ("XOP",  "ETF (E&P basket)",      "Equal-weightish E&P basket; diversified crude equity beta"),
    ("XLE",  "ETF (sector)",          "Cap-weighted: mostly XOM+CVX, so mostly integrated exposure"),
    ("USO",  "ETF (futures)",         "Holds CL futures; tracks crude but pays roll drag in contango"),
]
# Names people reach for that are no longer what they think:
RETIRED = [("MRO", "Marathon Oil (the E&P 'Marathon') was acquired by ConocoPhillips in 2024;"
                   " the surviving 'Marathon' ticker is MPC, the refiner")]

MONTH_CODES = "FGHJKMNQUVXZ"


def live_curve(cl_front: float) -> dict | None:
    """Front vs next CL contracts from Yahoo (live only; no free history). Returns
    annualized roll yield, or None when quotes are unreachable."""
    try:
        ticks = dlib.next_cl_contracts(n=2)
        q = []
        for t in ticks:
            df = dlib.fetch_yahoo(t, start=(dt.date.today() - dt.timedelta(days=10)).isoformat())
            q.append(float(df["value"].iloc[-1]))
        m1, m2 = q[0], q[1]
        carry_ann = (m1 / m2 - 1) * 12  # one-month slope, annualized
        return {"m1": m1, "m2": m2, "ticks": ticks, "carry_ann": carry_ann,
                "shape": "backwardation" if m1 > m2 else "contango"}
    except Exception as e:
        log.info("live curve unavailable: %s", e)
        return None


def build_note(cfg: Config, panel: pd.DataFrame, nav: float = 10_000.0) -> str:
    scores = signals.compute_all(panel, cfg).dropna(how="all")
    last = scores.iloc[-1]
    asof = scores.index[-1].date()
    score = float(last.mean())
    inst_vol = float(risk.realized_vol(panel["ret"], cfg.vol_lookback_days).iloc[-1])
    cl = float(panel["cl"].ffill().iloc[-1])
    ovx = float(panel["ovx"].ffill().iloc[-1]) if "ovx" in panel else float("nan")
    scalar = min(cfg.vol_target / inst_vol, cfg.max_leverage)
    pos = max(-cfg.max_leverage, min(cfg.max_leverage, score * scalar))
    direction = "LONG" if pos > 0.02 else "SHORT" if pos < -0.02 else "FLAT"

    # data-freshness guard: a desk note on stale data is worse than no note
    age_days = (pd.Timestamp.today().normalize() - scores.index[-1].normalize()).days
    stale = age_days > 5

    curve = live_curve(cl)
    kalshi_sigs = []
    scan_path = cfg.out_dir / "kalshi_scan_latest.json"
    if scan_path.exists():
        kalshi_sigs = [s for s in json.loads(scan_path.read_text()) if not s.get("flags")]

    mcl_notional = 100 * cl  # MCL micro future = 100 bbl
    n_mcl = abs(pos) * nav / mcl_notional

    L = []
    L.append(f"# oilx desk note - {asof}")
    L.append("")
    L.append("**Plain English:** " + {
        "LONG": "the signals lean bullish on crude",
        "SHORT": "the signals lean bearish on crude",
        "FLAT": "the signals roughly cancel; there is no trade today",
    }[direction] + f" (combined score {score:+.2f}), and at {inst_vol:.0%} realized vol the "
        f"risk budget allows {abs(pos):.2f}x of NAV. Everything below is a paper expression "
        "of that one view - the point is matching instrument to reason, not stacking bets.")
    if stale:
        L.append(f"\n> **STALE DATA ({age_days} days old). Run `2_fetch.bat` first; "
                 "do not act on this note.**")
    L.append("")
    L.append("## Signal state")
    for k, v in last.items():
        L.append(f"- `{k}`: {v:+.2f}")
    L.append(f"- realized vol {inst_vol:.0%}/yr; OVX {ovx:.0f}; CL front ${cl:.2f}")
    if curve:
        L.append(f"- curve ({curve['ticks'][0]} vs {curve['ticks'][1]}): {curve['m1']:.2f} vs "
                 f"{curve['m2']:.2f} -> **{curve['shape']}**, carry {curve['carry_ann']:+.1%}/yr")
    else:
        L.append("- curve: live quotes unreachable; inventory-vs-seasonal is the carry proxy "
                 f"(inv_level score {last.get('inv_level', float('nan')):+.2f})")
    L.append("")
    L.append(f"## Expressions, ranked (paper NAV ${nav:,.0f} -> target {pos:+.2f}x)")
    if direction == "FLAT":
        L.append("Flat book. The honest recommendation most days is: no position. "
                 "Watch the Wednesday EIA release and the Friday COT for the next push.")
    else:
        side = "Buy" if direction == "LONG" else "Sell short"
        rank = 1
        carry_ok = curve and ((curve["shape"] == "backwardation") == (direction == "LONG"))
        n_whole = round(n_mcl)
        size_txt = (f"{n_whole} MCL (micro WTI) future{'s' if n_whole != 1 else ''}" if n_whole >= 1
                    else f"{n_mcl:.2f} MCL - **below one micro contract at this NAV**; the futures"
                         " expression starts around $" + f"{mcl_notional / max(abs(pos), 1e-9):,.0f}"
                         " NAV, use the ETF or Kalshi line instead")
        L.append(f"{rank}. **{side} {size_txt}** (~${mcl_notional:,.0f} "
                 f"notional each). Cleanest expression; no roll drag day-to-day." +
                 (f" Curve agrees ({curve['shape']}): rolling the position **earns** carry "
                  f"({curve['carry_ann']:+.1%}/yr tailwind) - momentum-with-the-curve is the "
                  "double-sort the literature likes (Fuertes-Miffre-Rallis)." if carry_ok else
                  (f" Curve disagrees ({curve['shape']}): rolling **pays** carry; size down or "
                   "prefer the dated expression." if curve else "")))
        rank += 1
        try:
            uso = float(dlib.load_csv(cfg.raw_dir, "uso_adj_daily.csv").iloc[-1, 1])
        except Exception:
            uso = float("nan")
        uso_line = (f"~{abs(pos) * nav / uso:,.0f} shares" if uso == uso else "shares sized at run time")
        L.append(f"{rank}. **USO** for a cash account: {uso_line}. Same view, but it pays the "
                 "roll in contango and tracking drift; use only when futures aren't available.")
        rank += 1
        if kalshi_sigs:
            s0 = kalshi_sigs[0]
            L.append(f"{rank}. **Kalshi binary** ({s0['ticker']}, {s0['side']} @{s0['price']:.2f}, "
                     f"model edge {s0['edge']:+.2f}): defined-risk event expression; demo-exchange "
                     "only via `kalshi-demo`.")
            rank += 1
        else:
            L.append(f"{rank}. **Kalshi binaries**: scanner shows no clean edge today (usual, honest). "
                     "Binaries are for the Wednesday-report view, not the standing book.")
            rank += 1
        eq = "FANG / DVN / XOP" if direction == "LONG" else "XOP (short) or defer"
        L.append(f"{rank}. **Equity expression** ({eq}): levered crude beta plus company risk "
                 "(hedging policy, basins, buybacks). Use when the view is MONTHS long, not days; "
                 "see the exposure map below before picking a name.")
    L.append("")
    L.append("## Exposure map (what each name actually is)")
    L.append("| ticker | bucket | driver |")
    L.append("|---|---|---|")
    for t, b, d in EXPOSURE_MAP:
        L.append(f"| {t} | {b} | {d} |")
    for t, note in RETIRED:
        L.append(f"\n- Note: {note}.")
    L.append("")
    L.append("**Refiners are not a crude bet.** MPC/VLO earn the crack spread; crude is their "
             "input cost. In 2026 the cracks blew out while US crude lagged seaborne - refiners "
             "and crude told different stories. Holding a refiner 'for oil exposure' is the most "
             "common exposure mistake on this map.")
    L.append("")
    L.append("---\n*Paper research framework. Not investment advice; decisions and risk are "
             "the reader's. Data sources and release-lag rules: notes/Data Pipelines.md.*")
    return "\n".join(L)


def run(cfg: Config, panel: pd.DataFrame, nav: float = 10_000.0) -> Path:
    note = build_note(cfg, panel, nav)
    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    out = cfg.out_dir / "desk_note.md"
    out.write_text(note, encoding="utf-8")
    print(note)
    return out
