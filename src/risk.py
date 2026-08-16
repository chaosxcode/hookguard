#!/usr/bin/env python3
"""
HookGuard — registry risk pass.

Uniswap's official hooklist (486 production hooks, 16 chains) records what a hook
CAN do (permission bits) and some properties, but explicitly disclaims being a
safety signal. This pass turns those declared capabilities into a transparent,
reproducible risk profile: capability x mutability x verifiability.

It is deliberately NOT an audit. It flags where the ecosystem's risk is
concentrated so scarce audit funding can be aimed at it.
"""
import json, sys
from collections import Counter

RAW = json.load(open('data/hooklist.json'))

# Capability weights. Rationale, in order of how directly a bit lets a hook move
# value that isn't its own:
#   RETURNS_DELTA bits let a callback CHANGE token amounts (not just observe) —
#     this is the capability behind fee-siphoning and mispricing bugs.
#   beforeSwap+returnsDelta can absorb the swap entirely (custom curve): highest.
#   liquidity-delta bits can charge/credit the LP on add/remove.
#   plain observe bits are low risk on their own.
CAP = {
    'beforeSwapReturnsDelta':            5,
    'afterSwapReturnsDelta':             4,
    'afterAddLiquidityReturnsDelta':     4,
    'afterRemoveLiquidityReturnsDelta':  4,
    'beforeSwap':                        2,
    'afterSwap':                         1,
    'beforeAddLiquidity':                1,
    'beforeRemoveLiquidity':             1,
    'afterAddLiquidity':                 1,
    'afterRemoveLiquidity':              1,
    'beforeInitialize':                  1,
    'afterInitialize':                   0,
    'beforeDonate':                      0,
    'afterDonate':                       0,
}

def assess(e):
    h, f, p = e['hook'], e['flags'], e['properties']
    caps = [k for k, v in f.items() if v]
    cap_score = sum(CAP.get(k, 0) for k in caps)

    findings = []
    # --- the core compounding risk: mutable code behind an immutable address ---
    if p.get('upgradeable'):
        findings.append(('UPGRADEABLE',
            'Hook address encodes permissions permanently, but implementation code can be swapped. '
            'Pools cannot detach. Admin key is part of the trust boundary.'))
    if not h.get('verifiedSource'):
        findings.append(('UNVERIFIED_SOURCE',
            'Source not verified on the explorer: users and routers cannot review the code they are trusting.'))
    if not h.get('auditUrl'):
        findings.append(('NO_PUBLISHED_AUDIT', 'No audit URL in the registry.'))

    delta_caps = [c for c in caps if 'ReturnsDelta' in c]
    if delta_caps:
        findings.append(('VALUE_MOVING',
            f'Can alter token deltas via {", ".join(delta_caps)} — capability behind fee-siphoning/mispricing classes.'))
    if p.get('dynamicFee'):
        findings.append(('DYNAMIC_FEE', 'Sets swap fee at runtime; unbounded/manipulable fee logic harms LPs and takers.'))

    # compounding: value-moving AND mutable AND unreviewable
    critical = bool(delta_caps) and p.get('upgradeable') and not h.get('auditUrl')
    if critical:
        findings.append(('CRITICAL_COMBO',
            'Value-moving + upgradeable + no published audit: admin can change value-moving logic that no one has reviewed.'))

    risk = cap_score
    if p.get('upgradeable'): risk += 4
    if not h.get('verifiedSource'): risk += 3
    if not h.get('auditUrl'): risk += 2
    if p.get('dynamicFee'): risk += 1

    return {
        'name': h.get('name') or '(unnamed)', 'address': h['address'], 'chain': h.get('chain'),
        'risk': risk, 'caps': caps, 'findings': findings,
        'upgradeable': bool(p.get('upgradeable')), 'audited': bool(h.get('auditUrl')),
        'verified': bool(h.get('verifiedSource')), 'valueMoving': bool(delta_caps), 'critical': critical,
    }

rows = [assess(e) for e in RAW]
rows.sort(key=lambda r: -r['risk'])
n = len(rows)

print(f"HookGuard — risk pass over {n} registered Uniswap v4 hooks\n" + "="*74)
audited   = sum(r['audited'] for r in rows)
verified  = sum(r['verified'] for r in rows)
upgrade   = sum(r['upgradeable'] for r in rows)
valmov    = sum(r['valueMoving'] for r in rows)
crit      = sum(r['critical'] for r in rows)
print(f"  published audit URL : {audited:4d} / {n}  ({audited/n:5.1%})")
print(f"  verified source     : {verified:4d} / {n}  ({verified/n:5.1%})")
print(f"  upgradeable         : {upgrade:4d} / {n}  ({upgrade/n:5.1%})")
print(f"  value-moving (delta): {valmov:4d} / {n}  ({valmov/n:5.1%})")
print(f"  CRITICAL combo      : {crit:4d} / {n}  ({crit/n:5.1%})   <- value-moving + upgradeable + unaudited")

print(f"\n  value-moving AND unaudited     : {sum(r['valueMoving'] and not r['audited'] for r in rows)}")
print(f"  value-moving AND unverified    : {sum(r['valueMoving'] and not r['verified'] for r in rows)}")

print("\n  by chain (count / unaudited):")
bych = Counter(r['chain'] for r in rows)
for c, k in bych.most_common(8):
    ua = sum(1 for r in rows if r['chain'] == c and not r['audited'])
    print(f"    {str(c):<12} {k:4d}  unaudited {ua:4d} ({ua/k:5.1%})")

print("\n  TOP 12 BY RISK SCORE:")
for r in rows[:12]:
    tags = ','.join(t for t,_ in r['findings'] if t in ('CRITICAL_COMBO','VALUE_MOVING','UPGRADEABLE','UNVERIFIED_SOURCE'))
    print(f"    {r['risk']:3d}  {r['name'][:30]:<30} {r['chain']:<9} {r['address'][:10]}…  {tags}")

json.dump(rows, open('out/risk.json','w'), indent=1)
print(f"\n  wrote out/risk.json ({n} hooks scored)")
