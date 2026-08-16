# Measuring HookGuard against real deployed hooks

*2026-08-16. Reproduce with `python3 src/corpus.py && python3 src/scan.py corpus`.*

The README claims HookGuard is biased toward precision. That was an assertion.
This is the record of checking it against real deployed code — including the two
false-positive classes the check found, and a correction to numbers that were
published earlier the same day.

## Corpus

Verified source for hooks in Uniswap's registry, pulled from Sourcify (no API
key required).

| | |
|---|---|
| hooks in the registry | 486 |
| source retrieved | **383** (78.8%) |
| not in Sourcify (404) | 58 |
| still rate-limited, retryable | 44 |
| **actual hook contracts after filtering** | **272** |

The registry marks all 486 `verifiedSource: true`, yet only ~79% are
retrievable from Sourcify — the rest are verified on explorers Sourcify does not
mirror. "Verified" is not a single portable fact, which is worth recording on
its own.

## What fires, and how often

Across **272** hook contracts:

| Rule | Severity | Contracts | % of corpus |
|---|---|---:|---:|
| `PERMISSIONLESS_ATTACHMENT` | HIGH | 101 | 37.1% |
| `PERMISSIONLESS_BY_DESIGN` | INFO | 30 | 11.0% |
| `UNBOUNDED_DYNAMIC_FEE` | MEDIUM | 30 | 11.0% |
| `MISSING_POOLMANAGER_GUARD` | HIGH | 20 | 7.4% |
| `REENTRANCY_SURFACE` | MEDIUM | 2 | 0.7% |
| `UPGRADEABLE_HOOK` | HIGH | 1 | 0.4% |

**120 of 272 contracts (44%) produce nothing at all.** That is the number that
matters. A scanner which flags everything is worthless; 44% of real deployed
hooks coming back silent is evidence the rules discriminate.

## Two false-positive classes, found by reading the corpus

### 1. Inert callbacks

`MISSING_POOLMANAGER_GUARD` fired **ten times on one contract**
(`ArrakisPrivateHook`). It implements `IHooks` directly rather than inheriting
`BaseHook`, so Solidity requires it to define all ten callbacks even though it
uses two — and **eight of the flagged ones do nothing but `revert`**.

An unguarded callback that reverts unconditionally has no state to desync.
Flagging it is noise, and ten findings on one contract is precisely how a tool
gets muted. The rule now skips callbacks that revert unconditionally or only
return a selector without mutating state.

That contract went from **11 findings to 2**.

### 2. Non-hooks in the same source bundle

More serious, and it invalidated numbers published earlier the same day.

Verified-source bundles ship the *whole project*, not just the hook. The filter
deciding "is this a hook" matched any file mentioning `IHooks` — which caught
sibling contracts that merely **import** it. Flaunch's `BidWall`, `PoolSwap`,
`ReferralEscrow` and `IndexerSubscriber` were all being analysed as hooks and
counted as findings. They are not hooks.

A contract now only qualifies if it declares `getHookPermissions()` or inherits
`BaseHook`/`IHooks` in its `is` clause. Importing a type is not implementing it.

| | before | after |
|---|---:|---:|
| "hook" contracts in corpus | 338 | **272** |
| clean rate | 36% | **44%** |
| `PERMISSIONLESS_ATTACHMENT` | 147 (43.5%) | **101 (37.1%)** |

**Correction:** an earlier version of this page reported 338 contracts, a 36%
clean rate and 43.5% for `PERMISSIONLESS_ATTACHMENT`. Those figures counted
non-hooks and were too high. The numbers above supersede them.

Both fixtures behave identically through both fixes — `GuardedHook` stays at
zero findings, `RiskyHook` still trips all four of its rules. Neither fix cost
any detection, which is the only kind worth making.

## What this still does not establish

**This is not a false-positive rate.** Producing one means adjudicating each
finding against what the contract actually intends, which requires the authors
or an auditor — not me reading my own tool's output and marking my own homework.

What it does establish:

- rule-by-rule firing rates on real deployed code rather than fixtures
- that 44% of the corpus comes back clean
- two false-positive classes, found by reading source, characterised and fixed
- that published numbers get corrected when they turn out to be wrong

`PERMISSIONLESS_ATTACHMENT` at 37.1% still deserves scrutiny. It may be
*correct* — v4 pool creation genuinely is permissionless, so a hook with no
`beforeInitialize` gate genuinely can be attached by anyone. The open question
is not whether the detection is accurate but whether it is **actionable**, and
only hook authors can answer that.

## Next

- Retry the remaining 44 rate-limited fetches (201 → 317 → 383 across three passes)
- Fall back to explorer sources for the 58 Sourcify misses
- Put a sample of `PERMISSIONLESS_ATTACHMENT` findings to their authors and
  record whether they consider them real — the only honest route to a
  false-positive rate
- Retire or downgrade any rule that cannot survive that
