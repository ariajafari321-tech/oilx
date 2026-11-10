---
tags: [oilx, research, honesty]
---
# Evaluation and Honesty Checks

The pmx trader study found "93 skilled wallets" that evaporated under a both-tails check.
Same discipline here, before anyone gets excited about a Sharpe.

## Walk-forward weights (no hindsight in the mix)
Signal weights refit each January from each signal's **standalone gross Sharpe over the
trailing 5 years**, clipped at zero (a loser is floored at 10% weight, never sign-flipped
— flipping signs on losers is the classic overfit), normalized. Equal weights before the
first refit. The combined book therefore never uses information about which signal
"would have" worked.

## Results (net of costs, 2007-01 → 2026-10; incl. the 2026-10-22 GHR upgrades)

| period | ann ret | ann vol | Sharpe | NW-t | max DD |
|---|---|---|---|---|---|
| full | +2.6% | 8.4% | **0.31 ± 0.23** | 1.45 | −15.4% |
| 2007–2016 | +1.6% | 6.9% | 0.23 | 0.74 | −14.3% |
| 2017–2021 | +8.1% | 12.0% | 0.67 | 1.66 | −10.7% |
| 2022–now | −1.0% | 6.5% | **−0.15** | −0.32 | −15.4% |

Buy-and-hold WTI over the same window: Sharpe −0.09 (−7.4%/yr). Standalone (gross):
mom 0.27, crack 0.22, inv_surprise 0.24, cot 0.23, inv_level **−0.11** (kept at floor
weight; see [[Signals]]). The GHR upgrades (non-linear inventory, momentum-inventory
conditioning — theory-prescribed, not fitted) moved every number slightly the right way:
pre-upgrade full Sharpe 0.30, max DD −17.2%, 2022–now −0.19. Small and broad is what a
real theory prior looks like; a big jump would have been a red flag.

## The luck yardstick
A circular block bootstrap (500 draws, 10-day blocks) scrambles the instrument's returns
against the *real* position series: same positions, same costs, no alignment. Null Sharpe:
−0.02 ± 0.23. The realized 0.31 beats **~91%** of luck draws. In pmx language: the
yardstick says *probably something, not proof* — a z of about 1.4, not 3.

## Both tails
- **Inverted book:** −0.41 Sharpe. If the inverse of a strategy doesn't lose, the
  strategy was noise; this one loses properly.
- **The bad stretch is reported:** 2022–now is negative. The honest reading: trend
  whipsawed in 2024–25, cot fought the one-way 2026 war rally ([[The 2026 Oil Shock]]),
  and the kill switch (correctly) took the book out during the worst of it. Nothing was
  re-tuned to fix this stretch — a rule, because any 19-year backtest can be made
  beautiful by tuning on its last 4 years.

## What would upgrade the evidence
1. More independent events: the inventory signal has ~1,000 weekly releases, but regimes
   are few; a decade of paper trading beats another backtest.
2. Intraday release-day data, to separate the 10:30am jump (not capturable) from the
   multi-day drift (the actual claim).
3. A real futures curve, to replace the inventory proxy with measured carry.

Related: [[Risk Layer]], [[Oilx Build Log]]
