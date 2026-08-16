#!/usr/bin/env python3
"""Fetch verified source for registered hooks so the scanner can be measured
against real deployed code rather than fixtures.

Source comes from Sourcify, which serves verified sources with no API key.
Every hook in the registry is marked verifiedSource, so in principle all of
them are fetchable; in practice Sourcify's coverage varies by chain and that
gap is itself worth recording.

    python3 src/corpus.py            # all registered hooks
    python3 src/corpus.py --limit 80 # a sample

Writes corpus/<chain>/<address>/*.sol and corpus/index.json.
"""
import argparse, json, os, sys, urllib.request, urllib.error, concurrent.futures, threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "corpus")
HDRS = {"User-Agent": "curl/8.5.0", "Accept": "application/json"}
API = "https://sourcify.dev/server/v2/contract/{cid}/{addr}?fields=sources"

_print_lock = threading.Lock()


def load_registry():
    d = json.load(open(os.path.join(ROOT, "data", "hooklist.json")))
    return d["hooks"] if isinstance(d, dict) and "hooks" in d else d


def fetch_one(entry):
    hk = entry["hook"]
    cid, addr, chain = hk.get("chainId"), hk["address"], hk.get("chain", "unknown")
    name = hk.get("name", "")
    if not cid:
        return {"address": addr, "chain": chain, "name": name, "status": "no-chainid"}

    dest = os.path.join(OUT, chain, addr.lower())
    idx = os.path.join(dest, ".fetched.json")
    if os.path.exists(idx):                      # resumable; Sourcify is slow
        try:
            return json.load(open(idx))
        except Exception:
            pass

    try:
        req = urllib.request.Request(API.format(cid=cid, addr=addr), headers=HDRS)
        data = json.loads(urllib.request.urlopen(req, timeout=45).read())
    except urllib.error.HTTPError as e:
        return {"address": addr, "chain": chain, "name": name, "status": f"http-{e.code}"}
    except Exception as e:
        return {"address": addr, "chain": chain, "name": name, "status": f"err-{str(e)[:24]}"}

    sources = data.get("sources") or {}
    if not sources:
        return {"address": addr, "chain": chain, "name": name, "status": "no-sources"}

    os.makedirs(dest, exist_ok=True)
    written = 0
    for path, blob in sources.items():
        content = blob.get("content") if isinstance(blob, dict) else blob
        if not content:
            continue
        # Flatten: Sourcify paths can be deep and contain .. segments.
        safe = path.replace("\\", "/").split("/")[-1]
        if not safe.endswith(".sol"):
            continue
        # Skip vendored dependencies — we are measuring the hook, not OpenZeppelin.
        low = path.lower()
        if any(k in low for k in ("/node_modules/", "openzeppelin", "/lib/v4-core/",
                                  "/lib/v4-periphery/", "/forge-std/", "/solmate/")):
            continue
        with open(os.path.join(dest, safe), "w", encoding="utf-8") as fh:
            fh.write(content)
        written += 1

    rec = {"address": addr, "chain": chain, "name": name,
           "status": "ok" if written else "no-sol", "files": written,
           "dir": os.path.relpath(dest, ROOT)}
    if written:
        json.dump(rec, open(idx, "w"))
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()

    reg = load_registry()
    if a.limit:
        # Spread the sample across chains rather than taking the first N, which
        # would be one chain and would not represent the registry.
        by_chain = {}
        for e in reg:
            by_chain.setdefault(e["hook"].get("chain", "?"), []).append(e)
        picked, i = [], 0
        while len(picked) < a.limit and any(by_chain.values()):
            for c in list(by_chain):
                if by_chain[c]:
                    picked.append(by_chain[c].pop(0))
                    if len(picked) >= a.limit:
                        break
            i += 1
            if i > 5000:
                break
        reg = picked

    os.makedirs(OUT, exist_ok=True)
    print(f"fetching source for {len(reg)} hooks from Sourcify", flush=True)
    recs, done = [], 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for rec in ex.map(fetch_one, reg):
            recs.append(rec)
            done += 1
            if done % 25 == 0:
                ok = sum(1 for r in recs if r["status"] == "ok")
                print(f"  {done}/{len(reg)}  fetched={ok}", flush=True)

    json.dump(recs, open(os.path.join(OUT, "index.json"), "w"), indent=1)
    import collections
    st = collections.Counter(r["status"] for r in recs)
    print("\n  results:")
    for k, v in st.most_common():
        print(f"    {k:16s} {v}")
    ok = st["ok"]
    print(f"\n  usable: {ok}/{len(recs)} ({ok/len(recs)*100:.1f}%)")
    print(f"  wrote {os.path.join(OUT,'index.json')}")


if __name__ == "__main__":
    main()
