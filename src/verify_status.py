#!/usr/bin/env python3
"""Ask the block explorer whether the busiest unregistered hooks publish source.

Registry coverage says how many deployed hooks the hooklist can see. It does not
say whether the ones it misses can be reviewed at all. This takes the hooks that
survive the launchpad discount -- unregistered, and serving MIN_POOLS or more
live pools -- and checks each for published source.

    python3 src/verify_status.py        -> out/<chain>-unregistered-top.json

Blockscout is used rather than Etherscan because it needs no API key, so the
number is reproducible by anyone with a clone and no signup. A contract counts
as verified only on an explicit positive from the explorer; a fetch error is
recorded as an error and never silently folded into the unverified count.
"""
import json, os, sys, time, urllib.request, urllib.error

EXPLORERS = {
    "unichain": "https://unichain.blockscout.com",
    "base":     "https://base.blockscout.com",
    "ethereum": "https://eth.blockscout.com",
}
CHAIN     = os.environ.get("CHAIN", "unichain")
MIN_POOLS = int(os.environ.get("MIN_POOLS", "10"))
HDRS      = {"User-Agent": "curl/8.5.0", "Accept": "application/json"}
ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(*parts):
    path = os.path.join(ROOT, *parts)
    if not os.path.exists(path):
        sys.exit(f"missing {os.path.join(*parts)} -- run src/discover.py and src/risk.py first")
    with open(path) as f:
        return json.load(f)


def explorer(address):
    """Return (name, verified, proxy). Raises on transport failure."""
    url = f"{EXPLORERS[CHAIN]}/api/v2/smart-contracts/{address}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HDRS), timeout=30) as r:
            body = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, False, False       # explorer knows the address, holds no source
        raise
    name  = body.get("name")
    proxy = bool(body.get("implementations") or body.get("minimal_proxy_address_hash")
                 or (name or "").lower().endswith("proxy") or "proxy" in (name or "").lower())
    return name, bool(body.get("is_verified") or body.get("source_code")), proxy


def main():
    if CHAIN not in EXPLORERS:
        sys.exit(f"no explorer configured for {CHAIN}; known: {', '.join(EXPLORERS)}")

    onchain  = load("docs", f"{CHAIN}-onchain.json")
    registry = {h["address"].lower() for h in load("docs", "risk.json")
                if str(h.get("chain", "")).lower() == CHAIN}

    candidates = sorted(
        ((a, v) for a, v in onchain["hooks"].items()
         if a.lower() not in registry and v["pools"] >= MIN_POOLS),
        key=lambda kv: -kv[1]["pools"])

    print(f"{CHAIN}: {len(candidates)} unregistered hooks serving {MIN_POOLS}+ pools\n")

    rows, errors = [], 0
    for address, meta in candidates:
        try:
            name, verified, proxy = explorer(address)
            err = None
        except Exception as e:                      # noqa: BLE001 - recorded, not swallowed
            name, verified, proxy, err = None, None, None, f"{type(e).__name__}: {e}"
            errors += 1
        rows.append({"address": address, "pools": meta["pools"], "name": name,
                     "verified": verified, "proxy": proxy, "error": err})
        flag = "err  " if err else ("ver  " if verified else "     ")
        print(f"{meta['pools']:>5} pools  {flag}{address}  {name or ''}")
        time.sleep(0.4)                             # keyless endpoint; stay polite

    checked  = [r for r in rows if r["error"] is None]
    verified = [r for r in checked if r["verified"]]

    # An unreachable explorer must not masquerade as an unverified contract.
    if errors > len(rows) // 10:
        sys.exit(f"\naborting: {errors}/{len(rows)} explorer lookups failed -- "
                 "the verified share would be an undercount")

    out = {"chain": CHAIN, "minPools": MIN_POOLS, "candidates": len(rows),
           "checked": len(checked), "verified": len(verified),
           "verifiedPct": round(100 * len(verified) / len(checked), 1) if checked else None,
           "proxies": len([r for r in checked if r["proxy"]]),
           "errors": errors, "hooks": rows}

    dest = os.path.join(ROOT, "out", f"{CHAIN}-unregistered-top.json")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w") as f:
        json.dump(out, f, indent=1)

    print(f"\nverified {len(verified)}/{len(checked)} ({out['verifiedPct']}%)"
          f"   proxies {out['proxies']}   errors {errors}")
    print(f"-> {os.path.relpath(dest, ROOT)}")


if __name__ == "__main__":
    main()
