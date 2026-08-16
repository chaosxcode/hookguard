# Measuring HookGuard against real deployed hooks

*2026-08-16, 383 of 486 registered hooks. Reproduce with `python3 src/corpus.py && python3 src/scan.py corpus`.*

The README claims HookGuard is biased toward precision. Until now that was an
assertion. This is the start of checking it against real code rather than
fixtures.

## Corpus

Verified source for hooks in Uniswap's registry, fetched from Sourcify (no API
key required).

| | |
|---|---|
| hooks in the registry | 486 |
| source retrieved | **383** (78.8%) |
| not in Sourcify (404) | 58 |
| still rate-limited, retryable | 44 |
| concrete hook contracts after filtering | **338** |

The registry marks all 486 as `verifiedSource: true`, but only a fraction are
retrievable from Sourcify — the rest are verified on block explorers Sourcify
does not mirror. That gap is worth recording on its own: "verified" is not a
single, portable fact.

The 338 figure is lower than 383 because the scanner deliberately skips
abstract bases, interfaces, mocks and tests before any rule runs.

## What fires, and how often

Across 338 concrete hook contracts:

| Rule | Severity | Findings | Contracts | % of corpus |
|---|---|---:|---:|---:|
| `PERMISSIONLESS_ATTACHMENT` | HIGH | 147 | 147 | 43.5% |
| `MISSING_POOLMANAGER_GUARD` | HIGH | 60 | 25 | 7.4% |
| `PERMISSIONLESS_BY_DESIGN` | INFO | 48 | 48 | 14.2% |
| `UNBOUNDED_DYNAMIC_FEE` | MEDIUM | 31 | 31 | 9.2% |
| `REENTRANCY_SURFACE` | MEDIUM | 2 | 2 | 0.6% |
| `UPGRADEABLE_HOOK` | HIGH | 1 | 1 | 0.3% |

**121 of 338 contracts (36%) produce nothing at all.** That matters: a scanner
that flags everything is worthless, and over a third of real deployed hooks coming
back clean is evidence the rules discriminate.

## A false-positive class this pass found and fixed

`MISSING_POOLMANAGER_GUARD` was firing **10 times on a single contract**
(`ArrakisPrivateHook`). Reading the source: it implements `IHooks` directly
rather than inheriting `BaseHook`, so it must define all ten callbacks even
though it only uses two. **Eight of the flagged callbacks do nothing but
`revert`.**

An unguarded callback that reverts unconditionally has no state to desync.
Flagging it is noise, and ten findings on one contract is exactly the kind of
output that trains people to mute a tool.

The rule now skips callbacks that are *inert* — those that revert
unconditionally, or that only return a selector without mutating state.

| | before | after |
|---|---:|---:|
| findings on `ArrakisPrivateHook` | 11 | **2** |
| worst single contract, whole corpus | 11 | **5** |

The fix removed roughly a quarter of all `MISSING_POOLMANAGER_GUARD` findings.

Both fixtures still behave identically: `GuardedHook` stays at zero findings,
`RiskyHook` still trips all four of its rules. So this removed noise without
costing detection — which is the only kind of precision fix worth making.

## What this does not establish

**This is not a false-positive rate.** Producing one means adjudicating each
finding against what the contract actually intends, which needs the authors or
an auditor — not me reading it alone and marking my own homework.

What this pass establishes is narrower and worth stating plainly:

- rule-by-rule firing rates on real deployed code, not fixtures
- that a third of the corpus comes back clean
- one false-positive class, found by reading source, characterised and fixed

`PERMISSIONLESS_ATTACHMENT` at 43.5% deserves particular scrutiny. It may well be
*correct* — v4 pool creation genuinely is permissionless, so a hook with no
`beforeInitialize` gate genuinely can be attached by anyone. The open question
is not whether the detection is accurate but whether it is *actionable*, and
that needs hook authors to answer.

## Next

- Retry the remaining 44 rate-limited fetches (201 -> 317 -> 383 so far across three passes)
- Fall back to block-explorer sources for the 58 Sourcify misses
- Take a sample of `PERMISSIONLESS_ATTACHMENT` findings to their authors and
  record whether they consider them real — the only honest route to a
  false-positive rate
- Retire or downgrade any rule that cannot survive that
