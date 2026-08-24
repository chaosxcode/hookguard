#!/usr/bin/env python3
"""Proactive outreach scanner: run HookGuard against candidate repositories.

    python3 src/sweep.py candidates.json [--max-files 12] [--outdir /tmp/sweep]

candidates.json: JSON array of "owner/repo" strings.
Writes <outdir>/summary.json with per-repo scan results for drafting
advisories (findings) or clean-bill invites (none). Posting is manual and
deliberate — this tool only measures.
"""
import argparse, base64, json, os, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scan as scanner                                     # noqa: E402


def gh(*args):
    return subprocess.run(["gh", "api", *args], capture_output=True, text=True)


def tree_sol(repo):
    r = gh("api", f"repos/{repo}/git/trees/HEAD?recursive=1", "--jq", ".tree[].path")
    skip = ("test", "mock", "lib/", "node_modules", "script", "out/", "audit")
    return [p for p in r.stdout.splitlines()
            if p.endswith(".sol") and not any(s in p.lower() for s in skip)]


def fetch(repo, path):
    r = gh("api", f"repos/{repo}/contents/{path}", "--jq", ".content")
    if r.returncode != 0:
        return None
    import base64
    try:
        return base64.b64decode(r.stdout)
    except Exception:                                       # noqa: BLE001
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates", help="JSON file with [owner/repo, ...]")
    ap.add_argument("--max-files", type=int, default=12)
    ap.add_argument("--outdir", default="/tmp/hookguard-sweep")
    a = ap.parse_args()

    repos = json.load(open(a.candidates))
    shutil.rmtree(a.outdir, ignore_errors=True)
    os.makedirs(a.outdir, exist_ok=True)

    summary = []
    for repo in repos:
        d = os.path.join(a.outdir, repo.replace("/", "__"))
        os.makedirs(d, exist_ok=True)
        try:
            sols = tree_sol(repo)[: a.max_files]
        except Exception as e:                              # noqa: BLE001
            summary.append({"repo": repo, "error": str(e)[:80]})
            print(f"{repo:42s} tree-fail {str(e)[:40]}")
            continue
        fetched = 0
        for p in sols:
            blob = fetch(repo, p)
            if blob:
                open(os.path.join(d, p.replace("/", "__")), "wb").write(blob)
                fetched += 1
        results = [r for r in (scanner.analyze(os.path.join(d, f))
                               for f in sorted(os.listdir(d))) if r]
        findings = [(r['contract'], s, code, ln)
                    for r in results for s, code, msg, ln in r['findings']]
        entry = {"repo": repo, "files": fetched, "hooks": len(results),
                 "high": sum(1 for f in findings if f[1] == 'HIGH'),
                 "findings": [{"contract": c, "sev": s, "rule": code,
                               "line": ln} for c, s, code, ln in findings]}
        summary.append(entry)
        print(f"{repo:42s} files={fetched} hooks={len(results)} "
              f"findings={len(findings)} (HIGH {entry['high']})")

    dest = os.path.join(a.outdir, "summary.json")
    json.dump(summary, open(dest, "w"), indent=1)
    clean = [s['repo'] for s in summary if s.get('hooks') and not s.get('findings')]
    flagged = [s['repo'] for s in summary if s.get('findings')]
    print(f"\nclean: {len(clean)} | flagged: {len(flagged)} | wrote {dest}")


if __name__ == "__main__":
    main()
