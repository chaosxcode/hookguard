#!/usr/bin/env python3
"""Fetch verified source for hooks so the scanner can be measured against
real deployed code rather than fixtures.

Sources are tried in order:
  1. Sourcify   - primary; full multi-file bundles, no API key.
  2. Blockscout - per-chain public instance, also keyless. Covers contracts
     whose authors verified on an explorer Sourcify does not mirror; a
     registry entry can be "verified" without either source being complete,
     so provenance is recorded per contract.
  3. Etherscan v2 - only when ETHERSCAN_API_KEY is set. A number requiring
     signup is one fewer person can reproduce, so it stays optional.

Failed fetches are never cached, so every re-run retries them; --passes
bounds how many rounds of retries a single invocation does.

    python3 src/corpus.py                     # all registered hooks
    python3 src/corpus.py --chain unichain    # one chain
    python3 src/corpus.py --limit 80          # a sample

Writes corpus/<chain>/<address>/*.sol and corpus/index.json.
"""
import argparse, json, os, sys, time, urllib.request, urllib.error
import concurrent.futures

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "corpus")
HDRS = {"User-Agent": "curl/8.5.0", "Accept": "application/json"}
API = "https://sourcify.dev/server/v2/contract/{cid}/{addr}?fields=sources"
# Blockscout instances confirmed to serve /api/v2/smart-contracts. Chains not
# listed here have no usable keyless instance (probed Aug 2026); they fall
# through to the optional Etherscan pass instead of wasting requests.
BLOCKSCOUT = {
    "ethereum": "https://eth.blockscout.com",
    "base":     "https://base.blockscout.com",
    "optimism": "https://optimism.blockscout.com",
    "arbitrum": "https://arbitrum.blockscout.com",
    "polygon":  "https://polygon.blockscout.com",
    "celo":     "https://celo.blockscout.com",
    "unichain": "https://unichain.blockscout.com",
}
VENDORED = ("/node_modules/", "openzeppelin", "/lib/v4-core/",
            "/lib/v4-periphery/", "/forge-std/", "/solmate/")


def load_registry():
    d = json.load(open(os.path.join(ROOT, "data", "hooklist.json")))
    return d["hooks"] if isinstance(d, dict) and "hooks" in d else d


def get_json(url):
    req = urllib.request.Request(url, headers=HDRS)
    return json.loads(urllib.request.urlopen(req, timeout=45).read())


def sourcify(cid, addr):
    """(status, {path: content}). Sources dict is empty unless found."""
    try:
        data = get_json(API.format(cid=cid, addr=addr))
    except urllib.error.HTTPError as e:
        return f"http-{e.code}", {}
    except Exception as e:                                   # noqa: BLE001
        return f"err-{str(e)[:24]}", {}
    return "ok", {p: (b.get("content") if isinstance(b, dict) else b)
                  for p, b in (data.get("sources") or {}).items()}


def blockscout(chain, addr):
    host = BLOCKSCOUT.get(chain)
    if not host:
        return "no-explorer", {}
    try:
        body = get_json(f"{host}/api/v2/smart-contracts/{addr}")
    except urllib.error.HTTPError as e:
        return f"http-{e.code}", {}
    except Exception as e:                                   # noqa: BLE001
        return f"err-{str(e)[:24]}", {}
    if not body.get("is_verified"):
        return "not-verified", {}
    files = {}
    main = body.get("source_code")
    if main:
        files[body.get("file_path") or "Main.sol"] = main
    for s in body.get("additional_sources") or []:
        if s.get("content"):
            files[s.get("file_path") or "Extra.sol"] = s["content"]
    return ("ok", files) if files else ("no-sol", {})


def etherscan(cid, addr):
    key = os.environ.get("ETHERSCAN_API_KEY")
    if not (key and cid):
        return "no-key", {}
    url = (f"https://api.etherscan.io/v2/api?chainid={cid}&module=contract"
           f"&action=getsourcecode&address={addr}&apikey={key}")
    try:
        body = get_json(url)
    except Exception as e:                                   # noqa: BLE001
        return f"err-{str(e)[:24]}", {}
    rows = body.get("result") or []
    if body.get("status") != "1" or not rows or not (rows[0].get("SourceCode") or ""):
        return "not-verified", {}
    raw = rows[0]["SourceCode"]
    try:
        if raw.startswith("{{"):                             # standard-json multi-file
            inner = json.loads(raw[1:-1])
            files = inner.get("sources", inner)
            return "ok", {p: v.get("content", "") for p, v in files.items()}
        if raw.startswith("{"):
            files = json.loads(raw)
            return "ok", {p: v.get("content", "") for p, v in files.items()}
    except Exception:                                        # noqa: BLE001
        pass
    return "ok", {rows[0].get("ContractName") or "Main.sol": raw}


def write_bundle(dest, files):
    """Flatten into .sol files, skipping vendored dependencies — we measure the
    hook, not OpenZeppelin. Returns count written."""
    os.makedirs(dest, exist_ok=True)
    written = 0
    for path, content in files.items():
        if not content:
            continue
        safe = path.replace("\\", "/").split("/")[-1]
        if not safe.endswith(".sol") or any(k in path.lower() for k in VENDORED):
            continue
        with open(os.path.join(dest, safe), "w", encoding="utf-8") as fh:
            fh.write(content)
        written += 1
    return written


def fetch_one(entry):
    hk = entry["hook"]
    cid, addr, chain = hk.get("chainId"), hk["address"], hk.get("chain", "unknown")
    name = hk.get("name", "")
    if not cid and chain not in BLOCKSCOUT:
        return {"address": addr, "chain": chain, "name": name, "status": "no-chainid"}

    dest = os.path.join(OUT, chain, addr.lower())
    idx = os.path.join(dest, ".fetched.json")
    if os.path.exists(idx):                      # resumable; remote calls are slow
        try:
            return json.load(open(idx))
        except Exception:
            pass

    via, status, sources = "sourcify", *sourcify(cid, addr)
    if not any(sources.values()) and chain in BLOCKSCOUT:
        time.sleep(0.3)                          # keyless endpoint; stay polite
        via = "blockscout"
        status, sources = blockscout(chain, addr)
    if not any(sources.values()) and cid:
        via = "etherscan"
        status, sources = etherscan(cid, addr)

    if not any(sources.values()):
        return {"address": addr, "chain": chain, "name": name, "status": status}

    written = write_bundle(dest, sources)
    rec = {"address": addr, "chain": chain, "name": name, "via": via,
           "status": "ok" if written else "no-sol", "files": written,
           "dir": os.path.relpath(dest, ROOT)}
    if written:
        json.dump(rec, open(idx, "w"))
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--passes", type=int, default=3,
                    help="retry rounds over whatever is still missing")
    ap.add_argument("--chain", help="restrict to one registry chain")
    a = ap.parse_args()

    reg = load_registry()
    if a.chain:
        reg = [e for e in reg if e["hook"].get("chain") == a.chain]
        if not reg:
            sys.exit(f"no registry hooks for chain {a.chain}")
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
    print(f"fetching source for {len(reg)} hooks"
          f" (sourcify -> blockscout -> etherscan-if-keyed)", flush=True)
    final, work = {}, list(enumerate(reg))
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for p in range(1, a.passes + 1):
            round_recs = {i: r for (i, e), r in
                          zip(work, ex.map(fetch_one, [e for _, e in work]))}
            final.update(round_recs)
            ok = sum(1 for i, _ in work if round_recs[i]["status"] == "ok")
            print(f"  pass {p}: {ok}/{len(work)} fetched this round", flush=True)
            work = [(i, e) for (i, e) in work
                    if round_recs[i]["status"] not in ("ok", "no-sol")]
            if not work:
                break
            time.sleep(3 * p)                        # let rate limits cool off
            print(f"  retrying {len(work)} on pass {p + 1}", flush=True)

    recs = [final[i] for i in range(len(reg))]

    # A scoped run (--chain) must not erase the rest of the manifest: merge
    # into whatever index already exists, keyed by (chain, address).
    idx_path = os.path.join(OUT, "index.json")
    merged = {}
    if os.path.exists(idx_path):
        try:
            merged = {(r["chain"], r["address"].lower()): r
                      for r in json.load(open(idx_path))}
        except Exception:
            merged = {}
    for r in recs:
        merged[(r["chain"], r["address"].lower())] = r
    rows = sorted(merged.values(), key=lambda r: (r["chain"], r["address"].lower()))
    json.dump(rows, open(idx_path, "w"), indent=1)

    import collections
    st = collections.Counter(r["status"] for r in recs)
    vias = collections.Counter(r.get("via", "?") for r in recs if r["status"] == "ok")
    print("\n  this run:")
    for k, v in st.most_common():
        print(f"    {k:16s} {v}")
    print("  fetched via:")
    for k, v in vias.most_common():
        print(f"    {k:16s} {v}")
    ok = sum(1 for r in rows if r["status"] == "ok")
    print(f"\n  index total usable: {ok}/{len(rows)} ({ok/len(rows)*100:.1f}%)")
    print(f"  wrote {idx_path}")


if __name__ == "__main__":
    main()
