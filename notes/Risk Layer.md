---
tags: [oilx, risk]
---
# Risk Layer

The order of operations each day (`oilx/risk.py`):

1. **Combine.** Walk-forward-weighted average of the five scores, then rescaled by its
   own trailing RMS. Without that rescale, diversification across signals quietly
   de-levers the book (the first run realized 3.8% vol against a 10% target — the bug was
   found by *reading the realized vol*, not by the backtest failing).
2. **Volatility targeting.** Position = score × (10% target ÷ realized instrument vol),
   capped at 1.5× NAV. Oil's vol swings from 20% to 100%+; without this, "the same
   signal" takes five times the risk in 2020 as in 2017. The vol estimate is lagged one
   day — using today's vol to size today's position is a subtle peek.
3. **Kill switch.** A 15% trailing drawdown flattens the book for 10 trading days, then
   re-enters at half size and doubles back to full over ~10 days. Deliberately dumb: it
   exists so one broken signal or regime change cannot spend the whole risk budget, and
   its cost is *in* the backtest (it fired once in 19 years and the max drawdown still
   printed −17%, because the switch acts the day after the breach — reported, not hidden).
4. **Costs.** 2bp on every unit of turnover (CL micro futures half-spread + slippage)
   plus 0.5bp/day of holding drag (roll friction). Annual turnover ≈ 11×NAV, so costs
   matter and are charged before any number is quoted.

## Timing convention (the whole game)
Scores for day *t* use data available by the close of *t*; the position set at *t*'s
close earns day *t+1*'s return; costs hit at *t+1* on the change made at *t*. Weekly data
enters the panel only on its **release date plus one safety business day** (EIA Wednesday
→ Thursday; COT Friday → Monday). A test proves a same-day oracle earns nothing under
this convention (`test_no_same_day_peek`).

## What this would look like with real money
The tradable expression is CL micro futures (MCL, 100 bbl) or USO for a cash account.
At a $10,000 paper NAV and 0.17× average position, that is about 1-2 micro contracts —
the point is the process, not the notional.

Related: [[Signals]], [[Evaluation and Honesty Checks]]
