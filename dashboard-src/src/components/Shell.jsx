import React, { useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, Circle, Cloud, Droplets, ExternalLink, Laptop, Play, Power, RotateCcw, X, XCircle } from "lucide-react";
import { TONE, ago, deriveChecks, isoSec, money, post, signed, useCountUp } from "../lib.js";

/* ---------- a bento cell ---------- */
export function Cell({ className = "", title, aside, children, delay = 0, label }) {
  return (
    <section aria-label={label || title} className={"cell animate-rise " + className} style={{ animationDelay: delay + "ms" }}>
      {(title || aside) && (
        <header className="mb-4 flex min-h-[26px] flex-wrap items-center justify-between gap-x-3 gap-y-2">
          {title && <h2 className="cell-title">{title}</h2>}
          {aside}
        </header>
      )}
      {children}
    </section>
  );
}

/* ---------- boot sequence ---------- */
const BOOT = ["resolving bot endpoint", "requesting state snapshot", "decoding health report", "awaiting first reply"];
export function Boot({ failed }) {
  const [n, setN] = useState(1);
  useEffect(() => {
    const t = setInterval(() => setN((v) => Math.min(BOOT.length, v + 1)), 420);
    return () => clearInterval(t);
  }, []);
  return (
    <main className="grid min-h-screen place-items-center p-6">
      <div className="relative w-full max-w-md overflow-hidden rounded-2xl p-px" role="status" aria-live="polite">
        <div aria-hidden="true" className="absolute -inset-[100%] animate-spinborder"
          style={{ background: "conic-gradient(from 0deg, transparent 0 62%, #8a6f3f 78%, #e0bd7c 86%, transparent 94%)" }} />
        <div className="relative rounded-[15px] bg-ink-900 p-7">
          <div className="flex items-center gap-2.5">
            <Droplets className="h-5 w-5 text-crude" aria-hidden="true" />
            <span className="text-[15px] font-semibold tracking-tight">OIL<span className="text-crude">x</span></span>
            <span className="text-[13px] text-zinc-500">Control Room</span>
          </div>
          <p className="mt-6 text-xl font-medium tracking-tight">{failed ? "Can't reach the bot yet" : "Connecting to the bot"}</p>
          <ul className="num mt-4 space-y-1.5 text-[12.5px] text-zinc-500">
            {BOOT.slice(0, n).map((l, i) => (
              <li key={l} className="flex animate-rise items-center gap-2">
                <span className="text-crude-dim">›</span>
                <span className={i === n - 1 ? "text-zinc-300" : ""}>{l}</span>
                {i < n - 1 ? <Check className="h-3 w-3 text-bull" aria-hidden="true" />
                  : <span className="inline-block h-3.5 w-[7px] animate-caret bg-crude" aria-hidden="true" />}
              </li>
            ))}
          </ul>
          {failed && (
            <p className="mt-5 text-[13px] leading-relaxed text-zinc-400">
              No reply so far. Start the bot's dashboard with <span className="num text-zinc-200">scripts\10_dashboard.bat</span>,
              or open the cloud dashboard link. This page keeps retrying on its own.
            </p>
          )}
        </div>
      </div>
    </main>
  );
}

/* ---------- header ---------- */
export function Header({ S, status, live }) {
  const d = S.demo || {};
  const bal = d.balance ?? d.last_known_balance;
  const shown = useCountUp(bal ?? 0, 900);
  const tone = TONE[status.tone];
  const h = S.health;
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-ink-950/70 backdrop-blur-xl">
      <div className="mx-auto flex max-w-[1400px] items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-2.5">
          <Droplets className="h-[18px] w-[18px] text-crude" aria-hidden="true" />
          <span className="text-[15px] font-semibold tracking-tight">OIL<span className="text-crude">x</span></span>
          <span className="hidden text-[13px] text-zinc-500 sm:inline">Control Room</span>
        </div>

        <div className="flex min-w-0 items-center gap-3 rounded-full border border-line bg-ink-900/80 py-1 pl-2.5 pr-3" role="status" aria-label="Bot connection status">
          <span className="relative grid h-2.5 w-2.5 place-items-center">
            {status.tone !== "idle" && <span className={"absolute inset-0 animate-ping2 rounded-full " + tone.bg} aria-hidden="true" />}
            <span className={"relative h-2 w-2 rounded-full " + tone.bg} style={{ boxShadow: `0 0 10px ${tone.hex}` }} />
          </span>
          <span className={"text-[13px] font-medium " + tone.text}>{status.word}</span>
          <span className="hidden h-3 w-px bg-line md:block" aria-hidden="true" />
          <span className="num hidden text-[12px] text-zinc-500 md:inline">cycle {h ? ago(isoSec(h.ts)) : "–"}</span>
          <span className="hidden h-3 w-px bg-line lg:block" aria-hidden="true" />
          <span className="num hidden text-[12px] text-zinc-500 lg:inline" title="Round-trip time of the last sign-in to the exchange">
            {S.api_latency_ms ? S.api_latency_ms + " ms" : "– ms"}
          </span>
          <span className="hidden items-center gap-1 text-[12px] text-zinc-500 sm:flex">
            {live ? <Laptop className="h-3.5 w-3.5" aria-hidden="true" /> : <Cloud className="h-3.5 w-3.5" aria-hidden="true" />}
            {live ? "local" : "cloud"}
          </span>
        </div>

        <div className="ml-auto text-right">
          <div className="label">Practice balance{d.balance == null && bal != null ? " (last known)" : ""}</div>
          <div className="num text-[19px] font-medium leading-tight text-zinc-50 sm:text-[22px]" aria-live="off">{bal == null ? "–" : money(shown)}</div>
        </div>
      </div>
    </header>
  );
}

/* ---------- status + system checks ---------- */
const CHECK_ICON = {
  good: <Check className="h-3 w-3" aria-hidden="true" />, warn: <AlertTriangle className="h-3 w-3" aria-hidden="true" />,
  bad: <XCircle className="h-3 w-3" aria-hidden="true" />, idle: <Circle className="h-3 w-3" aria-hidden="true" />,
};
const CHECK_WORD = { good: "OK", warn: "needs a look", bad: "broken", idle: "no data yet" };

export function StatusPanel({ S, status, className, delay }) {
  const checks = deriveChecks(S);
  const bad = checks.filter((c) => c.state === "warn" || c.state === "bad");
  const fills = (S.shadow_fills || []).length, resting = (S.resting || []).length;
  const [open, setOpen] = useState(false);
  return (
    <Cell className={className} delay={delay} label="Bot status">
      <p className="label">Right now</p>
      <h1 className="mt-1.5 max-w-[30ch] text-[22px] font-medium leading-snug tracking-tight text-zinc-50 sm:text-[26px]">{status.line}</h1>
      <p className="mt-2 text-[13.5px] text-zinc-400">
        {fills ? fills + " paper " + (fills === 1 ? "fill" : "fills") + " on record" : "No fills on record yet"}
        {resting ? ", " + resting + " quotes resting on the practice exchange" : ""}{S.cycle_running ? ", a cycle is running now" : ""}.
      </p>

      <div className="mt-5 border-t border-line-soft pt-4">
        <div className="flex flex-wrap items-baseline gap-x-3">
          <h2 className="cell-title">System checks</h2>
          <span className="text-[12.5px] text-zinc-500">
            {bad.length ? `${checks.length - bad.length} of ${checks.length} healthy` : `all ${checks.length} healthy`}
          </span>
        </div>
        <ul className="mt-3 flex flex-wrap gap-1.5">
          {checks.map((c) => {
            const t = TONE[c.state === "good" ? "good" : c.state === "warn" ? "warn" : c.state === "bad" ? "bad" : "idle"];
            return (
              <li key={c.name} title={c.detail}
                className={"inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12px] " + (c.state === "good" ? "border-line text-zinc-300" : "border-transparent " + t.wash + " " + t.text)}>
                <span className={c.state === "good" ? "text-bull" : ""}>{CHECK_ICON[c.state]}</span>{c.name}
                <span className="sr-only"> – {CHECK_WORD[c.state]}</span>
              </li>
            );
          })}
        </ul>
        {(open ? checks : bad).length > 0 && (
          <ul className="mt-3 space-y-1.5">
            {(open ? checks : bad).map((c) => (
              <li key={c.name} className="flex gap-2 text-[13px] leading-relaxed text-zinc-400">
                <span className={"mt-[5px] " + TONE[c.state === "good" ? "good" : c.state === "warn" ? "warn" : c.state === "bad" ? "bad" : "idle"].text}>{CHECK_ICON[c.state]}</span>
                <span><span className="font-medium text-zinc-200">{c.name}.</span> {c.detail}</span>
              </li>
            ))}
          </ul>
        )}
        <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
          className="mt-3 text-[12.5px] text-zinc-500 underline-offset-4 transition hover:text-zinc-300 hover:underline">
          {open ? "Show only what needs a look" : "Show what every check saw"}
        </button>
      </div>
    </Cell>
  );
}

/* ---------- KPI cells ---------- */
function Kpi({ label, value, hint, tone }) {
  return (
    <div className="flex flex-col justify-center bg-ink-900 p-4">
      <div className="label">{label}</div>
      <div className={"num mt-1 text-[22px] font-medium leading-tight " + (tone || "text-zinc-50")}>{value}</div>
      <div className="mt-0.5 min-h-[18px] text-[12px] text-zinc-500">{hint}</div>
    </div>
  );
}
export function KpiGrid({ S, className, delay }) {
  const d = S.demo || {};
  const pos = (d.positions || []).reduce((a, p) => a + Math.abs(p.position || 0), 0);
  const carry = (S.curve || []).length ? S.curve[S.curve.length - 1].value : null;
  const pnl = S.daily_pnl, h = S.health || {};
  const flagged = h.signals ? h.signals.flagged : null;
  return (
    <section aria-label="Key figures" className={"animate-rise grid grid-cols-2 gap-px bg-line sm:grid-cols-3 " + className} style={{ animationDelay: delay + "ms" }}>
      <Kpi label="Today" value={pnl == null ? "–" : signed(pnl)} hint="since the first cycle today" tone={pnl > 0 ? "text-bull" : pnl < 0 ? "text-bear" : undefined} />
      <Kpi label="Open contracts" value={String(pos)} hint={(S.resting || []).length + " quotes resting"} />
      <Kpi label="Quotes wanted" value={String((S.maker_quotes || []).length)} hint={flagged == null ? "" : flagged + " signals set aside"} />
      <Kpi label="WTI" value={S.cl_live ? "$" + S.cl_live.toFixed(2) : S.cl_last ? "$" + S.cl_last.toFixed(2) : "–"} hint={S.cl_live ? "latest cycle" : S.raw_asof ? "close of " + S.raw_asof : ""} />
      <Kpi label="Oil volatility" value={S.ovx_live || S.ovx ? Math.round(S.ovx_live || S.ovx) + "%" : "–"} hint="OVX, annualised" />
      <Kpi label="Futures curve" value={carry == null ? "–" : Math.round(Math.abs(carry) * 100) + "%"} hint={carry == null ? "builds from the laptop log" : carry >= 0 ? "backwardation / yr" : "contango / yr"} />
    </section>
  );
}

/* ---------- controls ---------- */
export function Controls({ S, live, reload, className, delay }) {
  const [toast, setToast] = useState("");
  const [ask, setAsk] = useState(null);
  const dlg = useRef(null);
  useEffect(() => { if (ask) dlg.current?.showModal(); }, [ask]);
  useEffect(() => { if (!toast) return; const t = setTimeout(() => setToast(""), 6000); return () => clearTimeout(t); }, [toast]);
  const run = async (url, body) => { setToast(await post(url, body)); reload(); };
  const repo = S.repo ? "https://github.com/" + S.repo : null;

  if (!live) {
    return (
      <Cell className={className} delay={delay} title="Controls">
        <p className="text-[13.5px] leading-relaxed text-zinc-400">
          This page is a read-only snapshot the cloud bot publishes after every cycle. Running, stopping and resuming happen in GitHub Actions.
        </p>
        {repo && (
          <div className="mt-4 grid gap-2">
            <a className="btn" href={repo + "/actions/workflows/cycle.yml"} rel="noopener"><Play className="h-3.5 w-3.5 text-crude" aria-hidden="true" />Run a cycle<ExternalLink className="ml-auto h-3.5 w-3.5 text-zinc-600" aria-hidden="true" /></a>
            <a className="btn" href={repo + "/actions/workflows/control.yml"} rel="noopener"><Power className="h-3.5 w-3.5 text-bear" aria-hidden="true" />Stop, resume or flatten<ExternalLink className="ml-auto h-3.5 w-3.5 text-zinc-600" aria-hidden="true" /></a>
          </div>
        )}
      </Cell>
    );
  }
  return (
    <Cell className={className} delay={delay} title="Controls">
      <button type="button" role="switch" aria-checked={!!S.autotrade} onClick={() => run("api/autotrade", { on: !S.autotrade })}
        className="flex w-full items-center justify-between gap-4 rounded-md border border-line bg-ink-800 px-3 py-2.5 text-left text-[13px] font-medium transition hover:border-zinc-600">
        Trade automatically every hour
        <span className={"relative h-5 w-9 flex-none rounded-full transition-colors duration-300 " + (S.autotrade ? "bg-crude" : "bg-zinc-700")}>
          <span className={"absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-zinc-50 shadow transition-transform duration-300 ease-spring " + (S.autotrade ? "translate-x-4" : "")} />
        </span>
      </button>
      <div className="mt-2 grid gap-2">
        <button type="button" className="btn !border-crude-dim !bg-crude-wash !text-crude-bright" disabled={S.cycle_running || S.killed} onClick={() => run("api/cycle", {})}>
          <Play className="h-3.5 w-3.5" aria-hidden="true" />{S.cycle_running ? "Cycle running…" : "Run a cycle now"}
        </button>
        <button type="button" className="btn" onClick={() => setAsk({ title: "Close all positions?", body: "Cancels every resting quote and sells every open contract at the market, on the practice account.", yes: "Close all positions", go: () => run("api/flatten", {}) })}>
          <X className="h-3.5 w-3.5" aria-hidden="true" />Close all positions
        </button>
        {S.killed
          ? <button type="button" className="btn !border-transparent !bg-bull-wash !text-bull" onClick={() => run("api/kill", { on: false })}><RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />Resume trading</button>
          : <button type="button" className="btn !border-transparent !bg-bear-wash !text-bear" onClick={() => setAsk({ title: "Stop everything?", body: "Turns off the hourly schedule, cancels resting quotes, closes open positions and blocks all trading until you press Resume.", yes: "Stop everything", go: () => run("api/kill", { on: true }) })}><Power className="h-3.5 w-3.5" aria-hidden="true" />Stop everything</button>}
      </div>
      <dialog ref={dlg} onClose={() => setAsk(null)} className="max-w-sm rounded-xl border border-line bg-ink-800 p-6 text-zinc-100 backdrop:bg-black/70 backdrop:backdrop-blur-sm">
        {ask && (<>
          <h2 className="text-lg font-medium tracking-tight">{ask.title}</h2>
          <p className="mt-2 text-[13.5px] leading-relaxed text-zinc-400">{ask.body}</p>
          <div className="mt-5 flex justify-end gap-2">
            <button type="button" className="btn" onClick={() => dlg.current.close()}>Cancel</button>
            <button type="button" className="btn !border-transparent !bg-bear-wash !text-bear" onClick={() => { dlg.current.close(); ask.go(); }}>{ask.yes}</button>
          </div>
        </>)}
      </dialog>
      {toast && <div role="status" className="fixed bottom-5 left-1/2 z-50 max-w-[80vw] -translate-x-1/2 animate-rise rounded-lg border border-line bg-ink-700 px-4 py-2.5 text-[13px] shadow-2xl">{toast}</div>}
    </Cell>
  );
}

/* ---------- activity log ---------- */
function lineTone(l) {
  if (/FAILED|Traceback|Error\b|error|refusing|KILL/.test(l)) return "text-bear";
  if (/^=====|^---|^\$ oilx|^-{5,}/.test(l)) return "text-zinc-600";
  if (/placed|resting |shadow fill|maker: \d|PICK:/.test(l)) return "text-crude";
  if (/forward check|WARNING|skipped|unavailable|flagged/.test(l)) return "text-warn";
  return "text-zinc-400";
}
export function ActivityLog({ S, className, delay }) {
  const box = useRef(null);
  const lines = (S.logs || []).filter((l, i, a) => l.trim() !== "" || (a[i - 1] || "").trim() !== "");
  useEffect(() => { if (box.current) box.current.scrollTop = box.current.scrollHeight; }, [lines.length, S.ts]);
  return (
    <Cell className={className} delay={delay} title="Activity log" aside={<span className="num text-[11.5px] text-zinc-600">{lines.length} lines, newest last</span>}>
      <div ref={box} tabIndex={0} role="log" aria-label="Bot activity" className="num h-[280px] overflow-auto rounded-lg border border-line-soft bg-ink-950 p-3 text-[11.5px] leading-[1.7]">
        {lines.length ? lines.map((l, i) => (
          <div key={i} className={"whitespace-pre-wrap break-words " + lineTone(l)}>
            <span className="mr-3 select-none text-zinc-700">{String(i + 1).padStart(3, "0")}</span>{l}
          </div>
        )) : <div className="text-zinc-600">No activity logged yet.</div>}
      </div>
    </Cell>
  );
}
