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
Sourcify), not fixtures: **44% come back completely clean**. Two false-positive
classes were found by reading that corpus and fixed — callbacks that revert
unconditionally are no longer flagged for a missing PoolManager guard, and
sibling contracts that merely *import* `IHooks` are no longer treated as hooks
at all. Neither fix cost any detection: both fixtures behave identically.

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
