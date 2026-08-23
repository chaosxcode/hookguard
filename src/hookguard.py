#!/usr/bin/env python3
"""HookGuard CLI — scan any repository, get a verdict + optional HTML report.

    python3 src/hookguard.py scan https://github.com/owner/repo [options]

Options:
  --branch REF     branch/tag/sha to scan (default: HEAD)
  --paths SRC,...  subdirectories to scan (default: auto-detect)
  --html FILE      write a standalone HTML report
  --json FILE      write machine-readable results

Auto-detection order for paths: src, contracts/src, contracts/src/*,
contracts, then repo root. Vendored/test/mock directories are skipped by
the scanner itself; this CLI additionally skips fetching them.

Exit codes: 0 clean/INFO only · 1 findings at --fail-on threshold or above ·
2 usage/environment error.
"""
import argparse, base64, json, os, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scan as scanner                                     # noqa: E402
from score import compute_score                            # noqa: E402

SKIP = ("test", "mock", "script", "lib/", "node_modules", "/out/", ".forge", "cache")
AUTO_PATHS = ["src", "contracts/src", "contracts", "."]
BAND_CLASS = {"LOW": "s-low", "MODERATE": "s-moderate",
              "ELEVATED": "s-elevated", "HIGH": "s-high"}
SEV_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}


def sh(*args, binary=False):
    r = subprocess.run(args, capture_output=True, text=not binary)
    return (r.stdout if not binary else r.stdout) if r.returncode == 0 else None


def gh_json(path):
    out = sh("gh", "api", path, "--jq", ".")
    return json.loads(out) if out else None


def resolve_default_branch(repo):
    d = gh_json(f"repos/{repo}")
    return (d or {}).get("default_branch", "main")


def list_sol_files(repo, ref):
    t = gh_json(f"repos/{repo}/git/trees/{ref}?recursive=1") or {}
    files = []
    for e in t.get("tree", []):
        p = e.get("path", "")
        if not p.endswith(".sol"):
            continue
        low = p.lower()
        if e.get("type") != "blob" or any(s in low for s in SKIP):
            continue
        files.append(p)
    return files


def choose_paths(files):
    """Prefer conventional hook directories when present."""
    import collections
    tops = collections.Counter()
    for p in files:
        parts = p.split("/")
        tops["/".join(parts[:2]) if len(parts) > 2 else parts[0]] += 1
    for cand in AUTO_PATHS:
        hits = [p for p in files if p.startswith(cand.rstrip("/") + "/")]
        if hits:
            return hits
    return files


def fetch_files(repo, ref, files, dest):
    n = 0
    for p in files:
        raw = sh("gh", "api", f"repos/{repo}/contents/{p}?ref={ref}", "--jq", ".content")
        if raw is None:
            continue
        try:
            blob = base64.b64decode(raw.strip())
        except Exception:                                   # noqa: BLE001
            continue
        flat = p.replace("/", "__")
        open(os.path.join(dest, flat), "wb").write(blob)
        n += 1
        if n >= 60:
            break                                           # sanity cap per repo
    return n


def score_results(results):
    highs = sum(1 for c in results for s, *_ in [(f[0],) for f in c["findings"]] if s == "HIGH")
    meds = sum(1 for c in results for f in c["findings"] if f[0] == "MEDIUM")
    lows = sum(1 for c in results for f in c["findings"] if f[0] == "LOW")
    infos = sum(1 for c in results for f in c["findings"] if f[0] == "INFO")
    return compute_score({
        "source_analyzed": True,
        "high_findings": highs, "medium_findings": meds,
        "low_findings": lows, "info_findings": infos,
    })


def render_html(repo, ref, results, score):
    rows = ""
    for c in sorted(results, key=lambda c: [
        -min([SEV_ORDER[f[0]] for f in c["findings"]] or [4]), c["contract"]]):
        if not c["findings"]:
            rows += (f'<tr><td class="mono">{c["contract"]}</td>'
                     f'<td><span class="chip ok">clean</span></td></tr>')
            continue
        first = True
        for s, code, msg, ln in sorted(c["findings"], key=lambda f: SEV_ORDER[f[0]]):
            cls = {"HIGH": "b-no", "MEDIUM": "warn", "LOW": "b-dim",
                   "INFO": "b-dim"}[s]
            rows += (f'<tr><td class="mono">{"&nbsp;" if not first else c["contract"]}</td>'
                     f'<td><span class="badge {cls}">{s}</span> '
                     f'<span class="mono dim">{code}@{ln}</span><br>'
                     f'<span class="msg">{msg[:220]}</span></td></tr>')
            first = False
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>HookGuard report — {html_escape(repo)}</title><style>
body{{background:#05060b;color:#eceaf4;font:14.5px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;
margin:0;padding:40px 20px}}
.wrap{{max-width:900px;margin:auto}}
h1{{font-size:30px;letter-spacing:-.02em}} h1 span{{background:linear-gradient(120deg,#ff007a,#00d1ff);
-webkit-background-clip:text;background-clip:text;color:transparent}}
.meta{{color:#8f8fa8;font-size:13px;margin:8px 0 26px}}
.scorechip{{font-family:Menlo,monospace;font-weight:700;padding:4px 12px;border-radius:8px}}
table{{width:100%;border-collapse:collapse;margin-top:18px}}
td{{padding:11px 13px;border-bottom:1px solid rgba(255,255,255,.06);vertical-align:top}}
.badge{{padding:2px 9px;border-radius:999px;font-size:11px;border:1px solid rgba(255,255,255,.15)}}
.b-no{{color:#ff4d6b;border-color:rgba(255,77,107,.4)}} .warn{{color:#ffb547;border-color:rgba(255,181,71,.35)}}
.chip.ok{{color:#00e58f;border-color:rgba(0,229,143,.3);border-radius:999px;padding:2px 9px;font-size:11px;
border-style:solid;display:inline-block}}
.mono{{font-family:Menlo,monospace}} .dim{{color:#8f8fa8;font-size:11px}} .msg{{color:#c9c6dd;font-size:12.5px}}
.foot{{margin-top:28px;color:#5c5c74;font-size:12px}}
a{{color:#00d1ff}}
</style></head><body><div class="wrap">
<h1>HookGuard report — <span>{html_escape(repo)}</span></h1>
<div class="meta mono">@{html_escape(ref)} · {len(results)} hook contract(s) · generated by HookGuard heuristic scanner</div>
<p>Overall risk <span class="scorechip {BAND_CLASS[score['band']]}">{score['score']} {score['band']}</span>
<span style="color:#8f8fa8;font-size:12px"> confidence: {score['confidence']}</span>
— every contributing factor is itemized below; weights are public in
<a href="https://github.com/chaosxcode/hookguard/blob/master/src/score.py">src/score.py</a>.</p>
<table>{rows}</table>
<div class="foot"><b>Not an audit.</b> Findings are heuristic pattern matches — “worth a look”, never
“vulnerable”. Method, firing rates and published corrections:
<a href="https://github.com/chaosxcode/hookguard/blob/master/docs/precision.md">docs/precision.md</a>.</div>
</div></body></html>"""


def html_escape(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def cmd_scan(args):
    repo = args.repo
    repo = repo.removesuffix(".git")
    if "github.com/" in repo:
        repo = repo.split("github.com/", 1)[1].strip("/")
    ref = args.branch or resolve_default_branch(repo)
    if not gh_json(f"repos/{repo}"):
        print(f"error: repo {repo} not found or inaccessible", file=sys.stderr)
        return 2

    files = list_sol_files(repo, ref)
    if args.paths:
        filters = tuple(p.strip("/") for p in args.paths.split(","))
        files = [p for p in files if p.startswith(filters)]
    picked = choose_paths(files) or files

    with tempfile.TemporaryDirectory() as tmp:
        dest = os.path.join(tmp, "bundle")
        os.makedirs(dest)
        n = fetch_files(repo, ref, picked, dest)
        results = [r for r in (scanner.analyze(os.path.join(dest, f))
                               for f in sorted(os.listdir(dest))) if r]

    if not results:
        print(f"no concrete v4 hook contracts found in {repo}@{ref} "
              f"({n} Solidity file(s) fetched). Hooks declare getHookPermissions() "
              "or inherit BaseHook/IHooks.")
        return 0

    score = score_results(results)
    counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
    for c in results:
        for s, *_ in [(f[0],) for f in c["findings"]]:
            counts[s] += 1

    print(f"\nHookGuard scan — {repo}@{ref}")
    print("=" * 62)
    flagged = 0
    for c in sorted(results, key=lambda c: c['contract']):
        if not c['findings']:
            continue
        flagged += 1
        print(f"\n  {c['contract']}")
        for s, code, msg, ln in sorted(c['findings'], key=lambda f: SEV_ORDER[f[0]]):
            print(f"    [{s:<6}] {code} @{ln}")
    clean = len(results) - flagged
    print("-" * 62)
    print(f"  hooks: {len(results)} · clean: {clean} · "
          f"HIGH {counts['HIGH']} MEDIUM {counts['MEDIUM']} LOW {counts['LOW']} INFO {counts['INFO']}")
    print(f"  risk: {score['score']}/100 {score['band']} (confidence: {score['confidence']})")

    if args.json:
        json.dump({"repo": repo, "ref": ref, "score": score, "results": results},
                  open(args.json, "w"), indent=1)
        print(f"  json -> {args.json}")
    if args.html:
        open(args.html, "w").write(render_html(repo, ref, results, score))
        print(f"  html -> {args.html}")

    fail_ranks = {"INFO": 1, "LOW": 2, "MEDIUM": 3, "HIGH": 4}
    if args.fail_on != "never":
        thresh = fail_ranks[args.fail_on]
        if any(fail_ranks[f[0]] >= thresh for c in results for f in c["findings"]):
            return 1
    return 0


def main():
    ap = argparse.ArgumentParser(prog="hookguard")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="scan a GitHub repository")
    s.add_argument("repo")
    s.add_argument("--branch", default="")
    s.add_argument("--paths", default="")
    s.add_argument("--html", default="")
    s.add_argument("--json", default="")
    s.add_argument("--fail-on", default="never",
                   choices=["HIGH", "MEDIUM", "LOW", "never"])
    args = ap.parse_args()
    sys.exit(cmd_scan(args))


if __name__ == "__main__":
    main()
