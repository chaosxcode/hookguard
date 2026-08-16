#!/usr/bin/env python3
"""Build the public HookGuard site from out/risk.json.

Emits docs/index.html (browsable) and docs/risk.json (raw, consumable).
GitHub Pages serves /docs on the default branch.

    python3 src/risk.py && python3 src/site.py
"""
import json, os, shutil, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC  = os.path.join(ROOT, "out", "risk.json")
DOCS = os.path.join(ROOT, "docs")

hooks = json.load(open(SRC))
os.makedirs(DOCS, exist_ok=True)
shutil.copyfile(SRC, os.path.join(DOCS, "risk.json"))

N            = len(hooks)
audited      = sum(1 for h in hooks if h["audited"])
value_moving = sum(1 for h in hooks if h["valueMoving"])
upgradeable  = sum(1 for h in hooks if h["upgradeable"])
vm_unaudited = sum(1 for h in hooks if h["valueMoving"] and not h["audited"])
critical     = sum(1 for h in hooks if h.get("critical"))
pct          = lambda n: f"{n / N * 100:.1f}%"

by_chain = collections.Counter(h["chain"] for h in hooks)
chain_rows = []
for c, n in by_chain.most_common():
    un = sum(1 for h in hooks if h["chain"] == c and not h["audited"])
    chain_rows.append((c, n, un, un / n * 100))

EXPLORER = {
    "ethereum": "https://etherscan.io/address/",
    "base": "https://basescan.org/address/",
    "arbitrum": "https://arbiscan.io/address/",
    "optimism": "https://optimistic.etherscan.io/address/",
    "polygon": "https://polygonscan.com/address/",
    "bnb": "https://bscscan.com/address/",
    "unichain": "https://uniscan.xyz/address/",
    "avalanche": "https://snowtrace.io/address/",
    "blast": "https://blastscan.io/address/",
    "celo": "https://celoscan.io/address/",
    "zora": "https://explorer.zora.energy/address/",
    "worldchain": "https://worldscan.org/address/",
    "soneium": "https://soneium.blockscout.com/address/",
}

# trimmed payload for the client-side table
rows = [{
    "n": h["name"], "a": h["address"], "c": h["chain"], "r": h["risk"],
    "au": 1 if h["audited"] else 0, "vm": 1 if h["valueMoving"] else 0,
    "up": 1 if h["upgradeable"] else 0, "cr": 1 if h.get("critical") else 0,
    "f": [f[0] for f in h["findings"]], "k": h["caps"],
} for h in hooks]

matrix = "".join(
    '<i class="d %s"></i>' % ("vm-un" if (h["valueMoving"] and not h["audited"])
                              else "vm-au" if h["valueMoving"]
                              else "sf-au" if h["audited"] else "sf-un")
    for h in sorted(hooks, key=lambda x: (-x["valueMoving"], x["audited"])))

chain_html = "".join(
    f'<tr><td class="mono">{c}</td><td class="mono num">{n}</td>'
    f'<td class="mono num">{un}</td>'
    f'<td class="num"><span class="bar"><span style="width:{p:.1f}%"></span></span>'
    f'<b class="mono">{p:.1f}%</b></td></tr>'
    for c, n, un, p in chain_rows)

HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HookGuard — risk profile of the Uniswap v4 hook registry</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%230B0E13'/%3E%3Crect x='6' y='6' width='8' height='8' rx='2' fill='%23F2683C'/%3E%3Crect x='18' y='6' width='8' height='8' rx='2' fill='%23F2683C'/%3E%3Crect x='6' y='18' width='8' height='8' rx='2' fill='%23F2683C'/%3E%3Crect x='18' y='18' width='8' height='8' rx='2' fill='%2335C46B'/%3E%3C/svg%3E">
<meta name="description" content="A risk pass over all {N} hooks in Uniswap's official v4 registry. {vm_unaudited} can move value during a swap with no audit on record.">
<style>
:root {{
  --bg:#0B0E13; --surface:#141922; --line:#232B38; --text:#E8EEF5;
  --muted:#8494A8; --dim:#5A6980; --pink:#FF007A; --risk:#F2683C;
  --good:#35C46B; --warn:#F2C14E;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
html {{ -webkit-text-size-adjust:100%; }}
body {{
  background:var(--bg); color:var(--text); line-height:1.55;
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  font-size:16px; padding:0 24px 96px;
}}
.wrap {{ max-width:1180px; margin:0 auto; }}
.mono {{ font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }}
a {{ color:var(--pink); }}
h1,h2,h3 {{ letter-spacing:-.02em; line-height:1.15; }}

header {{ padding:76px 0 0; }}
.eyebrow {{ font-family:ui-monospace,monospace; font-size:12px; letter-spacing:.2em;
  text-transform:uppercase; color:var(--dim); }}
h1 {{ font-size:clamp(38px,6vw,64px); font-weight:800; margin:18px 0 0; }}
.lede {{ font-size:clamp(18px,2.4vw,23px); color:var(--muted); max-width:760px; margin-top:20px; }}
.lede b {{ color:var(--text); font-weight:600; }}
.links {{ margin-top:28px; display:flex; gap:12px; flex-wrap:wrap; }}
.btn {{ font-family:ui-monospace,monospace; font-size:13px; text-decoration:none;
  color:var(--text); border:1px solid var(--line); background:var(--surface);
  padding:10px 16px; border-radius:8px; }}
.btn:hover {{ border-color:var(--pink); }}
.btn.pri {{ border-color:var(--pink); color:var(--pink); }}

.stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr));
  gap:1px; background:var(--line); border:1px solid var(--line);
  border-radius:14px; overflow:hidden; margin-top:56px; }}
.stat {{ background:var(--bg); padding:26px 24px; }}
.stat .n {{ font-size:44px; font-weight:800; letter-spacing:-.03em; line-height:1; }}
.stat .c {{ font-size:14px; color:var(--muted); margin-top:10px; }}

section {{ margin-top:76px; }}
h2 {{ font-size:clamp(24px,3.4vw,34px); font-weight:700; }}
.sub {{ color:var(--muted); margin-top:12px; max-width:800px; }}

.matrix {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(14px,1fr));
  gap:5px; margin-top:28px; }}
.d {{ aspect-ratio:1; border-radius:3px; }}
.vm-un {{ background:var(--risk); }} .vm-au {{ background:var(--pink); }}
.sf-un {{ background:#26303F; }}     .sf-au {{ background:var(--good); }}
.legend {{ display:flex; gap:26px; flex-wrap:wrap; margin-top:22px;
  font-size:14px; color:var(--muted); }}
.legend i {{ width:12px; height:12px; border-radius:3px; display:inline-block;
  margin-right:8px; vertical-align:-1px; }}

.note {{ background:var(--surface); border:1px solid var(--line);
  border-left:3px solid var(--pink); border-radius:10px; padding:22px 26px;
  margin-top:28px; color:var(--muted); }}
.note b {{ color:var(--text); }}

table {{ width:100%; border-collapse:collapse; margin-top:24px; font-size:14px; }}
th {{ text-align:left; font-family:ui-monospace,monospace; font-size:11px;
  letter-spacing:.14em; text-transform:uppercase; color:var(--dim);
  padding:0 14px 12px 0; border-bottom:1px solid var(--line); white-space:nowrap; }}
td {{ padding:13px 14px 13px 0; border-bottom:1px solid var(--line);
  vertical-align:middle; }}
.num {{ text-align:right; }}
.bar {{ display:inline-block; width:110px; height:7px; background:#26303F;
  border-radius:4px; overflow:hidden; margin-right:12px; vertical-align:0px; }}
.bar span {{ display:block; height:100%; background:var(--risk); }}

.controls {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:26px; }}
input,select {{ font:inherit; font-size:14px; background:var(--surface);
  border:1px solid var(--line); color:var(--text); padding:10px 13px;
  border-radius:8px; }}
input {{ flex:1; min-width:210px; }}
input:focus,select:focus {{ outline:none; border-color:var(--pink); }}

.tag {{ font-family:ui-monospace,monospace; font-size:10.5px; letter-spacing:.06em;
  padding:3px 7px; border-radius:4px; margin-right:5px; white-space:nowrap;
  display:inline-block; }}
.t-vm {{ background:#F2683C1f; color:var(--risk); }}
.t-up {{ background:#F2C14E1f; color:var(--warn); }}
.t-cr {{ background:#FF007A24; color:var(--pink); }}
.t-au {{ background:#35C46B1f; color:var(--good); }}
.t-no {{ background:#5A698024; color:var(--dim); }}
.hookname {{ font-weight:600; }}
.addr {{ font-size:12px; color:var(--dim); text-decoration:none; }}
.addr:hover {{ color:var(--pink); }}
.count {{ font-family:ui-monospace,monospace; font-size:13px; color:var(--dim);
  margin-top:16px; }}
#tw {{ overflow-x:auto; }}

footer {{ margin-top:88px; padding-top:32px; border-top:1px solid var(--line);
  color:var(--dim); font-size:14px; }}
@media (max-width:640px) {{
  body {{ padding:0 16px 64px; }} header {{ padding-top:48px; }}
  .hidesm {{ display:none; }}
}}
</style>
</head>
<body>
<div class="wrap">

<header>
  <div class="eyebrow">Uniswap v4 &middot; hook registry &middot; risk pass</div>
  <h1>HookGuard</h1>
  <p class="lede">A risk pass over all <b>{N} hooks</b> in Uniswap's official
  registry. <b>{vm_unaudited}</b> of them can move value during a swap and have
  no audit on record.</p>
  <div class="links">
    <a class="btn pri" href="https://github.com/chaosxcode/hookguard">Source on GitHub</a>
    <a class="btn" href="risk.json">Raw JSON &darr;</a>
    <a class="btn" href="https://github.com/Uniswap/hooklist">Uniswap hooklist</a>
  </div>
</header>

<div class="stats">
  <div class="stat"><div class="n">{N}</div><div class="c">hooks registered, across {len(by_chain)} chains</div></div>
  <div class="stat"><div class="n" style="color:var(--good)">{audited}</div><div class="c">publish an audit URL &mdash; {pct(audited)}</div></div>
  <div class="stat"><div class="n">{value_moving}</div><div class="c">hold return-delta permissions &mdash; {pct(value_moving)}</div></div>
  <div class="stat"><div class="n" style="color:var(--risk)">{vm_unaudited}</div><div class="c">value-moving <em>and</em> unaudited &mdash; {pct(vm_unaudited)}</div></div>
  <div class="stat"><div class="n" style="color:var(--warn)">{upgradeable}</div><div class="c">upgradeable &mdash; {pct(upgradeable)}</div></div>
</div>

<section>
  <h2>The registry at a glance</h2>
  <p class="sub">One square per registered hook, coloured by what its permission
  flags allow and whether the registry records an audit.</p>
  <div class="matrix">{matrix}</div>
  <div class="legend">
    <span><i class="vm-un"></i>{vm_unaudited} value-moving, no recorded audit</span>
    <span><i class="vm-au"></i>{value_moving - vm_unaudited} value-moving, audited</span>
    <span><i class="sf-un"></i>{N - value_moving - (audited - (value_moving - vm_unaudited))} no value-moving permission</span>
    <span><i class="sf-au"></i>{audited - (value_moving - vm_unaudited)} audited, no value-moving permission</span>
  </div>
</section>

<section>
  <h2>Why this is worth measuring</h2>
  <p class="sub">A hook is trusted code sitting in the swap path, and v4 pool
  creation is permissionless &mdash; anyone can create a pool with
  attacker-chosen tokens pointing at an existing hook and drive its callbacks.
  <span class="mono">onlyPoolManager</span> proves the PoolManager called you,
  not that the pool is one you trust. Bunni&nbsp;v2, then the largest LP hook by
  TVL, was exploited for ~$8.3M in September 2025 and shut down.</p>

  <div class="note">
    <b>Stated plainly:</b> an empty <span class="mono">auditUrl</span> means the
    registry <em>records</em> no audit &mdash; not that no audit exists. That
    ambiguity is itself the finding: there is no machine-readable way for an LP,
    a router, or an integrator to tell a reviewed hook from an unreviewed one.
    If a hook here has a published audit, open an issue and the data gets fixed.
  </div>
  <div class="note" style="border-left-color:var(--dim)">
    <b>This is not an audit</b> and does not claim to be. It reads permission
    flags and registry metadata; it does not analyse hook logic. A high score
    means "worth a look," never "vulnerable." A low score means nothing was
    visible at this layer, never "safe."
  </div>
</section>

<section>
  <h2>By chain</h2>
  <table>
    <thead><tr><th>Chain</th><th class="num">Hooks</th><th class="num">Unaudited</th><th class="num">Share unaudited</th></tr></thead>
    <tbody>{chain_html}</tbody>
  </table>
</section>

<section>
  <h2>All {N} hooks</h2>
  <p class="sub">Sorted by risk score. The score is a heuristic weighting of
  permissions, audit status and upgradeability &mdash; a triage aid, not a verdict.</p>
  <div class="controls">
    <input id="q" type="search" placeholder="Search name or address…" autocomplete="off">
    <select id="chain"><option value="">All chains</option>{"".join(f'<option>{c}</option>' for c,_ in by_chain.most_common())}</select>
    <select id="filt">
      <option value="">All hooks</option>
      <option value="vmun">Value-moving &amp; unaudited</option>
      <option value="vm">Value-moving</option>
      <option value="un">Unaudited</option>
      <option value="au">Audited</option>
      <option value="up">Upgradeable</option>
    </select>
  </div>
  <div class="count" id="count"></div>
  <div id="tw"><table>
    <thead><tr><th class="num">Risk</th><th>Hook</th><th class="hidesm">Chain</th><th>Flags</th><th class="hidesm">Permissions</th></tr></thead>
    <tbody id="rows"></tbody>
  </table></div>
</section>

<footer>
  <p>Generated from <a href="https://github.com/Uniswap/hooklist">Uniswap/hooklist</a>
  by <a href="https://github.com/chaosxcode/hookguard">HookGuard</a>. Reproduce with
  <span class="mono">python3 src/risk.py &amp;&amp; python3 src/site.py</span>.</p>
  <p style="margin-top:10px">Heuristic and early. Findings are starting points for review, not verdicts.
  Corrections welcome as GitHub issues.</p>
</footer>

</div>
<script>
const D = {json.dumps(rows, separators=(",", ":"))};
const EX = {json.dumps(EXPLORER)};
const rowsEl = document.getElementById('rows'), cnt = document.getElementById('count');
const q = document.getElementById('q'), ch = document.getElementById('chain'), fl = document.getElementById('filt');
const esc = s => String(s).replace(/[&<>"]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}})[c]);

function tags(h) {{
  let t = '';
  if (h.cr) t += '<span class="tag t-cr">CRITICAL</span>';
  if (h.vm) t += '<span class="tag t-vm">VALUE-MOVING</span>';
  if (h.up) t += '<span class="tag t-up">UPGRADEABLE</span>';
  t += h.au ? '<span class="tag t-au">AUDITED</span>' : '<span class="tag t-no">NO AUDIT</span>';
  return t;
}}

function render() {{
  const s = q.value.trim().toLowerCase(), c = ch.value, f = fl.value;
  const out = D.filter(h => {{
    if (c && h.c !== c) return false;
    if (f === 'vmun' && !(h.vm && !h.au)) return false;
    if (f === 'vm' && !h.vm) return false;
    if (f === 'un' && h.au) return false;
    if (f === 'au' && !h.au) return false;
    if (f === 'up' && !h.up) return false;
    if (s && !(h.n.toLowerCase().includes(s) || h.a.toLowerCase().includes(s))) return false;
    return true;
  }}).sort((a, b) => b.r - a.r || a.n.localeCompare(b.n));

  cnt.textContent = out.length + ' of ' + D.length + ' hooks';
  rowsEl.innerHTML = out.map(h => {{
    const url = (EX[h.c] || '') + h.a;
    const addr = EX[h.c]
      ? '<a class="addr mono" href="' + url + '" target="_blank" rel="noopener">' + h.a.slice(0,10) + '…' + h.a.slice(-6) + '</a>'
      : '<span class="addr mono">' + h.a.slice(0,10) + '…' + h.a.slice(-6) + '</span>';
    return '<tr><td class="num mono" style="font-weight:600">' + h.r + '</td>'
      + '<td><div class="hookname">' + esc(h.n) + '</div>' + addr + '</td>'
      + '<td class="mono hidesm" style="font-size:12px;color:var(--muted)">' + h.c + '</td>'
      + '<td>' + tags(h) + '</td>'
      + '<td class="mono hidesm" style="font-size:11px;color:var(--dim)">' + h.k.join(' ') + '</td></tr>';
  }}).join('');
}}
[q, ch, fl].forEach(el => el.addEventListener('input', render));
render();
</script>
</body>
</html>"""

open(os.path.join(DOCS, "index.html"), "w").write(HTML)
print(f"  docs/index.html   {len(HTML):,} bytes")
print(f"  docs/risk.json    {os.path.getsize(os.path.join(DOCS,'risk.json')):,} bytes")
print(f"  {N} hooks | {audited} audited | {value_moving} value-moving | "
      f"{vm_unaudited} both | {critical} critical")
