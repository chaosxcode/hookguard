#!/usr/bin/env python3
"""Build the public HookGuard site from out/risk.json (+ out/unichain-onchain.json).

    python3 src/risk.py && python3 src/site.py

Writes docs/index.html and copies the raw JSON alongside it, so every number on
the page is checkable by whoever is reading it.
"""
import json, os, shutil, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC  = os.path.join(ROOT, "out", "risk.json")
UNIF = os.path.join(ROOT, "out", "unichain-onchain.json")
DOCS = os.path.join(ROOT, "docs")

hooks = json.load(open(SRC))
uni   = json.load(open(UNIF)) if os.path.exists(UNIF) else None
os.makedirs(DOCS, exist_ok=True)
shutil.copyfile(SRC, os.path.join(DOCS, "risk.json"))
if uni: shutil.copyfile(UNIF, os.path.join(DOCS, "unichain-onchain.json"))

N            = len(hooks)
audited      = sum(1 for h in hooks if h["audited"])
value_moving = sum(1 for h in hooks if h["valueMoving"])
upgradeable  = sum(1 for h in hooks if h["upgradeable"])
vm_unaudited = sum(1 for h in hooks if h["valueMoving"] and not h["audited"])
vm_audited   = value_moving - vm_unaudited
safe_audited = audited - vm_audited
safe_un      = N - value_moving - safe_audited
pct = lambda n: f"{n / N * 100:.1f}%"

by_chain = collections.Counter(h["chain"] for h in hooks)
chain_rows = []
for c, n in by_chain.most_common():
    un = sum(1 for h in hooks if h["chain"] == c and not h["audited"])
    chain_rows.append((c, n, un, un / n * 100))
MAXC = chain_rows[0][1]

EXPLORER = {
 "ethereum":"https://etherscan.io/address/","base":"https://basescan.org/address/",
 "arbitrum":"https://arbiscan.io/address/","optimism":"https://optimistic.etherscan.io/address/",
 "polygon":"https://polygonscan.com/address/","bnb":"https://bscscan.com/address/",
 "unichain":"https://uniscan.xyz/address/","avalanche":"https://snowtrace.io/address/",
 "blast":"https://blastscan.io/address/","celo":"https://celoscan.io/address/",
 "zora":"https://explorer.zora.energy/address/","worldchain":"https://worldscan.org/address/",
 "soneium":"https://soneium.blockscout.com/address/"}

def klass(h):
    if h["valueMoving"] and not h["audited"]: return "d1"
    if h["valueMoving"]: return "d2"
    if h["audited"]: return "d4"
    return "d3"

ordered = sorted(hooks, key=lambda h: (not h["valueMoving"], h["audited"], -h["risk"]))
matrix = "".join(f'<i class="d {klass(h)}" data-i="{i}" style="--dl:{i*1.6:.0f}ms"></i>'
                 for i, h in enumerate(ordered))
mrows = [{"n":h["name"],"a":h["address"],"c":h["chain"],"r":h["risk"],
          "au":1 if h["audited"] else 0,"vm":1 if h["valueMoving"] else 0} for h in ordered]
rows  = [{"n":h["name"],"a":h["address"],"c":h["chain"],"r":h["risk"],
          "au":1 if h["audited"] else 0,"vm":1 if h["valueMoving"] else 0,
          "up":1 if h["upgradeable"] else 0,"cr":1 if h.get("critical") else 0,
          "k":h["caps"]} for h in hooks]

chain_html = "".join(
 f'''<div class="crow reveal"><div class="cname mono">{c}</div>
   <div class="ctrack"><div class="cbar" style="width:{n/MAXC*100:.1f}%">
   <span class="cfill" data-w="{p:.1f}"></span></div></div>
   <div class="cnum mono">{n}</div><div class="cpct mono">{p:.0f}%</div></div>'''
 for c, n, un, p in chain_rows)

uni_html = "" if not uni else f"""
<section id="coverage"><div class="wrap">
  <div class="shead reveal"><span class="sk">02</span><h2>The list only shows the ones that signed up</h2></div>
  <p class="lede reveal">Uniswap's registry is opt-in — a hook is on it because someone asked.
  So we went and counted the real thing: <b>every pool ever created on Unichain</b>, and the hook
  attached to each one. Here's the gap.</p>

  <div class="vs reveal">
    <div class="vsb lo"><div class="vsn mono" data-count="{uni['registryHooksSeenOnchain']}">0</div><div class="vsl">on the list</div></div>
    <div class="vsx">vs</div>
    <div class="vsb hi"><div class="vsn mono" data-count="{uni['distinctHooks']}">0</div><div class="vsl">actually out there</div></div>
    <div class="vsp"><div class="vspn mono">{uni['registryCoveragePct']}%</div><div class="vsl">of them are listed</div></div>
  </div>

  <div class="g3">
    <div class="mini reveal"><div class="mn mono" data-count="{uni['poolsCreated']}">0</div><div class="ml">pools ever created</div></div>
    <div class="mini reveal"><div class="mn mono" data-count="{uni['poolsWithHook']}">0</div><div class="ml">of them use a hook — {uni['poolsWithHook']/uni['poolsCreated']*100:.0f}%</div></div>
    <div class="mini reveal"><div class="mn mono" data-count="{uni['hooksServingTenPlusPools']}">0</div><div class="ml">hooks used by 10+ pools</div></div>
  </div>

  <div class="note reveal"><b>Being straight about this number.</b>
  {uni['hooksServingOnePool']:,} of the {uni['distinctHooks']:,} are attached to exactly one pool —
  that's launchpads spitting out a fresh hook per token, not {uni['hooksServingOnePool']:,} real projects.
  The ones that matter are the <b>{uni['hooksServingMultiplePools']}</b> used by two or more pools, and the
  <b>{uni['hooksServingTenPlusPools']}</b> used by ten or more. Even so:
  <b>the second and third busiest hooks on Unichain aren't on the list at all.</b></div>

  <p class="foot reveal">Check it yourself: <span class="mono">CHAIN=unichain python3 src/discover.py</span>
   · it refuses to publish a partial scan, because undercounting is the one mistake that would quietly
   make this number a lie · <a href="unichain-onchain.json">raw data</a></p>
</div></section>"""

HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HookGuard — which Uniswap v4 hooks have actually been checked?</title>
<meta name="description" content="{vm_unaudited} of the {N} hooks on Uniswap's official v4 list can move money during a swap, with no audit on record. Browse every one.">
<meta property="og:title" content="HookGuard">
<meta property="og:description" content="{vm_unaudited} of {N} listed Uniswap v4 hooks can move money during a swap with no audit on record.">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%2308090C'/%3E%3Crect x='6' y='6' width='8' height='8' rx='2' fill='%23FF6B3D'/%3E%3Crect x='18' y='6' width='8' height='8' rx='2' fill='%23FF6B3D'/%3E%3Crect x='6' y='18' width='8' height='8' rx='2' fill='%23FF6B3D'/%3E%3Crect x='18' y='18' width='8' height='8' rx='2' fill='%233DD68C'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root{{--bg:#07080B;--card:#10131A;--line:#1C222D;--line2:#28303F;--tx:#EEF2F8;
--mu:#8B98AC;--dim:#5B6679;--pink:#FF007A;--risk:#FF6B3D;--good:#3DD68C;--warn:#F5C451;}}
*{{margin:0;padding:0;box-sizing:border-box}}
html{{scroll-behavior:smooth;-webkit-text-size-adjust:100%}}
body{{background:var(--bg);color:var(--tx);font-family:Inter,system-ui,sans-serif;
font-size:16px;line-height:1.6;letter-spacing:-.011em;-webkit-font-smoothing:antialiased;overflow-x:hidden}}
.mono{{font-family:"JetBrains Mono",ui-monospace,Menlo,monospace}}
a{{color:var(--pink);text-decoration:none}} a:hover{{text-decoration:underline}}
.wrap{{max-width:1140px;margin:0 auto;padding:0 26px}}

#bgfx{{position:fixed;inset:0;z-index:0;pointer-events:none;opacity:.55}}
.aurora{{position:fixed;z-index:0;pointer-events:none;filter:blur(90px);opacity:.5;
border-radius:50%;animation:drift 26s ease-in-out infinite alternate}}
.a1{{width:640px;height:640px;background:rgba(255,107,61,.22);top:-220px;left:-160px}}
.a2{{width:560px;height:560px;background:rgba(255,0,122,.18);top:120px;right:-200px;animation-delay:-9s}}
.a3{{width:520px;height:520px;background:rgba(61,214,140,.10);top:1100px;left:20%;animation-delay:-15s}}
@keyframes drift{{from{{transform:translate3d(0,0,0) scale(1)}}to{{transform:translate3d(60px,80px,0) scale(1.18)}}}}
nav,header,section,footer{{position:relative;z-index:2}}

nav{{position:sticky;top:0;z-index:60;backdrop-filter:blur(16px);
background:rgba(7,8,11,.75);border-bottom:1px solid var(--line)}}
nav .wrap{{display:flex;align-items:center;gap:26px;height:62px}}
.brand{{font-weight:800;letter-spacing:-.035em;font-size:17px;display:flex;align-items:center;gap:9px}}
.brand i{{width:10px;height:10px;border-radius:3px;background:var(--risk);
box-shadow:0 0 14px var(--risk);animation:pulse 2.6s ease-in-out infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.45}}}}
nav a.nl{{color:var(--mu);font-size:14px;font-weight:500}}
nav a.nl:hover{{color:var(--tx);text-decoration:none}}
nav .sp{{flex:1}}
.ghost{{border:1px solid var(--line2);padding:8px 15px;border-radius:9px;font-size:13px;
font-weight:600;color:var(--tx)!important;transition:.18s}}
.ghost:hover{{border-color:var(--pink);text-decoration:none!important;box-shadow:0 0 22px rgba(255,0,122,.25)}}
@media(max-width:800px){{nav a.nl{{display:none}}}}

header .wrap{{padding:104px 26px 84px}}
.tag{{display:inline-flex;align-items:center;gap:8px;font-size:11.5px;font-weight:700;
letter-spacing:.13em;text-transform:uppercase;color:var(--mu);border:1px solid var(--line2);
border-radius:99px;padding:7px 15px;margin-bottom:28px;background:rgba(16,19,26,.6)}}
.tag b{{color:var(--risk)}}
h1{{font-size:clamp(40px,7vw,80px);font-weight:900;line-height:1.0;letter-spacing:-.048em;max-width:15ch}}
h1 em{{font-style:normal;background:linear-gradient(96deg,var(--risk),var(--pink));
-webkit-background-clip:text;background-clip:text;color:transparent}}
.sub{{font-size:clamp(17px,2.1vw,21px);color:var(--mu);max-width:60ch;margin-top:26px;line-height:1.55}}
.sub b{{color:var(--tx);font-weight:600}}
.cta{{display:flex;gap:11px;flex-wrap:wrap;margin-top:36px}}
.btn{{padding:12px 20px;border-radius:11px;font-size:14.5px;font-weight:600;
border:1px solid var(--line2);color:var(--tx)!important;transition:.18s}}
.btn:hover{{border-color:var(--pink);text-decoration:none!important;transform:translateY(-2px);
box-shadow:0 10px 30px rgba(255,0,122,.18)}}
.btn.p{{background:linear-gradient(96deg,var(--risk),var(--pink));border-color:transparent;color:#fff!important}}
.btn.p:hover{{filter:brightness(1.1)}}

.hstats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(156px,1fr));gap:13px;margin-top:56px}}
.hs{{background:linear-gradient(180deg,rgba(16,19,26,.95),rgba(16,19,26,.4));
border:1px solid var(--line);border-radius:15px;padding:20px;transition:.2s}}
.hs:hover{{border-color:var(--line2);transform:translateY(-3px)}}
.hs .n{{font-size:38px;font-weight:800;letter-spacing:-.045em;line-height:1;font-family:"JetBrains Mono",monospace}}
.hs .l{{font-size:13px;color:var(--mu);margin-top:9px;line-height:1.4}}
.hs.a .n{{color:var(--risk);text-shadow:0 0 26px rgba(255,107,61,.45)}}
.hs.g .n{{color:var(--good)}} .hs.w .n{{color:var(--warn)}}

section{{padding:86px 0;border-top:1px solid var(--line)}}
.shead{{display:flex;align-items:baseline;gap:14px;margin-bottom:16px}}
.sk{{font-family:"JetBrains Mono",monospace;font-size:12px;color:var(--dim);letter-spacing:.1em}}
h2{{font-size:clamp(26px,3.8vw,38px);font-weight:800;letter-spacing:-.036em;line-height:1.1}}
.lede{{color:var(--mu);max-width:68ch;font-size:17px}} .lede b{{color:var(--tx);font-weight:600}}
.foot{{color:var(--dim);font-size:13.5px;margin-top:22px}}

.matrix{{display:grid;grid-template-columns:repeat(auto-fill,minmax(15px,1fr));gap:6px;margin-top:34px}}
.d{{aspect-ratio:1;border-radius:3.5px;cursor:crosshair;opacity:0;transform:scale(.4);
animation:pop .45s cubic-bezier(.2,.9,.3,1.3) forwards;animation-delay:var(--dl);transition:transform .12s,box-shadow .12s}}
@keyframes pop{{to{{opacity:1;transform:scale(1)}}}}
.d:hover{{transform:scale(1.7)!important;z-index:5;box-shadow:0 0 0 2px var(--tx),0 0 20px rgba(255,255,255,.35)}}
.d1{{background:var(--risk)}} .d2{{background:var(--pink)}}
.d3{{background:#212936}} .d4{{background:var(--good)}}
#tip{{position:fixed;z-index:99;pointer-events:none;opacity:0;transition:opacity .12s;
background:#04050A;border:1px solid var(--line2);border-radius:11px;padding:11px 14px;
font-size:13px;max-width:300px;box-shadow:0 16px 50px rgba(0,0,0,.7)}}
#tip .t{{font-weight:700;margin-bottom:5px}}
#tip .m{{font-family:"JetBrains Mono",monospace;font-size:11.5px;color:var(--mu)}}
.legend{{display:flex;gap:22px;flex-wrap:wrap;margin-top:26px;font-size:13.5px;color:var(--mu)}}
.legend i{{width:11px;height:11px;border-radius:3px;display:inline-block;margin-right:8px}}
.legend b{{color:var(--tx);font-family:"JetBrains Mono",monospace}}

.note{{background:rgba(16,19,26,.75);border:1px solid var(--line);border-left:3px solid var(--pink);
border-radius:13px;padding:20px 24px;margin-top:26px;color:var(--mu);font-size:15px}}
.note b{{color:var(--tx);font-weight:600}} .note.n2{{border-left-color:var(--dim)}}

.vs{{display:flex;align-items:center;gap:clamp(18px,4vw,46px);flex-wrap:wrap;margin:40px 0 30px}}
.vsn{{font-size:clamp(42px,7.6vw,80px);font-weight:900;letter-spacing:-.05em;line-height:1}}
.lo .vsn{{color:var(--good)}} .hi .vsn{{color:var(--risk);text-shadow:0 0 40px rgba(255,107,61,.4)}}
.vsl{{font-size:13.5px;color:var(--mu);margin-top:8px}}
.vsx{{font-size:15px;color:var(--dim);font-weight:700}}
.vsp{{margin-left:auto;text-align:right}}
.vspn{{font-size:clamp(30px,4.6vw,46px);font-weight:900;letter-spacing:-.045em;color:var(--pink);line-height:1}}
.g3{{display:grid;grid-template-columns:repeat(auto-fit,minmax(188px,1fr));gap:13px}}
.mini{{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:18px 20px;transition:.2s}}
.mini:hover{{border-color:var(--line2);transform:translateY(-3px)}}
.mn{{font-size:26px;font-weight:800;letter-spacing:-.04em}}
.ml{{font-size:13px;color:var(--mu);margin-top:6px}}

.chains{{margin-top:34px}}
.crow{{display:grid;grid-template-columns:116px 1fr 50px 50px;align-items:center;gap:16px;
padding:10px 0;border-bottom:1px solid var(--line);font-size:14px}}
.cname{{color:var(--mu);font-size:13px}}
.ctrack{{background:#12161E;border-radius:6px;height:10px;overflow:hidden}}
.cbar{{height:100%;background:#212936;border-radius:6px;position:relative}}
.cfill{{position:absolute;inset:0 auto 0 0;width:0;background:linear-gradient(90deg,var(--risk),var(--pink));
border-radius:6px;display:block;transition:width 1.1s cubic-bezier(.2,.8,.2,1)}}
.cnum{{text-align:right}} .cpct{{text-align:right;color:var(--risk);font-size:13px}}

.controls{{display:flex;gap:10px;flex-wrap:wrap;margin:30px 0 6px}}
input,select{{font:inherit;font-size:14px;background:var(--card);border:1px solid var(--line2);
color:var(--tx);padding:11px 14px;border-radius:11px}}
input{{flex:1;min-width:230px}}
input:focus,select:focus{{outline:none;border-color:var(--pink);box-shadow:0 0 0 3px rgba(255,0,122,.12)}}
.count{{font-family:"JetBrains Mono",monospace;font-size:13px;color:var(--dim);margin:14px 0}}
.tbl{{overflow-x:auto;border:1px solid var(--line);border-radius:15px;background:rgba(16,19,26,.7)}}
table{{width:100%;border-collapse:collapse;font-size:14px}}
thead th{{position:sticky;top:62px;background:#0C0F15;text-align:left;font-family:"JetBrains Mono",monospace;
font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);padding:13px 16px;
white-space:nowrap;border-bottom:1px solid var(--line)}}
tbody td{{padding:13px 16px;border-bottom:1px solid var(--line)}}
tbody tr:last-child td{{border-bottom:none}}
tbody tr:hover{{background:rgba(255,255,255,.025)}}
.rs{{font-family:"JetBrains Mono",monospace;font-weight:700;text-align:right}}
.hn{{font-weight:600}}
.ad{{font-family:"JetBrains Mono",monospace;font-size:11.5px;color:var(--dim)}}
.ad:hover{{color:var(--pink)}}
.tag2{{font-family:"JetBrains Mono",monospace;font-size:10px;letter-spacing:.05em;padding:3px 8px;
border-radius:5px;margin-right:5px;display:inline-block;white-space:nowrap}}
.t-vm{{background:rgba(255,107,61,.14);color:var(--risk)}}
.t-up{{background:rgba(245,196,81,.14);color:var(--warn)}}
.t-au{{background:rgba(61,214,140,.14);color:var(--good)}}
.t-no{{background:rgba(139,152,172,.12);color:var(--mu)}}
.t-cr{{background:rgba(255,0,122,.18);color:var(--pink)}}
.caps{{font-family:"JetBrains Mono",monospace;font-size:10.5px;color:var(--dim)}}
@media(max-width:820px){{.hide{{display:none}}thead th{{top:0}}}}

.reveal{{opacity:0;transform:translateY(22px);transition:opacity .7s ease,transform .7s cubic-bezier(.2,.8,.2,1)}}
.reveal.in{{opacity:1;transform:none}}
@media(prefers-reduced-motion:reduce){{
 .reveal{{opacity:1;transform:none;transition:none}}
 .d{{opacity:1;transform:none;animation:none}}
 .aurora{{animation:none}} .brand i{{animation:none}}}}

footer{{padding:54px 0 76px;color:var(--dim);font-size:14px;border-top:1px solid var(--line)}}
footer a{{color:var(--mu)}}
</style>
</head>
<body>
<canvas id="bgfx"></canvas>
<div class="aurora a1"></div><div class="aurora a2"></div><div class="aurora a3"></div>

<nav><div class="wrap">
  <span class="brand"><i></i>HookGuard</span>
  <a class="nl" href="#registry">The list</a>
  <a class="nl" href="#coverage">What it misses</a>
  <a class="nl" href="#chains">By chain</a>
  <a class="nl" href="#all">Browse all</a>
  <span class="sp"></span>
  <a class="ghost" href="https://github.com/chaosxcode/hookguard">GitHub</a>
</div></nav>

<header><div class="wrap">
  <div class="tag">Uniswap v4 · <b>{N} hooks</b> · {len(by_chain)} chains</div>
  <h1>{vm_unaudited} hooks can move your money. <em>Nobody checked them.</em></h1>
  <p class="sub">A hook is code that runs every time someone trades in a pool — it can change the
  price, take a fee, or move the tokens. Uniswap lists <b>{N}</b> of them. Only <b>{audited}</b>
  have an audit on record. <b>{vm_unaudited}</b> can move money and have none.</p>
  <div class="cta">
    <a class="btn p" href="#all">Browse all {N} hooks</a>
    <a class="btn" href="risk.json">Get the raw data</a>
    <a class="btn" href="https://github.com/chaosxcode/hookguard#use-it-in-ci">Run it on your own hook</a>
  </div>
  <div class="hstats">
    <div class="hs"><div class="n" data-count="{N}">0</div><div class="l">hooks on the list</div></div>
    <div class="hs g"><div class="n" data-count="{audited}">0</div><div class="l">have an audit — {pct(audited)}</div></div>
    <div class="hs"><div class="n" data-count="{value_moving}">0</div><div class="l">can move money — {pct(value_moving)}</div></div>
    <div class="hs a"><div class="n" data-count="{vm_unaudited}">0</div><div class="l">both — {pct(vm_unaudited)}</div></div>
    <div class="hs w"><div class="n" data-count="{upgradeable}">0</div><div class="l">can be swapped out later — {pct(upgradeable)}</div></div>
  </div>
</div></header>

<section id="registry"><div class="wrap">
  <div class="shead reveal"><span class="sk">01</span><h2>Every hook on the list, one square each</h2></div>
  <p class="lede reveal">Orange means it can move money and has no audit on record.
  <b>Hover any square</b> to see which hook it is.</p>
  <div class="matrix" id="mx">{matrix}</div>
  <div class="legend reveal">
    <span><i style="background:var(--risk)"></i><b>{vm_unaudited}</b> moves money, no audit</span>
    <span><i style="background:var(--pink)"></i><b>{vm_audited}</b> moves money, audited</span>
    <span><i style="background:#212936"></i><b>{safe_un}</b> can't move money</span>
    <span><i style="background:var(--good)"></i><b>{safe_audited}</b> audited, can't move money</span>
  </div>

  <div class="note reveal"><b>Why this is worth caring about.</b> A hook sits in the path of every
  trade in its pool, and anyone can open a new pool pointing at an existing hook — you don't need
  the author's permission. Bunni v2, at the time the biggest hook by money held, was drained of
  <b>~$8.3M</b> in September 2025 and shut down.</div>

  <div class="note n2 reveal"><b>One honest caveat.</b> "No audit" here means <i>the list doesn't
  record one</i> — not that none exists. That gap is the actual point: right now there's no
  machine-readable way for anyone to tell a reviewed hook from an unreviewed one. If a hook here
  has been audited, open an issue and we'll fix the data.</div>

  <div class="note n2 reveal"><b>This is not an audit.</b> It reads permissions and list metadata;
  it does not read what the hook actually does. A high score means <i>worth a look</i>, never
  <i>broken</i>. A low score means nothing showed up at this level, never <i>safe</i>.
  <a href="https://github.com/chaosxcode/hookguard/blob/master/docs/precision.md">How we tested the
  rules — and the five ways they were wrong →</a></div>
</div></section>

{uni_html}

<section id="chains"><div class="wrap">
  <div class="shead reveal"><span class="sk">03</span><h2>Which chains are worst</h2></div>
  <p class="lede reveal">Bar length is how many hooks that chain has. The coloured part is the
  share with <b>no audit on record</b>.</p>
  <div class="chains">{chain_html}</div>
</div></section>

<section id="all"><div class="wrap">
  <div class="shead reveal"><span class="sk">04</span><h2>Browse all {N}</h2></div>
  <p class="lede reveal">Search, filter, click through to the block explorer. The score is a rough
  triage number, not a verdict.</p>
  <div class="controls">
    <input id="q" type="search" placeholder="Search by name or address…" autocomplete="off">
    <select id="chain"><option value="">All chains</option>{"".join(f'<option>{c}</option>' for c,_ in by_chain.most_common())}</select>
    <select id="filt">
      <option value="">Everything</option>
      <option value="vmun">Moves money, no audit</option>
      <option value="vm">Moves money</option>
      <option value="un">No audit</option>
      <option value="au">Audited</option>
      <option value="up">Upgradeable</option>
    </select>
  </div>
  <div class="count" id="count"></div>
  <div class="tbl"><table>
    <thead><tr><th class="rs">Score</th><th>Hook</th><th class="hide">Chain</th><th>Flags</th><th class="hide">Permissions</th></tr></thead>
    <tbody id="rows"></tbody>
  </table></div>
</div></section>

<footer><div class="wrap">
  <p>Built from <a href="https://github.com/Uniswap/hooklist">Uniswap's official hook list</a> by
  <a href="https://github.com/chaosxcode/hookguard">HookGuard</a> · every number here regenerates with
  <span class="mono">python3 src/risk.py &amp;&amp; python3 src/site.py</span></p>
  <p style="margin-top:9px">Early and heuristic. Findings are starting points, not verdicts.
  Corrections welcome as GitHub issues. MIT licensed.</p>
</div></footer>

<div id="tip"></div>
<script>
const D={json.dumps(rows,separators=(",",":"))};
const M={json.dumps(mrows,separators=(",",":"))};
const EX={json.dumps(EXPLORER)};
const esc=s=>String(s).replace(/[&<>"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}})[c]);
const RM=matchMedia('(prefers-reduced-motion:reduce)').matches;

/* particles */
(()=>{{
  const cv=document.getElementById('bgfx'),cx=cv.getContext('2d');
  let w,h,P=[];
  const resize=()=>{{w=cv.width=innerWidth;h=cv.height=innerHeight;
    const n=Math.min(70,Math.round(w*h/26000));
    P=Array.from({{length:n}},()=>({{x:Math.random()*w,y:Math.random()*h,
      vx:(Math.random()-.5)*.16,vy:(Math.random()-.5)*.16,r:Math.random()*1.5+.5}}));}};
  resize();addEventListener('resize',resize);
  if(RM){{cv.style.display='none';return;}}
  (function loop(){{
    cx.clearRect(0,0,w,h);
    for(const p of P){{
      p.x+=p.vx;p.y+=p.vy;
      if(p.x<0)p.x=w; if(p.x>w)p.x=0; if(p.y<0)p.y=h; if(p.y>h)p.y=0;
      cx.beginPath();cx.arc(p.x,p.y,p.r,0,7);cx.fillStyle='rgba(150,170,200,.5)';cx.fill();
    }}
    for(let i=0;i<P.length;i++)for(let j=i+1;j<P.length;j++){{
      const dx=P[i].x-P[j].x,dy=P[i].y-P[j].y,d2=dx*dx+dy*dy;
      if(d2<15000){{cx.beginPath();cx.moveTo(P[i].x,P[i].y);cx.lineTo(P[j].x,P[j].y);
        cx.strokeStyle='rgba(120,140,175,'+(.16*(1-d2/15000))+')';cx.lineWidth=1;cx.stroke();}}
    }}
    requestAnimationFrame(loop);
  }})();
}})();

/* count-up + reveal + bars */
const io=new IntersectionObserver(es=>{{
  for(const e of es){{
    if(!e.isIntersecting)continue;
    const el=e.target;
    el.classList.add('in');
    if(el.dataset.count!==undefined&&!el.dataset.done){{
      el.dataset.done=1;
      const to=+el.dataset.count,dur=RM?0:1100,t0=performance.now();
      const step=t=>{{const k=Math.min(1,(t-t0)/dur),v=Math.round(to*(1-Math.pow(1-k,3)));
        el.textContent=v.toLocaleString();if(k<1)requestAnimationFrame(step);}};
      requestAnimationFrame(step);
    }}
    if(el.classList.contains('crow')){{
      const f=el.querySelector('.cfill'); if(f)f.style.width=f.dataset.w+'%';
    }}
    io.unobserve(el);
  }}
}},{{threshold:.25}});
document.querySelectorAll('.reveal,[data-count]').forEach(el=>io.observe(el));

/* matrix tooltip */
const tip=document.getElementById('tip'),mx=document.getElementById('mx');
mx.addEventListener('mouseover',e=>{{
  const d=e.target.closest('.d'); if(!d)return;
  const h=M[+d.dataset.i]; if(!h)return;
  tip.innerHTML='<div class="t">'+esc(h.n)+'</div><div class="m">'+h.c+' · score '+h.r+' · '
    +(h.vm?'moves money':'cannot move money')+' · '+(h.au?'audited':'no audit')+'</div>';
  tip.style.opacity=1;
}});
mx.addEventListener('mousemove',e=>{{
  const pad=16,w=tip.offsetWidth,h=tip.offsetHeight;
  let x=e.clientX+pad,y=e.clientY+pad;
  if(x+w>innerWidth-8)x=e.clientX-w-pad;
  if(y+h>innerHeight-8)y=e.clientY-h-pad;
  tip.style.left=x+'px';tip.style.top=y+'px';
}});
mx.addEventListener('mouseleave',()=>tip.style.opacity=0);

/* table */
const rowsEl=document.getElementById('rows'),cnt=document.getElementById('count');
const q=document.getElementById('q'),ch=document.getElementById('chain'),fl=document.getElementById('filt');
function tags(h){{let t='';
  if(h.cr)t+='<span class="tag2 t-cr">CRITICAL</span>';
  if(h.vm)t+='<span class="tag2 t-vm">MOVES MONEY</span>';
  if(h.up)t+='<span class="tag2 t-up">UPGRADEABLE</span>';
  t+=h.au?'<span class="tag2 t-au">AUDITED</span>':'<span class="tag2 t-no">NO AUDIT</span>';
  return t;}}
function render(){{
  const s=q.value.trim().toLowerCase(),c=ch.value,f=fl.value;
  const out=D.filter(h=>{{
    if(c&&h.c!==c)return false;
    if(f==='vmun'&&!(h.vm&&!h.au))return false;
    if(f==='vm'&&!h.vm)return false;
    if(f==='un'&&h.au)return false;
    if(f==='au'&&!h.au)return false;
    if(f==='up'&&!h.up)return false;
    if(s&&!(h.n.toLowerCase().includes(s)||h.a.toLowerCase().includes(s)))return false;
    return true;
  }}).sort((a,b)=>b.r-a.r||a.n.localeCompare(b.n));
  cnt.textContent=out.length+' of '+D.length+' hooks';
  rowsEl.innerHTML=out.map(h=>{{
    const short=h.a.slice(0,10)+'…'+h.a.slice(-6);
    const addr=EX[h.c]?'<a class="ad" href="'+EX[h.c]+h.a+'" target="_blank" rel="noopener">'+short+'</a>'
      :'<span class="ad">'+short+'</span>';
    const col=h.r>=20?'var(--risk)':h.r>=12?'var(--warn)':'var(--mu)';
    return '<tr><td class="rs" style="color:'+col+'">'+h.r+'</td>'
      +'<td><div class="hn">'+esc(h.n)+'</div>'+addr+'</td>'
      +'<td class="hide mono" style="font-size:12px;color:var(--mu)">'+h.c+'</td>'
      +'<td>'+tags(h)+'</td><td class="hide caps">'+h.k.join(' ')+'</td></tr>';
  }}).join('');
}}
[q,ch,fl].forEach(el=>el.addEventListener('input',render));
render();
</script>
</body>
</html>"""

open(os.path.join(DOCS, "index.html"), "w").write(HTML)
print(f"  docs/index.html   {len(HTML):,} bytes")
print(f"  {N} hooks | {audited} audited | {value_moving} value-moving | {vm_unaudited} both")
