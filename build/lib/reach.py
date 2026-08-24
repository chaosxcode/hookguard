#!/usr/bin/env python3
"""Measure external adoption of chaosxcode/hookguard@v1.

    python3 src/reach.py     -> out/adoption.json

Searches public GitHub for workflow files referencing the action, excludes
everything under the chaosxcode org (our own repos and CI runs do not count),
and reports progress against the stated goal: 3-5 unrelated hook projects
installing it. Public data only; nothing here is self-reported.
"""
import json, os, subprocess, sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOAL = 5


def sh(*args):
    r = subprocess.run(args, capture_output=True, text=True)
    return r.stdout


def main():
    out = sh("gh", "search", "code", '"chaosxcode/hookguard@v1"',
             "--limit", "50", "--json", "repository,path")
    hits = json.loads(out) if out.strip() else []
    seen, repos = set(), []
    own = 0
    for h in hits:
        repo = h["repository"]["nameWithOwner"]
        if not h["path"].startswith(".github/workflows/"):
            continue
        if repo.lower().startswith("chaosxcode/"):
            own += 1
            continue
        if repo in seen:
            continue
        seen.add(repo)
        repos.append({"repo": repo, "path": h["path"]})

    data = {
        "schemaVersion": 1,
        "label": "external installs",
        "message": f"{len(repos)} of {GOAL}",
        "color": "brightgreen" if len(repos) >= 3 else ("orange" if len(repos) else "inactive"),
        "searchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "goal": GOAL,
        "externalInstalls": len(repos),
        "ownReferences": own,
        "repos": repos,
        "method": 'GitHub code search: ".github/workflows/" files referencing chaosxcode/hookguard@v1',
    }
    dest = os.path.join(ROOT, "out", "adoption.json")
    json.dump(data, open(dest, "w"), indent=1)
    print(f"external installs: {len(repos)}/{GOAL} goal "
          f"(+{own} own-repo references excluded)")
    for r in repos:
        print(f"  {r['repo']}")
    print(f"wrote {os.path.relpath(dest, ROOT)}")
    return data


if __name__ == "__main__":
    main()
