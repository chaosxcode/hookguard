#!/usr/bin/env python3
"""
HookGuard — source pattern scanner for Uniswap v4 hooks.

CI/Foundry-native: point it at a repo, it flags documented v4 hook risk patterns
BEFORE deployment. Heuristic and transparent by design — it is not an audit and
never claims to be. Every rule cites the mechanism it is checking.

Rules derive from: Trail of Bits "Building secure Uniswap v4 hooks" (2026),
Uniswap's own Security Framework, OpenZeppelin, Cyfrin, and the Bunni v2
($8.3M, Sept 2025) and Cork Protocol (~$10M+) post-mortems.
"""
import re, sys, os, json, glob

# permission -> the callback that must implement it
CALLBACKS = ['beforeInitialize','afterInitialize','beforeAddLiquidity','afterAddLiquidity',
             'beforeRemoveLiquidity','afterRemoveLiquidity','beforeSwap','afterSwap',
             'beforeDonate','afterDonate']

def strip_comments(s):
    # Replace comments with the same number of newlines instead of deleting them,
    # so every character offset still maps to its real line in the source file.
    # Without this, CI annotations point at the wrong line.
    keep_nl = lambda m: '\n' * m.group(0).count('\n')
    s = re.sub(r'/\*.*?\*/', keep_nl, s, flags=re.S)
    return re.sub(r'//[^\n]*', '', s)

def line_of(src, pos):
    """1-indexed line number for a character offset."""
    return src.count('\n', 0, pos) + 1

def analyze(path):
    raw = open(path, encoding='utf-8', errors='ignore').read()
    src = strip_comments(raw)
    # only look at things that are actually hooks
    if not re.search(r'getHookPermissions|IHooks|BaseHook', src):
        return None
    # Only analyse CONCRETE, DEPLOYABLE hooks. Abstract bases, interfaces, mocks and
    # tests are templates or scaffolding — flagging them is noise, and a scanner that
    # fires on everything trains people to ignore it. Precision over recall.
    cm = re.search(r'(abstract\s+)?contract\s+(\w+)', src)
    if not cm or cm.group(1):
        return None                                   # abstract base
    name = cm.group(2)
    low = path.lower()
    if any(k in low for k in ('/mocks/', '/mock/', '/test/', '/tests/')) or \
       re.search(r'(Mock|Test|Harness|Example)$', name):
        return None                                   # not deployed
    F = []
    decl_line = line_of(src, cm.start())
    perms = re.search(r'getHookPermissions\s*\([^)]*\)[^{]*\{(.*?)\n\s*\}', src, re.S)
    pblock = perms.group(1) if perms else ''
    declared = {c: bool(re.search(rf'\b{c}\s*:\s*true', pblock)) for c in CALLBACKS}
    ret_delta = {k: bool(re.search(rf'\b{k}\s*:\s*true', pblock)) for k in
                 ['beforeSwapReturnsDelta','afterSwapReturnsDelta',
                  'afterAddLiquidityReturnsDelta','afterRemoveLiquidityReturnsDelta']}

    # R1 permissionless pool attachment: anyone can create a pool pointing at this hook
    if not declared.get('beforeInitialize') and \
       not re.search(r'(allowlist|allowList|whitelist|authorizedPool|validPool|onlyValidPool|poolId\s*==|PoolIdLibrary\.toId)', src, re.I):
        # Severity is driven by what an attacker-created pool could actually corrupt.
        # A stateless observer hook is fine being permissionless — that is often the design.
        # A hook holding funds or per-pool accounting is not.
        holds_funds = bool(re.search(r'(safeTransfer|transferFrom|\.transfer\(|take\(|settle\(|mint\(|burn\()', src))
        pool_state  = bool(re.search(r'mapping\s*\(\s*PoolId', src))
        if holds_funds or pool_state:
            F.append(('HIGH','PERMISSIONLESS_ATTACHMENT',
                'No beforeInitialize gate or pool validation, AND the hook holds funds or keeps per-PoolId state. '
                'v4 pool creation is permissionless: anyone can create a pool with attacker-chosen tokens pointing at '
                'this hook and drive its callbacks to corrupt that state. onlyPoolManager proves the PoolManager '
                'called you, NOT that the pool is one you trust.', decl_line))
        else:
            F.append(('INFO','PERMISSIONLESS_BY_DESIGN',
                'Any pool may attach this hook (no beforeInitialize gate). No funds or per-pool state detected, so '
                'this is likely intentional — confirm it is.', decl_line))

    # R2 callbacks lacking the PoolManager guard (only matters if not using BaseHook)
    uses_basehook = bool(re.search(r'\bis\b[^{]*BaseHook', src))
    if not uses_basehook:
        for c in CALLBACKS:
            m = re.search(rf'function\s+{c}\s*\([^)]*\)([^{{]*)\{{', src, re.S)
            if m and not re.search(r'onlyPoolManager|onlyByPoolManager|poolManagerOnly|msg\.sender\s*==\s*address\(\s*poolManager', m.group(1)+src[m.end():m.end()+200]):
                F.append(('HIGH','MISSING_POOLMANAGER_GUARD',
                    f'{c}() has no onlyPoolManager-style guard and the contract does not inherit BaseHook. '
                    'Anyone can call the callback directly and desync hook state.', line_of(src, m.start())))

    # R3 return-delta declared but callback never returns a non-zero delta (or vice versa)
    if ret_delta['beforeSwapReturnsDelta']:
        body = re.search(r'function\s+_?beforeSwap\s*\(.*?\n\s*\}', src, re.S)
        if body and not re.search(r'toBeforeSwapDelta|BeforeSwapDelta\s*\(', body.group(0)):
            F.append(('MEDIUM','DELTA_FLAG_MISMATCH',
                'beforeSwapReturnsDelta permission declared but beforeSwap does not construct a BeforeSwapDelta. '
                'Flag/implementation mismatch — the inverse (returning a delta without the flag) makes EVERY swap revert (DoS).', line_of(src, body.start())))
    for k, cb in [('afterSwapReturnsDelta','afterSwap')]:
        if ret_delta[k]:
            body = re.search(rf'function\s+_?{cb}\s*\(.*?\n\s*\}}', src, re.S)
            if body and not re.search(r'return\s*\([^)]*,\s*(?!0\b)', body.group(0)):
                F.append(('LOW','DELTA_FLAG_UNUSED', f'{k} declared but {cb} appears to always return a zero delta.', line_of(src, body.start())))

    # R4 revert-DoS: external dependency inside a required callback with no failure path
    for c in ['beforeSwap','afterSwap']:
        if declared.get(c):
            body = re.search(rf'function\s+_?{c}\s*\(.*?\n\s*\}}', src, re.S)
            if body:
                b = body.group(0)
                ext = re.search(r'\b(latestRoundData|getPrice|oracle\.|\.call\(|staticcall|IERC20\([^)]*\)\.(transfer|transferFrom))', b)
                if ext and 'try ' not in b:
                    F.append(('MEDIUM','REVERT_DOS_RISK',
                        f'{c} makes an external call ({ext.group(1)}) with no try/catch. If the dependency reverts or '
                        'is paused, every swap on every pool using this hook is bricked — including LP exits.', line_of(src, body.start() + ext.start())))

    # R5 unbounded dynamic fee
    if re.search(r'DYNAMIC_FEE_FLAG|updateDynamicLPFee', src):
        if not re.search(r'(MAX_FEE|maxFee|require\s*\([^)]*fee\s*<|fee\s*=\s*fee\s*>\s*\w+\s*\?)', src):
            F.append(('MEDIUM','UNBOUNDED_DYNAMIC_FEE',
                'Dynamic fee is set with no visible upper bound. An unbounded or manipulable fee lets a privileged '
                'party (or manipulated input) tax swappers/LPs arbitrarily.', decl_line))

    # R6 upgradeable: address bits are immutable, implementation is not
    if re.search(r'\b(UUPSUpgradeable|Initializable|TransparentUpgradeableProxy|_authorizeUpgrade|delegatecall)\b', src):
        F.append(('HIGH','UPGRADEABLE_HOOK',
            'Upgradeable/delegatecall pattern. The hook ADDRESS permanently encodes permissions and pools cannot '
            'detach, but the implementation can be swapped — the upgrade admin is part of the trust boundary.', decl_line))

    # R7 reentrancy surface: external call in a callback with no guard
    if not re.search(r'ReentrancyGuard|nonReentrant|_locked|transient', src):
        for c in CALLBACKS:
            if not declared.get(c): continue
            body = re.search(rf'function\s+_?{c}\s*\(.*?\n\s*\}}', src, re.S)
            if body and re.search(r'\.call\{|\.call\(|safeTransfer|transferFrom|\.send\(', body.group(0)):
                F.append(('MEDIUM','REENTRANCY_SURFACE',
                    f'{c} performs a token/native transfer with no reentrancy guard. One hook serves many pools; '
                    'assume re-entry into this and other pools before the callback sequence completes.', line_of(src, body.start())))
                break
    return {'file': path, 'contract': name, 'findings': F,
            'declared': [c for c,v in declared.items() if v],
            'returnsDelta': [k for k,v in ret_delta.items() if v]}

def main(paths):
    files = []
    for p in paths:
        files += glob.glob(os.path.join(p, '**', '*.sol'), recursive=True) if os.path.isdir(p) else [p]
    results = [r for r in (analyze(f) for f in sorted(set(files))) if r]
    sev = {'HIGH':0,'MEDIUM':0,'LOW':0,'INFO':0}
    print(f"HookGuard source scan — {len(results)} hook contracts analysed\n" + "="*74)
    flagged = 0
    for r in results:
        if not r['findings']: continue
        if any(f[0] in ('HIGH','MEDIUM','LOW') for f in r['findings']): flagged += 1
        print(f"\n  {r['contract']}   ({os.path.relpath(r['file'])})")
        if r['declared']: print(f"    permissions: {', '.join(r['declared'])}")
        for f in r['findings']:
            s, code, msg = f[0], f[1], f[2]
            sev[s] += 1
            print(f"    [{s:<6}] {code}\n             {msg[:150]}")
    print("\n" + "="*74)
    print(f"  contracts analysed : {len(results)}")
    print(f"  contracts flagged  : {flagged}")
    print(f"  findings           : HIGH {sev['HIGH']}  MEDIUM {sev['MEDIUM']}  LOW {sev['LOW']}  INFO {sev['INFO']}")
    json.dump(results, open('out/scan.json','w'), indent=1)
    print("  wrote out/scan.json")

if __name__ == '__main__':
    main(sys.argv[1:] or ['/tmp/v4t/src'])
