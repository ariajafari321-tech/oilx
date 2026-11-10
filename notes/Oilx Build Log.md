---
tags: [oilx, log]
---
# Oilx Build Log

Same format as the pmx [[Build Log]]: newest first; each entry records a decision, the
alternative considered, and why.

## 2026-11-10 (midday): the guard that switched the bot off every morning

First full day in the cloud. Overnight it signed in and rested six WTI quotes; by 9:50am
it had quoted nothing for hours. Cause: the forward check compared Yahoo's quote with
the strip's implied forward and allowed 0.1 settlement sd. With five hours to settle
that is about $0.11 - and a 10-15 minute delayed quote in a falling market was $0.60
off. The guard was measuring the quote's delay, not the market's health, and it tripped
harder the closer the strip got to settling. Yesterday's fix for the Brent
contract-month error had been written in the wrong units.

Change: `pricing_forward`. The market's own nearest threshold strip supplies the
forward (right contract, as fresh as the book); the outside quote is only a sanity
check, in percent (3%), which still catches a broken feed but not a late one. This
also fixes Brent properly instead of benching it: priced off its own strip, the
contract-month basis disappears. Brent still pays an extra 2c of margin for using WTI
vol as a proxy.

What that costs, stated plainly: anchored to the market's own forward, the model
agrees with the market at the money by construction. The remaining opinion is the
SHAPE of the curve. Taker edges all but vanish; the maker is quoting a margin under a
market-anchored fair value, so its results will be about spread capture against
adverse selection, not about a view on the level of oil.

Also on record from this morning: two paper fills (yes above $85.49 at 54c, yes above
$86.99 at 25c) as WTI fell from $85.8 to $84.8 through the quotes - adverse selection
doing exactly what the shadow-fill rule was built to expose. They will be graded at
settlement like everything else.

## 2026-11-10: the control room, rebuilt as a real front-end

The dashboard is now a React + Tailwind + Recharts app (`dashboard-src/`), compiled by
Vite into ONE self-contained `oilx/dashboard.html` — scripts, styles and the Geist
fonts are inlined, so the page still needs no CDN and no server-side assets, and the
same file runs from `oilx serve`, from GitHub Pages, or offline. Rebuild with
`cd dashboard-src && npm install && npm run build`.

Decisions: a bento grid whose 1px dividers are the grid gap showing through (no card
shadows); one accent, a burnished crude-gold, for the model and for anything
clickable; desaturated green/red for bullish/bearish; numbers in a monospace face so
columns align. Things the page deliberately does not fake: the "score trend"
sparklines are each name's logged ranking score per cycle (they start empty and fill
in), not stock prices the bot has no feed for; order "speed" is the measured
round-trip of each order request, shown only where one was recorded; the connection
latency is the last real sign-in time. New state fields to support that:
`equity_scores`, `ms` on orders, `book_bid`/`book_ask` on quotes.

## 2026-11-09 (night): the scanner was blind for a month

**The finding.** The bot never traded, and this log repeatedly called that discipline
("the liquid strips are fairly priced"). It was not. Kalshi's market payload had moved
to fixed-point string fields — `yes_bid_dollars`, `yes_ask_dollars`,
`open_interest_fp` — and dropped the legacy names. The parser read the old names, got
the defaults (bid 0, ask 1, open interest 0), and every market failed the open-interest
floor. **Every live "no signals" since launch was a parsing failure.** The Oct 15
"validation" used a snapshot written in the parser's own schema, so it could not have
caught this. Entries above that describe the zero-trade record as honest discipline are
wrong and are left in place as the record of what was believed at the time.

How it was found: after two rounds of adjusting maker filters by reasoning, one look at
a raw payload. The rule that falls out: *look at the data before theorising about the
filter.*

**What the first real scan showed** (2026-11-09 daily strip, CL 86.44, OVX 57):
- strip-implied forward 86.46 vs the CL quote 86.44 — the model is calibrated at the
  money, within ~1c of the market for |z| < 0.7;
- in both wings the market is 2–4c richer than the model: a volatility smile a
  flat-vol model does not have;
- the maker's first six candidate quotes were all wing quotes — selling tail risk for
  pennies exactly where the model is known to be wrong.

**What changed.**
1. `normalize_market` reads every schema generation; positions read `position_fp`.
2. A **schema canary** (`quote_health`): a populated series with no two-sided quote and
   no open interest is reported as a parsing failure, loudly, never as a quiet market.
3. A **wing guard** (`wing_z = 0.7`): outside the trusted moneyness band, signals are
   logged with a `wing` flag and never traded; the maker never quotes there.
4. **Shadow fills**: last cycle's passive quotes are judged against the production
   book (filled only if the ask came down to the quote) and logged for settlement
   grading. Demo fills prove plumbing; shadow fills test the strategy.
5. `health.json` every scan: what each subsystem actually read and did.
6. Regression tests run on the raw captured payload (`tests/fixtures/`), so the test
   data can no longer share the parser's assumptions.

**The first cycle with working eyes found two more layers within the hour.**
- *Orders:* every order came back HTTP 410 — Kalshi retired the legacy order endpoint.
  Ported to the V2 order API (`/portfolio/events/orders`): everything is quoted from
  the YES side (buying NO at 40c is an `ask` at 60c), prices and counts are fixed-point
  strings. Taker orders are now immediate-or-cancel; maker quotes are `post_only`, so
  a quote can never cross even if a price convention were misread. The mapping is a
  pure function with its own test. So the bot could not have traded in its first month
  even with a working parser: two independent breaks, one hiding the other.
- *Brent:* the scan printed four 10–13c "edges" on Brent, all in the same direction.
  That uniformity is the signature of a wrong forward, not a mispriced market: the
  Yahoo Brent quote was $2.11 (0.39 sd) above the forward the strip itself implies —
  almost certainly a different contract month. The stale guard allowed 0.5 sd, which
  admits ~20c of fake edge; it is now 0.1 sd, with the arithmetic in `config.toml`,
  and each cycle's quote-vs-strip gap is written to `health.json`. The order endpoint
  being dead is the only reason those four orders did not go out. Luck is not a
  control; the guard is.

**01:44 UTC, the first cycle on the V2 order API: six resting quotes placed** — the first
orders this bot has ever put on an exchange. And the check an hour later found the next
hole: five of the six were on *monthly* Brent. The weekly Brent strip had been flagged
(quote 0.48 sd from its implied forward), but the monthly strip passed, because a fixed
sd fraction is a wider dollar band at a longer horizon — the same wrong quote slipped
through the looser gate. Fix: when an underlying's quote disagrees with its most
precise strip, the quote itself is distrusted and every strip priced off it is flagged
(`distrust_forward`). One Brent shadow fill from the pre-guard cycle sits in the signal
log as `maker_shadow`; it stays, as a record of what the looser guard would have done.

**Also this sitting:** [[Cloud Mode]] — the bot runs on GitHub Actions, off the laptop
and off the campus network; and the dashboard was rebuilt with no CDN dependencies
(one vendored chart library), a plain-language state line, the health checks, and a
model-vs-market chart of the live strip. Tests: 78.

## 2026-11-09: EIA miss #3 is a network verdict, and the maker gets a confession log

**The burst worked; the network didn't.** The Wednesday wake task fired Nov 4 (late —
the 10:27 wake caught up at 1:46pm) and burst mode ran exactly as designed... into a
wall: every Kalshi request for 70 minutes died with `ConnectionResetError 10054` —
the campus network actively resets the connection. Three EIA Wednesdays, three misses,
three different failure layers (asleep; TLS flake; hard reset). Software is out of
moves. The operational fix is a decision, not code: on Wednesdays the laptop stays
home, plugged in, on home Wi-Fi, and the 10:27 wake task does the rest — or a phone
hotspot from 10:25 if it must travel. Recorded because "uptime is alpha" now has a
corollary: *the network is part of the machine.*

**Maker, round two.** The Nov 3 depth fix deployed and still: 0 quotes in 64 cycles.
This time, no guessing — a look at the live weekly strip showed the real book: $1-wide
range buckets whose richest mid is 5–10¢, OI concentrated 100–1,100, and only ~4 of 27
markets above the OI-500 floor. Two changes: the floor drops to 300 (reason documented
in config), and — the overdue application of this log's own Nov 3 lesson —
`maker_quotes` now counts every rejection by reason (window / stale_strip / low_oi /
unparsable / price_bounds) and the scan prints the tally. Next "0 staged" line will
carry its own explanation. Tests: 66.

## 2026-11-03: the maker that never quoted (a bug the logs caught)

Status forensics found maker mode had staged **zero quotes in 35 straight cycles** —
"no eligible maker quotes" every hour since launch. Root cause, by reading the code
against the live books: v1 required a quote to *join or improve the best bid*, but in
any tight or slightly rich book, fair − margin sits **below** the bid, so every liquid
market was skipped and the illiquid ones died on the OI floor. The rule contradicted
the strategy: resting below the bid is what passive *means* — the quote fills when the
market trades down to it, and the margin is the payment for that adverse selection.
Fix: quotes may rest up to `max_depth` (6¢) below the best bid, still capped at
ask − 1¢ and still only on liquid, non-stale strips. A regression test now pins the
exact failure (tight book → quote below the bid). Tests: 65.

Lesson for the log: the honest-zero discipline ("no trades is the system working") can
camouflage a dead subsystem. "Zero because priced fairly" and "zero because a filter is
impossible to satisfy" print the same line — the fix is logging *why* candidates were
rejected, and checking subsystem outputs against intent after launch, which is exactly
how this was caught.

Also seen in the same logs, same day: CL fell $98.5 → $93.7 intraday (OVX 63) on
Iran-headline whipsaw; the stale-underlying guard flagged strips through the fast move
and the book stayed flat — correct behavior under the rules as written. And a 32¢
demo-balance drift (3,250.00 → 3,249.68, Oct 29 04:44 UTC) with no order ever placed
and no position — a demo-exchange-side adjustment, noted and not ours.

## 2026-10-29 (small hours): the fast-data sitting

Aria asked where to get faster data. The honest answer first: oilx's claimed edges are
multi-day drifts, so latency only matters in one window a week — Wednesday 10:30am ET.
Two builds and one lesson:

1. **EIA burst mode** (`oilx burst`, `12_eia_burst.bat`): scan + trade every 2 minutes
   for 70 minutes, same public endpoints, same caps, same KILL switch — just a faster
   clock inside the window that matters. `11_wake_for_eia.bat` now schedules it for
   Wed 10:27am with wake-from-sleep. Reaction time to the inventory print: ~60 min → ~2.
   Considered Kalshi's WebSocket instead: cleaner, but market-data WS needs production
   credentials (we hold demo only) and burst polling achieves the same effective latency
   for a weekly event with zero new accounts.
2. **GDELT fetcher + the tone study harness** (`data.fetch_gdelt`,
   `scripts/research_news_tone.py`): GDELT's DOC API is the free headline archive
   (2017→now, daily tone + volume) that can put the caged news tilt on trial. Tonight it
   429-rate-limited every request for 40 minutes — from two different networks — so the
   fetcher went into the data layer with gentle pacing, chunked spans, and a
   keep-old-files failure mode, and the study script (verdict rules written BEFORE the
   data arrives: promote / keep caged / retire) sits ready for the moment a
   `2_fetch.bat` run lands the CSVs. Lesson repeated from the whole project: a flaky
   source is an ops problem, and ops problems get retry loops, not heroics.

## 2026-10-28 (late): the equity desk + the news tilt

Same night, second sitting: [[Equity Desk and News Tilt]]. A 17-name oil-equity universe
(upstream / integrated / midstream / refiner / services / ETF) with hand-written
strengths and weaknesses, ranked every cycle off the **same signal state as the futures
book** — the desk question is "which wrapper carries this view best?", not "another
view". Decisions worth remembering:

1. **Betas are stated priors, not fits.** Fitting per-name exposures to our daily panel
   would be a new overfitting surface with ~no independent regimes. Priors are printed
   with every pick; the scored log (vs XLE, 5-day horizon, `equity-score`) is what gets
   to prove them wrong.
2. **The refiner test.** `crude_beta <= 0` is enforced by a unit test for MPC/VLO/PSX —
   the "Marathon Petroleum is oil exposure" interview mistake is now structurally
   impossible. MRO's absence (absorbed by COP, 2024) is also a test.
3. **News is caged until it earns parole.** Google News RSS headlines scored by a
   transparent lexicon, every match logged with the pattern that fired. No free headline
   archive exists → no honest backtest → the tilt is live-only, half-weighted, equity
   ranking only. It cannot touch the futures book or Kalshi thresholds until its own log
   justifies it. First live run: container network blocked the feed and the desk
   degraded cleanly to tilt=0 — the failure path got tested before the feature did.
4. **No-trade is an output.** |top score| < 0.10 → "a weak view through equities is just
   fees." And the kill switch silences this desk too: one risk layer, every instrument.

First live rank (crude view +0.41, crack +0.51, vol 34%): OXY on top, VLO/MPC right
behind on the crack, midstream at the bottom — the 2026 regime, read correctly off the
signals with no hand-holding. Tests: 48 → 62.

## 2026-10-28: three ways to actually get filled (without lowering the bar)

Two weeks live, zero trades. Correct — the liquid WTI strips are fairly priced — but a
trading system that never trades generates no execution data either. Today's question:
how do you get real flow without corrupting the discipline? Three answers, each with its
own honesty story:

1. **Probe tier.** Edges of 3–5¢ stay below the 5¢ conviction threshold, but "never
   trade them" also means "never learn whether they're real." Probe orders buy that
   information: 2 contracts max, 3 per cycle, logged with `tier="probe"`, and
   `kalshi-score` now grades each tier separately so probe results can never inflate the
   main track record. Framing matters: this is calibration spend, not a lower bar — the
   5¢ threshold for size is untouched.
2. **Maker mode — the real fill engine.** The taker scan asks "is the displayed price
   wrong by more than the fee?" (almost always no). The maker question is better: "at
   what price would I be happy to be filled?" Each cycle the bot cancels every resting
   order and posts up to 6 fresh passive bids at model fair −2¢ on the most liquid,
   non-stale strips — capped at ask−1¢ so a quote can never cross, floored at the bid so
   it can actually fill, counted against the open-contract cap *as if every quote
   fills* (the conservative reading). Cancel-all-then-repost means nothing ever rests on
   stale information for more than an hour. This is the pmx trader study's core finding
   operationalized: makers earned roughly what takers lost. On Kalshi the maker side
   pays no fee, so a fill at fair−2¢ is +EV by construction *if the model is right* —
   which is exactly what the scored log will now start measuring with real fills.
3. **Brent.** KXBRENTW / KXBRENTMON priced off the live BZ=F quote — more markets, and
   the one place the 2026 story (Brent−WTI ~$29) actually lives. Honesty cost: there is
   no free Brent vol index, so σ is OVX (WTI vol) as a documented proxy, and Brent
   signals pay a +2¢ edge penalty for it. The alternative — pretending OVX is Brent vol
   at full confidence — is how fake edges get born.

Ops, same sitting: the scan now retries 3× (20s apart) inside a cycle, because the
Oct 28 EIA release was missed *again* — laptop awake this time, but on the campus
network that intermittently blocks Kalshi (10:44 and 11:44 cycles died on TLS). Retries
fix transient drops; a hard-blocked network needs a hotspot — recorded as an ops
constraint, not a code bug. Emergency flatten now also cancels all resting quotes (a
stop that leaves bids resting isn't a stop). Tests: 39 → 48.

## 2026-10-22 (night): four upgrades in one sitting

1. **Range markets.** The Kalshi scanner now prices `between` and `less` strikes
   (P(>lo) − P(>hi)), which admits the weekly and monthly WTI strips it previously
   skipped — roughly double the tradable universe at the same 5¢ edge threshold. A
   strip with no one-sided strikes gets a fallback stale guard: the max-mid bucket's
   midpoint stands in for the implied forward, with the bucket width added to the
   tolerance. Unknown strike structures are never priced (pmx rule: don't trade what
   you can't parse).
2. **GHR upgrades, run as tested changes.** Non-linear inventory (glut side counts at
   0.5×, per the convexity of convenience yield) and momentum-inventory conditioning
   (trend at 1.25×/0.75× by inventory agreement). Theory-prescribed before testing, then
   the full walk-forward: Sharpe 0.30→0.31, max DD −17.2%→−15.4%, 2022–now −0.19→−0.15,
   luck percentile 90→91. Kept. Every number moved a little and in the same direction,
   which is the signature of a real prior rather than a fit.
3. **[[Brent-WTI Convergence Study]].** 40 years, ten closed episodes above $12, ten
   convergences paying $6.5–8.9/bbl — and a 834-day, +$17.6-adverse 2011 episode plus
   the current one (already +$18.5 adverse, second-worst ever) as the sizing lesson.
4. **Curve clock + demand data.** Every hourly scan now logs the live CL front/2nd/3rd
   quotes to `curve_history.csv` (free forward curve data accruing from today), and the
   EIA pipeline gained product supplied, refinery utilization, and SPR series.

Context that prompted the sitting: the bot slept through the 2026-10-21 EIA release
(laptop asleep 7:44–13:16); `11_wake_for_eia.bat` now exists to wake the machine, and
the ops lesson — uptime is alpha — is recorded here on purpose.

## 2026-10-15 (night): the desk note (`oilx recommend`)

### What got built
`oilx/recommend.py` + `7_desk_note.bat`: a daily briefing that turns the signal state
into one direction and size (from the risk layer), then ranks the paper expressions -
micro futures (curve-aware: it reads the live front-vs-second CL slope and says whether
the roll earns or pays), USO for cash accounts, Kalshi binaries when the scanner has a
clean edge, and equities by exposure bucket. Plus two reference notes: [[Instrument Menu
and Exposure Map]] and [[Oil Reading List]] (ten papers, each tagged with what it would
upgrade in the code). Tests: 29.

### Decisions
**One view, many wrappers - never many views.** The note expresses the single combined
score in different instruments by horizon; it refuses to stack "a futures bet plus an
equity bet plus a Kalshi bet" as if they were diversification. They're the same trade.

**Sizing tells the truth at small NAV.** 0.11x of $10k is 0.1 micro contracts, which
doesn't exist; the note says "below one micro contract, use the ETF line" instead of
printing a fiction. (First draft printed "Buy 0.1 MCL" - caught by reading the output.)

**The exposure map leads with the classic mistake.** Marathon *Petroleum* (MPC) is a
refiner - crack-spread exposure, crude is its input cost - and Marathon *Oil* (MRO), the
E&P, was absorbed by ConocoPhillips in 2024. Refiners enter the menu only as a `crack`
expression, never as "oil exposure."

**Curve momentum stays live-only.** The momentum×term-structure conditioning
(Fuertes-Miffre-Rallis) is quoted in the note when live contract quotes are reachable;
backtesting it honestly needs curve history (top of the paid-data wishlist).

### Also fixed
- Demo credentials loader now accepts Windows' hidden-extension `.pem.txt` and validates
  the key *looks like* a key (PEM header, ~1.7KB) with a plain-English error - the first
  file saved in `secrets/` was 119 bytes, which no RSA key is.

## 2026-10-15: Kalshi oil scanner + demo trader (the pmx bridge)

### What got built
`oilx/kalshi.py` (fair value, scan, guards, scoring) and `oilx/kalshi_demo.py` (demo-only
order placement), commands `kalshi-scan` / `kalshi-score` / `kalshi-demo`, 12 new tests
(24 total). Full write-up: [[Kalshi Oil Markets]].

### Decisions
**Flat OVX vol instead of a surface, and the model knows it.** Oil has no free options
chain, so σ = OVX with no skew. Live data immediately showed the consequence: Kalshi's
Nov 3 left tail trades ~4-5¢ richer than flat-vol fair (crash skew). Decision: the model
never trades tails (min-edge + suspect guard keep it near the money) and the gap is
documented rather than "fixed" with a fudge factor.

**The strip's own implied forward polices the quote.** Fed yesterday's CL close against
today's strip, the scanner saw 30¢ of fake edge — and flagged all of it `stale_underlying`
because the strip's implied forward (94.71) disagreed with the quote (93.85). pmx's
"price from the book" rule, automated. Alternative: trust the quote and hope; rejected by
the first test.

**Demo trading is structurally demo-only.** The order client raises on any base URL that
isn't the demo exchange, credentials live in gitignored `secrets/`, orders are buy-only
limits with per-order / per-run / total caps, and flagged signals never trade. Fills on
the demo book prove mechanics, not liquidity — written on the tin.

**First result, recorded before anyone is tempted to tune:** with the correct forward,
today's scan emits **zero signals**. Same as pmx's BTC scan: the liquid strips are priced
by people already running this model with better inputs. The product is the scored signal
log (`kalshi-score`: P&L + Brier vs Kalshi's mid, distinct events as N), not a daily edge.

### Bugs found
- Float dust in the fee ceiling: 0.07·100·0.25 = 1.7500000000000002 ceil'd to $1.76.
  Round before ceiling; a test now pins $1.75.
- My first "planted loser" test for the walk-forward was a double-negated winner
  (yesterday); today's equivalent: my first epoch arithmetic for the Kalshi close-time
  window was off by five days and returned zero markets. Both caught by checking output
  against expectation, not by luck.

## 2026-10-15: v0.1, first build

### What got built
Data pipelines (EIA weekly inventories ×3, CFTC COT, CL/RB/HO front futures, USO/XOP,
OVX, T-bills, WTI/Brent spot), the aligned daily panel with release-lag joins, five
signals, the risk layer (RMS-normalized combine → vol targeting → kill switch → costs),
walk-forward weights, the backtest with bootstrap/inverted-book honesty checks, a
self-contained HTML tearsheet, 12 offline tests, and these notes.

### Decisions

**Trade one instrument (WTI front) with many signals, not many instruments.**
*Alternative:* a crude "portfolio" (WTI, Brent, products, equities).
*Why:* with one instrument, every risk-layer decision is legible and the signal math has
no cross-sectional machinery to hide bugs in. Oil equities (XOP) stay in the data layer
for research. *Cost:* no diversification across markets; the Sharpe ceiling is lower.

**Inventory scarcity stands in for carry.**
*Alternative:* real front-vs-second futures carry — the textbook commodity signal.
*Why:* no free contract-level history exists; the inventory–basis link (Gorton–
Rouwenhorst) is the same economics measured at the source. The live curve read exists in
`oilx now` so the proxy can be sanity-checked forward. First thing to upgrade with a
paid curve.

**Weekly data gets a +1 business day safety lag beyond the official release.**
*Alternative:* join on the release timestamp exactly.
*Why:* daily closes don't know intraday release times, and one conservative day costs a
little edge while removing a whole class of look-ahead bugs. The backtest should be the
pessimistic estimate.

**Losing signals are floored, never sign-flipped, by the walk-forward.**
*Alternative:* let weights go negative (the optimizer would love to).
*Why:* flipping the sign of a loser in-sample is the most reliable way to manufacture a
fake Sharpe. inv_level lost money standalone (−0.08) and is reported that way.

**The kill switch is path-dependent and dumb on purpose.**
*Alternative:* a vol-regime model or no stop at all (vol targeting already adapts).
*Why:* explainability. "15% down → flat two weeks → half size back in" survives any
interview; a regime model is another thing to overfit. Its one firing (2026) and its cost
are in the printed numbers.

**Seed data was collected through the browser from primary sources** (EIA dnav pages,
CFTC Socrata, Yahoo chart API) because FRED dropped the EIA weekly series and both FMP's
COT and Alpha Vantage's full-history equity endpoints turned out to be premium-gated.
`oilx fetch` reproduces the whole lake from a normal network connection — no key, no
subscription, which also makes the project easy for anyone to run.

### Bugs found by looking at the output (pmx tradition)
- **The book ran at 3.8% vol against a 10% target.** Averaging five signals shrinks the
  combined score, so diversification silently de-levered the book. Fix: rescale the
  combined score by its trailing RMS before vol targeting. Found by reading realized vol
  in the first run, not by any test failing.
- **A planted "loser" in the walk-forward test was secretly a winner** (double negation
  through the cot fade). The test failed, which is what tests are for; the plant was
  fixed, not the code.
- **Two bad prints in the EIA spot series** (double-digit spot moves while CL barely
  moved) — caught by the cross-check rule, treated as missing.

### Known limitations
- 2022–now is net negative (−0.19 Sharpe); see [[Evaluation and Honesty Checks]] and
  [[The 2026 Oil Shock]]. Not re-tuned.
- EIA revisions aren't modeled (today's vintage only).
- The inventory-surprise claim is about multi-day drift; without intraday data the
  10:30am jump and the drift can't be separated.

### Next steps (rough priority)
1. **Port the pmx options model to oil**: a free CL options chain (or USO options) →
   implied-vol smile → digital probabilities, compared against Kalshi's oil price
   markets — the exact pmx scanner, new underlying. This would unite the two projects.
2. Paper-trade `oilx now` forward for a semester and grade it monthly (a decade of
   backtest < a semester of true out-of-sample).
3. Brent-leg and freight-rate inputs so the inventory picture isn't US-only.
4. Event study on release days with intraday data, to locate where the surprise edge
   actually lives.
5. Vintage (as-printed) EIA data via ALFRED, if the series return there.
