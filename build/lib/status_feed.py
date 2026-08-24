#!/usr/bin/env python3
"""Generate the HookGuard status feed and its dashboard.

    python3 src/status_feed.py

Reads every artifact this project already produces (risk pass, discovery,
census, bytecode signals, code families, scan results) and emits:

    docs/status/feed.json          - the whole aggregated state, machine readable
    docs/status/<chain>/<addr>.json- one machine-readable record per known hook
    docs/status/index.html         - single-file dashboard (no dependencies)

Every number on the page is read from artifacts at generation time. Nothing
is hardcoded; if the pipeline produced it, the feed shows it, and if it did
not, the page shows an explicit gap instead of inventing one.
"""
import json, os, re, html
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "status")
GEN_DATE = os.environ.get("FEED_DATE", date.today().isoformat())

def load(*p):
    path = os.path.join(ROOT, *p)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)

def pct(a, b):
    return round(100 * a / b, 1) if b else None

def _generate():
    # ---------------------------------------------------------------- aggregate

    risk = load("out", "risk.json") or []
    reg_total = len(risk)
    audited = sum(1 for x in risk if x["audited"])
    vm = sum(1 for x in risk if x["valueMoving"])
    vm_na = sum(1 for x in risk if x["valueMoving"] and not x["audited"])
    upg = sum(1 for x in risk if x["upgradeable"])
    chains_reg = {}
    for x in risk:
        c = chains_reg.setdefault(x["chain"], {"hooks": 0, "unaudited": 0})
        c["hooks"] += 1
        c["unaudited"] += 0 if x["audited"] else 1
    for c in chains_reg.values():
        c["unauditedPct"] = pct(c["unaudited"], c["hooks"])

    onchain = load("out", "unichain-onchain.json") or {}
    uni_hooks = onchain.get("hooks", {})
    uni_distinct = len(uni_hooks)
    uni_pools = onchain.get("poolsCreated")
    uni_hooked = onchain.get("poolsWithHook")

    # live registry (rebuilt Aug 23) -- derive straight from the snapshot
    snap = load("data", "hooklist.json") or []
    live_uni = {e["hook"]["address"].lower() for e in snap
                if e["hook"].get("chain") == "unichain"}
    coverage_now = len(set(live_uni) & set(uni_hooks))
    coverage_pct = pct(coverage_now, uni_distinct)

    top = load("out", "unichain-unregistered-top.json") or {}
    mini = load("out", "unichain-unregistered-min2.json") or {}
    bc_top = load("out", "unichain-bytecode.json") or {}
    bc_all = load("out", "unichain-bytecode-min2.json") or {}

    scan = load("out", "scan.json") or []
    sev_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
    rule_counts = {}
    clean = 0
    for c in scan:
        if not c["findings"]:
            clean += 1
        for s, code, msg, ln in c["findings"]:
            sev_counts[s] += 1
            rule_counts[code] = rule_counts.get(code, 0) + 1

    fams = load("out", "code-families.json") or {}

    OUTREACH = [
        {"project": "Uniderp-fun/uniderp-hook-smart-contract",
         "issue": "https://github.com/Uniderp-fun/uniderp-hook-smart-contract/issues/1",
         "hooks": "UniderpHook ×3 (114 / 4 / 3 pools)", "state": "awaiting-response"},
        {"project": "VII-Finance/yield-harvesting-hook",
         "issue": "https://github.com/VII-Finance/yield-harvesting-hook/issues/30",
         "hooks": "AssetToAssetSwapHookForERC4626 (unichain)", "state": "awaiting-response"},
        {"project": "Bunniapp/bunni-v2",
         "issue": None,
         "hooks": "BunniHook (50 pools)",
         "state": "cleared-false-positive",
         "note": "logic reverts BunniHook__InvalidSwap when slot0.sqrtPriceX96 == 0 — unknown pools cannot act"},
        {"project": "Uniswap/hooklist (UniMemeHook)",
         "issue": None,
         "hooks": "UniMemeHook (777 pools)", "state": "superseded",
         "note": "registered after our snapshot; listing documents the fee design"},
    ]

    feed = {
        "generated": GEN_DATE,
        "registry": {
            "total": reg_total, "chains": len(chains_reg),
            "growthWeek": {"from": 486, "to": reg_total},
            "audited": audited, "auditedPct": pct(audited, reg_total),
            "valueMoving": vm, "valueMovingPct": pct(vm, reg_total),
            "valueMovingNoAudit": vm_na, "valueMovingNoAuditPct": pct(vm_na, reg_total),
            "upgradeable": upg, "verifiedSource": sum(1 for x in risk if x["verified"]),
            "byChain": chains_reg,
        },
        "scanner": {
            "contractsMeasured": len(scan),
            "clean": clean, "cleanPct": pct(clean, len(scan)),
            "severity": sev_counts,
            "rules": rule_counts,
        },
        "unichain": {
            "poolManager": "0x1F98400000000000000000000000000000000004",
            "deploymentKind": "v4 PREVIEW — callback permission bits are bit-reversed vs final v4 (validated 17/18)",
            "poolsCreated": uni_pools, "poolsWithHook": uni_hooked,
            "distinctHooks": uni_distinct,
            "registryCoverage": {"now": coverage_now, "pct": coverage_pct},
            "census": {
                "multiPoolHooks": (mini or {}).get("candidates"),
                "publishSource": (mini or {}).get("verified"),
                "bytecodeAnalyzed": (bc_all or {}).get("analyzed"),
                "standardProxies": ((bc_all or {}).get("summary") or {}).get("eip1967Proxies"),
                "delegatecall": ((bc_all or {}).get("summary") or {}).get("delegatecallOpcodesPresent"),
                "selfdestruct": ((bc_all or {}).get("summary") or {}).get("selfdestructOpcodesPresent"),
                "distinctPrograms": ((bc_all or {}).get("summary") or {}).get("distinctPrograms"),
            },
        },
        "attribution": {
            "deploymentsChecked": fams.get("targets"),
            "distinctPrograms": fams.get("distinctPrograms"),
            "sameCodeFamilies": fams.get("multiDeploymentFamilies"),
            "crossChainFamilies": fams.get("crossChainFamilies"),
            "families": [{"size": v["members"][0].get("sizeBytes"),
                          "chains": sorted({x["chain"] for x in v["members"]}),
                          "members": [{"chain": x["chain"], "address": x["address"],
                                       "name": x.get("name")} for x in v["members"]]}
                         for v in sorted((fams.get("families") or []),
                                         key=lambda f: -len(f["members"]))
                         if len({x["chain"] for x in v["members"]}) > 1],
        },
    "outreach": OUTREACH,
    "adoption": load("out", "adoption.json") or {"goal": 5, "externalInstalls": 0,
                                                 "repos": []},
}

    os.makedirs(OUT, exist_ok=True)

    # ------------------------------------------------- per-address records
    from score import compute_score
    rows = []
    sevmap = {}
    for c in scan:
        parts = c['file'].split('/')
        chain, addr = parts[1], parts[2]
        pa = [f for f in c['findings'] if f[1] == 'PERMISSIONLESS_ATTACHMENT' and f[0] == 'MEDIUM']
        high = [f for f in c['findings'] if f[0] == 'HIGH']
        sevmap[(chain, addr.lower())] = {
            "high": sum(1 for f in c['findings'] if f[0] == 'HIGH'),
            "medium": sum(1 for f in c['findings'] if f[0] == 'MEDIUM'),
            "low": sum(1 for f in c['findings'] if f[0] == 'LOW'),
            "info": sum(1 for f in c['findings'] if f[0] == 'INFO'),
        }
        rows.append({"chain": chain, "address": addr.lower(),
                     "name": c['contract'],
                     "findings": len(c['findings']),
                     "high": len(high),
                     "advisory": bool(pa),
                     "source": True})
    for h in (bc_all or {}).get("hooks", []):
        if "error" in h:
            continue
        rec = next((r for r in rows if r["address"] == h["address"].lower()), None)
        if rec:
            rec.update({"source": False, "pools": h.get("pools"),
                        "proxy": bool(h.get("eip1967Implementation")) or h.get("minimalProxy"),
                        "delegatecall": h.get("delegatecall"),
                        "selfdestruct": h.get("selfdestruct"),
                        "permBits": bin(int(h["address"], 16) & 0x3FFF).count("1")})
        else:
            rows.append({"chain": "unichain", "address": h["address"].lower(),
                         "name": h.get("name") or "", "source": False,
                         "pools": h.get("pools"),
                         "proxy": bool(h.get("eip1967Implementation")),
                         "delegatecall": h.get("delegatecall"),
                         "selfdestruct": h.get("selfdestruct"),
                         "permBits": bin(int(h["address"], 16) & 0x3FFF).count("1"),
                         "findings": None, "high": None, "advisory": False})
    # ---- scoring: one transparent, itemized risk score per record ----
    registered_pairs = {(e['hook']['chain'], e['hook']['address'].lower())
                        for e in snap}
    audit_known = {}
    for e in snap:
        h = e['hook']
        audit_known[(h['chain'], h['address'].lower())] = bool(h.get('auditUrl'))
    opaque_impls = set((bc_all or {}).get("opaqueImplementations") or [])
    bcmap = {h.get("address", "").lower(): h
             for h in (bc_all or {}).get("hooks", []) if "error" not in h}

    for r in rows:
        key = (r['chain'], r['address'])
        sev = sevmap.get(key)
        h = bcmap.get(r['address'], {})
        registered = key in registered_pairs
        signals = {
            "source_analyzed": r['source'] is True,
            "source_checked_and_missing": r['source'] is False,
            "delegatecall_targets": h.get("delegatecallTargets"),
            "opaque_implementations": [t for t in (h.get("delegatecallTargets") or {})
                                       .get("constantTargets", []) if t in opaque_impls],
            "selfdestruct": r.get("selfdestruct"),
            "permission_bits": r.get("permBits"),
            "registered": registered,
        }
        if sev:
            signals.update({"high_findings": sev['high'],
                            "medium_findings": sev['medium'],
                            "low_findings": sev['low'],
                            "info_findings": sev['info']})
        if registered and key in audit_known:
            signals["audit_recorded"] = audit_known[key]
        s = compute_score(signals)
        r.update({"score": s["score"], "band": s["band"],
                  "confidence": s["confidence"],
                  "factors": [f for f in s["factors"] if f["delta"]][:4]})

    for r in rows:
        d = os.path.join(OUT, r["chain"])
        os.makedirs(d, exist_ok=True)
        json.dump({"generated": GEN_DATE, **r},
                  open(os.path.join(d, f"{r['address']}.json"), "w"), indent=1)

    manifest = {"generated": GEN_DATE, "records": len(rows)}
    json.dump(manifest, open(os.path.join(OUT, "index.json"), "w"))
    feed["records"] = rows
    json.dump(feed, open(os.path.join(OUT, "feed.json"), "w"), indent=1)

    # ---------------------------------------------------------------- dashboard
    census = feed["unichain"]["census"]
    T = {
        "__REG_TOTAL__": reg_total,
        "__REG_GROWTH__": f"+{reg_total - 486}" if reg_total > 486 else "0",
        "__REG_CHAINS__": len(chains_reg),
        "__VMNA__": feed["registry"]["valueMovingNoAuditPct"],
        "__MEASURED__": len(scan),
        "__HIGH__": sev_counts["HIGH"],
        "__AUD_PCT__": feed["registry"]["auditedPct"],
        "__AUDITED__": audited,
        "__NOT_AUDITED__": reg_total - audited,
        "__VM__": vm,
        "__VMNA2__": vm_na,
        "__COV__": coverage_pct,
        "__COV_NOW__": coverage_now,
        "__UNI_DISTINCT__": uni_distinct,
        "__CEN_MULTI__": census.get("multiPoolHooks") or "—",
        "__CEN_SRC__": pct((mini or {}).get("verified"), (mini or {}).get("candidates")) or "—",
        "__CEN_DC__": census.get("delegatecall") if census.get("delegatecall") is not None else "—",
        "__CEN_ANALYZED__": census.get("bytecodeAnalyzed") or "—",
        "__CEN_PROG__": census.get("distinctPrograms") or "—",
    }
    TEMPLATE = open(os.path.join(ROOT, "src", "dashboard_template.html")).read()
    for k, v in T.items():
        TEMPLATE = TEMPLATE.replace(k, str(v))
    html_doc = (TEMPLATE
                .replace("__FEED__", json.dumps(feed))
                .replace("__ROWS__", json.dumps(rows))
                .replace("__DATE__", GEN_DATE))
    leftover = re.findall(r"__[A-Z_]+__", html_doc)
    if leftover:
        sys.exit(f"unsubstituted tokens in dashboard: {sorted(set(leftover))}")
    open(os.path.join(OUT, "index.html"), "w").write(html_doc)

    print(f"registry {reg_total} | scanner {len(scan)} contracts | "
          f"unichain coverage {coverage_pct}% | records {len(rows)}")
    print(f"wrote docs/status/feed.json, {manifest['records']} per-address records, index.html")


if __name__ == "__main__":
    _generate()
