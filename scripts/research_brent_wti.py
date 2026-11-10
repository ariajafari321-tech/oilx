"""Brent-WTI convergence study: 40 years of the spread, its extremes, and what a sized
convergence position would have lived through. Reproduces notes/Brent-WTI Convergence
Study.md; run from the oilx root: python scripts/research_brent_wti.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load() -> pd.DataFrame:
    wti = pd.read_csv(ROOT / "data/raw/wti_spot_daily.csv")
    brent = pd.read_csv(ROOT / "data/raw/brent_spot_daily.csv")
    for df in (wti, brent):
        df.columns = ["date", "px"]
        df["date"] = pd.to_datetime(df["date"])
        df["px"] = pd.to_numeric(df["px"], errors="coerce")
    m = wti.merge(brent, on="date", suffixes=("_wti", "_brent")).dropna().sort_values("date")
    m["spread"] = m["px_brent"] - m["px_wti"]
    # glitch guard (same rule as the panel): drop prints where the spread jumps absurdly
    jump = m["spread"].diff().abs()
    m = m[jump.fillna(0) < 15].set_index("date")
    return m


ERAS = [("1987-2010 (pre-shale)", "1987", "2010"),
        ("2011-2014 (shale glut at Cushing)", "2011", "2014"),
        ("2015-2025 (export era)", "2015", "2025"),
        ("2026 (Hormuz war premium)", "2026", "2027")]


def era_table(m: pd.DataFrame) -> list[str]:
    out = ["| era | mean | median | p95 | max | days>$10 |", "|---|---|---|---|---|---|"]
    for name, lo, hi in ERAS:
        s = m.loc[lo:hi, "spread"]
        if s.empty:
            continue
        out.append(f"| {name} | {s.mean():+.1f} | {s.median():+.1f} | {s.quantile(.95):+.1f} "
                   f"| {s.max():+.1f} | {(s > 10).sum()} |")
    return out


def episodes(m: pd.DataFrame, enter: float = 12.0, exit_: float = 6.0) -> pd.DataFrame:
    """Each episode: first close above `enter`, held short-spread until first close below
    `exit_`. Records duration, worst further widening (max adverse excursion), P&L/bbl."""
    s = m["spread"]
    rows, in_ep, t0, peak = [], False, None, None
    for t, v in s.items():
        if not in_ep and v > enter:
            in_ep, t0, entry, peak = True, t, v, v
        elif in_ep:
            peak = max(peak, v)
            if v < exit_:
                rows.append({"entered": t0.date(), "exited": t.date(),
                             "entry": round(entry, 1), "worst": round(peak, 1),
                             "mae_bbl": round(peak - entry, 1),
                             "days": (t - t0).days, "pnl_bbl": round(entry - v, 1)})
                in_ep = False
    if in_ep:  # still open (2026)
        rows.append({"entered": t0.date(), "exited": "OPEN", "entry": round(entry, 1),
                     "worst": round(peak, 1), "mae_bbl": round(peak - entry, 1),
                     "days": (s.index[-1] - t0).days, "pnl_bbl": None})
    return pd.DataFrame(rows)


def half_life(s: pd.Series) -> float:
    ds = s.diff().dropna()
    lag = s.shift(1).dropna().loc[ds.index]
    beta = np.polyfit(lag, ds, 1)[0]
    return float(np.log(2) / -beta) if beta < 0 else float("inf")


def chart(m: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(m.index, m["spread"], color="#2a78d6", lw=0.8)
    ax.axhline(12, color="#c2611e", lw=1, ls="--", label="episode entry ($12)")
    ax.axhline(0, color="#999", lw=0.6)
    ax.set_title("Brent minus WTI, daily spot ($/bbl)")
    ax.legend(frameon=False, fontsize=8)
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    m = load()
    print(f"{len(m)} aligned days {m.index[0].date()} -> {m.index[-1].date()}; "
          f"current spread {m['spread'].iloc[-1]:+.1f}")
    print("\n".join(era_table(m)))
    eps = episodes(m)
    print(eps.to_string(index=False))
    for name, lo, hi in ERAS:
        s = m.loc[lo:hi, "spread"]
        if len(s) > 300:
            print(f"half-life {name}: {half_life(s):.0f} trading days")
    out = ROOT / "notes" / "attachments"
    out.mkdir(exist_ok=True)
    chart(m, out / "brent_wti_spread.png")
    print(f"chart -> {out / 'brent_wti_spread.png'}")
