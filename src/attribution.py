#!/usr/bin/env python3
"""Attribute anonymous hook deployments by their runtime code.

The same compiled program is frequently deployed to several chains under
different addresses. Where one instance has verified source (or a known repo),
every byte-identical twin is attributed too -- no matter how anonymous its own
address looks. This turns "unattributed launchpad clone" into "same program as
<X>, which we can talk to".

    python3 src/attribution.py     -> out/code-families.json

Scope: contracts the scanner flagged PERMISSIONLESS_ATTACHMENT (MEDIUM) -- the
outreach cohort. RPCs are public and best-effort per chain; a chain that fails
is recorded, never silently dropped.
"""
import json, os, sys, collections, urllib.request, concurrent.futures

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bytecode import keccak256, _real_opcodes               # noqa: E402

RPCS = {
    "unichain":  "https://mainnet.unichain.org",
    "base":      "https://mainnet.base.org",
    "ethereum":  "https://eth.drpc.org",
    "arbitrum":  "https://arb1.arbitrum.io/rpc",
    "optimism":  "https://mainnet.optimism.io",
    "polygon":   "https://polygon-rpc.com",
    "bnb":       "https://bsc-dataseed.binance.org",
    "avalanche": "https://api.avax.network/ext/bc/C/rpc",
    "celo":      "https://forno.celo.org",
    "blast":     "https://rpc.blast.io",
    "zora":      "https://rpc.zora.energy",
    "worldchain":"https://worldchain-mainnet.g.alchemy.com/public",
    "soneium":   "https://rpc.soneium.org",
    "xlayer":    "https://xlayerrpc.okx.com",
    "monad":     "https://rpc.monad.xyz",
    "robinhood": "https://rpc.robinhoodchain.com",
}
HDRS = {"Content-Type": "application/json", "User-Agent": "curl/8.5.0"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_code(chain, addr):
    req = urllib.request.Request(RPCS[chain], method="POST", headers=HDRS,
        data=json.dumps({"jsonrpc": "2.0", "id": 1,
                         "method": "eth_getCode",
                         "params": [addr, "latest"]}).encode())
    res = json.loads(urllib.request.urlopen(req, timeout=45).read())
    return res.get("result", "0x")


def main():
    scan = json.load(open(os.path.join(ROOT, "out", "scan.json")))
    targets = {}
    for c in scan:
        if not any(f[1] == 'PERMISSIONLESS_ATTACHMENT' and f[0] == 'MEDIUM'
                   for f in c['findings']):
            continue
        # file layout: corpus/<chain>/<addr>/<File>.sol ; keep first addr seen
        parts = c['file'].split('/')
        chain, addr = parts[1], parts[2]
        targets.setdefault((chain, addr.lower()),
                           {'name': c['contract'], 'contract': c['contract']})

    print(f"fetching runtime code for {len(targets)} flagged deployments "
          f"across {len({c for c, _ in targets})} chains\n")

    rows = []

    def work(key):
        chain, addr = key
        try:
            code = get_code(chain, addr)
            b = bytes.fromhex(code[2:]) if len(code) > 2 else b""
            return {'chain': chain, 'address': addr,
                    'name': targets[key]['contract'],
                    'codeHash': keccak256(b).hex() if b else None,
                    'sizeBytes': len(b),
                    'error': None if b else 'no-code'}
        except Exception as e:                              # noqa: BLE001
            return {'chain': chain, 'address': addr,
                    'name': targets[key]['contract'],
                    'codeHash': None, 'sizeBytes': None,
                    'error': f"{type(e).__name__}: {str(e)[:80]}"}

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        for r in ex.map(work, list(targets)):
            rows.append(r)
            mark = r['error'] or f"{r['sizeBytes']}B"
            print(f"  {r['chain']:10s} {r['address'][:12]} {mark}")

    ok = [r for r in rows if r['codeHash']]
    fams = collections.defaultdict(list)
    for r in ok:
        fams[r['codeHash']].append(r)
    multi = {h: v for h, v in fams.items() if len(v) > 1}
    crosschain = {h: v for h, v in multi.items()
                  if len({x['chain'] for x in v}) > 1}

    # A family member whose source sits in the corpus attributes the rest.
    corpus = json.load(open(os.path.join(ROOT, "corpus", "index.json")))
    have_source = {(x['chain'], x['address'].lower()) for x in corpus
                   if x.get('status') == 'ok'}

    out = {
        "targets": len(targets), "fetched": len(ok),
        "errors": len(rows) - len(ok),
        "distinctPrograms": len(fams),
        "multiDeploymentFamilies": len(multi),
        "crossChainFamilies": len(crosschain),
        "chainsFailed": sorted({r['chain'] for r in rows if r['error']}),
        "families": [{"codeHash": h, "members": v} for h, v in
                     sorted(multi.items(), key=lambda kv: -len(kv[1]))],
    }
    dest = os.path.join(ROOT, "out", "code-families.json")
    json.dump(out, open(dest, "w"), indent=1)

    print(f"\n  distinct programs        {len(fams)} across {len(ok)} deployments")
    print(f"  same-code families       {len(multi)}")
    print(f"  spanning 2+ chains       {len(crosschain)}")
    for h, v in sorted(crosschain.items(), key=lambda kv: -len(kv[1])):
        named = next((x for x in v if (x['chain'], x['address']) in have_source), None)
        tag = f"  <- source known: {named['name']} ({named['chain']})" if named else ""
        print(f"    {len(v)}x {v[0]['sizeBytes']}B : "
              + ", ".join(sorted({x['chain'] for x in v})) + tag)
    print(f"\n  wrote {os.path.relpath(dest, ROOT)}")


if __name__ == "__main__":
    main()
