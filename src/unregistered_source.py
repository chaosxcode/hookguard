#!/usr/bin/env python3
"""Fetch published source for UNREGISTERED hooks that serve many live pools.

Registry coverage on Unichain measured 1.24%: the hooklist sees almost nothing
of what is actually deployed. The hooks outside it are also mostly unverified
-- but five of the busiest thirty DO publish source. Those are production hooks
sitting in the swap path of hundreds of pools, and a source-level scanner has
never been pointed at them. This pulls what they publish into the same corpus
layout src/scan.py reads, and follows verified proxies to their implementation:
the proxy's address fixes the permissions forever, but the logic that has to be
reviewed lives behind it.

    python3 src/unregistered_source.py      -> corpus/<chain>/<addr>/*.sol

Keyless Blockscout only, same rule as verify_status.py: reproducible with a
clone and no signup. A lookup error aborts rather than quietly shrinking the
set -- these five are the whole population this script claims to cover.
"""
import json, os, sys, time, urllib.request, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from corpus import HDRS, write_bundle                     # noqa: E402
from discover import CHAINS                               # noqa: E402

EXPLORER = {
    "unichain": "https://unichain.blockscout.com",
}
CHAIN   = os.environ.get("CHAIN", "unichain")
MINPOOL = int(os.environ.get("MIN_POOLS", "10"))
ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# keccak256("eip1967.proxy.implementation") - 1
EIP1967_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"


def get_json(url):
    req = urllib.request.Request(url, headers=HDRS)
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.load(r)


def eip1967_implementation(addr):
    """Read the standard proxy storage slot over the chain's public RPC.

    Explorers often leave `implementations` empty even for textbook EIP-1967
    proxies (PrediXHookProxyV2 is one), so ask the chain instead."""
    rpc = CHAINS[CHAIN][0]
    payload = json.dumps({"jsonrpc": "2.0", "id": 1,
                          "method": "eth_getStorageAt",
                          "params": [addr, EIP1967_SLOT, "latest"]}).encode()
    req = urllib.request.Request(rpc, method="POST",
                                 headers={"Content-Type": "application/json",
                                          **{k: v for k, v in HDRS.items()
                                             if k != "Accept"}},
                                 data=payload)
    val = json.loads(urllib.request.urlopen(req, timeout=30).read()).get("result", "0x0")
    return "0x" + val[-40:] if int(val or "0x0", 16) else None


def contract_source(addr):
    """(name, {path: content}, implementations) for one address."""
    body = get_json(f"{EXPLORER[CHAIN]}/api/v2/smart-contracts/{addr}")
    if not body.get("is_verified"):
        return body.get("name"), {}, []
    files = {}
    if body.get("source_code"):
        files[body.get("file_path") or "Main.sol"] = body["source_code"]
    for s in body.get("additional_sources") or []:
        if s.get("content"):
            files[s.get("file_path") or "Extra.sol"] = s["content"]
    impls = [(i.get("address"), i.get("name"))
             for i in (body.get("implementations") or []) if i.get("address")]
    return body.get("name"), files, impls


def main():
    if CHAIN not in EXPLORER:
        sys.exit(f"no keyless explorer configured for {CHAIN}")

    top_path = os.path.join(ROOT, "out", f"{CHAIN}-unregistered-top.json")
    if not os.path.exists(top_path):
        sys.exit("missing out/{c}-unregistered-top.json -- run src/verify_status.py first")
    rows = [r for r in json.load(open(top_path))["hooks"]
            if r["verified"] and r["pools"] >= MINPOOL]
    print(f"{CHAIN}: fetching source for {len(rows)} unregistered hooks "
          f"serving {MINPOOL}+ pools\n")

    idx_path = os.path.join(ROOT, "corpus", "index.json")
    try:
        index = {(r["chain"], r["address"].lower()): r
                 for r in json.load(open(idx_path))}
    except Exception:
        index = {}

    def remember(rec):
        index[(rec["chain"], rec["address"].lower())] = rec

    errors = 0
    for r in rows:
        addr = r["address"]
        dest = os.path.join(ROOT, "corpus", CHAIN, addr.lower())
        try:
            name, files, impls = contract_source(addr)
            err = None
        except Exception as e:                              # noqa: BLE001
            name, files, impls, err = None, {}, [], f"{type(e).__name__}: {e}"
            errors += 1

        if files:
            written = write_bundle(dest, files)
            rec = {"address": addr, "chain": CHAIN, "name": r["name"] or name,
                   "via": "blockscout", "registered": False,
                   "pools": r["pools"],
                   "status": "ok" if written else "no-sol",
                   "files": written, "dir": os.path.relpath(dest, ROOT)}
            json.dump(rec, open(os.path.join(dest, ".fetched.json"), "w"))
            remember(rec)
            print(f"  {r['pools']:>5} pools  {r['name']}: {written} file(s)")
        else:
            print(f"  {r['pools']:>5} pools  {r['name']}: "
                  f"NO SOURCE ({err or 'explorer holds none'})")

        # Follow verified proxies: the implementation is where reviewable logic
        # actually lives, and it can change without the hook address moving.
        # Explorer metadata first; empty there, ask the EIP-1967 slot directly.
        impls = list(impls)
        if not impls and "proxy" in (r["name"] or name or "").lower():
            try:
                i = eip1967_implementation(addr)
                if i:
                    print(f"          EIP-1967 slot -> implementation {i}")
                    impls.append((i, None))
            except Exception as e:                          # noqa: BLE001
                print(f"          EIP-1967 read failed ({e})")
        seen = set()
        for iaddr, iname in impls:
            if iaddr.lower() in seen:
                continue
            seen.add(iaddr.lower())
            idest = os.path.join(ROOT, "corpus", CHAIN, iaddr.lower())
            if os.path.exists(os.path.join(idest, ".fetched.json")):
                print(f"          impl {iaddr} already in corpus")
                continue
            try:
                _, ifiles, _ = contract_source(iaddr)
            except Exception as e:                          # noqa: BLE001
                print(f"          impl {iaddr}: fetch failed ({e})")
                errors += 1
                continue
            if not ifiles:
                print(f"          impl {iaddr}: no published source")
                continue
            w = write_bundle(idest, ifiles)
            rec = {"address": iaddr, "chain": CHAIN,
                   "name": iname or f"impl-of-{r['name']}",
                   "via": "blockscout", "registered": False,
                   "role": "implementation", "proxy": addr,
                   "status": "ok" if w else "no-sol",
                   "files": w, "dir": os.path.relpath(idest, ROOT)}
            json.dump(rec, open(os.path.join(idest, ".fetched.json"), "w"))
            remember(rec)
            print(f"          impl {iaddr}: {w} file(s)")
        time.sleep(0.4)

    # Five contracts is the entire claim; a failed lookup would make the scan
    # below silently incomplete, so refuse to publish an index from a bad run.
    if errors:
        sys.exit(f"\nABORT: {errors} lookup(s) failed -- re-run before scanning")

    os.makedirs(os.path.dirname(idx_path), exist_ok=True)
    rows_out = sorted(index.values(), key=lambda x: (x["chain"], x["address"].lower()))
    json.dump(rows_out, open(idx_path, "w"), indent=1)
    ok = sum(1 for x in rows_out if x.get("registered") is False
             and x["status"] == "ok")
    print(f"\n  unregistered hooks in corpus: {ok}")
    print(f"  wrote {os.path.relpath(idx_path, ROOT)}")


if __name__ == "__main__":
    main()
