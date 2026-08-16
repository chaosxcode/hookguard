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

## Status

Early. Heuristic, regex-based, deliberately biased toward precision over recall.
Findings are starting points for review, not verdicts.
