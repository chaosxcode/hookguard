#!/usr/bin/env python3
"""The HookGuard scoring engine: turn every signal we compute into one
transparent, defensible risk score per hook.

    python3 src/score.py     # standalone demo over current artifacts

Design rules, in order of importance:

1.  NOTHING IS HIDDEN. Every point comes with a label and a reason; the
    breakdown ships next to the score everywhere the score appears.
2.  ONLY FACTS MOVE THE NUMBER. No deductions for absence of evidence. An
    unaudited hook is not a dangerous hook -- it is a hook whose audit status
    is unknown, and unknown costs less than proven-bad.
3.  CONFIDENCE TRAVELS WITH SCORE. A score built from full source analysis is
    not comparable to one inferred from bytecode alone. Both carry a
    confidence tier; consumers must read both.
4.  AUTHOR RESPONSES REWRITE HISTORY. A confirmed-intended pattern reduces
    the score it contributed to; a false positive is removed outright. The
    ledger feeds the engine.

Weight table (each entry justified in one line):

  +25  no published source          -- nothing else can be checked; opacity itself
  +20  delegates to OPAQUE impl     -- logic lives in unreadable code (bytecode v2)
  +15  storage-derived delegatecall -- live-upgradeable in practice
  +12  standard proxy pattern       -- EIP-1967/EIP-1167; upgrade surface exists
   +5  SELFDESTRUCT opcode          -- capability present in runtime code
   +5  maximum permission surface   -- all 14 address flags set
  +15  per HIGH source finding      -- demonstrated broken invariant claims
   +7  per MEDIUM finding           -- accurate detection, unproven consequence
   +3  per LOW finding              -- minor
   +1  per INFO                     -- informational
  +10  no audit URL recorded        -- weak signal; means "unknown", priced cheap
   +8  absent from the registry     -- opt-in transparency signal not exercised
  -12  author confirms pattern intended -- strongest evidence there is

Bands: 0-24 LOW · 25-49 MODERATE · 50-74 ELEVATED · 75-100 HIGH risk.
Confidence: high (source + bytecode), medium (one layer), low (sparse).
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WEIGHTS = {
    "no_source":            25,
    "opaque_implementation": 20,
    "storage_upgradeable":  15,
    "standard_proxy":       12,
    "selfdestruct":          5,
    "max_permissions":       5,
    "high_finding":         15,
    "medium_finding":        7,
    "low_finding":           3,
    "info_finding":          1,
    "no_audit_recorded":    10,
    "unregistered":          8,
}
CONFIRM_INTENDED = -12

BANDS = [(24, "LOW"), (49, "MODERATE"), (74, "ELEVATED"), (100, "HIGH")]


def band(score):
    for cap, name in BANDS:
        if score <= cap:
            return name
    return "HIGH"


def compute_score(signals):
    """signals: dict of facts -> value. Returns {score, band, confidence,
    factors:[{key,label,delta,detail}], data_layers}.

    Unknown keys are ignored; missing facts simply contribute nothing --
    rule 2 above. Callers should pass only what was actually measured."""
    score = 0
    factors = []

    def add(key, label, delta, detail):
        nonlocal score
        score += delta
        factors.append({"key": key, "label": label,
                        "delta": delta, "detail": detail})

    layers = set()
    if signals.get("source_analyzed"):
        layers.add("source")
        n_h = signals.get("high_findings", 0)
        n_m = signals.get("medium_findings", 0)
        n_l = signals.get("low_findings", 0)
        n_i = signals.get("info_findings", 0)
        if n_h: add("high_finding", f"{n_h}× HIGH finding(s)", WEIGHTS["high_finding"]*n_h,
                    "demonstrated invariant breaks from source analysis")
        if n_m: add("medium_finding", f"{n_m}× MEDIUM finding(s)", WEIGHTS["medium_finding"]*n_m,
                    "accurate detections awaiting author confirmation")
        if n_l: add("low_finding", f"{n_l}× LOW finding(s)", WEIGHTS["low_finding"]*n_l, "")
        if n_i: add("info_finding", f"{n_i}× informational", WEIGHTS["info_finding"]*n_i, "")
    elif signals.get("source_checked_and_missing"):
        layers.add("bytecode")
        add("no_source", "no published source",
            WEIGHTS["no_source"],
            "nothing at source level can be checked; opacity priced, not guilt")

    dt = signals.get("delegatecall_targets") or {}
    kind = dt.get("kind")
    opaque_impls = signals.get("opaque_implementations") or []
    if kind == "constant":
        layers.add("bytecode")
        if opaque_impls:
            add("opaque_implementation", "fixed delegation to unreadable implementation",
                WEIGHTS["opaque_implementation"],
                ", ".join(opaque_impls[:2]) + ("…" if len(opaque_impls) > 2 else ""))
        else:
            add("standard_proxy", "delegates to implementation",
                WEIGHTS["standard_proxy"], "target appears readable")
    elif kind == "storage-derived":
        layers.add("bytecode")
        add("storage_upgradeable", "storage-derived delegatecall target",
            WEIGHTS["storage_upgradeable"], "upgradeable in practice")

    if signals.get("selfdestruct"):
        layers.add("bytecode")
        add("selfdestruct", "SELFDESTRUCT capability present",
            WEIGHTS["selfdestruct"], "opcode-level fact")

    bits = signals.get("permission_bits")
    if bits is not None and bits >= 14:
        layers.add("address")
        add("max_permissions", "maximum permission surface",
            WEIGHTS["max_permissions"], "all 14 address flags set")

    if signals.get("registered") is False:
        add("unregistered", "absent from the hooklist registry",
            WEIGHTS["unregistered"], "opt-in transparency signal not exercised")
    if signals.get("audit_recorded") is False:
        add("no_audit_recorded", "no audit URL recorded",
            WEIGHTS["no_audit_recorded"], "means unknown, not audited-absent")

    if signals.get("author_confirmed_intended"):
        add("author_confirmed", "author confirms pattern intended",
            CONFIRM_INTENDED, "recorded in public ledger")

    score = max(0, min(100, score))
    conf = ("high" if {"source", "bytecode"} <= layers else
            "medium" if layers else "low")
    return {"score": score, "band": band(score),
            "confidence": conf,
            "dataLayers": sorted(layers),
            "factors": sorted(factors, key=lambda f: -abs(f["delta"]))}


def _demo():
    """Score everything we know, print the top of the risk table."""
    sys.path.insert(0, os.path.join(ROOT, "src"))
    from status_feed import load                                  # noqa: E402
    scan = {(c['file'].split('/')[1], c['file'].split('/')[2]): c
            for c in (load("out", "scan.json") or [])}
    bc_all = load("out", "unichain-bytecode-min2.json") or {}
    snap = load("data", "hooklist.json") or []
    registered = {(e['hook']['chain'], e['hook']['address'].lower())
                  for e in snap}

    results = []
    for (chain, addr), c in scan.items():
        highs = sum(1 for f in c['findings'] if f[0] == 'HIGH')
        meds = sum(1 for f in c['findings'] if f[0] == 'MEDIUM')
        lows = sum(1 for f in c['findings'] if f[0] == 'LOW')
        infos = sum(1 for f in c['findings'] if f[0] == 'INFO')
        s = compute_score({
            "source_analyzed": True,
            "high_findings": highs, "medium_findings": meds,
            "low_findings": lows, "info_findings": infos,
            "registered": (chain, addr.lower()) in registered,
        })
        s.update({"chain": chain, "address": addr, "name": c['contract']})
        results.append(s)

    for h in (bc_all.get("hooks") or []):
        if "error" in h or "codeHash" not in h:
            continue
        addr = h["address"].lower()
        if any(r["address"] == addr for r in results):
            continue                                   # source layer already scored
        dt = h.get("delegatecallTargets") or {}
        opaque = dt.get("constantTargets", []) if dt.get("kind") == "constant" else []
        s = compute_score({
            "source_checked_and_missing": True,
            "delegatecall_targets": dt,
            "opaque_implementations": opaque,
            "selfdestruct": h.get("selfdestruct"),
            "permission_bits": bin(int(h["address"], 16) & 0x3FFF).count("1"),
            "registered": ("unichain", addr) in registered,
        })
        s.update({"chain": "unichain", "address": addr, "name": h.get("name") or ""})
        results.append(s)

    results.sort(key=lambda r: (-r["score"], r["address"]))
    json.dump(results, open(os.path.join(ROOT, "out", "scores.json"), "w"), indent=1)

    print(f"scored {len(results)} hooks -> out/scores.json\n")
    dist = {}
    for r in results:
        dist[r["band"]] = dist.get(r["band"], 0) + 1
    print("  bands:", "  ".join(f"{k} {v}" for k, v in sorted(dist.items())))
    print(f"\n  {'band':9s} {'conf':6s} {'pts':>4}  hook")
    for r in results[:18]:
        print(f"  {r['band']:9s} {r['confidence']:6s} {r['score']:>4}  "
              f"{(r['name'] or '')[:30]:30s} {r['chain']}:{r['address'][:10]}")


if __name__ == "__main__":
    _demo()
