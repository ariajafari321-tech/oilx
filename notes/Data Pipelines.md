---
tags: [oilx, data]
---
# Data Pipelines

All sources are free and keyless; `python -m oilx fetch` refreshes every cache file and
refuses to overwrite a cache with a suspiciously short download. Sources named once, used
everywhere: the **EIA** is the US Energy Information Administration (the statistics arm
of the Department of Energy); the **CFTC** is the Commodity Futures Trading Commission
(the US futures regulator — the same one that regulates Kalshi, which is how pmx led
here); **OVX** is Cboe's oil version of the VIX.

| series | source | note |
|---|---|---|
| Crude stocks ex-SPR, Cushing, gasoline (weekly, 1982→) | EIA dnav history pages, parsed from HTML | FRED dropped these series, so oilx reads the primary source |
| COT: non-commercial & commercial positions, OI (weekly, 1986→) | CFTC Socrata API (`publicreporting.cftc.gov`) | legacy format for the long history; both WTI contract codes kept, larger-OI one used |
| CL, RB (gasoline), HO (diesel) front futures (daily, 2005→) | Yahoo chart API | RB+HO+CL give the true 3-2-1 crack |
| USO, XOP adjusted (daily, 2006→) | Yahoo chart API | tradable cash expression; equity lead-lag research |
| OVX, 13-week T-bill (daily) | Yahoo chart API | regime context; cash hurdle |
| WTI & Brent spot (daily, 1986→) | Alpha Vantage (EIA spot series) | pre-2005 history + cross-checks |

## The two rules that keep the backtest honest
1. **Release lags.** Weekly data joins the daily panel via `merge_asof` on its release
   date **plus one safety business day** (EIA: week-ending Friday → the next Thursday;
   COT: as-of Tuesday → the next Monday). Tested (`test_*_availability_is_lagged`).
2. **Cross-checked prices.** The EIA spot series contains bad prints (e.g. a −12% spot
   day while CL futures moved 2%). Any spot move > 12% while CL moved < 4% is treated as
   missing — the pmx rule "price from the book, never from summary fields," translated.
   Two prints were flagged in the current files, both in Sep 2026.

## Live-only extras (shown by `oilx now`, never backtested)
- Front-vs-second CL spread (real carry) via `data.next_cl_contracts` — no free history.
- Alpha Vantage news sentiment on oil topics — no deep history.
Rule from pmx: if it can't be measured over history, it doesn't get a backtest line, and
it doesn't quietly leak into the weights.

## Known gaps
- No real futures-curve history (paid), so carry is proxied by inventory scarcity.
- EIA revisions aren't modeled: the cache holds today's vintage, not what was printed at
  the time. For stocks the revisions are small; still a known limitation. ALFRED-style
  vintage data would fix it.
- The 2026 files end at the collection date (Oct 14, 2026); `2_fetch.bat` extends them.
