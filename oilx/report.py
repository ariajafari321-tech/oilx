"""Text report and a self-contained HTML tearsheet (matplotlib figures inlined)."""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from .backtest import Result
from .config import Config

PALETTE = {"line": "#1a6a8f", "accent": "#c2611e", "grey": "#7a7a7a", "bad": "#a33"}


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def text_report(res: Result) -> str:
    lines = ["oilx backtest", "=" * 60]
    for s in res.summary:
        lines.append(f"{s['period']:>10}: ann {s['ann_return']*100:6.2f}%  vol {s['ann_vol']*100:5.2f}%  "
                     f"Sharpe {s['sharpe']:5.2f} ± {s['sharpe_se']:.2f}  NW-t {s['nw_t']:5.2f}  "
                     f"maxDD {s['max_drawdown']*100:6.2f}%")
    lines.append("-" * 60)
    lines.append("standalone signals (gross, full window):")
    for s in res.per_signal:
        lines.append(f"{s['signal']:>13}: ann {s['ann_return']*100:6.2f}%  Sharpe {s['sharpe']:5.2f} "
                     f"± {s['sharpe_se']:.2f}  NW-t {s['nw_t']:5.2f}")
    lines.append("-" * 60)
    h = res.honesty
    lines.append(f"honesty: Sharpe {h['realized_sharpe']} vs scrambled-returns null "
                 f"{h['bootstrap_null_mean']} ± {h['bootstrap_null_sd']} "
                 f"(beats {h['pct_of_null_below']*100:.0f}% of luck)")
    lines.append(f"         inverted book {h['inverted_book_sharpe']}, "
                 f"buy & hold {h['buy_hold_sharpe']} ({h['buy_hold_ann_return']*100:.1f}%/yr)")
    return "\n".join(lines)


def tearsheet(res: Result, cfg: Config, panel: pd.DataFrame) -> Path:
    d = res.daily
    figs = {}

    fig, ax = plt.subplots(figsize=(9, 3.4))
    ax.plot(d.index, d["nav"], color=PALETTE["line"], lw=1.4, label="oilx net")
    bh = (1 + d["ret_instr"].fillna(0)).cumprod()
    ax.plot(d.index, bh, color=PALETTE["grey"], lw=1.0, alpha=0.8, label="long WTI")
    ax.set_yscale("log"); ax.legend(frameon=False); ax.set_title("Growth of $1 (log scale)")
    figs["nav"] = _fig_to_b64(fig)

    fig, ax = plt.subplots(figsize=(9, 2.4))
    dd = d["nav"] / d["nav"].cummax() - 1
    ax.fill_between(d.index, dd, 0, color=PALETTE["bad"], alpha=0.6)
    ax.set_title("Drawdown"); ax.set_ylim(min(-0.16, dd.min() * 1.1), 0)
    figs["dd"] = _fig_to_b64(fig)

    fig, ax = plt.subplots(figsize=(9, 2.4))
    ax.plot(d.index, d["position"], color=PALETTE["accent"], lw=0.7)
    ax.axhline(0, color="#999", lw=0.6)
    ax.set_title("Position (x NAV), after vol targeting and kill switch")
    figs["pos"] = _fig_to_b64(fig)

    scols = [c for c in d.columns if c.startswith("s_")]
    fig, axes = plt.subplots(len(scols), 1, figsize=(9, 1.3 * len(scols)), sharex=True)
    for ax, c in zip(axes, scols):
        ax.plot(d.index, d[c], lw=0.6, color=PALETTE["line"])
        ax.set_ylabel(c[2:], rotation=0, ha="right", fontsize=8); ax.set_ylim(-1.1, 1.1)
    axes[0].set_title("Signal scores")
    figs["sigs"] = _fig_to_b64(fig)

    fig, ax = plt.subplots(figsize=(9, 2.6))
    w = res.weights.reindex(d.index).ffill()
    ax.stackplot(w.index, [w[c] for c in w.columns], labels=list(w.columns), alpha=0.85)
    ax.legend(frameon=False, ncol=len(w.columns), fontsize=8); ax.set_title("Walk-forward weights")
    figs["wts"] = _fig_to_b64(fig)

    rows_sum = "".join(
        f"<tr><td>{s['period']}</td><td>{s['ann_return']*100:.2f}%</td><td>{s['ann_vol']*100:.2f}%</td>"
        f"<td>{s['sharpe']:.2f} ± {s['sharpe_se']:.2f}</td><td>{s['nw_t']:.2f}</td>"
        f"<td>{s['max_drawdown']*100:.1f}%</td></tr>" for s in res.summary)
    rows_sig = "".join(
        f"<tr><td>{s['signal']}</td><td>{s['ann_return']*100:.2f}%</td>"
        f"<td>{s['sharpe']:.2f} ± {s['sharpe_se']:.2f}</td><td>{s['nw_t']:.2f}</td></tr>"
        for s in res.per_signal)
    h = res.honesty
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>oilx tearsheet</title>
<style>body{{font:14px/1.5 system-ui;margin:2rem auto;max-width:900px;color:#222}}
table{{border-collapse:collapse;margin:0.6rem 0}}td,th{{border:1px solid #ccc;padding:3px 10px;text-align:right}}
td:first-child{{text-align:left}}img{{max-width:100%}}h2{{margin-top:1.6rem}}
.note{{background:#f6f3ec;padding:0.7rem 1rem;border-left:3px solid {PALETTE['accent']}}}</style></head><body>
<h1>oilx: multi-signal WTI strategy - backtest tearsheet</h1>
<p class="note"><b>Paper only.</b> Costs: {cfg.spread_slippage_bps:.0f}bp per unit turnover +
{cfg.holding_bps_per_day}bp/day holding. Vol target {cfg.vol_target*100:.0f}%, leverage cap
{cfg.max_leverage}x, kill switch at {cfg.kill_drawdown*100:.0f}% trailing drawdown.
Weekly data enters on its release date, padded one extra business day.</p>
<h2>Performance (net)</h2><table><tr><th>period</th><th>ann ret</th><th>ann vol</th>
<th>Sharpe</th><th>NW-t</th><th>max DD</th></tr>{rows_sum}</table>
<img src="data:image/png;base64,{figs['nav']}"><img src="data:image/png;base64,{figs['dd']}">
<img src="data:image/png;base64,{figs['pos']}">
<h2>Signals</h2>
<table><tr><th>signal</th><th>ann ret (gross)</th><th>Sharpe</th><th>NW-t</th></tr>{rows_sig}</table>
<img src="data:image/png;base64,{figs['sigs']}"><img src="data:image/png;base64,{figs['wts']}">
<h2>Honesty checks</h2>
<p>Realized Sharpe <b>{h['realized_sharpe']}</b> against a scrambled-returns null of
{h['bootstrap_null_mean']} ± {h['bootstrap_null_sd']} (beats {h['pct_of_null_below']*100:.0f}% of
luck draws). Inverted book: {h['inverted_book_sharpe']}. Buy &amp; hold WTI:
{h['buy_hold_sharpe']} ({h['buy_hold_ann_return']*100:.1f}%/yr over the same window).</p>
</body></html>"""
    out = cfg.out_dir / "tearsheet.html"
    out.write_text(html)
    return out
