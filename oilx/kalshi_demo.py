"""Order placement on Kalshi's DEMO exchange only. Paper money, real mechanics.

Safety rails, in order of importance:
1. **Demo-only, structurally.** The client refuses to construct unless its base URL
   contains "demo". There is no code path that signs a request to the production API.
2. **Credentials never live in this repo's history.** The key id and RSA private key are
   read from `secrets/` (gitignored). Create them on the demo account at
   https://demo.kalshi.co -> account -> API keys, then save:
       secrets/kalshi_demo_key_id.txt          (the key id, one line)
       secrets/kalshi_demo_private_key.pem     (the private key file Kalshi gives you)
3. **Caps.** Max contracts per order, max orders per run, max total open contracts; a
   signal flagged suspect or stale_underlying is never traded; limit orders only, priced
   at the scanned ask (never chased).
4. **One book.** Positions are checked first; a market we already hold is skipped.

Honesty note: the scan finds edges on PRODUCTION prices, but demo orders fill against the
demo exchange's own (thin) books. A demo fill proves the pipeline executes end to end; it
says nothing about real liquidity. That is what this is for - mechanics, not P&L claims.
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import os
import logging
import time
import uuid
from pathlib import Path

import requests

log = logging.getLogger("oilx.kalshi_demo")

DEMO_BASE = "https://demo-api.kalshi.co/trade-api/v2"


def position_size(p: dict) -> int:
    """Signed contracts held. Kalshi moved this to the fixed-point string field
    position_fp (the legacy integer `position` is gone); read either generation."""
    for k in ("position_fp", "position"):
        try:
            return int(round(float(p[k])))
        except (KeyError, TypeError, ValueError):
            continue
    return 0


class DemoClient:
    def __init__(self, secrets_dir: Path, base: str = DEMO_BASE):
        if "demo" not in base:
            raise ValueError("refusing non-demo base URL: this client is demo-only")
        self.base = base
        # Cloud mode: credentials from environment (GitHub Actions secrets), so the bot
        # can run on a hosted runner with no laptop and no campus network in the loop.
        env_id = os.environ.get("KALSHI_DEMO_KEY_ID", "").strip().strip('"')
        env_pem = os.environ.get("KALSHI_DEMO_PRIVATE_KEY", "")
        if env_id and env_pem.strip():
            src = "KALSHI_DEMO_PRIVATE_KEY (environment)"
            id_src = "KALSHI_DEMO_KEY_ID (environment)"
            pem_bytes = env_pem.replace("\\n", "\n").replace("\r", "").encode().strip()
            self.key_id = env_id
        else:
            key_id_path = None  # canonical name first, then common saved-as names
            for name in ("kalshi_demo_key_id.txt", "Public Key.txt", "public key.txt",
                         "key_id.txt"):
                if (secrets_dir / name).exists():
                    key_id_path = secrets_dir / name
                    break
            pem_path = None  # tolerate Windows Explorer's hidden-extension .pem.txt
            for name in ("kalshi_demo_private_key.pem", "kalshi_demo_private_key.pem.txt",
                         "kalshi_demo_private_key.key", "kalshi_demo_private_key.txt"):
                if (secrets_dir / name).exists():
                    pem_path = secrets_dir / name
                    break
            if key_id_path is None or pem_path is None:
                raise FileNotFoundError(
                    f"demo credentials not found in {secrets_dir} (or in the environment "
                    "variables KALSHI_DEMO_KEY_ID / KALSHI_DEMO_PRIVATE_KEY). Create an API "
                    "key on the demo exchange and save kalshi_demo_key_id.txt + "
                    "kalshi_demo_private_key.pem there.")
            src, id_src = pem_path.name, key_id_path.name
            pem_bytes = pem_path.read_bytes().lstrip(b"\xef\xbb\xbf").strip()  # drop BOM
            self.key_id = key_id_path.read_text(encoding="utf-8-sig").strip().strip('"')
        if b"-----BEGIN" not in pem_bytes or len(pem_bytes) < 1000:
            raise ValueError(
                f"{src} does not look like an RSA private key: expected ~1.7KB of "
                "PEM text starting '-----BEGIN RSA PRIVATE KEY-----' (25-30 lines). Kalshi "
                "shows the private key only once when the API key is created - if it wasn't "
                "saved, generate a new demo API key and save the full key file here.")
        if not (20 <= len(self.key_id) <= 64) or "\n" in self.key_id:
            raise ValueError(f"{id_src} doesn't look like a Kalshi API key id "
                             "(expected one short token, e.g. a UUID, on one line)")
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        self._hashes, self._padding = hashes, padding
        try:
            self._key = serialization.load_pem_private_key(pem_bytes, password=None)
        except Exception as e:
            raise ValueError(
                f"{src} could not be parsed as a private key ({e}). Re-save the "
                "key exactly as Kalshi provided it: plain text, starting '-----BEGIN' and "
                "ending '-----END', no extra characters before or after.") from e

    def _headers(self, method: str, path: str) -> dict:
        ts = str(int(time.time() * 1000))
        msg = (ts + method.upper() + "/trade-api/v2" + path).encode()
        sig = self._key.sign(
            msg,
            self._padding.PSS(mgf=self._padding.MGF1(self._hashes.SHA256()),
                              salt_length=self._padding.PSS.DIGEST_LENGTH),
            self._hashes.SHA256())
        return {"KALSHI-ACCESS-KEY": self.key_id,
                "KALSHI-ACCESS-TIMESTAMP": ts,
                "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
                "Content-Type": "application/json"}

    def _req(self, method: str, path: str, body: dict | None = None,
             params: dict | None = None) -> dict:
        # Kalshi signs ts + METHOD + /trade-api/v2 + path WITHOUT the query string
        url = self.base + path
        r = requests.request(method, url, headers=self._headers(method, path),
                             json=body, params=params, timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
        return r.json() if r.text else {}

    def balance(self) -> dict:
        return self._req("GET", "/portfolio/balance")

    def positions(self) -> list[dict]:
        return self._req("GET", "/portfolio/positions").get("market_positions", [])


    def resting_orders(self) -> list[dict]:
        return self._req("GET", "/portfolio/orders",
                         params={"status": "resting", "limit": 200}).get("orders", [])

    # ---- orders: Kalshi's V2 order API -------------------------------------------
    # The legacy POST /portfolio/orders now answers HTTP 410 ("switch to the V2
    # endpoints"). V2 lives at /portfolio/events/orders, quotes EVERYTHING from the YES
    # side (bid = buy YES; ask = sell YES, which is how a NO position is bought, at
    # 1 - the NO price), and takes fixed-point strings for price and count.

    def cancel_order(self, order_id: str, ticker: str | None = None) -> dict:
        params = {"market_ticker": ticker} if ticker else None
        return self._req("DELETE", f"/portfolio/events/orders/{order_id}", params=params)

    @staticmethod
    def order_body(ticker: str, side: str, count: int, limit_price: float, *,
                   post_only: bool = False, tif: str = "good_till_canceled",
                   reduce_only: bool = False) -> dict:
        """The V2 request for "buy `count` of `side` at `limit_price`" (side-native
        price, e.g. NO at 0.40). Pure function so the mapping is unit-tested."""
        if side not in ("yes", "no"):
            raise ValueError(f"side must be yes or no, got {side!r}")
        yes_price = limit_price if side == "yes" else 1 - limit_price
        if not 0.01 <= round(yes_price, 4) <= 0.99:
            raise ValueError(f"price {limit_price} out of range for a {side} order")
        body = {"ticker": ticker, "side": "bid" if side == "yes" else "ask",
                "count": f"{int(count)}.00", "price": f"{yes_price:.4f}",
                "time_in_force": tif, "self_trade_prevention_type": "taker_at_cross",
                "client_order_id": str(uuid.uuid4())}
        if post_only:
            body["post_only"] = True
        if reduce_only:
            body["reduce_only"] = True
        return body

    def create_order(self, ticker: str, side: str, count: int, limit_price: float, *,
                     post_only: bool = False, tif: str = "good_till_canceled") -> dict:
        """Limit order, buy only, demo only. Returns the legacy-shaped
        {"order": {"status", "order_id", ...}} the callers and logs already use."""
        resp = self._req("POST", "/portfolio/events/orders",
                         self.order_body(ticker, side, count, limit_price,
                                         post_only=post_only, tif=tif))
        filled = float(resp.get("fill_count", 0) or 0)
        remaining = float(resp.get("remaining_count", 0) or 0)
        status = ("resting" if remaining > 0 else "executed" if filled > 0
                  else "canceled (nothing to trade against)")
        return {"order": {"order_id": resp.get("order_id", ""), "status": status,
                          "fill_count": filled, "remaining_count": remaining,
                          "average_fill_price": resp.get("average_fill_price")}}

    def sell_market(self, ticker: str, side: str, count: int) -> dict:
        """Close an existing demo position now (flatten only). V2 has no market type:
        an immediate-or-cancel order at the worst allowed price, reduce-only so it can
        never open a new position. Closing YES = sell YES (ask); closing NO = buy YES."""
        closing_yes = side == "yes"
        body = {"ticker": ticker, "side": "ask" if closing_yes else "bid",
                "count": f"{int(count)}.00", "price": "0.0100" if closing_yes else "0.9900",
                "time_in_force": "immediate_or_cancel", "reduce_only": True,
                "self_trade_prevention_type": "taker_at_cross",
                "client_order_id": str(uuid.uuid4())}
        return self._req("POST", "/portfolio/events/orders", body)


def trade_signals(scan_path: Path, secrets_dir: Path, *,
                  max_contracts: int = 10, max_orders: int = 5,
                  max_open_contracts: int = 100, min_edge: float = 0.05,
                  probe: dict | None = None, maker: dict | None = None) -> str:
    """Place demo orders for the latest scan: taker orders for main-tier signals, tiny
    taker orders for probe-tier signals, and (if enabled) refreshed passive maker bids.
    Every outcome, including a crash, is appended to kalshi_demo_log.txt."""
    logp = scan_path.parent / "kalshi_demo_log.txt"

    def _log(text: str) -> str:
        stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        logp.parent.mkdir(parents=True, exist_ok=True)
        with logp.open("a") as f:
            f.write(f"\n=== {stamp} ===\n{text}\n")
        return text

    try:
        return _log(_trade_signals(scan_path, secrets_dir, max_contracts=max_contracts,
                                   max_orders=max_orders, max_open_contracts=max_open_contracts,
                                   min_edge=min_edge, probe=probe or {}, maker=maker or {}))
    except Exception:
        import traceback
        return _log("FAILED before any order was placed:\n" + traceback.format_exc())


def _trade_signals(scan_path: Path, secrets_dir: Path, *,
                   max_contracts: int, max_orders: int,
                   max_open_contracts: int, min_edge: float,
                   probe: dict, maker: dict) -> str:
    if (scan_path.parent / "KILL").exists():
        return "KILL switch engaged (data/out/KILL exists) - refusing to trade; resume from the dashboard or delete the file"
    if not scan_path.exists():
        return "no scan found - run kalshi-scan first"
    signals = json.loads(scan_path.read_text())
    client = DemoClient(secrets_dir)

    bal = client.balance().get("balance", 0) / 100
    held = {p.get("ticker"): p for p in client.positions()
            if position_size(p) != 0}
    open_contracts = sum(abs(position_size(p)) for p in held.values())
    _append_balance(scan_path.parent, bal, open_contracts)

    lines = [f"demo balance ${bal:,.2f}; open contracts {open_contracts}"]
    # per-tier caps: probe is calibration spend, never conviction size
    caps = {"main": {"size": max_contracts, "max": max_orders, "floor": min_edge},
            "probe": {"size": int(probe.get("max_contracts_per_order", 2)),
                      "max": int(probe.get("max_orders_per_run", 3)),
                      "floor": float(probe.get("min_edge", 0.03))}}
    if not probe.get("enabled", False):
        caps.pop("probe")
    placed = {t: 0 for t in caps}
    for s in signals:
        tier = s.get("tier", "main")
        c = caps.get(tier)
        if c is None or placed[tier] >= c["max"]:
            continue
        if s.get("flags"):
            continue  # suspect / stale signals never trade, in any tier
        if s["edge"] < c["floor"]:
            continue
        if s["ticker"] in held:
            lines.append(f"skip {s['ticker']}: already held")
            continue
        if open_contracts + c["size"] > max_open_contracts:
            lines.append("stopped: open-contract cap reached")
            break
        try:
            resp = client.create_order(s["ticker"], s["side"], c["size"], s["price"],
                                       tif="immediate_or_cancel")
            status = (resp.get("order") or {}).get("status", "?")
            lines.append(f"placed [{tier}] {s['side']} x{c['size']} {s['ticker']} "
                         f"@{s['price']:.2f} (edge {s['edge']:+.2f}) -> {status}")
            _append_order(scan_path.parent, {"ticker": s["ticker"], "side": s["side"],
                                             "action": "buy", "count": c["size"],
                                             "price": s["price"], "edge": s["edge"],
                                             "status": status, "tier": tier,
                                             "underlying": s.get("underlying", "WTI")})
            placed[tier] += 1
            held[s["ticker"]] = {"ticker": s["ticker"]}  # one order per market per run
            open_contracts += c["size"]
            time.sleep(0.3)
        except Exception as e:
            lines.append(f"order failed {s['ticker']}: {e}")
    if sum(placed.values()) == 0:
        lines.append("no taker orders placed (no clean signals above the edge thresholds)")

    if maker.get("enabled", False):
        lines.append(refresh_maker_quotes(
            scan_path.parent, client, held=held, open_contracts=open_contracts,
            max_open_contracts=max_open_contracts,
            contracts_per_order=int(maker.get("contracts_per_order", 5)),
            max_resting=int(maker.get("max_resting_orders", 6))))
    return "\n".join(lines)


def refresh_maker_quotes(out_dir: Path, client: DemoClient, *, held: dict,
                         open_contracts: int, max_open_contracts: int,
                         contracts_per_order: int, max_resting: int) -> str:
    """Cancel every resting demo order, then post fresh passive bids from the scan's
    kalshi_maker_quotes.json. Cancel-all-then-repost each cycle means no quote ever
    rests on stale information for more than an hour. Resting orders count toward the
    open-contract cap at full size, as if they all filled (the conservative reading)."""
    lines = ["maker: refreshing resting quotes"]
    try:
        resting = client.resting_orders()
    except Exception as e:
        return f"maker: could not list resting orders ({e}); posting nothing this cycle"
    for o in resting:
        try:
            client.cancel_order(o.get("order_id") or o.get("id", ""), o.get("ticker"))
            lines.append(f"  cancelled {o.get('ticker')} {o.get('outcome_side', o.get('side'))} "
                         f"x{o.get('remaining_count_fp', o.get('remaining_count', '?'))}")
            time.sleep(0.2)
        except Exception as e:
            lines.append(f"  cancel FAILED {o.get('ticker')}: {e}")

    quotes_path = out_dir / "kalshi_maker_quotes.json"
    if not quotes_path.exists():
        lines.append("  no maker quotes file from the scan; nothing posted")
        _write_open_orders(out_dir, [])
        return "\n".join(lines)
    quotes = json.loads(quotes_path.read_text())
    posted, tracked = 0, []
    for q in quotes:
        if posted >= max_resting:
            break
        if q["ticker"] in held:
            continue  # never quote a market we already own or just bought
        if open_contracts + (posted + 1) * contracts_per_order > max_open_contracts:
            lines.append("  stopped: open-contract cap would be breached if all quotes filled")
            break
        try:
            resp = client.create_order(q["ticker"], q["side"], contracts_per_order, q["price"],
                                       post_only=True)   # can only ever rest, never cross
            order = resp.get("order") or {}
            lines.append(f"  resting {q['side']} x{contracts_per_order} {q['ticker']} "
                         f"@{q['price']:.2f} (fair {q['fair']:.2f})")
            _append_order(out_dir, {"ticker": q["ticker"], "side": q["side"], "action": "buy",
                                    "count": contracts_per_order, "price": q["price"],
                                    "edge": round(q["fair"] - q["price"], 4),
                                    "status": order.get("status", "resting"), "tier": "maker",
                                    "underlying": q.get("underlying", "WTI")})
            tracked.append({"order_id": order.get("order_id", ""), "ticker": q["ticker"],
                            "side": q["side"], "price": q["price"], "fair": q["fair"],
                            "count": contracts_per_order})
            posted += 1
            time.sleep(0.3)
        except Exception as e:
            lines.append(f"  quote FAILED {q['ticker']}: {e}")
    _write_open_orders(out_dir, tracked)
    if posted == 0 and len(lines) == 1:
        lines.append("  no eligible maker quotes this cycle")
    return "\n".join(lines)


def _write_open_orders(out_dir: Path, orders: list[dict]) -> None:
    (out_dir / "kalshi_open_orders.json").write_text(json.dumps({
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "orders": orders}, indent=1))


def _append_order(out_dir: Path, row: dict) -> None:
    row = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), **row}
    with (out_dir / "kalshi_orders.jsonl").open("a") as f:
        f.write(json.dumps(row) + "\n")


def _append_balance(out_dir: Path, balance: float, open_contracts: float) -> None:
    p = out_dir / "balance_history.csv"
    if not p.exists():
        p.write_text("ts,balance,open_contracts\n")
    with p.open("a") as f:
        f.write(f"{dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')},"
                f"{balance:.2f},{open_contracts:.0f}\n")


def flatten_all(secrets_dir: Path, out_dir: Path) -> str:
    """Cancel every resting order and close every open demo position with market sells.
    Dashboard / emergency use - a stop that leaves maker bids resting isn't a stop."""
    client = DemoClient(secrets_dir)
    lines = []
    try:
        for o in client.resting_orders():
            client.cancel_order(o.get("order_id") or o.get("id", ""), o.get("ticker"))
            lines.append(f"cancelled resting {o.get('ticker')} "
                         f"{o.get('outcome_side', o.get('side'))}")
            time.sleep(0.2)
        _write_open_orders(out_dir, [])
    except Exception as e:
        lines.append(f"cancel-resting FAILED: {e}")
    for p in client.positions():
        pos = position_size(p)
        if pos == 0:
            continue
        side = "yes" if pos > 0 else "no"
        try:
            client.sell_market(p["ticker"], side, abs(pos))
            lines.append(f"flattened {p['ticker']}: sold {abs(pos)} {side}")
            _append_order(out_dir, {"ticker": p["ticker"], "side": side, "action": "sell",
                                    "count": abs(pos), "price": None, "edge": None,
                                    "status": "flatten"})
            time.sleep(0.3)
        except Exception as e:
            lines.append(f"flatten FAILED {p['ticker']}: {e}")
    if not lines:
        lines = ["no open positions to flatten"]
    stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    with (out_dir / "kalshi_demo_log.txt").open("a") as f:
        f.write(f"\n=== {stamp} (flatten) ===\n" + "\n".join(lines) + "\n")
    return "\n".join(lines)
