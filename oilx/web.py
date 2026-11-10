"""The oilx control room: a local web dashboard served by the bot itself.

`python -m oilx serve` -> http://127.0.0.1:8766  (binds localhost only; the signing key,
the scheduler and the engine all stay on this machine - that's why this is a local page
and not a hosted one).

GET  /            the terminal UI (web/dashboard.html)
GET  /api/state   everything the UI shows, one JSON blob (cached ~15s)
POST /api/autotrade {"on": true|false}   register/remove the hourly Windows task
POST /api/cycle                          run one scan+trade cycle now (background)
POST /api/flatten                        market-close every open demo position
POST /api/kill      {"on": true|false}   KILL: stop the task, flatten, and drop the
                                         sentinel file that makes trade_signals refuse;
                                         off = resume (sentinel removed)

Every mutating action is a POST from the browser on this machine - the human clicks.
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pandas as pd

from . import risk, signals
from .config import Config

log = logging.getLogger("oilx.web")
TASKNAME = "oilx demo trader"
BBL = 42.0


class Hub:
    """State cache + the control actions."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._state: dict = {}
        self._state_ts = 0.0
        self._lock = threading.Lock()
        self.cycle_running = False

    # ---------------- controls

    def autotrade_status(self) -> bool:
        try:
            r = subprocess.run(["schtasks", "/Query", "/TN", TASKNAME],
                               capture_output=True, text=True, timeout=10)
            return r.returncode == 0
        except Exception:
            return False

    def set_autotrade(self, on: bool) -> str:
        bat = self.cfg.root / "scripts" / "run_cycle.bat"
        if on:
            cmd = ["schtasks", "/Create", "/F", "/SC", "HOURLY", "/TN", TASKNAME,
                   "/TR", f'cmd /c ""{bat}""']
        else:
            cmd = ["schtasks", "/Delete", "/F", "/TN", TASKNAME]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return (r.stdout + r.stderr).strip() or ("on" if on else "off")

    def kill_path(self) -> Path:
        return self.cfg.out_dir / "KILL"

    def set_kill(self, on: bool) -> str:
        from . import kalshi_demo
        msgs = []
        if on:
            self.cfg.out_dir.mkdir(parents=True, exist_ok=True)
            self.kill_path().write_text("engaged from dashboard\n")
            msgs.append("KILL sentinel set - trading refused until resume")
            try:
                msgs.append(self.set_autotrade(False))
            except Exception as e:
                msgs.append(f"autotrade off failed: {e}")
            try:
                msgs.append(kalshi_demo.flatten_all(self.cfg.root / "secrets", self.cfg.out_dir))
            except Exception as e:
                msgs.append(f"flatten failed: {e}")
        else:
            self.kill_path().unlink(missing_ok=True)
            msgs.append("KILL cleared - bot may trade again (autotrade stays off until you enable it)")
        return "\n".join(msgs)

    def run_cycle_async(self) -> str:
        if self.cycle_running:
            return "a cycle is already running"
        def _run():
            self.cycle_running = True
            try:
                out = []
                for cmdname in ("kalshi-scan", "kalshi-demo"):
                    r = subprocess.run([sys.executable, "-m", "oilx", cmdname],
                                       capture_output=True, text=True,
                                       cwd=self.cfg.root, timeout=600)
                    out.append(f"$ oilx {cmdname}\n{r.stdout}{r.stderr}")
                logp = self.cfg.out_dir / "auto_run_log.txt"
                with logp.open("a") as f:
                    f.write(f"\n===== dashboard cycle =====\n" + "\n".join(out) + "\n")
            finally:
                self.cycle_running = False
                self._state_ts = 0  # force refresh
        threading.Thread(target=_run, daemon=True).start()
        return "cycle started"

    def flatten(self) -> str:
        from . import kalshi_demo
        return kalshi_demo.flatten_all(self.cfg.root / "secrets", self.cfg.out_dir)

    # ---------------- state

    def state(self) -> dict:
        with self._lock:
            if time.time() - self._state_ts < 15 and self._state:
                return self._state
            s = self._build_state()
            self._state, self._state_ts = s, time.time()
            return s

    def _build_state(self) -> dict:
        return build_state(self.cfg, mode="local", autotrade=self.autotrade_status(),
                           cycle_running=self.cycle_running)


def _read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text()) if path.exists() else default
    except Exception:
        return default


def _tail_jsonl(path: Path, n: int) -> list[dict]:
    try:
        if not path.exists():
            return []
        return [json.loads(l) for l in path.read_text().splitlines()[-n:] if l.strip()]
    except Exception:
        return []


def build_state(cfg: Config, *, mode: str = "local", autotrade: bool | None = None,
                cycle_running: bool = False) -> dict:
    """Everything the dashboard shows, as one JSON-able dict. Used two ways: served
    live by the local control room (mode="local"), and written to a static state.json
    by `oilx export-state` when the bot runs on a hosted runner (mode="cloud")."""
    import os
    out: dict = {"ts": time.time(), "mode": mode, "cycle_running": cycle_running,
                 "killed": (cfg.out_dir / "KILL").exists(),
                 # in cloud mode the scheduler is the workflow itself: on unless killed
                 "autotrade": autotrade if autotrade is not None else mode == "cloud",
                 "repo": os.environ.get("GITHUB_REPOSITORY", "")}

    # prices + crack from the raw cache (fast; no network)
    try:
        cl = pd.read_csv(cfg.raw_dir / "cl_front_daily.csv", parse_dates=["date"])
        rb = pd.read_csv(cfg.raw_dir / "rbob_front_daily.csv", parse_dates=["date"])
        ho = pd.read_csv(cfg.raw_dir / "heatoil_front_daily.csv", parse_dates=["date"])
        m = cl.merge(rb, on="date").merge(ho, on="date").tail(260)
        m["crack"] = (2 * m.iloc[:, 2] * BBL + m.iloc[:, 3] * BBL - 3 * m.iloc[:, 1]) / 3
        out["price_series"] = [{"time": d.strftime("%Y-%m-%d"), "value": round(v, 2)}
                               for d, v in zip(m["date"], m.iloc[:, 1])]
        out["crack_series"] = [{"time": d.strftime("%Y-%m-%d"), "value": round(v, 2)}
                               for d, v in zip(m["date"], m["crack"])]
        out["cl_last"] = float(m.iloc[-1, 1])
        out["raw_asof"] = m["date"].iloc[-1].strftime("%Y-%m-%d")
    except Exception as e:
        out["price_error"] = str(e)

    # signals + target position
    try:
        from . import panel as panel_mod
        pnl = panel_mod.build(cfg)
        sc = signals.compute_all(pnl, cfg).dropna(how="all")
        last = sc.iloc[-1]
        vol = float(risk.realized_vol(pnl["ret"], cfg.vol_lookback_days).iloc[-1])
        score = float(last.mean())
        scalar = min(cfg.vol_target / vol, cfg.max_leverage)
        out["signals"] = {k: round(float(v), 2) for k, v in last.items()}
        out["signal_asof"] = str(sc.index[-1].date())
        out["score"] = round(score, 2)
        out["inst_vol"] = round(vol, 3)
        out["target_pos"] = round(max(-cfg.max_leverage, min(cfg.max_leverage, score * scalar)), 3)
        out["ovx"] = round(float(pnl["ovx"].ffill().iloc[-1]), 1) if "ovx" in pnl else None
    except Exception as e:
        out["signal_error"] = str(e)

    # kalshi scan + health + strip + maker
    p = cfg.out_dir / "kalshi_scan_latest.json"
    out["scan"] = _read_json(p, [])
    out["scan_ts"] = p.stat().st_mtime if p.exists() else None
    out["health"] = _read_json(cfg.out_dir / "health.json")
    out["strip"] = _read_json(cfg.out_dir / "kalshi_strip_latest.json")
    out["maker_quotes"] = _read_json(cfg.out_dir / "kalshi_maker_quotes.json", [])
    out["shadow_fills"] = _tail_jsonl(cfg.out_dir / "kalshi_shadow_fills.jsonl", 40)
    out["health_log"] = _tail_jsonl(cfg.out_dir / "health_log.jsonl", 72)

    # live quote overrides the stale daily file when the last scan has one
    h = out["health"] or {}
    if isinstance(h.get("fwd"), dict) and h["fwd"].get("WTI"):
        out["cl_live"] = round(float(h["fwd"]["WTI"]), 2)
        out["ovx_live"] = round(float(h.get("sigma", 0)) * 100, 1) or None

    # demo account
    try:
        from .kalshi_demo import DemoClient, position_size
        t0 = time.time()
        client = DemoClient(cfg.root / "secrets")
        bal = client.balance()
        out["api_latency_ms"] = round((time.time() - t0) * 1000)
        pos = [{"ticker": q.get("ticker"), "position": position_size(q),
                "exposure": q.get("market_exposure_dollars")} for q in client.positions()]
        out["demo"] = {"balance": bal.get("balance", 0) / 100,
                       "positions": [q for q in pos if q["position"] != 0]}
    except Exception as e:
        out["demo"] = {"error": str(e)}

    # history, orders, logs
    try:
        p = cfg.out_dir / "balance_history.csv"
        if p.exists():
            bh = pd.read_csv(p)
            out["balance_history"] = bh.tail(500).to_dict("records")
            if "balance" not in out["demo"] and len(bh):
                out["demo"]["last_known_balance"] = float(bh.iloc[-1]["balance"])
            today = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
            day = bh[bh["ts"].str.startswith(today)]
            if len(day) and "balance" in out["demo"]:
                out["daily_pnl"] = round(out["demo"]["balance"] - float(day.iloc[0]["balance"]), 2)
    except Exception:
        pass
    out["orders"] = _tail_jsonl(cfg.out_dir / "kalshi_orders.jsonl", 40)
    out["resting"] = (_read_json(cfg.out_dir / "kalshi_open_orders.json", {}) or {}).get("orders", [])
    out["equity"] = _read_json(cfg.out_dir / "equity_pick_latest.json")
    hist: dict = {}
    for row in _tail_jsonl(cfg.out_dir / "equity_pick_log.jsonl", 48):
        for tk, sc in (row.get("scores") or {}).items():
            hist.setdefault(tk, []).append(sc)
    out["equity_scores"] = hist
    try:
        cp = cfg.out_dir / "curve_history.csv"
        if cp.exists():
            ch = pd.read_csv(cp).tail(400)
            out["curve"] = [{"time": int(t), "value": round(float(c), 4)}
                            for t, c in zip(ch["ts"], ch["carry_ann"]) if pd.notna(c)]
    except Exception:
        pass
    logs = []
    for name, n in (("kalshi_demo_log.txt", 30), ("auto_run_log.txt", 30)):
        lp = cfg.out_dir / name
        if lp.exists():
            logs += lp.read_text(errors="replace").splitlines()[-n:]
    out["logs"] = logs
    return out


def make_handler(hub: Hub, html_path: Path):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj).encode(), "application/json")

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(200, html_path.read_bytes(), "text/html; charset=utf-8")
            elif self.path.startswith("/vendor/"):
                # vendored JS only: a fixed directory, plain file names, no traversal
                name = self.path[len("/vendor/"):].split("?")[0]
                f = html_path.parent / "vendor" / name
                if name and "/" not in name and "\\" not in name and ".." not in name \
                        and f.is_file() and f.suffix == ".js":
                    self._send(200, f.read_bytes(), "application/javascript; charset=utf-8")
                else:
                    self._json({"error": "not found"}, 404)
            elif self.path == "/api/state":
                try:
                    self._json(hub.state())
                except Exception as e:
                    self._json({"error": str(e)}, 500)
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                body = {}
            try:
                if self.path == "/api/autotrade":
                    msg = hub.set_autotrade(bool(body.get("on")))
                elif self.path == "/api/cycle":
                    msg = hub.run_cycle_async()
                elif self.path == "/api/flatten":
                    msg = hub.flatten()
                elif self.path == "/api/kill":
                    msg = hub.set_kill(bool(body.get("on", True)))
                else:
                    return self._json({"error": "not found"}, 404)
                hub._state_ts = 0
                self._json({"ok": True, "message": msg})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)
    return H


def serve(cfg: Config, port: int = 8766) -> None:
    hub = Hub(cfg)
    html = Path(__file__).resolve().parent / "dashboard.html"
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(hub, html))
    print(f"oilx control room: http://127.0.0.1:{port}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
