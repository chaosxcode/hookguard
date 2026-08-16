#!/usr/bin/env python3
"""Discover every hook actually deployed on Unichain, by scanning PoolManager
Initialize events across full chain history.

The Uniswap hooklist registry is opt-in, so it records only hooks whose authors
chose to register them. This asks the chain instead: for every pool ever created
on Unichain, which hook contract was attached?

    python3 src/discover_unichain.py        -> out/unichain-onchain.json

Runtime ~2 min against the public RPC (5,600 range queries, 10k blocks each).
"""
import json, os, sys, collections, urllib.request, concurrent.futures

RPC   = os.environ.get("UNICHAIN_RPC", "https://mainnet.unichain.org")
PM    = "0x1F98400000000000000000000000000000000004"   # Unichain PoolManager
# keccak("Initialize(bytes32,address,address,uint24,int24,address,uint160,int24)")
TOPIC = "0xdd466e674ea557f56295e2d0218a125ea4b4f0f6f3307b95f85e6110838d6438"
STEP  = 10_000                                          # public RPC range cap
HDRS  = {"Content-Type": "application/json", "User-Agent": "curl/8.5.0", "Accept": "*/*"}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rpc(method, params):
    req = urllib.request.Request(RPC, method="POST", headers=HDRS,
        data=json.dumps({"jsonrpc": "2.0", "id": 1,
                         "method": method, "params": params}).encode())
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def fetch(rng):
    """Return logs for a block range, or None if it never succeeded."""
    for _ in range(4):
        try:
            res = rpc("eth_getLogs", [{"address": PM, "fromBlock": hex(rng[0]),
                                       "toBlock": hex(rng[1]), "topics": [TOPIC]}])
            if "result" in res:
                return res["result"]
        except Exception:
            pass
    return None


def main():
    latest = int(rpc("eth_blockNumber", [])["result"], 16)
    ranges = [(b, min(b + STEP - 1, latest)) for b in range(0, latest + 1, STEP)]
    print(f"scanning blocks 0 -> {latest:,} in {len(ranges)} queries", flush=True)

    logs, failed, done = [], 0, 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for out in ex.map(fetch, ranges):
            done += 1
            if out is None:
                failed += 1
            else:
                logs.extend(out)
            if done % 1000 == 0:
                print(f"  {done}/{len(ranges)}  {len(logs)} events  {failed} failed", flush=True)

    if failed:
        # Partial coverage would silently understate the hook count, which is the
        # one number this whole thing exists to report. Refuse to publish it.
        print(f"\nABORT: {failed}/{len(ranges)} ranges never succeeded. "
              f"Result would undercount. Re-run.", file=sys.stderr)
        sys.exit(1)

    # Initialize data words: 0=fee 1=tickSpacing 2=hooks 3=sqrtPriceX96 4=tick
    hooks, hookless = {}, 0
    for lg in logs:
        d = lg["data"][2:]
        addr = "0x" + d[128:192][-40:]
        if int(addr, 16) == 0:
            hookless += 1
            continue
        e = hooks.setdefault(addr, {"pools": 0, "firstBlock": None})
        e["pools"] += 1
        bn = int(lg["blockNumber"], 16)
        if e["firstBlock"] is None or bn < e["firstBlock"]:
            e["firstBlock"] = bn

    # Cross-reference the registry
    risk = os.path.join(ROOT, "out", "risk.json")
    registered = set()
    if os.path.exists(risk):
        registered = {h["address"].lower() for h in json.load(open(risk))
                      if h["chain"] == "unichain"}
    onchain = {a.lower() for a in hooks}
    unregistered = onchain - registered

    multi = {a: v for a, v in hooks.items() if v["pools"] >= 2}
    dist = collections.Counter(v["pools"] for v in hooks.values())

    out = {
        "chain": "unichain", "poolManager": PM, "scannedToBlock": latest,
        "poolsCreated": len(logs), "poolsWithHook": len(logs) - hookless,
        "poolsWithoutHook": hookless,
        "distinctHooks": len(hooks),
        "registryHooks": len(registered),
        "registryHooksSeenOnchain": len(registered & onchain),
        "unregisteredHooks": len(unregistered),
        "registryCoveragePct": round(len(registered & onchain) / len(onchain) * 100, 2),
        "hooksServingOnePool": dist[1],
        "hooksServingMultiplePools": len(multi),
        "hooksServingTenPlusPools": sum(1 for v in hooks.values() if v["pools"] >= 10),
        "hooks": hooks,
    }
    dest = os.path.join(ROOT, "out", "unichain-onchain.json")
    json.dump(out, open(dest, "w"), indent=1)

    print(f"\n  pools created            {out['poolsCreated']:,}")
    print(f"  pools using a hook       {out['poolsWithHook']:,}")
    print(f"  distinct hooks onchain   {out['distinctHooks']:,}")
    print(f"  in Uniswap's registry    {out['registryHooksSeenOnchain']}")
    print(f"  registry coverage        {out['registryCoveragePct']}%")
    print(f"  serving 2+ pools         {out['hooksServingMultiplePools']:,}")
    print(f"  serving 10+ pools        {out['hooksServingTenPlusPools']}")
    print(f"\n  wrote {dest}")


if __name__ == "__main__":
    main()
