# HookGuard

A transparent, CI-native risk scanner for Uniswap v4 hooks.

**It is not an audit and never claims to be.** It is a heuristic pass that flags
documented v4 risk patterns early and cheaply, so scarce audit budget can be
aimed where it matters.

## Why

Uniswap's official [hooklist](https://github.com/Uniswap/hooklist) registers
**486 production hooks across 16 chains** — and explicitly disclaims being a
safety signal. A risk pass over that registry (`src/risk.py`):

| | |
|---|---|
| hooks with a published audit URL | **29 / 486 (6.0%)** |
| hooks that can move value (return-delta permissions) | **340 / 486 (70%)** |
| **value-moving AND no audit recorded** | **315 (65% of the ecosystem)** |
| upgradeable | 20 (4.1%) |
| verified source | 486 (100%) |

Unaudited share by chain: Ethereum 94.7%, Base 95.1%, Unichain 94.4%.

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

Measured against **272 real deployed hooks** (verified source pulled from
Sourcify), not fixtures: **56% come back completely clean**, and only **4% carry any HIGH finding**. Five false-positive
classes were found by reading that corpus and fixed. Three were caught only by
verifying findings before contacting their authors — and the tool's
highest-firing rule was **downgraded from HIGH to MEDIUM** as a result, because
it turned out to detect accurately but could not justify the severity it
claimed.

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
