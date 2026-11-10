---
tags: [oilx, concept]
---
# Thesis in Plain English

Imagine a grocery store that announces, every Wednesday at 10:30am, exactly how much milk
is in its warehouse. If the warehouse is emptier than it usually is at this time of year,
milk prices tend to firm up over the following days; if it is unexpectedly full, they
soften. Oil actually works like this: the US government (the EIA) publishes the crude oil
"warehouse number" every week, on a schedule, for free.

oilx trades on five such plain facts:

1. **The warehouse number** (two ways). Is this week's change in storage bigger or
   smaller than the usual seasonal change? And is the overall level unusually low or high
   for this time of year? Low and draining = bullish; full and building = bearish.
2. **The refiner's paycheck.** Refineries buy crude and sell gasoline and diesel. When
   their margin (the *crack spread*) is fat, they run harder and buy more crude.
3. **The crowd.** Regulators publish how speculators are positioned every week. When
   nearly everyone is already long, there's nobody left to buy; at extremes it pays to
   lean the other way.
4. **The trend.** Oil moves in long swings (2008, 2014, 2020, 2022, 2026). A simple
   trend-follower catches enough of them to pay for its mistakes.

None of these is a secret — which is exactly the right question to ask: **why would any
of this still pay?** Three honest answers:
- Each edge is *small and slow*; it pays per month, not per minute, so fast money doesn't
  compete for it and slow money (index funds, hedgers) has other objectives.
- Hedgers in oil are *paid to be there* (an airline shorting fuel risk doesn't care about
  a half-Sharpe signal), and someone collects what they pay.
- Some of it may be luck anyway. The project's bootstrap says the result beats ~90% of
  luck — good, not conclusive, and the write-up never claims more.

**The real product is the risk control.** Any intern can fit a signal; the part a desk
cares about is that the position is sized to a fixed 10% volatility budget, capped at
1.5x, cut to zero for two weeks after a 15% drawdown, and charged realistic costs — so
one wrong idea can never spend the whole bankroll. Rule from pmx, carried over: *a
backtest that prints huge free money is a bug report, not a result.*

Related: [[Signals]], [[Risk Layer]], [[Evaluation and Honesty Checks]]
