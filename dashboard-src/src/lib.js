// Shared formatting, data fetching and the logic that turns raw bot state into
// plain statements about what the machine is doing.
import { useEffect, useRef, useState } from "react";

export const money = (v) =>
  v == null ? "–" : "$" + Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const signed = (v, d = 2) => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(d);
export const cents = (p) => (p == null ? "–" : Math.round(p * 100) + "¢");
export const cents1 = (p) => (p == null ? "–" : (p * 100).toFixed(1) + "¢");
export const isoSec = (iso) => (iso ? Date.parse(iso) / 1000 : 0);

export function ago(tsSec) {
  if (!tsSec) return "never";
  const m = Math.max(0, (Date.now() / 1000 - tsSec) / 60);
  if (m < 1.5) return "just now";
  if (m < 90) return Math.round(m) + "m ago";
  if (m < 36 * 60) return Math.round(m / 60) + "h ago";
  return Math.round(m / 1440) + "d ago";
}

/* KXWTI-26NOV1014-T86.49 -> { u: "WTI", text: "above $86.49", date: "Nov 10" } */
export function market(ticker) {
  const m = /^KX(WTI|BRENT)\w*-(\d{2})([A-Z]{3})(\d{2})\d*-([TB])([\d.]+)$/.exec(ticker || "");
  if (!m) return { u: "", text: ticker || "", date: "" };
  const mon = m[3][0] + m[3].slice(1).toLowerCase();
  return { u: m[1] === "WTI" ? "WTI" : "Brent", text: (m[5] === "T" ? "above $" : "near $") + m[6], date: mon + " " + Number(m[4]) };
}

/* ---------- data ---------- */
const onThisComputer = ["127.0.0.1", "localhost", "[::1]"].includes(location.hostname);
async function grab(url) {
  try {
    const r = await fetch(url, { cache: "no-store" });
    if (r.ok) return await r.json();
  } catch (e) {}
  return null;
}

/** Polls the bot. Served by the bot itself -> live API; anywhere else -> the snapshot. */
export function useBotState() {
  const [state, setState] = useState(null);
  const [live, setLive] = useState(false);
  const [failed, setFailed] = useState(false);
  const [lastGood, setLastGood] = useState(0);
  const timer = useRef(null);
  const load = useRef(null);

  load.current = async () => {
    let got = onThisComputer ? await grab("api/state") : null;
    let isLive = !!got;
    if (!got) got = await grab("state.json?" + Date.now());
    if (got && !got.error) {
      setState(got); setLive(isLive); setFailed(false); setLastGood(Date.now());
    } else setFailed(true);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => load.current(), isLive ? 10000 : 60000);
  };
  useEffect(() => {
    const t = setTimeout(() => load.current(), 900); // let the boot sequence breathe once
    return () => { clearTimeout(t); clearTimeout(timer.current); };
  }, []);
  return { state, live, failed, lastGood, reload: () => load.current() };
}

export async function post(url, body) {
  try {
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json();
    return j.ok ? j.message || "Done" : "That didn't work: " + (j.error || r.status);
  } catch (e) {
    return "Couldn't reach the bot on this computer. Is the dashboard window still open?";
  }
}

/* ---------- animated numbers ---------- */
export function useCountUp(value, ms = 700) {
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    if (value == null || Number.isNaN(value)) { setShown(value); return; }
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const start = from.current ?? value, t0 = performance.now();
    if (reduce || start === value) { setShown(value); from.current = value; return; }
    let raf;
    const tick = (t) => {
      const k = Math.min(1, (t - t0) / ms), e = 1 - Math.pow(1 - k, 3);
      setShown(start + (value - start) * e);
      if (k < 1) raf = requestAnimationFrame(tick); else from.current = value;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, ms]);
  return shown;
}

/* re-render on a clock so "3m ago" stays true between polls */
export function useTick(ms = 30000) {
  const [, set] = useState(0);
  useEffect(() => { const t = setInterval(() => set((n) => n + 1), ms); return () => clearInterval(t); }, [ms]);
}

/* ---------- the state of the machine ---------- */
export function deriveStatus(S) {
  const h = S.health, age = h ? (Date.now() / 1000 - isoSec(h.ts)) / 60 : Infinity;
  const nMk = h?.series ? Object.values(h.series).reduce((a, s) => a + s.markets, 0) : 0;
  const staged = h?.maker ? h.maker.staged : 0;
  const sig = h?.signals ? h.signals.main + h.signals.probe : 0;
  if (S.killed) return { word: "Stopped", tone: "bear", line: "The kill switch is on. Nothing trades until you resume." };
  if (!h) return { word: "Waiting", tone: "idle", line: "No cycle has reported in yet." };
  if (h.schema_suspect) return { word: "Blind", tone: "bear", line: "Market data is arriving in a shape the parser can't read. Any “no signals” right now means nothing." };
  if (h.ok === false) return { word: "Cut off", tone: "bear", line: "The last cycle couldn't reach the exchange. That is usually the network it ran on." };
  if (age > 150) return { word: "Quiet", tone: "warn", line: "The last cycle reported " + ago(isoSec(h.ts)) + ". The scheduler may not be running." };
  return {
    word: S.autotrade ? "Hunting" : "Armed", tone: S.autotrade ? "bull" : "idle",
    line: "The last cycle read " + nMk + " markets, " + (sig ? "found " + sig + (sig === 1 ? " signal" : " signals") : "found no mispricing")
      + " and wants " + staged + (staged === 1 ? " quote" : " quotes") + " resting." + (S.autotrade ? "" : " Auto-trade is off."),
  };
}

const WHY = { low_oi: "too thinly traded", wing: "outside the zone where the model is trusted", stale_strip: "failed the price check",
  window: "too close to or far from expiry", price_bounds: "without a sensible price", unparsable: "of an unknown type" };

export function deriveChecks(S) {
  const h = S.health, out = [];
  const add = (name, state, detail) => out.push({ name, state, detail });
  if (!h) add("Heartbeat", "idle", "No cycle has written a health report yet.");
  else {
    const age = (Date.now() / 1000 - isoSec(h.ts)) / 60;
    add("Heartbeat", age > 150 ? "warn" : "good", "Last cycle " + ago(isoSec(h.ts)) + (S.mode === "cloud" ? ", on the cloud runner." : ", on this computer."));
    const ser = h.series ? Object.values(h.series) : [];
    const mk = ser.reduce((a, s) => a + s.markets, 0), two = ser.reduce((a, s) => a + s.two_sided, 0);
    if (h.ok === false && !mk) add("Market data", "bad", h.reason || "Nothing came back from the exchange.");
    else add("Market data", mk ? "good" : "warn", mk + " markets read, " + two + " with a live two-sided quote.");
    add("Data format", h.schema_suspect ? "bad" : mk ? "good" : "idle",
      h.schema_suspect ? "Markets look empty: the exchange changed its field names again." : "Quotes and open interest parse correctly.");
    const stand = Object.values(h.sources || {}).filter((v) => /unavailable/.test(v)), ne = (h.network_errors || []).length;
    if (stand.length) add("Price feed", "warn", "The live quote source didn't answer, so this cycle used a stand-in: " + stand[0].replace(" (live quote unavailable)", "") + ".");
    else add("Price feed", ne ? "warn" : "good", ne ? ne + " request" + (ne > 1 ? "s" : "") + " failed last cycle (" + h.network_errors[0] + ")." : "Live WTI, Brent and volatility quotes all arrived.");
    for (const [nm, fc] of Object.entries(h.fwd_check || {})) {
      const off = fc.gap_sd > fc.limit_sd;
      add(nm === "WTI" ? "WTI price check" : "Brent price check", off ? "warn" : "good", off
        ? "The quote says $" + fc.quote.toFixed(2) + " but the market's own prices imply $" + fc.implied.toFixed(2) + ". Too far apart to trust, so these markets are left alone."
        : "The quote and the market's own prices agree ($" + fc.quote.toFixed(2) + " vs $" + fc.implied.toFixed(2) + ").");
    }
    if (h.maker) {
      const rj = Object.entries(h.maker.rejects || {}).filter(([, v]) => v).sort((a, b) => b[1] - a[1]);
      add("Quoting", h.maker.staged ? "good" : "warn", h.maker.staged
        ? h.maker.staged + " quotes chosen." + (rj.length ? " Most skipped markets were " + (WHY[rj[0][0]] || rj[0][0]) + " (" + rj[0][1] + ")." : "")
        : "No quotes chosen." + (rj.length ? " Most markets were " + (WHY[rj[0][0]] || rj[0][0]) + " (" + rj[0][1] + ")." : ""));
    }
  }
  if (S.signal_asof) {
    const days = (Date.now() - Date.parse(S.signal_asof)) / 864e5;
    add("Signal inputs", days > 5 ? "warn" : "good", days > 5
      ? "The reports behind the five signals were last refreshed " + S.signal_asof + ", so the signals are reading old data."
      : "Data through " + S.signal_asof + ".");
  } else if (S.signal_error) add("Signal inputs", "bad", S.signal_error);
  const d = S.demo || {};
  add("Practice account", d.error ? "bad" : "good", d.error
    ? S.creds && (S.creds.key_id !== "present" || S.creds.private_key !== "present")
      ? "GitHub isn't handing the bot its keys: KALSHI_DEMO_KEY_ID is " + S.creds.key_id + ", KALSHI_DEMO_PRIVATE_KEY is " + S.creds.private_key + ". They must be repository secrets (not variables) with exactly those names."
      : /credentials not found/.test(d.error) ? "The exchange keys aren't set where this bot runs, so it can read markets but can't place orders." : "Couldn't sign in: " + String(d.error).slice(0, 110)
    : "Signed in" + (S.api_latency_ms ? " in " + S.api_latency_ms + " ms." : "."));
  return out;
}

export const SIG_NAME = { mom: "Price trend", crack: "Refining margin", inv_level: "Inventory level", inv_surprise: "Inventory surprise", cot: "Crowd positioning" };
export const SIG_HINT = {
  mom: "Oil trends: supply takes years to adjust.",
  crack: "Fat refinery margins pull more crude through.",
  inv_level: "Stocks against their seasonal norm.",
  inv_surprise: "This week's report against what is typical.",
  cot: "Leans against extreme speculator positioning.",
};

export const TONE = {
  bull: { text: "text-bull", bg: "bg-bull", wash: "bg-bull-wash", hex: "#4fae87" },
  good: { text: "text-bull", bg: "bg-bull", wash: "bg-bull-wash", hex: "#4fae87" },
  bear: { text: "text-bear", bg: "bg-bear", wash: "bg-bear-wash", hex: "#d2625a" },
  bad: { text: "text-bear", bg: "bg-bear", wash: "bg-bear-wash", hex: "#d2625a" },
  warn: { text: "text-warn", bg: "bg-warn", wash: "bg-warn-wash", hex: "#e08a3c" },
  idle: { text: "text-zinc-400", bg: "bg-zinc-500", wash: "bg-zinc-800/60", hex: "#71717a" },
};
