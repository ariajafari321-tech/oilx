"""The equity desk: pick the oil-exposed company that best expresses today's view.

Instead of asking "long or short crude?", a desk asks "WHICH instrument carries this view
best?" A bullish-crude view belongs in a high-beta pure-play E&P; a wide-crack view
belongs in a refiner (whose input cost is crude - refiners are NOT "oil exposure", the
classic interview mistake); a no-view, high-vol regime belongs in fee-based midstream or
cash. This module encodes a fixed 17-name universe with hand-written strengths and
weaknesses, scores every name off the SAME signal state that drives the futures book
(plus the news tilt), and logs one paper pick per run - graded later against XLE.

Honesty rules, same as everywhere else in oilx:
- The exposure betas are stated priors (how much each name should move per unit of crude
  or crack view), not fitted coefficients. They are printed with every pick.
- The news tilt comes from a transparent keyword lexicon over free Google News RSS
  headlines. There is no free historical headline archive, so this signal CANNOT be
  backtested - it is live-only, logged from day one, and allowed to tilt equity ranking
  ONLY. It never touches the futures book or Kalshi thresholds.
- This is a recommendation engine with a scored paper track record, not an order router:
  there is no equity brokerage attached, and `equity-score` grades every past pick
  against XLE over the configured horizon so the picker can be fired by its own log.
"""
from __future__ import annotations

import html
import json
import logging
import re
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

log = logging.getLogger("oilx.equities")

# ------------------------------------------------------------------ the universe
# crude_beta / crack_beta: stated priors in "score units per unit of view", not fits.
# defensive: how much the name is a place to hide when vol is high and the view is weak.

UNIVERSE: list[dict] = [
    # ---- upstream pure plays: the crude view at full volume
    dict(ticker="EOG", name="EOG Resources", bucket="upstream", crude_beta=1.0, crack_beta=0.0,
         defensive=0.0,
         strengths="low-cost shale inventory, net cash, premium-drilling discipline",
         weaknesses="pure price-taker: no downstream buffer when crude falls"),
    dict(ticker="OXY", name="Occidental", bucket="upstream", crude_beta=1.3, crack_beta=0.0,
         defensive=-0.2,
         strengths="highest crude beta in the book (leverage + Permian scale)",
         weaknesses="debt-heavy; the same leverage cuts twice as hard on the way down"),
    dict(ticker="DVN", name="Devon Energy", bucket="upstream", crude_beta=1.1, crack_beta=0.0,
         defensive=0.0,
         strengths="variable-dividend model returns spikes to holders fast",
         weaknesses="shorter reserve life; needs sustained prices to re-rate"),
    dict(ticker="FANG", name="Diamondback", bucket="upstream", crude_beta=1.1, crack_beta=0.0,
         defensive=0.0,
         strengths="pure Permian, best-in-class cost per barrel",
         weaknesses="single-basin concentration; serial-acquirer integration risk"),
    dict(ticker="COP", name="ConocoPhillips", bucket="upstream", crude_beta=0.9, crack_beta=0.0,
         defensive=0.1,
         strengths="global E&P scale (absorbed Marathon Oil's assets in 2024)",
         weaknesses="size dilutes the beta: moves less than the pure shale names"),
    # ---- integrated: the view at half volume, with a refining shock absorber
    dict(ticker="XOM", name="ExxonMobil", bucket="integrated", crude_beta=0.5, crack_beta=0.3,
         defensive=0.3,
         strengths="Guyana growth barrels + refining/chemicals buffer both directions",
         weaknesses="too big to be a trade: expresses a view slowly"),
    dict(ticker="CVX", name="Chevron", bucket="integrated", crude_beta=0.5, crack_beta=0.2,
         defensive=0.3,
         strengths="fortress balance sheet, Permian + Hess growth",
         weaknesses="same dilution: the index already owns it"),
    dict(ticker="SHEL", name="Shell", bucket="integrated", crude_beta=0.4, crack_beta=0.2,
         defensive=0.2,
         strengths="world's biggest LNG trader; persistent valuation discount to US peers",
         weaknesses="the discount persists for governance reasons - catalysts are slow"),
    # ---- midstream: paid per barrel MOVED, not per dollar of price - the hiding spot
    dict(ticker="EPD", name="Enterprise Products", bucket="midstream", crude_beta=0.15,
         crack_beta=0.0, defensive=1.0,
         strengths="fee-based cash flows, 25+ years of distribution growth",
         weaknesses="wrong instrument for a price view - that's the point"),
    dict(ticker="PAA", name="Plains All American", bucket="midstream", crude_beta=0.25,
         crack_beta=0.0, defensive=0.7,
         strengths="Permian crude gathering: volume growth when drilling runs hot",
         weaknesses="more commodity-linked than it markets itself as"),
    dict(ticker="ET", name="Energy Transfer", bucket="midstream", crude_beta=0.2,
         crack_beta=0.0, defensive=0.6,
         strengths="cheapest large midstream on distributable cash flow",
         weaknesses="serial complexity + governance history = permanent discount risk"),
    # ---- refiners: LONG the crack, roughly flat-to-SHORT crude (input cost!)
    dict(ticker="MPC", name="Marathon Petroleum", bucket="refiner", crude_beta=-0.2,
         crack_beta=1.0, defensive=0.0,
         strengths="largest US refiner; prints money when cracks blow out (2026: $60+)",
         weaknesses="crude is its INPUT - a supply-shock crude rally squeezes it"),
    dict(ticker="VLO", name="Valero", bucket="refiner", crude_beta=-0.2, crack_beta=1.1,
         defensive=0.0,
         strengths="Gulf Coast complexity: runs cheap heavy crude, exports products",
         weaknesses="purest crack exposure cuts both ways when margins normalize"),
    dict(ticker="PSX", name="Phillips 66", bucket="refiner", crude_beta=-0.1, crack_beta=0.7,
         defensive=0.2,
         strengths="chemicals + midstream mix smooths refining cyclicality",
         weaknesses="the mix means you only get ~70% of the crack view"),
    # ---- services: a capex cycle, not a price - lagged and torquey
    dict(ticker="SLB", name="SLB (Schlumberger)", bucket="services", crude_beta=0.7,
         crack_beta=0.0, defensive=-0.1,
         strengths="international/offshore cycle leader; wins when producers re-invest",
         weaknesses="lags price: producers must BELIEVE the price before they spend"),
    dict(ticker="HAL", name="Halliburton", bucket="services", crude_beta=0.8, crack_beta=0.0,
         defensive=-0.1,
         strengths="North America pressure pumping: fastest to feel a drilling pickup",
         weaknesses="shale discipline era = producers no longer chase price with rigs"),
    # ---- ETFs: the wrappers
    dict(ticker="XOP", name="SPDR Oil & Gas E&P ETF", bucket="etf", crude_beta=1.1,
         crack_beta=0.1, defensive=0.0,
         strengths="equal-weight E&P basket: the crude view without single-name risk",
         weaknesses="no alpha by construction - it IS the average"),
    dict(ticker="USO", name="United States Oil Fund", bucket="etf", crude_beta=1.0,
         crack_beta=0.0, defensive=-0.3,
         strengths="direct front-futures exposure in a cash account",
         weaknesses="pays the roll in contango; never a buy-and-hold (see Instrument Menu)"),
]
BENCHMARK = "XLE"  # every pick is graded against the sector, not against zero


# ------------------------------------------------------------------ news tilt

# (pattern, weight) - transparent on purpose; every matched headline is logged with its
# matched pattern so the tilt is auditable line by line.
LEXICON: list[tuple[str, float]] = [
    # bullish crude: supply out, conflict, draws
    (r"supply (cut|cuts|disruption|risk)", +1), (r"output cut|production cut", +1),
    (r"opec\+? (cut|extends? cut|holds? cut)", +1), (r"sanction", +0.7),
    (r"attack|\bstrikes?\b|\bstruck\b|drone|missile", +1), (r"hormuz|red sea", +1),
    (r"escalat", +0.7), (r"embargo|shortage", +1), (r"outage|shut[- ]?in|force majeure", +0.8),
    (r"(inventories|stockpiles|crude) (fell|drop|draw)|drawdown", +0.6),
    (r"spr (purchase|refill|buy)", +0.4), (r"demand (grew|growth|strong|record)", +0.5),
    # bearish crude: supply back, peace, builds, demand fear
    (r"output (hike|boost|increase)|(raise|boost|ramp up|increase)[sd]? (oil )?(production|output)", -1),
    (r"opec\+? (hike|increase|unwind|adds supply|raises)", -1),
    (r"ceasefire|truce|peace (deal|talks progress)|de-?escalat", -1),
    (r"(inventories|stockpiles|crude) (rose|build|surge)|surplus|glut|oversupply", -0.8),
    (r"spr release", -0.5), (r"demand (concern|worr|fear|weak|slump|destruction)", -0.8),
    (r"recession|slowdown fear", -0.6), (r"price cap", -0.3),
]

# A conflict headline that is being called OFF is bearish, not bullish: "new strikes on
# Iran unlikely" matched "strikes on" and scored +1 in the live log of 2026-11-09.
NEGATORS = r"unlikely|rules? out|ruled out|calls? off|called off|no (new|further|more)|eas(es|ed|ing)|fad(es|ed|ing)|averted|avoid(s|ed)?|denies|denied|walks? back"

GOOGLE_NEWS = ("https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en")


def fetch_headlines(max_headlines: int = 40, lookback: str = "1d",
                    timeout: int = 20) -> list[str]:
    """Crude-oil headlines from Google News RSS - free, keyless, reachable from a normal
    network connection (same bar as every other oilx data source)."""
    q = urllib.parse.quote(f'"crude oil" OR "oil prices" OR OPEC when:{lookback}')
    r = requests.get(GOOGLE_NEWS.format(q=q), timeout=timeout,
                     headers={"User-Agent": "oilx/0.1 (student research)"})
    r.raise_for_status()
    titles = re.findall(r"<title>(.*?)</title>", r.text, flags=re.S)
    out = []
    for t in titles[1:]:  # first <title> is the feed's own name
        t = html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", t)).strip()
        t = re.sub(r"\s+-\s+[^-]+$", "", t)  # strip trailing "- Publisher"
        if t and t not in out:
            out.append(t)
        if len(out) >= max_headlines:
            break
    return out


def news_tilt(headlines: list[str]) -> tuple[float, list[dict]]:
    """Score headlines against the lexicon. Returns (tilt in [-1, 1], matched rows).
    Unmatched headlines count in the denominator: one scary headline among forty quiet
    ones is a whisper, not a regime."""
    matches = []
    total = 0.0
    for hline in headlines:
        low = hline.lower()
        for pat, w in LEXICON:
            if re.search(pat, low):
                if w > 0 and re.search(NEGATORS, low):
                    w, pat = -abs(w), pat + "  [negated]"
                matches.append({"headline": hline, "pattern": pat, "weight": w})
                total += w
                break  # one score per headline: first (most specific) match wins
    tilt = max(-1.0, min(1.0, total / max(len(headlines), 10)))
    return round(tilt, 3), matches


# ------------------------------------------------------------------ the picker

@dataclass(slots=True)
class View:
    crude: float        # combined signal score in [-1, 1] (the futures book's direction)
    crack: float        # the crack signal alone
    vol: float          # OVX-style annualized vol (0.49 = 49%)
    tilt: float         # news tilt in [-1, 1]
    kill: bool          # risk layer's kill switch state


def rank(view: View, universe: list[dict] | None = None) -> list[dict]:
    """Score = how well each name expresses the current view, by the stated priors.
    High-vol regimes add a defensive bonus; the kill switch zeroes directional appetite
    (the equity desk respects the same risk layer as the futures book)."""
    universe = universe if universe is not None else UNIVERSE
    crude = 0.0 if view.kill else view.crude
    crack = 0.0 if view.kill else view.crack
    hv = max(0.0, min(1.0, (view.vol - 0.40) / 0.30))  # 0 below 40 vol, 1 at 70+
    rows = []
    for u in universe:
        s = (crude * u["crude_beta"]
             + crack * u["crack_beta"]
             + view.tilt * 0.5 * u["crude_beta"]   # news tilts, never dominates
             + hv * 0.25 * u["defensive"])
        why = []
        if abs(crude * u["crude_beta"]) >= 0.05:
            why.append(f"crude view {crude:+.2f} x beta {u['crude_beta']:+.2f}")
        if abs(crack * u["crack_beta"]) >= 0.05:
            why.append(f"crack view {crack:+.2f} x beta {u['crack_beta']:+.2f}")
        if abs(view.tilt * 0.5 * u["crude_beta"]) >= 0.05:
            why.append(f"news tilt {view.tilt:+.2f}")
        if hv * 0.25 * u["defensive"] >= 0.05:
            why.append(f"high-vol defensive bonus")
        rows.append({**u, "score": round(s, 3), "why": "; ".join(why) or "no strong driver"})
    rows.sort(key=lambda r: -r["score"])
    return rows


def pick(view: View, *, min_score: float = 0.10,
         universe: list[dict] | None = None) -> dict:
    rows = rank(view, universe)
    top, bottom = rows[0], rows[-1]
    if view.kill:
        verdict = {"action": "none", "reason": "kill switch engaged - the equity desk "
                   "respects the same risk layer as the futures book"}
    elif top["score"] >= min_score:
        verdict = {"action": "long", "ticker": top["ticker"], "name": top["name"],
                   "bucket": top["bucket"], "score": top["score"], "why": top["why"],
                   "strengths": top["strengths"], "weaknesses": top["weaknesses"]}
    else:
        verdict = {"action": "none", "reason": f"no name scores above {min_score:.2f} - "
                   "a weak view expressed through equities is just fees; stay in cash "
                   "or fee-based midstream"}
    return {"view": {"crude": view.crude, "crack": view.crack, "vol": view.vol,
                     "tilt": view.tilt, "kill": view.kill},
            "pick": verdict,
            "avoid": {"ticker": bottom["ticker"], "score": bottom["score"],
                      "why": bottom["why"]},
            "ranked": rows}


# ------------------------------------------------------------------ run + log + grade

def run(cfg, pnl, *, quotes_fn=None) -> dict:
    """Assemble the view from the live panel + news, rank, log one paper pick."""
    from . import risk, signals
    scores = signals.compute_all(pnl, cfg)
    last = scores.dropna(how="all").iloc[-1]
    crude_view = float(max(-1.0, min(1.0, last.mean())))
    crack_view = float(last.get("crack", 0.0) or 0.0)
    vol = float(risk.realized_vol(pnl["ret"], cfg.vol_lookback_days).iloc[-1])
    kill = (cfg.out_dir / "KILL").exists()

    tilt, matches, headlines = 0.0, [], []
    if cfg.news.get("enabled", True):
        try:
            headlines = fetch_headlines(int(cfg.news.get("max_headlines", 40)),
                                        str(cfg.news.get("lookback", "1d")))
            tilt, matches = news_tilt(headlines)
        except Exception as e:
            log.warning("news fetch failed (%s); tilt = 0 this run", e)

    out = pick(View(crude=crude_view, crack=crack_view, vol=vol, tilt=tilt, kill=kill),
               min_score=float(cfg.equities.get("min_score", 0.10)))
    out["ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out["news"] = {"tilt": tilt, "n_headlines": len(headlines),
                   "matches": matches[:12],
                   "note": "live-only signal: no free headline archive exists, so this is "
                           "logged from day one instead of backtested"}

    # entry quotes for grading (best effort - never blocks the pick)
    quotes_fn = quotes_fn or _yahoo_last
    entry = {}
    tickers = ([out["pick"]["ticker"]] if out["pick"].get("ticker") else []) + [BENCHMARK]
    for t in tickers:
        try:
            entry[t] = quotes_fn(t)
        except Exception:
            entry[t] = None
    out["entry_quotes"] = entry

    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    (cfg.out_dir / "equity_pick_latest.json").write_text(json.dumps(out, indent=1))
    with (cfg.out_dir / "equity_pick_log.jsonl").open("a") as f:
        slim = {k: out[k] for k in ("ts", "view", "pick", "avoid", "entry_quotes")}
        slim["tilt"] = tilt
        f.write(json.dumps(slim) + "\n")
    return out


def _yahoo_last(ticker: str) -> float | None:
    from . import data
    df = data.fetch_yahoo(ticker, start="2026-09-01")
    return float(df["value"].iloc[-1]) if df is not None and len(df) else None


def render(out: dict) -> str:
    v, p = out["view"], out["pick"]
    lines = [f"equity desk  (crude view {v['crude']:+.2f}, crack {v['crack']:+.2f}, "
             f"vol {v['vol']:.0%}, news tilt {v['tilt']:+.2f})", "-" * 78]
    if p["action"] == "long":
        lines.append(f"PICK: long {p['ticker']} ({p['name']}, {p['bucket']})  "
                     f"score {p['score']:+.2f}")
        lines.append(f"  because: {p['why']}")
        lines.append(f"  strengths:  {p['strengths']}")
        lines.append(f"  weaknesses: {p['weaknesses']}")
    else:
        lines.append(f"PICK: none - {p['reason']}")
    a = out["avoid"]
    lines.append(f"WEAKEST EXPRESSION: {a['ticker']} (score {a['score']:+.2f}; {a['why']}) "
                 "- not a short call, just the worst wrapper for this view")
    lines.append("")
    lines.append(f"{'ticker':>6} {'bucket':>10} {'score':>7}  name")
    for r in out["ranked"]:
        lines.append(f"{r['ticker']:>6} {r['bucket']:>10} {r['score']:>+7.2f}  {r['name']}")
    n = out.get("news", {})
    if n.get("matches"):
        lines.append("")
        lines.append(f"news ({n['n_headlines']} headlines, {len(n['matches'])} matched):")
        for m in n["matches"][:6]:
            lines.append(f"  {'+' if m['weight'] > 0 else '-'} {m['headline'][:72]}")
    return "\n".join(lines)


def score(log_path: Path, *, horizon_days: int = 5, quotes_fn=None) -> str:
    """Grade every logged pick old enough to judge: pick return vs XLE return since
    entry. Relative to the sector on purpose - 'energy went up' is not skill."""
    if not log_path.exists():
        return "no equity picks logged yet - run equity-pick first"
    quotes_fn = quotes_fn or _yahoo_last
    rows = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
    now = time.time()
    graded, rel_sum, wins = 0, 0.0, 0
    quotes: dict[str, float | None] = {}
    for r in rows:
        p = r.get("pick", {})
        t = p.get("ticker")
        e = r.get("entry_quotes", {})
        if p.get("action") != "long" or not t or not e.get(t) or not e.get(BENCHMARK):
            continue
        age_days = (now - datetime.fromisoformat(r["ts"]).timestamp()) / 86400
        if age_days < horizon_days:
            continue
        for q in (t, BENCHMARK):
            if q not in quotes:
                try:
                    quotes[q] = quotes_fn(q)
                except Exception:
                    quotes[q] = None
        if not quotes.get(t) or not quotes.get(BENCHMARK):
            continue
        rel = (quotes[t] / e[t] - 1) - (quotes[BENCHMARK] / e[BENCHMARK] - 1)
        rel_sum += rel
        wins += rel > 0
        graded += 1
    if not graded:
        return (f"no picks are older than the {horizon_days}-day grading horizon yet "
                "(or entry quotes were missing) - patience is part of the method")
    return (f"{graded} picks graded vs {BENCHMARK} over >= {horizon_days} days\n"
            f"avg relative return: {rel_sum / graded:+.2%}  |  beat the sector "
            f"{wins}/{graded} times\n"
            "(relative to XLE on purpose: 'energy went up' is not stock-picking skill)")
