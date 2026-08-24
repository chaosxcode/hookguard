# HookGuard

[![external installs](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/chaosxcode/hookguard/master/out/adoption.json)](https://github.com/chaosxcode/hookguard/blob/master/docs/ROADMAP.md)
[![self-test](https://github.com/chaosxcode/hookguard/actions/workflows/selftest.yml/badge.svg)](https://github.com/chaosxcode/hookguard/actions/workflows/selftest.yml)

A transparent, CI-native risk scanner for Uniswap v4 hooks.

**It is not an audit and never claims to be.** It is a heuristic pass that flags
documented v4 risk patterns early and cheaply, so scarce audit budget can be
aimed where it matters.

**Live status feed & dashboard:** <https://chaosxcode.github.io/hookguard/status/>

Machine-readable records follow the [HookScore spec draft](docs/HOOKSCORE-SPEC.md) — per-address JSON with published weights and confidence tiers.

## Add it to your hook in 60 seconds

```yaml
# .github/workflows/hookguard.yml
name: hookguard
on: [pull_request]

permissions:
  contents: read
  pull-requests: write   # only needed for the summary comment

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: chaosxcode/hookguard@v1
        with:
          paths: src
```

Annotations land on the offending lines; a single PR comment summarizes.
`fail-on: HIGH` by default — heuristics advise, they don't gate.

### Install & scan any repo, right now

```bash
pip install hookguard                      # 0.9.0 live on PyPI
hookguard scan https://github.com/owner/v4-hook-repo --html report.html
hookguard scan ./my-hooks --local           # offline, local directory
```

Or without installing:

```bash
python3 src/hookguard.py scan https://github.com/owner/v4-hook-repo --html report.html
```

Starting a new hook project? Use [hookguard-example](https://github.com/chaosxcode/hookguard-example)
— a minimal starter with HookGuard CI preinstalled, scanning clean by design.

Auto-detects hook directories, prints findings with an itemized risk score,
and writes a standalone HTML report. `--fail-on HIGH` exits non-zero for
pipeline use.

## Why

Uniswap's official [hooklist](https://github.com/Uniswap/hooklist) registers
**551 production hooks across 16 chains** (snapshot refreshed Aug 23, 2026 —
it grew from 486 in one week) — and explicitly disclaims being a safety
signal. A risk pass over that registry (`src/risk.py`):

| | |
|---|---|
| hooks with a published audit URL | **30 / 551 (5.4%)** |
| hooks that can move value (return-delta permissions) | **393 / 551 (71%)** |
| **value-moving AND no audit recorded** | **367 (67% of the ecosystem)** |
| upgradeable | 21 (3.8%) |
| verified source | 551 (100%) |

Unaudited share by chain: Ethereum 94.9%, Base 95.4%, Unichain 95.5%.

Hooks are trusted code in the swap path and pool creation is permissionless.
Bunni v2 — then the largest LP hook by TVL — was exploited for ~$8.3M in
September 2025 and shut down. Audit subsidies do not scale to 486 hooks.

*Caveat, stated plainly:* an empty `auditUrl` means the registry records no
audit, not that none exists. That ambiguity is itself the gap — there is no
machine-readable way for a router, LP, or integrator to tell a reviewed hook
from an unreviewed one.

## The registry is opt-in — so how much does it miss?

Registry coverage assumes hooks register themselves. Scanning **every
`Initialize` event in Unichain's full history** — every pool ever created and
the hook attached to it — measures the gap:

| | |
|---|---|
| pools ever created on Unichain | **7,539** |
| pools that attach a hook | **5,366** (71%) |
| distinct hook contracts deployed | **1,211** |
| of those, in Uniswap's registry | **15** |
| **registry coverage** | **1.24%** |

Stated carefully, because the raw number oversells it: 1,094 of the 1,211 serve
exactly one pool — launchpads minting a hook per token, not 1,094 distinct
designs. The population that matters is the **117** serving 2+ pools and the
**35** serving 10+. Even after that discount, **the two busiest hooks on
Unichain are not in the registry at all**.

> **Correction, Aug 23:** the registry moved. Four hooks named in this
> section — PrediX, UniMeme, Polymarket, UniswapCup — registered within days
> of these numbers going public. Live coverage is now **19 / 1,211 = 1.57%**,
> and the busiest still-unregistered hook is a 165-pool contract at
> `0x782d…8444`. Full note:
> [findings/author-outreach.md](findings/author-outreach.md). The Aug 19
> figures below stand as measured against the registry as it was.

Reproduce with `CHAIN=unichain python3 src/discover.py`. The scan aborts rather
than publish a partial result — an undercount is the one error that would
quietly invalidate the number.

## The hooks off the registry are also the unverified ones

Coverage is the smaller half of the problem. Taking the **30 unregistered
Unichain hooks that serve 10+ pools** — the population left after discounting
launchpad one-offs — and asking the block explorer whether each has published
source:

| | |
|---|---|
| registry hooks with verified source | **486 / 486 (100%)** |
| busiest unregistered hooks with verified source | **5 / 30 (17%)** |

The registry is 100% verified because publishing source is effectively a
condition of being listed. That number describes the listing process, not the
ecosystem. Off the registry, 25 of the 30 hooks sitting in the swap path of 10
or more live pools each have no published source at all — nothing to audit,
nothing to scan, nothing for an integrator to read.

The five that do publish source are not obscure: `PrediXHookProxyV2` (1,034
pools), `UniMemeHook` (777), `BunniHook` (50), `PolymarketHook` (34) and
`UniswapCupHook` (32). Recognisable names are the exception off-registry, not
the rule.

This is the ceiling on every source-level tool in v4, including this one.
HookGuard's own scanner needs source; on the hooks that most need checking,
there isn't any. Bytecode-level analysis is the only thing that reaches them.

The single busiest unregistered hook on Unichain, `PrediXHookProxyV2` at
**1,034 pools**, is a verified *proxy* — the address bits fix its permissions
forever and pools cannot detach, but the implementation behind it can still be
swapped.

Reproduce with `python3 src/verify_status.py`. Data:
[`out/unichain-unregistered-top.json`](out/unichain-unregistered-top.json).

## Reading the ones that publish nothing

A bytecode pass (`src/bytecode.py`, keyless and dependency-free) reaches
around source for those 25 hooks:

| signal | count |
|---|---:|
| standard proxies (EIP-1967 / EIP-1167) | **0 / 25** |
| `DELEGATECALL` opcode in runtime code | 17 / 25 |
| `SELFDESTRUCT` opcode in runtime code | 17 / 25 |
| distinct programs across the 25 addresses | **16** |

Several shared-code families sit at addresses whose permission bits are *all*
set — every callback, every return-delta flag, no published source.

It also settled something about the chain itself: Unichain's PoolManager is
the **v4 preview deployment**, and hook addresses there encode their callback
permissions in the reverse bit order from final v4 (validated against every
source-verifiable hook: 17/18 reversed vs 1/18). Any tool reading v4 hook
permissions off addresses with mainnet semantics misreads Unichain's.

Details: [`findings/unichain-bytecode.md`](findings/unichain-bytecode.md).

Extended to every unregistered hook serving 2+ pools — all 107 of them — the
picture holds: 19 publish source (17.8%, unchanged from the busiest tier), 88
were bytecode-analyzed with a single standard proxy among them, and 77
distinct programs account for the 88 addresses.

## What it checks

`src/scan.py` analyses **concrete, deployable** hook contracts (abstract bases,
interfaces, mocks and tests are skipped — a scanner that fires on everything is
noise) and reports:

| Rule | Severity | Mechanism |
|---|---|---|
| `PERMISSIONLESS_ATTACHMENT` | HIGH | No `beforeInitialize` gate or pool validation **and** the hook holds funds or keeps per-`PoolId` state. Anyone can create a pool with attacker-chosen tokens pointing at the hook. `onlyPoolManager` proves *the PoolManager* called you, not that the pool is trusted. |
| `PERMISSIONLESS_BY_DESIGN` | INFO | Same, but stateless and fund-free — usually intentional. |
| `MISSING_POOLMANAGER_GUARD` | HIGH | A callback with no `onlyPoolManager`-style guard on a contract that doesn't inherit `BaseHook`. |
| `UPGRADEABLE_HOOK` | HIGH | Address bits encode permissions forever and pools can't detach, but the implementation can be swapped. The upgrade admin is part of the trust boundary. |
| `DELTA_FLAG_MISMATCH` | MEDIUM | `RETURNS_DELTA` permission declared but no delta constructed. The inverse bricks **every** swap (DoS). |
| `DELTA_FLAG_UNUSED` | LOW | `afterSwapReturnsDelta` declared but the callback always returns a zero delta — dead weight on the permission surface. |
| `REVERT_DOS_RISK` | MEDIUM | External call in a required callback with no `try/catch`. A paused oracle bricks every pool using the hook — including LP exits. |
| `UNBOUNDED_DYNAMIC_FEE` | MEDIUM | Dynamic fee with no visible upper bound. |
| `REENTRANCY_SURFACE` | MEDIUM | Transfer inside a callback with no guard. One hook serves many pools. |

Rules derive from Trail of Bits' *Building secure Uniswap v4 hooks* (2026),
Uniswap's Security Framework, OpenZeppelin, Cyfrin, and the Bunni v2 and Cork
Protocol post-mortems.

## Usage

```bash
python3 src/risk.py                 # registry-wide risk profile -> out/risk.json
python3 src/scan.py path/to/src ...  # source scan            -> out/scan.json
```

## Does it actually discriminate?

Measured against **315 real deployed hooks** — registry bundles across nine
chains, plus the source-publishing production hooks that were *never*
registered (Unichain's off-registry hooks, up to 1,034 pools) — not fixtures:
**55% come back completely clean** (173/315), and only **2 carry any HIGH
finding** (<1%), both the upgradeable-proxy class. One of the two is proven,
not inferred: the proxy's implementation was read out of its EIP-1967 slot
on-chain.

Eight false-positive classes have been found by reading that corpus and fixed.
Three were caught only by verifying findings before contacting their authors —
and the tool's highest-firing rule was **downgraded from HIGH to MEDIUM** as a
result, because it turned out to detect accurately but could not justify the
severity it claimed. The second pass then found three more spellings of an
already-fixed class and left its flagship HIGH rule with **zero** findings
ecosystem-wide; the details are the interesting part:
[docs/precision.md](docs/precision.md).

Full method, per-rule firing rates, and what it does *not* establish:
[docs/precision.md](docs/precision.md).

## Use it in CI

Add this to `.github/workflows/hookguard.yml` in your hook repo. It runs on
every pull request and annotates the offending lines.

```yaml
name: hookguard
on: [pull_request]

permissions:
  contents: read
  pull-requests: write   # only needed for the summary comment

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: chaosxcode/hookguard@v1
        with:
          paths: src
```

| Input | Default | Meaning |
|---|---|---|
| `paths` | `src` | Space-separated paths. Directories are searched recursively for `.sol`. |
| `fail-on` | `HIGH` | Severity that fails the check: `HIGH`, `MEDIUM`, `LOW`, or `never`. |
| `comment` | `true` | Maintain one PR comment, edited in place. Needs `pull-requests: write`. |
| `json-out` | *(none)* | Write machine-readable results to this path. |

Outputs `high`, `total` and `contracts` for downstream steps.

**On `fail-on`.** The default fails the check only on HIGH. HookGuard is a
heuristic pattern scanner, so blocking a merge on a MEDIUM would be overreach —
MEDIUM and below are advisory. Set `fail-on: never` if you want the annotations
without a gate, which is the right setting while you decide whether you trust it.

**Forks.** Pull requests from forks get a read-only token, so the comment step
is skipped automatically. Annotations and the job summary still appear; the run
does not fail because of it.

## Status

Early. Heuristic, regex-based, deliberately biased toward precision over recall.
Findings are starting points for review, not verdicts.

Where this is going: [docs/ROADMAP.md](docs/ROADMAP.md).

**Live status feed:** every known hook now has a machine-readable record at
`docs/status/<chain>/<address>.json`, one aggregate `feed.json`, and a
dashboard to read it all — [docs/status/index.html](docs/status/index.html).
