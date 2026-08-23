#!/usr/bin/env python3
"""What can be known about a hook that publishes no source.

The verification-gap finding left 25 of the busiest unregistered Unichain
hooks unreachable by any source-level tool. This reaches around source, in
three layers ordered by how much they cost to trust:

1. The ADDRESS itself. Final v4 encodes permissions in the hook address's low
   14 bits. But Unichain's PoolManager (0x1F984000...0004) is the earlier
   preview deployment, not final v4 (mainnet's 0x000000000004444c...A90) --
   visible already in its interface, whose PoolKey orders fields differently.
   Decoding every hook whose verified source we hold shows the ten CALLBACK
   flags match a REVERSED bit order exactly (17/18 contracts; the exceptions
   are one bundle with unparseable permissions and one implementation contract
   that was never CREATE2-mined). The four return-delta positions match NO
   current layout. Both decodings are reported and the validation runs live,
   so this claim degrades loudly if the chain changes under it.
2. STORAGE. One eth_getStorageAt against the EIP-1967 slot settles "is this a
   proxy, and what sits behind it" with no bytecode interpretation at all.
3. RUNTIME BYTES. EIP-1167 minimal-proxy pattern, DELEGATECALL / SELFDESTRUCT
   byte presence, code size, and whether the getHookPermissions selector
   appears. Selector presence is a WEAK signal -- Solidity emits `.selector`
   constants for callbacks a contract merely reverts in -- so it is reported
   but never scored.

    CHAIN=unichain python3 src/bytecode.py     -> out/<chain>-bytecode.json

Reads out/<chain>-unregistered-top.json (verify_status.py) for the target set
and out/scan.json for layout ground truth. Aborts above 10% RPC errors rather
than publish a partial population.
"""
import json, os, sys, time, urllib.request, urllib.error
import concurrent.futures

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from discover import CHAINS                               # noqa: E402

# keccak-256 (Keccak-f[1600], 0x01 padding) -- enough to derive IHooks
# selectors without pulling a dependency into a repo that has none.
_RC = [0x0000000000000001,0x0000000000008082,0x800000000000808A,0x8000000080008000,
       0x000000000000808B,0x0000000080000001,0x8000000080008081,0x8000000000008009,
       0x000000000000008A,0x0000000000000088,0x0000000080008009,0x000000008000000A,
       0x000000008000808B,0x800000000000008B,0x8000000000008089,0x8000000000008003,
       0x8000000000008002,0x8000000000000080,0x000000000000800A,0x800000008000000A,
       0x8000000080008081,0x8000000000008080,0x0000000080000001,0x8000000080008008]
_ROT = [[0,36,3,41,18],[1,44,10,45,2],[62,6,43,15,61],[28,55,25,21,56],[27,20,39,8,14]]
_M = (1 << 64) - 1

def _rol(x, n):
    n %= 64
    return ((x << n) | (x >> (64 - n))) & _M

def _keccak_f(a):
    for rc in _RC:
        c = [a[x][0] ^ a[x][1] ^ a[x][2] ^ a[x][3] ^ a[x][4] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rol(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                a[x][y] ^= d[x]
        b = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                b[y][(2 * x + 3 * y) % 5] = _rol(a[x][y], _ROT[x][y])
        for x in range(5):
            for y in range(5):
                a[x][y] = b[x][y] ^ ((~b[(x + 1) % 5][y]) & _M & b[(x + 2) % 5][y])
        a[0][0] ^= rc
    return a

def keccak256(data):
    rate = 136
    pad = data + b"\x01" + b"\x00" * ((-len(data) - 1) % rate)
    pad = pad[:-1] + bytes([pad[-1] | 0x80])
    a = [[0] * 5 for _ in range(5)]
    for off in range(0, len(pad), rate):
        blk = pad[off:off + rate]
        for i in range(rate // 8):
            a[i % 5][i // 5] ^= int.from_bytes(blk[i * 8:(i + 1) * 8], "little")
        a = _keccak_f(a)
    return b"".join(a[i % 5][i // 5].to_bytes(8, "little") for i in range(4))

assert keccak256(b"").hex() == \
    "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470", "keccak self-test"

# Preview-deployment interface, validated empirically against deployed hooks
# whose source we hold (see findings/unichain-bytecode.md): PoolKey puts hooks
# last and SwapParams carries no exactInput.
_KEY = "(address,address,uint24,int24,address)"
_SELECTORS = {
    "getHookPermissions": "getHookPermissions()",
    "beforeSwap": f"beforeSwap(address,{_KEY},(bool,int256,uint160),bytes)",
    "afterSwap": f"afterSwap(address,{_KEY},(bool,int256,uint160),int256,bytes)",
}
SELECTOR_HEX = {n: keccak256(s.encode())[:4].hex() for n, s in _SELECTORS.items()}

PERMS_FINAL = ["beforeInitialize","afterInitialize","beforeAddLiquidity",
               "afterAddLiquidity","beforeRemoveLiquidity","afterRemoveLiquidity",
               "beforeSwap","afterSwap","beforeDonate","afterDonate",
               "beforeSwapReturnsDelta","afterSwapReturnsDelta",
               "afterAddLiquidityReturnsDelta","afterRemoveLiquidityReturnsDelta"]

CHAIN = os.environ.get("CHAIN", "unichain")
MINPOOL = int(os.environ.get("MIN_POOLS", "10"))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HDRS = {"Content-Type": "application/json", "User-Agent": "curl/8.5.0"}
HDRS2 = {"User-Agent": "curl/8.5.0", "Accept": "application/json"}
EIP1967 = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
EIP1167_HEAD = "363d3d373d3d3d363d"
EIP1167_TAIL = "57fd5bf3"


def rpc(method, params, tries=4):
    url = CHAINS[CHAIN][0]
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": params}).encode()
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, method="POST", headers=HDRS, data=body)
            res = json.loads(urllib.request.urlopen(req, timeout=45).read())
            if "result" in res:
                return res["result"]
            last = RuntimeError(str(res.get("error")))
        except Exception as e:                              # noqa: BLE001
            last = e
        time.sleep(1.5 * (attempt + 1))
    raise last


def decode_perms(addr):
    """Both candidate readings of the low 14 bits."""
    bits = int(addr, 16) & 0x3FFF
    fwd = [PERMS_FINAL[i] for i in range(14) if (bits >> i) & 1]
    rev = [PERMS_FINAL[13 - i] for i in range(14) if (bits >> i) & 1]
    return {"finalV4Order": fwd, "previewReversedOrder": rev}


_CALLBACKS = set(PERMS_FINAL[:10])

def _real_opcodes(code_bytes):
    """Opcode positions with PUSH operands skipped -- without this, a plain
    substring search reports opcodes that are actually PUSH data."""
    i, out = 0, set()
    n = len(code_bytes)
    while i < n:
        op = code_bytes[i]
        if 0x60 <= op <= 0x7F:
            i += (op - 0x5F) + 1                # PUSHn: opcode + n operand bytes
        else:
            out.add(op)
            i += 1
    return out


def _disasm(code_bytes):
    """Linear disassembly as (offset, opcode, operand_hex|None)."""
    i, ins = 0, []
    n = len(code_bytes)
    while i < n:
        op = code_bytes[i]
        if 0x60 <= op <= 0x7F:
            w = op - 0x5F
            ins.append((i, op, code_bytes[i + 1:i + 1 + w].hex()))
            i += 1 + w
        else:
            ins.append((i, op, None))
            i += 1
    return ins


def classify_delegatecalls(code_bytes, near=10):
    """Where do this contract's DELEGATECALL targets come from?

    Only the instructions immediately feeding the call count -- the canonical
    tail is `... PUSH20 <target> GAS DELEGATECALL`, and proxies load the
    target with `PUSH32 <slot> SLOAD` just before:

      constant        -> a plausible address constant sits in the near
          window and no SLOAD does: fixed delegation to one implementation
      storage-derived -> an SLOAD sits there instead: the target lives in
          storage and can be rewritten => upgradeable in practice
      unknown         -> neither: needs real stack emulation

    The near window keeps unrelated constants (PoolManager comparisons, zero
    guards) out of the verdict; those were exactly the false attributions a
    wide window produced."""
    pm = CHAINS[CHAIN][1].lower()
    ins = _disasm(code_bytes)
    sites = []
    for k, (off, op, arg) in enumerate(ins):
        if op != 0xF4:
            continue
        win = ins[max(0, k - near):k]
        consts = {("0x" + a[-40:]) for _, o, a in win
                  if o == 0x73 and a}                       # PUSH20 only
        consts = {c for c in consts
                  if int(c, 16) > 2 ** 152 and c != pm}
        sload = any(o == 0x54 for _, o, _a in win)
        if consts and not sload:
            kind = "constant"
        elif sload and not consts:
            kind = "storage-derived"
        elif consts and sload:
            kind = "mixed"
        else:
            kind = "unknown"
        sites.append({"offset": off,
                      "kind": kind,
                      "constants": sorted(consts)[:3]})
    kinds = {s["kind"] for s in sites}
    if len(kinds) > 1 and "unknown" in kinds:
        kinds.discard("unknown")
    kind = kinds.pop() if len(kinds) == 1 else \
        ("mixed" if kinds else None)
    return {
        "sites": len(sites),
        "kind": kind,
        "constantTargets": sorted({c for s in sites for c in s["constants"]})[:4],
        "heuristic": f"adjacent-{near}-instruction window per site",
    }


def analyze(addr):
    code = rpc("eth_getCode", [addr, "latest"])
    if len(code) <= 2:
        return {"address": addr, "error": "no-code"}
    b = code[2:].lower()
    raw = bytes.fromhex(b)
    ops = _real_opcodes(raw)
    rec = {
        "address": addr,
        "codeSizeBytes": len(raw),
        # sha3 of the runtime code itself: identical bytes across addresses =
        # one program deployed many times, not many programs.
        "codeHash": keccak256(raw).hex(),
        "permsFromAddress": decode_perms(addr),
        "delegatecall": 0xF4 in ops,
        "callcode": 0xF2 in ops,
        "staticcall": 0xFA in ops,
        "selfdestruct": 0xFF in ops,
        "selectorsPresent": {n: (h in b) for n, h in SELECTOR_HEX.items()},
    }
    if 0xF4 in ops:
        rec["delegatecallTargets"] = classify_delegatecalls(raw)
    # EIP-1167 minimal proxy: fixed prefix/suffix with the target embedded.
    if b.startswith(EIP1167_HEAD) and b.endswith(EIP1167_TAIL) and len(b) == 90:
        rec["minimalProxy"] = True
        rec["implementation"] = "0x" + b[20:60][-40:]
    else:
        rec["minimalProxy"] = False
    # EIP-1967: ask storage, not bytecode -- explorers miss this constantly.
    val = rpc("eth_getStorageAt", [addr, EIP1967, "latest"])
    impl = "0x" + val[-40:]
    if int(val, 16):
        rec["eip1967Implementation"] = impl
    return rec


def validate_layout():
    """Callback-flag agreement against every unichain contract whose verified
    source already yielded declared permissions (out/scan.json).

    Only the ten callback flags are scored: the four return-delta positions
    matched no layout anywhere (see findings doc), so counting them here would
    blur a proven result with an open one."""
    scan_path = os.path.join(ROOT, "out", "scan.json")
    if not os.path.exists(scan_path):
        return None
    rows = json.load(open(scan_path))
    rev_ok = fwd_ok = n = 0
    for c in rows:
        if "/unichain/" not in c["file"]:
            continue
        declared = set(c["declared"]) | set(c["returnsDelta"])
        cb_src = {f for f in declared if f in _CALLBACKS}
        if not cb_src:
            continue                         # nothing comparable in this bundle
        addr = c["file"].split("/unichain/")[1].split("/")[0]
        perms = decode_perms(addr)
        n += 1
        rev_ok += {f for f in perms["previewReversedOrder"] if f in _CALLBACKS} == cb_src
        fwd_ok += {f for f in perms["finalV4Order"] if f in _CALLBACKS} == cb_src
    return {"contractsChecked": n, "previewReversedOrderMatches": rev_ok,
            "finalV4OrderMatches": fwd_ok,
            "note": "callback flags only; return-delta bit positions match "
                    "neither layout and stay unclaimed"} if n else None


def load_impl_verification(targets):
    """Ask Blockscout whether each constant delegatecall target publishes
    source -- the difference between 'hidden but readable' and 'opaque'."""
    out = {}
    host = {"unichain": "https://unichain.blockscout.com"}.get(CHAIN)
    if not host:
        return out
    for t in targets:
        try:
            req = urllib.request.Request(
                f"{host}/api/v2/smart-contracts/{t}", headers=HDRS2)
            body = json.loads(urllib.request.urlopen(req, timeout=30).read())
            if body.get("is_verified"):
                out[t] = {"name": body.get("name")}
            time.sleep(0.3)
        except Exception:                                   # noqa: BLE001
            pass                                            # opaque by default
    return out


def main():
    top_path = os.path.join(ROOT, "out", f"{CHAIN}-unregistered-top.json")
    if MINPOOL != 10:
        top_path = os.path.join(ROOT, "out", f"{CHAIN}-unregistered-min{MINPOOL}.json")
    if not os.path.exists(top_path):
        sys.exit(f"missing {os.path.relpath(top_path, ROOT)} -- run src/verify_status.py first")
    targets = sorted(
        (r for r in json.load(open(top_path))["hooks"]
         if r["verified"] is False and not r.get("error")),
        key=lambda r: -r["pools"])
    print(f"{CHAIN}: bytecode pass over {len(targets)} unverified hooks "
          f"serving {MINPOOL}+ pools\n")

    layout = validate_layout()
    if layout:
        print(f"  layout check vs verified-source hooks: "
              f"preview-reversed {layout['previewReversedOrderMatches']}/"
              f"{layout['contractsChecked']}, "
              f"final-v4 {layout['finalV4OrderMatches']}/{layout['contractsChecked']}")

    results, errors = [], 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(analyze, r["address"]): r for r in targets}
        for fut in concurrent.futures.as_completed(futs):
            r = futs[fut]
            try:
                rec = fut.result()
                err = None
            except Exception as e:                          # noqa: BLE001
                rec, err = {"address": r["address"], "error": str(e)[:120]}, e
                errors += 1
            rec.update({"name": r["name"], "pools": r["pools"]})
            results.append(rec)
            if err or "error" in rec:
                print(f"  {r['pools']:>5}p  ERR {r['address']} {err or rec['error']}")
            else:
                p = rec["permsFromAddress"]
                proxy = ("EIP1967->" + rec["eip1967Implementation"][:10]) if \
                    rec.get("eip1967Implementation") else \
                    ("EIP1167" if rec["minimalProxy"] else "-")
                flags = "".join(c for c, on in (
                    ("D", rec["delegatecall"]), ("S", rec["selfdestruct"])) if on)
                print(f"  {r['pools']:>5}p  {rec['codeSizeBytes']:>6}B  "
                      f"proxy={proxy:22s}{flags:3s} {r['name'] or r['address'][:12]}")

    if errors > max(1, len(targets) // 10):
        sys.exit(f"\nABORT: {errors}/{len(targets)} lookups failed")

    results.sort(key=lambda x: -x.get("pools", 0))
    ok = [r for r in results if "error" not in r]
    proxies1967 = [r for r in ok if r.get("eip1967Implementation")]
    minis = [r for r in ok if r.get("minimalProxy")]

    # Identical runtime code under different addresses: the launchpad pattern
    # measured among registry hooks, now checked off-registry too.
    families = {}
    for r in ok:
        families.setdefault(r["codeHash"], []).append(r)
    shared = {h: v for h, v in families.items() if len(v) > 1}

    out = {
        "chain": CHAIN, "poolManagerPreviewDeployment": CHAINS[CHAIN][1],
        "targets": len(targets), "analyzed": len(ok),
        "errors": errors,
        "layoutValidation": layout,
        "summary": {
            "eip1967Proxies": len(proxies1967),
            "eip1167MinimalProxies": len(minis),
            "delegatecallOpcodesPresent": sum(1 for r in ok if r["delegatecall"]),
            **{f"delegatecall{k}":
               sum(1 for r in ok
                   if (r.get("delegatecallTargets") or {}).get("kind") == k)
               for k in ("storage-derived", "constant", "mixed")},
            "selfdestructOpcodesPresent": sum(1 for r in ok if r["selfdestruct"]),
            "getHookPermissionsSelectorPresent":
                sum(1 for r in ok if r["selectorsPresent"]["getHookPermissions"]),
            "distinctCodeHashes": len(families),
            "contractsSharingCodeWithOthers": sum(len(v) for v in shared.values()),
            "largestSharedCodeFamily": max((len(v) for v in shared.values()), default=1),
        },
        "hooks": results,
    }
    dest = os.path.join(ROOT, "out", f"{CHAIN}-bytecode.json")
    if MINPOOL != 10:
        dest = os.path.join(ROOT, "out", f"{CHAIN}-bytecode-min{MINPOOL}.json")
    json.dump(out, open(dest, "w"), indent=1)

    print(f"\n  analyzed              {len(ok)}/{len(targets)}")
    print(f"  EIP-1967 proxies      {len(proxies1967)}")
    for r in proxies1967:
        print(f"      {r['name'] or ''}: impl {r['eip1967Implementation']}")
    print(f"  EIP-1167 minimal      {len(minis)}")
    print(f"  DELEGATECALL opcode   {out['summary']['delegatecallOpcodesPresent']}")
    for k, label in (("storage-derived", "storage-derived (upgradeable in practice)"),
                     ("constant", "constant target (fixed delegation)"),
                     ("mixed", "mixed signals (needs emulation)")):
        n = out['summary'][f"delegatecall{k}"]
        print(f"    {label:38s} {n}")
        if k == "constant":
            by_impl = {}
            for r in ok:
                dt = r.get("delegatecallTargets") or {}
                if dt.get("kind") != "constant":
                    continue
                for t in dt.get("constantTargets", []):
                    by_impl.setdefault(t, []).append(r["address"])
            impls = load_impl_verification(by_impl.keys()) if by_impl else {}
            for t, addrs in sorted(by_impl.items(), key=lambda kv: -len(kv[1])):
                ver = impls.get(t)
                tag = f"  [{'VERIFIED: ' + ver['name'] + ' | ' if ver else ''}"
                tag += "READABLE" if ver else "OPAQUE -- no published source"
                print(f"      {t}  <- {len(addrs)} deployment(s){tag}]")
        elif k == "storage-derived":
            for r in ok:
                dt = r.get("delegatecallTargets") or {}
                if dt.get("kind") == "storage-derived":
                    print(f"      {r['address']}")
    print(f"  SELFDESTRUCT opcode   {out['summary']['selfdestructOpcodesPresent']}")
    print(f"  getHookPermissions    {out['summary']['getHookPermissionsSelectorPresent']}   (weak signal)")
    print(f"  distinct programs     {len(families)} across {len(ok)} contracts")
    for h, v in sorted(shared.items(), key=lambda kv: -len(kv[1]))[:5]:
        addrs = ", ".join(x["address"][:10] + ".." for x in v[:3])
        print(f"      {len(v)}x identical code ({v[0]['codeSizeBytes']}B): {addrs}"
              + (" ..." if len(v) > 3 else ""))
    print(f"\n  wrote {os.path.relpath(dest, ROOT)}")


if __name__ == "__main__":
    main()
