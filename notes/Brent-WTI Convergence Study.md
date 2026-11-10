---
tags: [oilx, research, brent-wti]
---
# Brent-WTI Convergence Study

*Reproduce: `python scripts/research_brent_wti.py` (8,406 aligned trading days,
1987 → Oct 2026). Chart: `attachments/brent_wti_spread.png`.*

**Plain English:** Brent (seaborne, waterborne-priced crude) and WTI (landlocked US
crude) are nearly the same molecule, so their price gap is a bet on *logistics and
geopolitics*, not on oil. Today the gap is **~$29/bbl** against a long-run norm of $0-4.
The question: is "short the spread and wait" a well-thought-out bet? Answer: yes - it
has literally never failed to pay in 40 years - but only at a size that can survive
years of being early, and history says exactly how much pain to budget.

## The spread by era
| era | mean | median | p95 | max | days>$10 |
|---|---|---|---|---|---|
| 1987-2010 (pre-shale) | -1.3 | -1.4 | +1.7 | +13.2 | 1 |
| 2011-2014 (shale glut at Cushing) | +12.5 | +11.8 | +23.8 | +29.6 | 551 |
| 2015-2025 (export era) | +4.0 | +3.7 | +8.9 | +14.4 | 59 |
| 2026 (Hormuz war premium) | +8.9 | +6.7 | +23.7 | +30.8 | 55 |

Mean-reversion speed is regime-dependent: half-life ~4 trading days pre-shale, ~11 in
the export era, but **39 days inside the 2011-14 blowout** - when the cause is
structural, the spread is slow even to mean-revert *within* its new level.

## Every episode above $12, 1987-2026
Rule: enter short-spread at the first close above $12, exit at the first close below $6.

| entered | exited | entry | worst | widened against you | days | P&L $/bbl |
|---|---|---|---|---|---|---|
| 2009-02 | 2009-02 | 13.2 | 13.2 | 0.0 | 1 | +7.5 |
| **2011-01** | **2013-05** | **12.0** | **29.6** | **+17.6** | **834** | +6.5 |
| 2013-11 | 2014-02 | 13.2 | 19.3 | +6.1 | 107 | +7.3 |
| 2015-02 | 2015-03 | 13.7 | 13.7 | 0.0 | 27 | +8.3 |
| 2018-10 | 2018-12 | 12.2 | 12.2 | 0.0 | 66 | +6.8 |
| 2019-05 | 2019-07 | 13.1 | 13.3 | +0.2 | 49 | +7.5 |
| 2022-03 | 2022-04 | 12.6 | 12.6 | 0.0 | 12 | +7.8 |
| 2022-06 | 2022-08 | 12.0 | 14.4 | +2.4 | 49 | +8.9 |
| 2026-03 | 2026-05 | 12.4 | 25.9 | +13.6 | 50 | +7.4 |
| 2026-07 | 2026-07 | 12.2 | 12.2 | 0.0 | 5 | +7.6 |
| **2026-09** | **OPEN** | **12.2** | **30.8** | **+18.5** | **27+** | **?** |

**Ten for ten.** Every closed episode converged and paid $6.5-8.9/bbl. But the two
structural episodes (2011, and the current one) widened $17-19 past entry first, and
2011 took 2.3 years. A position sized to "the spread never stays above $20" would have
been carried out twice - including last month.

## The honest thesis for today
- The current episode is already the **second-worst adverse excursion in 40 years**.
  Entering here (~$29) rather than at $12 changes the shape: less room to widen if 2011
  (~$30) is the ceiling, but the ceiling is an assumption, not a law - a tanker war has
  no Cushing-pipeline-style physical cap.
- The 2011 gap closed when **pipelines got built** (structural fix, slow). This gap
  closes when **shipping normalizes** (political fix, can be fast). That asymmetry -
  slow to build, fast to sign - is the case for the trade paying quickly *when* it pays.
- **Falsifier:** escalation. The position must be sized for another $10+ of widening
  and a year of waiting; the tell to watch is tanker freight (BDTI/BCTI on the
  [[Data Wishlist]]) softening before the spread does.
- **Expression:** short Brent / long WTI futures (or BNO vs USO in a cash account),
  dollar-neutral per barrel. Spot indices here are not directly tradable; futures carry
  roll differences the spot study ignores - treat the P&L column as magnitude, not a
  tradable Sharpe.

Not in the live book: this is an event-driven special situation, run (if at all) as its
own position with its own stop, not as a sixth signal. Paper framework; not investment
advice.

Related: [[The 2026 Oil Shock]], [[Instrument Menu and Exposure Map]]
