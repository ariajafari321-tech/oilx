"""Commands: fetch, backtest, now, kalshi-scan, kalshi-score, kalshi-demo.

  python -m oilx fetch        refresh every raw data file from the free sources
  python -m oilx backtest     build panel -> run backtest -> write outputs + tearsheet
  python -m oilx now          print today's signal scores and target position
  python -m oilx kalshi-scan  price Kalshi's WTI markets off a flat-vol digital model
                              (--snapshot FILE for offline; --forward / --vol override)
  python -m oilx kalshi-score grade every logged signal that has settled (P&L + Brier)
  python -m oilx kalshi-demo  place capped limit orders for clean signals on the DEMO
                              exchange (needs secrets/, see oilx/kalshi_demo.py)
  python -m oilx recommend    write the desk note: today's view, ranked paper expressions
                              (futures/curve/ETF/Kalshi/equities), exposure map (--nav N)
  python -m oilx equity-pick  rank the 17-name oil-equity universe off the live signal
                              state + news tilt; log one paper pick (graded vs XLE)
  python -m oilx equity-score grade every logged equity pick old enough to judge
  python -m oilx serve        the control room: local dashboard at http://127.0.0.1:8766
                              (charts, blotter, signals, autotrade toggle, kill switch)
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("oilx")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="oilx")
    ap.add_argument("command", choices=["fetch", "backtest", "now", "recommend", "serve",
                                        "kalshi-scan", "kalshi-score", "kalshi-demo",
                                        "equity-pick", "equity-score", "burst",
                                        "export-state", "stop", "resume", "flatten"])
    ap.add_argument("--minutes", type=float, default=70.0, help="burst: how long to run")
    ap.add_argument("--interval", type=float, default=120.0, help="burst: seconds between passes")
    ap.add_argument("--wait-until", default=None, metavar="HH:MM",
                    help="burst: sleep until this New York time first; exits quietly if "
                         "that is more than --max-wait minutes away or already past "
                         "(lets one UTC cron cover both EST and EDT)")
    ap.add_argument("--max-wait", type=float, default=45.0, help="burst: see --wait-until")
    ap.add_argument("--nav", type=float, default=10_000.0, help="recommend: paper NAV for sizing")
    ap.add_argument("--port", type=int, default=8766, help="serve: dashboard port")
    ap.add_argument("--config", default=None, help="path to config.toml")
    ap.add_argument("--snapshot", default=None, help="kalshi-scan: offline markets JSON")
    ap.add_argument("--forward", type=float, default=None, help="kalshi-scan: override CL forward")
    ap.add_argument("--vol", type=float, default=None, help="kalshi-scan: override sigma (e.g. 0.49)")
    args = ap.parse_args(argv)

    from . import config as cfg_mod
    cfg_path = args.config or Path(__file__).resolve().parent.parent / "config.toml"
    cfg = cfg_mod.load(cfg_path)

    if args.command == "fetch":
        from . import data
        written = data.refresh(cfg.raw_dir)
        print(f"refreshed {len(written)} files: {', '.join(written) or 'none'}")
        return 0

    if args.command == "serve":
        from . import web
        web.serve(cfg, port=args.port)
        return 0

    if args.command == "burst":
        # EIA release mode: scan+trade every --interval seconds for --minutes minutes.
        # The weekly inventory number lands Wednesday 10:30am ET and the strips reprice
        # over the following minutes; the hourly cadence watches that through a keyhole.
        # Burst polls the same public endpoints, just faster, only inside this window.
        import time as _t
        from datetime import datetime as _dt
        if args.wait_until:
            from zoneinfo import ZoneInfo
            ny = _dt.now(ZoneInfo("America/New_York"))
            hh, mm = (int(x) for x in args.wait_until.split(":"))
            wait_min = (ny.replace(hour=hh, minute=mm, second=0, microsecond=0) - ny
                        ).total_seconds() / 60
            if wait_min > args.max_wait or wait_min < -20:
                print(f"burst: {args.wait_until} New York is {wait_min:+.0f} min away - "
                      "not this run's window; exiting")
                return 0
            if wait_min > 0:
                print(f"burst: waiting {wait_min:.0f} min for {args.wait_until} New York")
                _t.sleep(wait_min * 60)
        end = _t.time() + args.minutes * 60
        n = 0
        print(f"burst: every {args.interval:.0f}s for {args.minutes:.0f}m "
              f"(caps per pass unchanged; KILL respected)")
        while _t.time() < end:
            if (cfg.out_dir / "KILL").exists():
                print("burst: KILL engaged - stopping")
                break
            n += 1
            print(f"--- burst pass {n} at {_dt.now().isoformat(timespec='seconds')} ---")
            for sub in ("kalshi-scan", "kalshi-demo"):
                try:
                    main([sub] + (["--config", str(cfg_path)] if args.config else []))
                except SystemExit:
                    pass
                except Exception as e:
                    print(f"burst: {sub} failed this pass: {e}")
            rem = end - _t.time()
            if rem <= 0:
                break
            _t.sleep(min(args.interval, rem))
        print(f"burst done after {n} passes")
        return 0

    if args.command in ("stop", "resume", "flatten"):
        from . import kalshi_demo
        cfg.out_dir.mkdir(parents=True, exist_ok=True)
        kill = cfg.out_dir / "KILL"
        if args.command == "resume":
            kill.unlink(missing_ok=True)
            print("KILL cleared - the bot may trade again")
            return 0
        if args.command == "stop":
            kill.write_text("engaged from the command line\n")
            print("KILL set - trading refused until `oilx resume`")
        print(kalshi_demo.flatten_all(cfg.root / "secrets", cfg.out_dir))
        return 0

    if args.command == "export-state":
        # Cloud mode: write everything the dashboard shows to one static JSON file, so
        # the same page works from a static host (GitHub Pages) with no server at all.
        import json as _json
        from . import web
        st = web.build_state(cfg, mode="cloud")
        cfg.out_dir.mkdir(parents=True, exist_ok=True)
        (cfg.out_dir / "state.json").write_text(_json.dumps(st))
        print(f"state exported: {len(_json.dumps(st)) // 1024} KB")
        return 0

    if args.command == "equity-score":
        from . import equities
        print(equities.score(cfg.out_dir / "equity_pick_log.jsonl",
                             horizon_days=int(cfg.equities.get("horizon_days", 5))))
        return 0

    if args.command.startswith("kalshi"):
        from . import kalshi
        kc = cfg.kalshi
        out_dir = cfg.out_dir
        if args.command == "kalshi-score":
            print(kalshi.score(out_dir / "kalshi_signals_log.jsonl"))
            return 0
        if args.command == "kalshi-demo":
            from . import kalshi_demo
            d = kc.get("demo", {})
            print(kalshi_demo.trade_signals(
                out_dir / "kalshi_scan_latest.json", cfg.root / "secrets",
                max_contracts=int(d.get("max_contracts_per_order", 10)),
                max_orders=int(d.get("max_orders_per_run", 5)),
                max_open_contracts=int(d.get("max_open_contracts", 100)),
                min_edge=float(kc.get("min_edge", 0.05)),
                probe=d.get("probe", {}), maker=d.get("maker", {})))
            return 0
        # kalshi-scan
        from . import data

        def _retry(fn, what):
            """Campus Wi-Fi drops TLS to Kalshi/Yahoo intermittently; retry in-cycle so
            an hourly run survives a transient failure instead of losing the hour."""
            tries = int(kc.get("scan_retries", 3))
            wait = float(kc.get("scan_retry_wait_sec", 20))
            import time as _t
            for i in range(tries):
                try:
                    return fn()
                except Exception as e:
                    if i == tries - 1:
                        raise
                    log.warning("%s failed (%s); retry %d/%d in %.0fs",
                                what, e, i + 1, tries - 1, wait)
                    _t.sleep(wait)

        import json as _json
        from datetime import datetime as _dt, timezone as _tz
        net_err: list[str] = []

        def _write_health(**kw):
            """One small file per scan saying what every subsystem actually did, so a
            dead component can never again hide behind an honest-looking 'no signals'."""
            out_dir.mkdir(parents=True, exist_ok=True)
            kw.update(ts=_dt.now(_tz.utc).isoformat(timespec="seconds"), network_errors=net_err)
            (out_dir / "health.json").write_text(_json.dumps(kw, indent=1))
            with (out_dir / "health_log.jsonl").open("a") as f:
                f.write(_json.dumps({k: kw[k] for k in ("ts", "ok", "schema_suspect")
                                     if k in kw} | {"net": len(net_err)}) + "\n")

        sources: dict = {}
        sigma = args.vol
        if sigma is None:
            try:
                sigma = _retry(lambda: float(
                    data.fetch_yahoo("^OVX", start="2026-09-01")["value"].iloc[-1]) / 100, "OVX")
                sources["sigma"] = "OVX live"
            except Exception as e:
                # Quote hosts sometimes refuse datacenter IPs. Vol moves slowly, so the
                # last value the bot itself recorded is a sound stand-in - and it is
                # labelled as such in the health report, never passed off as live.
                net_err.append(f"OVX: {type(e).__name__}")
                sigma = None
                try:  # 1) FRED publishes the CBOE's OVX close daily, free and keyless
                    import io as _io
                    import pandas as _pd
                    import requests as _rq
                    r = _rq.get("https://fred.stlouisfed.org/graph/fredgraph.csv",
                                params={"id": "OVXCLS"}, timeout=30,
                                headers={"User-Agent": "oilx/0.1 (student research)"})
                    r.raise_for_status()
                    col = _pd.to_numeric(_pd.read_csv(_io.StringIO(r.text)).iloc[:, 1],
                                         errors="coerce").dropna()
                    if len(col) and 5 < float(col.iloc[-1]) < 400:
                        sigma = float(col.iloc[-1]) / 100
                        sources["sigma"] = "OVX previous close from FRED (live quote unavailable)"
                except Exception as e2:
                    net_err.append(f"FRED OVX: {type(e2).__name__}")
                if sigma is None:
                    try:  # 2) the last value this bot recorded FROM A REAL SOURCE - a stale
                        # stand-in must never be recycled as if it were a measurement
                        hj = _json.loads((out_dir / "health.json").read_text())
                        src = str(hj.get("sources", {}).get("sigma", ""))
                        if src.startswith("OVX live") or "FRED" in src:
                            sigma = float(hj["sigma"])
                            sources["sigma"] = "last OVX this bot measured (live quote unavailable)"
                    except Exception:
                        pass
                if sigma is None:
                    try:  # 3) the daily file, however old - labelled as such
                        import pandas as _pd
                        sigma = float(_pd.read_csv(cfg.raw_dir / "ovx_daily.csv").iloc[-1, 1]) / 100
                        sources["sigma"] = "OVX from the daily file (live quote unavailable)"
                    except Exception:
                        print("kalshi-scan: no volatility input available; nothing scanned")
                        _write_health(ok=False, reason="no volatility input (OVX unreachable)")
                        return 0

        # underlying groups: WTI off CL=F; Brent off BZ=F with OVX as the vol PROXY
        # (no free Brent vol index exists), so Brent pays an extra edge penalty.
        if args.snapshot:
            groups = [("WTI", {"snapshot": kalshi.load_snapshot(Path(args.snapshot))},
                       args.forward, 0.0)]
            if groups[0][2] is None:
                groups = [("WTI", groups[0][1],
                           _retry(lambda: float(data.fetch_yahoo(
                               "CL=F", start="2026-09-01")["value"].iloc[-1]), "CL=F"), 0.0)]
        else:
            groups = []
            pfs: dict = {}
            for name, series, symbol, extra in (
                    ("WTI", kc.get("series", kalshi.SERIES), "CL=F", 0.0),
                    ("BRENT", kc.get("brent_series", []), kc.get("brent_symbol", "BZ=F"),
                     float(kc.get("brent_extra_edge", 0.02)))):
                if not series:
                    continue
                by_series = {}
                for s in series:
                    try:
                        by_series[s] = _retry(lambda s=s: kalshi.fetch_markets(s), s)
                    except Exception as e:
                        log.warning("series %s skipped: %s", s, e)
                        net_err.append(f"{s}: {type(e).__name__}")
                if not any(by_series.values()):
                    continue
                quote = args.forward if name == "WTI" else None
                if quote is None:
                    try:
                        quote = _retry(lambda: float(data.fetch_yahoo(
                            symbol, start="2026-09-01")["value"].iloc[-1]), symbol)
                    except Exception as e:
                        net_err.append(f"{symbol}: {type(e).__name__}")
                allm = [m for mk in by_series.values() for m in mk]
                pf = kalshi.pricing_forward(allm, quote,
                                            max_gap_pct=float(kc.get("max_forward_gap_pct", 3.0)))
                if pf is None:  # no quote and no threshold strip: last resort, range buckets
                    rng = kalshi.implied_forward_from_ranges(allm)
                    if not rng:
                        log.warning("%s: no forward available; group skipped", name)
                        continue
                    pf = {"fwd": rng[0], "source": "ranges", "quote": None, "implied": None,
                          "gap": None, "gap_pct": None, "limit_pct": None, "distrust": False}
                f = pf["fwd"]
                pfs[name] = pf
                sources[name] = {"strip": "the market's own prices" + ("" if quote is not None else " (live quote unavailable)"),
                                 "quote": f"{symbol} live", "ranges": "range buckets (live quote unavailable)"}[pf["source"]]
                print({name: {k: len(v) for k, v in by_series.items()}, "fwd": round(f, 2)})
                groups.append((name, by_series, f, extra))
        if not groups:
            print("kalshi-scan: no market group reachable this cycle (network); nothing scanned")
            _write_health(ok=False, reason="no market group reachable (network)")
            return 0
        fwd = groups[0][2]  # WTI forward, for curve logging + the render header
        # curve logging: every scan appends the live front contracts (free forward data)
        if not args.snapshot:
            try:
                import csv as _csv, time as _time
                ticks, quotes = [], []
                for t in data.next_cl_contracts(n=4):  # skip just-expired contracts
                    if len(quotes) == 2:
                        break
                    try:
                        df = data.fetch_yahoo(t, start="2026-09-01")
                        if df is not None and len(df):
                            ticks.append(t)
                            quotes.append(float(df["value"].iloc[-1]))
                    except Exception:
                        continue
                if len(quotes) < 2:
                    raise RuntimeError("fewer than two live contracts quoted")
                cp = cfg.out_dir / "curve_history.csv"
                cfg.out_dir.mkdir(parents=True, exist_ok=True)
                new = not cp.exists()
                with cp.open("a", newline="") as f:
                    w = _csv.writer(f)
                    if new:
                        w.writerow(["ts", "cl_front_quote", "m1_ticker", "m1", "m2_ticker", "m2",
                                    "carry_ann"])
                    carry = (quotes[0] / quotes[1] - 1) * 12 if quotes[1] else ""
                    w.writerow([int(_time.time()), fwd, ticks[0], quotes[0], ticks[1], quotes[1],
                                round(carry, 4) if carry != "" else ""])
            except Exception as e:
                log.info("curve logging skipped: %s", e)
        probe_cfg = kc.get("demo", {}).get("probe", {})
        maker_cfg = kc.get("demo", {}).get("maker", {})
        base_edge = float(kc.get("min_edge", 0.05))
        probe_base = float(probe_cfg.get("min_edge", 0.03)) if probe_cfg.get("enabled") else None
        sigs, quotes = [], []
        maker_rej: dict = {}
        wing_z = float(kc.get("wing_z", 0.7))
        health_series, all_markets, fwds, fwd_check = {}, [], {}, {}
        import math as _math
        for name, by_series, f, extra in groups:
            fwds[name] = f
            pf = (pfs if not args.snapshot else {}).get(name)
            distrust = bool(pf and pf["distrust"])
            if pf and pf["quote"] is not None and pf["implied"] is not None:
                fwd_check[name] = {k: pf[k] for k in ("quote", "implied", "gap", "gap_pct", "limit_pct")}
                if distrust:
                    print(f"forward check: {name} quote {pf['quote']:.2f} vs the market's own "
                          f"{pf['implied']:.2f} ({pf['gap_pct']:.1f}% apart) - too far to be a "
                          f"delay; every {name} market is flagged and left alone this cycle")
            for sname, mk in by_series.items():
                h = kalshi.quote_health(mk)
                health_series[sname] = h
                all_markets += mk
                if h["suspect_schema"]:
                    print(f"!!! SCHEMA DRIFT SUSPECTED in {sname}: {h['markets']} markets, none "
                          "with a two-sided quote or open interest - the parser is probably "
                          "reading the wrong field names. Signals from this series are void.")
            sigs += kalshi.scan(by_series, f, sigma,
                                min_edge=base_edge + extra,
                                probe_edge=(probe_base + extra) if probe_base is not None else None,
                                underlying=name, wing_z=wing_z, distrust_forward=distrust,
                                suspect_edge=float(kc.get("suspect_edge", 0.25)),
                                min_hours=float(kc.get("min_hours_to_close", 2.0)),
                                max_days=float(kc.get("max_days_to_close", 45)),
                                min_oi=float(kc.get("min_open_interest", 100)),
                                taker_rate=float(kc.get("taker_rate", 0.07)),
                                stale_sd_frac=float(kc.get("stale_sd_frac", 0.1)))
            if maker_cfg.get("enabled"):
                quotes += kalshi.maker_quotes(
                    by_series, f, sigma, underlying=name, reject_counts=maker_rej,
                    wing_z=wing_z, distrust_forward=distrust,
                    margin=float(maker_cfg.get("margin", 0.02)) + extra,  # Brent pays for its proxy vol
                    max_depth=float(maker_cfg.get("max_depth", 0.06)),
                    min_oi=float(maker_cfg.get("min_open_interest", 500)),
                    max_quotes=int(maker_cfg.get("max_resting_orders", 6)),
                    min_hours=float(kc.get("min_hours_to_close", 2.0)),
                    max_days=float(kc.get("max_days_to_close", 45)),
                    stale_sd_frac=float(kc.get("stale_sd_frac", 0.1)))
        sigs.sort(key=lambda s: (s.flags != "", s.tier != "main", -s.edge))
        n_fills = 0
        if maker_cfg.get("enabled"):
            out_dir.mkdir(parents=True, exist_ok=True)
            qp = out_dir / "kalshi_maker_quotes.json"
            # shadow fills: did LAST cycle's quotes trade on the production book?
            if qp.exists() and not args.snapshot:
                try:
                    prev = _json.loads(qp.read_text())
                    fills = kalshi.shadow_fills(
                        prev, all_markets, _dt.now(_tz.utc).isoformat(timespec="seconds"))
                    n_fills = len(fills)
                    for fp in ("kalshi_signals_log.jsonl", "kalshi_shadow_fills.jsonl"):
                        with (out_dir / fp).open("a") as fh:
                            for row in fills:
                                fh.write(_json.dumps(row) + "\n")
                    for row in fills:
                        print(f"shadow fill: {row['side']} {row['ticker']} @{row['price']:.2f} "
                              f"(fair at quote {row['model_p']:.2f})")
                except Exception as e:
                    log.warning("shadow-fill check skipped: %s", e)
            quotes.sort(key=lambda q: -q["oi"])
            quotes = quotes[:int(maker_cfg.get("max_resting_orders", 6))]
            qp.write_text(_json.dumps(quotes, indent=1))
            why = ", ".join(f"{k} {v}" for k, v in sorted(maker_rej.items()) if v)
            print(f"maker: {len(quotes)} passive quotes staged for the demo trader"
                  + (f" (rejected: {why})" if why else ""))
        kalshi.save_signals(sigs, out_dir)
        try:  # model-vs-market picture for the dashboard (nearest WTI threshold strip)
            wti = [m for mk in groups[0][1].values() for m in mk]
            sv = kalshi.strip_view(wti, groups[0][2], sigma, wing_z=wing_z)
            if sv:
                (out_dir / "kalshi_strip_latest.json").write_text(_json.dumps(sv))
        except Exception as e:
            log.warning("strip view skipped: %s", e)
        print(kalshi.render(sigs, fwd, sigma))
        if not args.snapshot:
            _write_health(
                ok=not any(h["suspect_schema"] for h in health_series.values()),
                schema_suspect=any(h["suspect_schema"] for h in health_series.values()),
                series=health_series, fwd=fwds, sigma=sigma, sources=sources,
                fwd_check=fwd_check,
                signals={"main": sum(1 for s in sigs if not s.flags and s.tier == "main"),
                         "probe": sum(1 for s in sigs if not s.flags and s.tier == "probe"),
                         "flagged": sum(1 for s in sigs if s.flags)},
                maker={"staged": len(quotes), "rejects": maker_rej, "shadow_fills": n_fills})
        return 0

    from . import panel as panel_mod
    pnl = panel_mod.build(cfg)

    if args.command == "equity-pick":
        from . import equities
        out = equities.run(cfg, pnl)
        print(equities.render(out))
        return 0

    if args.command == "recommend":
        from . import recommend
        out = recommend.run(cfg, pnl, nav=args.nav)
        print(f"\nsaved: {out}")
        return 0

    if args.command == "backtest":
        from . import backtest, report
        res = backtest.run(pnl, cfg)
        backtest.save(res, cfg)
        print(report.text_report(res))
        out = report.tearsheet(res, cfg, pnl)
        print(f"\ntearsheet: {out}")
        return 0

    if args.command == "now":
        from . import risk, signals
        scores = signals.compute_all(pnl, cfg)
        last = scores.dropna(how="all").iloc[-1]
        vol = risk.realized_vol(pnl["ret"], cfg.vol_lookback_days).iloc[-1]
        print(f"as of {scores.index[-1].date()}  (instrument vol ~{vol*100:.0f}%/yr)")
        for k, v in last.items():
            print(f"  {k:>13}: {v:+.2f}")
        eq = last.mean()
        scalar = min(cfg.vol_target / vol, cfg.max_leverage)
        print(f"  equal-weight score {eq:+.2f} -> target position {eq*scalar:+.2f}x NAV")
        print("  (walk-forward weights apply in the backtest; `now` shows equal weights)")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
