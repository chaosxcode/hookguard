#!/usr/bin/env python3
"""HookGuard CI entrypoint — runs the source scan and reports into GitHub.

Emits inline annotations on the offending lines, writes a job summary, and
(optionally) maintains a single PR comment that is edited in place rather than
re-posted, so a long-lived PR doesn't accumulate a wall of bot noise.

Exit code is controlled by --fail-on. Default is HIGH: a HIGH finding fails the
check, everything else is advisory. HookGuard is a heuristic, not an audit, so
failing a build on a MEDIUM would be overreach.

    python3 src/ci.py src --fail-on HIGH
"""
import argparse, json, os, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scan  # noqa: E402

# GitHub annotation levels. LOW/INFO deliberately map to notice: they are
# context, and a scanner that shouts about context gets muted.
LEVEL = {"HIGH": "error", "MEDIUM": "warning", "LOW": "notice", "INFO": "notice"}
ORDER = ["HIGH", "MEDIUM", "LOW", "INFO"]

DOCS = "https://github.com/chaosxcode/hookguard#what-it-checks"


def esc(s):
    """GitHub workflow-command escaping for annotation message bodies."""
    return s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def collect(paths):
    import glob
    files = []
    for p in paths:
        if os.path.isdir(p):
            files += glob.glob(os.path.join(p, "**", "*.sol"), recursive=True)
        elif p.endswith(".sol"):
            files.append(p)
    return [r for r in (scan.analyze(f) for f in sorted(set(files))) if r]


def rel(path):
    try:
        return os.path.relpath(path, os.environ.get("GITHUB_WORKSPACE", os.getcwd()))
    except ValueError:
        return path


def annotate(results):
    for r in results:
        for f in r["findings"]:
            sev, code, msg = f[0], f[1], f[2]
            line = f[3] if len(f) > 3 else 1
            print(f"::{LEVEL[sev]} file={rel(r['file'])},line={line},"
                  f"title=HookGuard {sev}: {code}::{esc(msg)}")


def summarise(results):
    counts = {k: 0 for k in ORDER}
    for r in results:
        for f in r["findings"]:
            counts[f[0]] += 1
    return counts


def markdown(results, counts, scanned):
    L = ["## HookGuard", ""]
    if not scanned:
        L += ["No Uniswap v4 hook contracts found in the scanned paths.", ""]
        return "\n".join(L)

    total = sum(counts.values())
    if total == 0:
        L += [f"Scanned **{scanned}** hook contract(s). No risk patterns matched.", ""]
    else:
        L += [f"Scanned **{scanned}** hook contract(s) — "
              + ", ".join(f"**{counts[k]}** {k}" for k in ORDER if counts[k]) + ".", ""]
        L += ["| Severity | Rule | Contract | Line | Mechanism |",
              "|---|---|---|---:|---|"]
        rank = {k: i for i, k in enumerate(ORDER)}
        rows = []
        for r in results:
            for f in r["findings"]:
                rows.append((rank[f[0]], f, r))
        for _, f, r in sorted(rows, key=lambda x: x[0]):
            sev, code, msg = f[0], f[1], f[2]
            line = f[3] if len(f) > 3 else 1
            body = msg.replace("|", "\\|")
            if len(body) > 240:
                body = body[:237] + "..."
            L.append(f"| {sev} | `{code}` | `{r['contract']}` | {line} | {body} |")
        L.append("")

    L += ["<sub>HookGuard is a heuristic pattern scanner, **not an audit**. A finding "
          "means *worth a look*, never *vulnerable*; no findings means nothing matched "
          f"at this layer, never *safe*. [What each rule checks]({DOCS})</sub>"]
    return "\n".join(L)


def gh(method, url, token, payload=None):
    req = urllib.request.Request(
        url, method=method,
        data=json.dumps(payload).encode() if payload else None,
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json",
                 "User-Agent": "hookguard-action"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read() or b"{}")


MARKER = "<!-- hookguard-report -->"


def upsert_comment(body):
    """Keep exactly one HookGuard comment per PR, edited in place."""
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    ev = os.environ.get("GITHUB_EVENT_PATH")
    if not (token and repo and ev and os.path.exists(ev)):
        return
    try:
        event = json.load(open(ev))
        pr = (event.get("pull_request") or {}).get("number") or (event.get("issue") or {}).get("number")
        if not pr:
            return
        body = MARKER + "\n" + body
        base = f"https://api.github.com/repos/{repo}/issues"
        existing = gh("GET", f"{base}/{pr}/comments?per_page=100", token)
        mine = next((c for c in existing
                     if MARKER in (c.get("body") or "")
                     and (c.get("user") or {}).get("type") == "Bot"), None)
        if mine:
            gh("PATCH", f"https://api.github.com/repos/{repo}/issues/comments/{mine['id']}",
               token, {"body": body})
        else:
            gh("POST", f"{base}/{pr}/comments", token, {"body": body})
    except Exception as e:
        # Never fail the build because commenting failed — permissions vary
        # (forks get a read-only token) and the annotations already landed.
        print(f"::notice::HookGuard could not post a PR comment ({e}). "
              f"Findings are in the annotations and job summary.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", default=["src"])
    ap.add_argument("--fail-on", default="HIGH",
                    choices=["HIGH", "MEDIUM", "LOW", "never"])
    ap.add_argument("--comment", default="true")
    ap.add_argument("--json-out", default="")
    a = ap.parse_args()
    paths = a.paths or ["src"]

    results = collect(paths)
    counts = summarise(results)
    annotate(results)

    md = markdown(results, counts, len(results))
    print("\n" + md.replace("<sub>", "").replace("</sub>", "") + "\n")

    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(md + "\n")

    if a.json_out:
        os.makedirs(os.path.dirname(a.json_out) or ".", exist_ok=True)
        json.dump(results, open(a.json_out, "w"), indent=1)

    # Expose counts as step outputs so downstream steps can branch on them.
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
            fh.write(f"high={counts['HIGH']}\n")
            fh.write(f"total={sum(counts.values())}\n")
            fh.write(f"contracts={len(results)}\n")

    if a.comment.lower() == "true":
        upsert_comment(md)

    if a.fail_on != "never":
        threshold = ORDER.index(a.fail_on)
        tripped = sum(counts[k] for k in ORDER[:threshold + 1])
        if tripped:
            print(f"::error::HookGuard: {tripped} finding(s) at or above {a.fail_on}.")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
