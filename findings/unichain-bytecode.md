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

## Finding 2: they are proxies after all — just not *standard* ones

All 25 hooks fetched, decoded, and opcode-walked. The first version of this
section stopped at "no EIP-1967 slot, no EIP-1167 pattern" and concluded zero
standard proxies. Classifying what actually feeds each `DELEGATECALL` — the
instructions immediately adjacent to the call — corrected that in the most
interesting direction:

| signal | count |
|---|---:|
| EIP-1967 implementation slot set | 0 / 25 |
| EIP-1167 minimal-proxy shape | 0 / 25 |
| `DELEGATECALL` with a **constant target** | **17 / 25** |
| distinct opaque implementations behind them | **7** |
| implementations that publish source | **0 / 7** |

Every one of those 17 is a textbook immutable proxy shell —
`PUSH20 <impl> GAS DELEGATECALL`, no storage read anywhere near it — pointed
at a hardcoded implementation contract:

| implementation | deployments | source |
|---|---:|---|
| `0xf7ce73d8…9f6f` | 11 | **opaque** |
| `0x69220726…a032` | 5 | **opaque** |
| `0xac0bb547…c500` | 4 | **opaque** |
| `0xaedf2fc7…af7b` | 4 | **opaque** |
| three others, 1 each | 3 | **opaque** |

So the launchpad families are not standalone hooks at all. Each address is a
thin, permanently-permissioned shell whose every swap executes inside one of
seven programs that **nobody can read**. "Zero standard proxies" was literally
true and substantively wrong: this is a proxy architecture standard tooling
does not see, governing dozens of pools per family, with an upgrade surface
(the deployer can ship a new implementation at will) and no published code on
either layer.

In the full census (88 contracts, 2+ pools) the same constant-target
signature covers 22 more shells, alongside two genuinely storage-derived
upgradeables — including the census's one 176-byte EIP-1967 delegate, which
the classifier identifies correctly.

*Method note:* classification reads only the instructions immediately
adjacent to each call site; a wide window initially produced false
attributions (PoolManager comparisons and zero-guards posing as targets).
Both the heuristic and its correction are visible in `src/bytecode.py`.

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

## Census, same day: every multi-pool hook on the chain

The pass above covered the 30 busiest unregistered hooks. Lowering the
threshold to any hook serving two or more pools — the launchpad-discounted
population the coverage finding identified as the one that matters — gives the
full picture of what exists off the registry on Unichain:

| | |
|---|---|
| unregistered hooks serving 2+ pools | **107** |
| of those, publishing verified source | **19 (17.8%)** |
| bytecode-analyzed (publish nothing) | **88 / 88** |
| standard proxies among them (EIP-1967) | **1** — a 176-byte contract delegating to `0xd26c…0909` |
| `DELEGATECALL` opcode present | 28 / 88 |
| `SELFDESTRUCT` opcode present | 35 / 88 |
| distinct programs across the 88 addresses | **77** |

Two things the wider sample changes:

- **Cloning is concentrated at the top.** The top-25 were 16 programs across
  25 addresses; across all 88 it is 77 programs — the identical-code families
  belong mostly to the busiest hooks. Depth of use, not prevalence.
- **Source publication does not improve with obscurity.** It was 17% at 10+
  pools and 17.8% at 2+. Whatever drives authors to verify, pool count is not
  it.

The nineteen newly readable hooks went through the source scanner too: corpus
now **301 contracts**, clean rate 56.1%, and still exactly **two HIGH
findings ecosystem-wide** — both the proven/pattern-level upgradeable-proxy
class. Everything the census added came back clean or advisory
(`PERMISSIONLESS_ATTACHMENT` on the second and third `UniderpHook`
deployments, an unbounded-dynamic-fee advisory on a 2-pool limit-order hook).

## What this is not

This is still not an audit and finds no vulnerability. `DELEGATECALL` presence
is not an upgradeable proxy; a full-permission address may be fully intended;
identical code under many addresses may be one well-audited template. What it
is: the first machine-readable facts about hooks that publish nothing — and a
demonstration that "no source" no longer means "no data".

## Reproduce

```bash
CHAIN=unichain python3 src/discover.py            # find every deployed hook
python3 src/verify_status.py                      # who publishes source (10+ pools)
CHAIN=unichain MIN_POOLS=2 python3 src/verify_status.py     # ...and 2+ pools
CHAIN=unichain python3 src/bytecode.py            # this pass (10+)
CHAIN=unichain MIN_POOLS=2 python3 src/bytecode.py          # census (2+)
```

Raw output: [`out/unichain-bytecode.json`](../out/unichain-bytecode.json).
The layout self-check re-runs on every invocation against whatever
source-verifiable hooks exist, so if Unichain ever upgrades its PoolManager to
final v4, the reversed-order claim fails loudly instead of rotting quietly.
