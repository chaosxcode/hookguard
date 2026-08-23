# The unread 25, read anyway: what bytecode says about Unichain's unverified hooks

*August 23, 2026*

The [coverage finding](unichain-hook-coverage.md) left this sentence standing:
the 25 busiest unregistered Unichain hooks publish no source, so nothing
source-level can reach them. This pass stops treating them as unreachable.
Three layers, ordered by how much they cost to trust: the hook's own address,
one storage slot, and the runtime bytecode.

    python3 src/bytecode.py        # -> out/unichain-bytecode.json

No API key, no disassembler dependency: keccak-256 is implemented inline, the
EVM walk skips PUSH operands so opcodes are real opcodes, and every claim below
re-derives itself from public chain data on each run.

## Finding 1: Unichain is running the v4 *preview* release, and its permission bits are laid out backwards

HookGuard's discovery script already showed the tell: Unichain's PoolManager
sits at `0x1F984000...0000000004` — the address family of the **v4 preview
deployment** — while Ethereum mainnet runs final v4 at
`0x000000000004444c5dc75cB358380D2e3dE08A90`. The interfaces differ too, and
not cosmetically. Deriving selectors from deployed bytecode confirms the
preview shapes: `PoolKey` ends with `hooks` (`(address,address,uint24,int24,address)`)
and `SwapParams` carries `(bool,int256,uint160)` — final v4 orders `PoolKey`
differently and added `exactInput`.

The consequence nobody has documented: **the permission bits encoded in a
hook's address read differently on this chain.**

Validated against every Unichain hook whose verified source yields its true
`getHookPermissions` (18 contracts): the ten callback-flag positions agree
with a **bit-reversed** reading in **17/18** cases and with the final-v4
reading in **1/18**. Read UniMemeHook's address with mainnet semantics and you
conclude it hooks `beforeSwap`; read it correctly and it hooks `afterSwap`.
The four return-delta positions match *neither* layout anywhere, so this tool
reports them raw and claims nothing.

Anyone building address-based permission checks for v4 — routers, LP dashboards,
scanners — will systematically misread Unichain hooks until they handle the
preview layout. HookGuard now ships both decodings plus a live self-check
against source-verifiable hooks, so the assumption degrades loudly rather than
silently.

## Finding 2: the unverified population is not proxied — it carries its switches internally

All 25 hooks fetched, decoded, opcode-walked:

| signal | count |
|---|---:|
| EIP-1967 implementation slot set | **0 / 25** |
| EIP-1167 minimal-proxy shape | **0 / 25** |
| `DELEGATECALL` opcode present | 17 / 25 |
| `SELFDESTRUCT` opcode present | 17 / 25 |
| `getHookPermissions` selector present | 24 / 25 |

Unlike `PrediXHookProxyV2` — whose proxy was proven by reading its EIP-1967
slot — none of the unread 25 delegate through a standard pattern. Where
`DELEGATECALL` and `SELFDESTRUCT` appear together, they appear *inside* the
hook's own runtime code, clustered in the shared-code families below. Opcode
presence does not prove an upgrade path or a kill switch; it proves the
capability exists in code that nobody can read. That is precisely the gap an
underwriter cannot price from source alone.

## Finding 3: 25 addresses, 16 programs — and some were born with every permission

keccak of each contract's runtime code groups the population into **16
distinct programs**, with byte-identical clones under different addresses:

| program size | copies | pools served |
|---|---|---|
| 18,541 B | 4 (+4 more in a second variant of the same size) | 14–15 each |
| 21,272 B | 4 | 15 each |
| … | singles down to one 6.9 kB hook serving 165 pools | |

Worse than the duplication: several families sit at addresses whose low
fourteen bits are **all set** — every callback flag and every return-delta
flag switched on. Under either bit-layout reading, that is the maximum-trust
surface a v4 hook can declare: it can intercept initialization, both liquidity
directions, swaps, donations, and move value via all four delta mechanisms.
These are live in ten-plus pools' swap paths each, and there is no source for
any of them.

## What this is not

This is still not an audit and finds no vulnerability. `DELEGATECALL` presence
is not an upgradeable proxy; a full-permission address may be fully intended;
identical code under many addresses may be one well-audited template. What it
is: the first machine-readable facts about hooks that publish nothing — and a
demonstration that "no source" no longer means "no data".

## Reproduce

```bash
CHAIN=unichain python3 src/discover.py            # find every deployed hook
python3 src/verify_status.py                      # who publishes source
CHAIN=unichain python3 src/bytecode.py            # this pass
```

Raw output: [`out/unichain-bytecode.json`](../out/unichain-bytecode.json).
The layout self-check re-runs on every invocation against whatever
source-verifiable hooks exist, so if Unichain ever upgrades its PoolManager to
final v4, the reversed-order claim fails loudly instead of rotting quietly.
