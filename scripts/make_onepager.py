"""One-page interview PDF for the oilx project, plain-English edition. Run from oilx root."""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph,
                                Spacer, Table, TableStyle, FrameBreak)

OUT = Path(__file__).resolve().parent.parent / "notes" / "oilx One-Pager.pdf"

INK = colors.HexColor("#1a1a1e")
MUT = colors.HexColor("#55555e")
BLUE = colors.HexColor("#1a5f9e")
RULE = colors.HexColor("#c9c9cf")

base = dict(fontName="Helvetica", textColor=INK)
S = {
    "title": ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=INK),
    "sub": ParagraphStyle("s", fontSize=8.4, leading=11.0, textColor=MUT,
                          **{k: v for k, v in base.items() if k != "textColor"}),
    "h": ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=9.4, leading=11.5,
                        textColor=BLUE, spaceBefore=7, spaceAfter=2),
    "q": ParagraphStyle("q", fontSize=8.1, leading=10.4, spaceAfter=3, **base),
}


def P(text, style="q"):
    return Paragraph(text, S[style])


def sig_table():
    rows = [
        ("The trend", "Oil moves in long swings because supply takes years to adjust. If it's been rising, lean that way."),
        ("The warehouse", "Every Wednesday the government says how much oil is in storage. Emptier than normal for the season = prices firm up. Fuller = they soften."),
        ("The surprise", "The same report vs. what's typical: a surprisingly big drain is bullish news that echoes for a few days."),
        ("The refiner's paycheck", "Refineries buy crude and sell gasoline and diesel. When their profit per barrel is fat, they run harder and buy more crude."),
        ("The crowd", "Regulators publish how the speculators are positioned. When nearly everyone is already betting one way, there's no one left to join - lean against the extreme."),
    ]
    t = Table([[Paragraph(f"<b>{n}</b>", S["q"]), Paragraph(d, S["q"])] for n, d in rows],
              colWidths=[1.02 * inch, 2.48 * inch])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def results_table():
    rows = [["", "per year", "vs. risk taken"],
            ["the system (20 yrs, after costs)", "+2.6%", "modest but real"],
            ["just buying oil, same years", "-7.4%", "lost money"],
            ["worst losing stretch", "-15%", "then recovered"]]
    t = Table([[Paragraph(f"<b>{c}</b>" if r == 0 else c, S["q"]) for c in row]
               for r, row in enumerate(rows)],
              colWidths=[1.78 * inch, 0.75 * inch, 0.97 * inch])
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.7, INK),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


doc = BaseDocTemplate(str(OUT), pagesize=letter,
                      leftMargin=0.55 * inch, rightMargin=0.55 * inch,
                      topMargin=0.5 * inch, bottomMargin=0.45 * inch)
W = letter[0] - 1.1 * inch
H = letter[1] - 0.95 * inch
head_h = 1.78 * inch
col_gap = 0.28 * inch
col_w = (W - col_gap) / 2
col_h = H - head_h

frames = [
    Frame(doc.leftMargin, doc.bottomMargin + col_h, W, head_h, id="head",
          leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0),
    Frame(doc.leftMargin, doc.bottomMargin, col_w, col_h, id="left",
          leftPadding=0, rightPadding=0, topPadding=4, bottomPadding=0),
    Frame(doc.leftMargin + col_w + col_gap, doc.bottomMargin, col_w, col_h, id="right",
          leftPadding=0, rightPadding=0, topPadding=4, bottomPadding=0),
]


def decorate(canv, _doc):
    canv.saveState()
    y = doc.bottomMargin + col_h + 2
    canv.setStrokeColor(INK)
    canv.setLineWidth(1.1)
    canv.line(doc.leftMargin, y, doc.leftMargin + W, y)
    canv.restoreState()


doc.addPageTemplates([PageTemplate(id="p", frames=frames, onPage=decorate)])

story = [
    P("oilx &mdash; a robot that trades oil carefully", "title"),
    Spacer(1, 3),
    P("Aria Jafari &middot; built in Python (about 5,000 lines, 74 automated checks) &middot; tested on 20 years of history &middot; running live on practice money since October 2026", "sub"),
    Spacer(1, 4),
    P("<b>The idea, in plain words:</b> oil is unusual because the facts that move its price are announced on a public schedule. Every Wednesday morning the "
      "US government says exactly how much oil is sitting in storage; every Friday the regulator says how traders are positioned; every day the market "
      "shows what refineries earn turning crude into fuel. None of this is secret &mdash; but each piece tends to nudge the price in a known direction for "
      "weeks, because the big players who could trade it fast are busy elsewhere and many oil market participants (airlines, producers) trade to reduce risk, "
      "not to make money. My system reads five of these public facts, turns them into one opinion &mdash; lean bullish or lean bearish &mdash; and then, the part "
      "I'm proudest of, <b>keeps the bet deliberately small and survivable no matter how confident the opinion is.</b>", "sub"),
    FrameBreak(),

    P("The five things it watches", "h"),
    sig_table(),
    P("How it stays safe (the real point)", "h"),
    P("<b>A thermostat for risk:</b> when oil gets wilder, the position automatically shrinks so a bad week always costs about the same. The target: the account should swing about 10% a year, never more than it can afford.", "q"),
    P("<b>A circuit breaker:</b> if losses ever reach 15% from the peak, everything shuts off for two weeks, then restarts at half size. Simple on purpose - I can explain it in one sentence, so it can't hide a mistake.", "q"),
    P("<b>No cheating on time:</b> the Wednesday report only enters the system the day after it was actually published. A test proves the system earns nothing from information it shouldn't have yet.", "q"),
    P("<b>Trading costs included:</b> every simulated trade pays a realistic fee, so the results aren't flattered.", "q"),
    FrameBreak(),

    P("Did it work? The honest answer", "h"),
    results_table(),
    Spacer(1, 2),
    P("Then I tried to prove myself wrong: I reshuffled history 500 times to see what pure luck produces &mdash; my result beats about 9 out of 10 "
      "luck runs. Good sign, not proof. I also checked that doing the <i>opposite</i> of my system loses money (it does), and the recent weak stretch "
      "(the 2026 oil shock) is reported, not hidden.", "q"),
    P("The live robot", "h"),
    P("Every hour it reads about 60 yes/no oil contracts on Kalshi (a US-regulated exchange where you can bet "
      "on things like \"will oil close above $86 tomorrow\"), compares each price to its own estimate of fair value, and only "
      "quotes where the two can be trusted to agree &mdash; on a practice account, with strict size limits. <b>The honest history:</b> "
      "for its first month it placed zero trades, and I believed that was discipline. It wasn't. The exchange had renamed its data "
      "fields, and my code was reading every market as empty. I caught it by looking at the raw data instead of trusting a quiet log, "
      "fixed it, and added an alarm so a blind robot can never again pass for a careful one.", "q"),
    P("Questions I expect", "h"),
    P("<b>\"2.6% a year? That's small.\"</b> For one market, after costs, with nothing massaged - yes, and that's the point. When my first test showed huge free money, the real finding was a bug (a stale price). Small and honest beats big and fake.", "q"),
    P("<b>\"If the data is public, why does it work at all?\"</b> Because the people who could arbitrage it away work on faster things, many oil traders are hedging rather than profit-seeking, and maybe it partly doesn't - which is why the robot keeps grading itself in real time.", "q"),
    P("<b>\"Biggest lesson?\"</b> For a month, \"no trades\" and \"broken\" printed the same line in my logs. Now every part of the system reports what it actually saw, not just whether it crashed. Silence is not evidence.", "q"),
]

doc.build(story)
print(f"wrote {OUT}")
