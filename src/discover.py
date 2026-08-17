#!/usr/bin/env python3
"""Discover every hook actually deployed on a v4 chain, by scanning PoolManager
Initialize events across full chain history.

The Uniswap hooklist registry is opt-in, so it records only hooks whose authors
chose to register them. This asks the chain instead: for every pool ever created
on Unichain, which hook contract was attached?

    python3 src/discover_unichain.py        -> out/unichain-onchain.json

Runtime ~2 min against the public RPC (5,600 range queries, 10k blocks each).
"""
import json, os, sys, collections, urllib.request, concurrent.futures

CHAINS = {
    "unichain": ("https://mainnet.unichain.org", "0x1F98400000000000000000000000000000000004"),
    "base":     ("https://mainnet.base.org",     "0x498581fF718922c3f8e6A244956aF099B2652b2b"),
    "ethereum": ("https://eth.llamarpc.com",     "0x000000000004444c5dc75cB358380D2e3dE08A90"),
}
CHAIN = os.environ.get("CHAIN", "unichain")
RPC, PM = CHAINS[CHAIN]
RPC = os.environ.get("RPC_URL", RPC)
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


def fetch(rng, depth=0):
    """Logs for a block range. Bisects when the node refuses an oversized
    response, so busy chains work without guessing a chunk size up front.
    Returns None only if a range genuinely never succeeded."""
    lo, hi = rng
    for _ in range(4):
        try:
            res = rpc("eth_getLogs", [{"address": PM, "fromBlock": hex(lo),
                                       "toBlock": hex(hi), "topics": [TOPIC]}])
            if "result" in res:
                return res["result"]
            msg = str(res.get("error", "")).lower()
            if ("too large" in msg or "too many" in msg or "limit" in msg) and hi > lo and depth < 12:
                mid = (lo + hi) // 2
                a, b = fetch((lo, mid), depth + 1), fetch((mid + 1, hi), depth + 1)
                return None if a is None or b is None else a + b
        except Exception:
            pass
    if hi > lo and depth < 12:
        mid = (lo + hi) // 2
        a, b = fetch((lo, mid), depth + 1), fetch((mid + 1, hi), depth + 1)
        return None if a is None or b is None else a + b
    return None


def has_code(block):
    res = rpc("eth_getCode", [PM, hex(block)])
    if "error" in res:
        raise RuntimeError(res["error"])
    return len(res.get("result", "0x")) > 2


def start_block(latest):
    """First block where the PoolManager has code, so the scan skips the history
    that predates it. On Base that is most of the chain.

    A pruned node answers "no code" for every old block, which would put the
    start far too late and silently undercount -- the one error this script
    exists to avoid. So the guess is verified: the range immediately before it
    must contain zero Initialize events. Anything unexpected falls back to 0,
    which is slower and always correct."""
    try:
        if not has_code(latest):
            sys.exit(f"ABORT: no PoolManager code at {PM} on {CHAIN}")
        if has_code(0):
            return 0
        lo, hi = 0, latest
        while lo < hi:
            mid = (lo + hi) // 2
            if has_code(mid):
                hi = mid
            else:
                lo = mid + 1
    except Exception as e:
        print(f"  could not locate deployment ({type(e).__name__}), scanning from 0", flush=True)
        return 0

    probe_lo = max(0, lo - STEP)
    before = fetch((probe_lo, max(probe_lo, lo - 1)))
    if before is None or before:
        print(f"  deployment probe at {lo:,} did not verify, scanning from 0", flush=True)
        return 0
    return (lo // STEP) * STEP


def main():
    latest = int(rpc("eth_blockNumber", [])["result"], 16)
    first  = start_block(latest)
    ranges = [(b, min(b + STEP - 1, latest)) for b in range(first, latest + 1, STEP)]
    skipped = first // STEP
    print(f"scanning blocks {first:,} -> {latest:,} in {len(ranges)} queries"
          + (f" ({skipped:,} pre-deployment ranges skipped)" if skipped else ""), flush=True)

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
                      if h["chain"] == CHAIN}
    onchain = {a.lower() for a in hooks}
    unregistered = onchain - registered

    multi = {a: v for a, v in hooks.items() if v["pools"] >= 2}
    dist = collections.Counter(v["pools"] for v in hooks.values())

    out = {
        "chain": CHAIN, "poolManager": PM, "scannedToBlock": latest,
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
    dest = os.path.join(ROOT, "out", f"{CHAIN}-onchain.json")
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
