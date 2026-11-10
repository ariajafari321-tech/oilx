"""Control-room tests: state endpoint serves offline, KILL blocks trading, flatten math."""
from __future__ import annotations

import json
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from oilx import web, kalshi_demo
from oilx.config import load as load_cfg


@pytest.fixture()
def cfg(tmp_path):
    root = Path(__file__).resolve().parent.parent
    shutil.copytree(root / "data" / "raw", tmp_path / "data" / "raw")
    (tmp_path / "config.toml").write_text((root / "config.toml").read_text())
    return load_cfg(tmp_path / "config.toml")


def test_kill_sentinel_blocks_trading(cfg):
    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    (cfg.out_dir / "KILL").write_text("x")
    (cfg.out_dir / "kalshi_scan_latest.json").write_text("[]")
    msg = kalshi_demo.trade_signals(cfg.out_dir / "kalshi_scan_latest.json",
                                    cfg.root / "secrets")
    assert "KILL switch engaged" in msg
    # and the refusal is logged
    assert "KILL" in (cfg.out_dir / "kalshi_demo_log.txt").read_text()


def test_flatten_sides(monkeypatch, tmp_path):
    calls = []
    class FakeClient:
        def positions(self):
            return [{"ticker": "A", "position": 7}, {"ticker": "B", "position": -3},
                    {"ticker": "C", "position": 0}]
        def sell_market(self, ticker, side, count):
            calls.append((ticker, side, count))
            return {}
    monkeypatch.setattr(kalshi_demo, "DemoClient", lambda *a, **k: FakeClient())
    out = kalshi_demo.flatten_all(tmp_path, tmp_path)
    assert ("A", "yes", 7) in calls and ("B", "no", 3) in calls
    assert all(c[0] != "C" for c in calls)          # flat position untouched
    assert "flattened A" in out and "flattened B" in out


def test_state_endpoint_serves_without_network(cfg, monkeypatch):
    hub = web.Hub(cfg)
    monkeypatch.setattr(web.Hub, "autotrade_status", lambda self: False)
    handler = web.make_handler(hub, Path(web.__file__).parent / "dashboard.html")
    import http.server
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    port = srv.server_address[1]
    try:
        page = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=10).read()
        assert b"oilx control room" in page.lower()
        # the page must load with no internet: no CDN references, charts vendored locally
        assert b"cdn." not in page and b"unpkg" not in page and b"https://cdn" not in page
        js = urllib.request.urlopen(f"http://127.0.0.1:{port}/vendor/lightweight-charts.js",
                                    timeout=10).read()
        assert len(js) > 100_000
        for bad in ("/vendor/..%2Fweb.py", "/vendor/../web.py", "/vendor/nope.js"):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}{bad}", timeout=10)
                raise AssertionError(f"{bad} should not be served")
            except urllib.error.HTTPError as e:
                assert e.code == 404
        state = json.loads(urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/state", timeout=120).read())
        assert "price_series" in state and len(state["price_series"]) > 100
        assert "signals" in state and "mom" in state["signals"]
        assert state["killed"] is False
        assert state["mode"] == "local"
        # demo section degrades gracefully with no credentials
        assert "error" in state.get("demo", {})
    finally:
        srv.shutdown()


def test_kill_endpoint_sets_and_clears(cfg, monkeypatch):
    monkeypatch.setattr(web.Hub, "autotrade_status", lambda self: False)
    monkeypatch.setattr(web.Hub, "set_autotrade", lambda self, on: "off")
    monkeypatch.setattr(kalshi_demo, "flatten_all", lambda *a: "no open positions to flatten")
    hub = web.Hub(cfg)
    hub.set_kill(True)
    assert hub.kill_path().exists()
    hub.set_kill(False)
    assert not hub.kill_path().exists()


def test_cloud_state_export_is_self_contained(cfg, monkeypatch):
    """`oilx export-state` must produce everything the static dashboard reads, with no
    server behind it - that is what lets the bot run off the laptop entirely."""
    monkeypatch.setenv("GITHUB_REPOSITORY", "someone/oilx")
    monkeypatch.delenv("KALSHI_DEMO_KEY_ID", raising=False)
    monkeypatch.delenv("KALSHI_DEMO_PRIVATE_KEY", raising=False)
    (cfg.out_dir).mkdir(parents=True, exist_ok=True)
    (cfg.out_dir / "health.json").write_text(json.dumps({
        "ts": "2026-11-10T00:00:00+00:00", "ok": True, "schema_suspect": False,
        "network_errors": [], "series": {}, "fwd": {"WTI": 86.44}, "sigma": 0.57,
        "signals": {"main": 0, "probe": 0, "flagged": 0},
        "maker": {"staged": 0, "rejects": {}, "shadow_fills": 0}}))
    st = web.build_state(cfg, mode="cloud")
    json.dumps(st)                                   # fully serialisable
    assert st["mode"] == "cloud" and st["repo"] == "someone/oilx"
    assert st["autotrade"] is True                   # the schedule IS the workflow
    assert st["creds"] == {"key_id": "missing", "private_key": "missing"}   # names itself
    monkeypatch.setenv("KALSHI_DEMO_KEY_ID", "0f8fad5b-d9cb-469f-a165-70867728950e")
    monkeypatch.setenv("KALSHI_DEMO_PRIVATE_KEY", "not a pem")
    c = web.build_state(cfg, mode="cloud")["creds"]
    assert c == {"key_id": "present", "private_key": "wrong shape"}
    assert "0f8fad5b" not in json.dumps(c)             # shape only, never the value
    assert st["cl_live"] == 86.44 and st["health"]["ok"] is True
    for key in ("price_series", "signals", "maker_quotes", "shadow_fills", "orders", "logs"):
        assert key in st
