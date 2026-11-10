import React from "react";
import { deriveStatus, ago, useBotState, useTick } from "./lib.js";
import { ActivityLog, Boot, Controls, Header, KpiGrid, StatusPanel } from "./components/Shell.jsx";
import { CrackPanel, EquityCurve, PriceChart, StripChart } from "./components/Charts.jsx";
import { EquityDesk, OrderPanel, SignalCenter } from "./components/Panels.jsx";

export default function App() {
  const { state: S, live, failed, lastGood, reload } = useBotState();
  useTick();
  if (!S) return <Boot failed={failed} />;
  const status = deriveStatus(S);
  const lost = failed && Date.now() - lastGood > 60000;
  return (
    <>
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded focus:bg-ink-700 focus:px-3 focus:py-2">Skip to dashboard</a>
      <Header S={S} status={status} live={live} />
      <main id="main" className="mx-auto max-w-[1400px] px-3 pb-16 pt-4 sm:px-6 sm:pt-6">
        {lost && <p role="alert" className="mb-3 rounded-lg border border-warn/40 bg-warn-wash px-4 py-2 text-[13px] text-warn">Lost contact with the bot {ago(lastGood / 1000)}. Showing the last state received.</p>}
        {/* the bento: 1px dividers come from the grid gap showing the line colour through */}
        <div className="grid grid-cols-1 gap-px overflow-hidden rounded-2xl border border-line bg-line lg:grid-cols-12">
          <StatusPanel S={S} status={status} className="lg:col-span-7" delay={0} />
          <KpiGrid S={S} className="lg:col-span-5" delay={60} />

          <PriceChart S={S} className="lg:col-span-8" delay={120} />
          <SignalCenter S={S} className="lg:col-span-4" delay={180} />

          <StripChart S={S} className="lg:col-span-6" delay={240} />
          <CrackPanel S={S} className="md:col-span-1 lg:col-span-3" delay={300} />
          <EquityCurve S={S} className="lg:col-span-3" delay={360} />

          <OrderPanel S={S} className="lg:col-span-7" delay={420} />
          <EquityDesk S={S} className="lg:col-span-5" delay={480} />

          <ActivityLog S={S} className="lg:col-span-8" delay={540} />
          <Controls S={S} live={live} reload={reload} className="lg:col-span-4" delay={600} />
        </div>
        <footer className="mt-5 flex flex-wrap justify-between gap-2 text-[12px] text-zinc-600">
          <span>{live ? "Live from this computer" : "Snapshot from the cloud bot"}, updated {ago(S.ts)}.</span>
          <span>Practice money only. Nothing here is a real order.</span>
        </footer>
      </main>
    </>
  );
}
