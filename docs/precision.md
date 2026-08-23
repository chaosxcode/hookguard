# Measuring HookGuard against real deployed hooks

*2026-08-16. Reproduce with `python3 src/corpus.py && python3 src/scan.py corpus`.*

The README claims HookGuard is biased toward precision. That was an assertion.
This is the record of checking it against real deployed code — the three
false-positive classes that check found, and a correction to numbers published
earlier the same day.

Two of the four were found only because I sat down to verify findings *before*
sending them to the teams they concerned. Both would have been wrong. That is
the entire argument for verifying first.

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
| `PERMISSIONLESS_ATTACHMENT` | MEDIUM | 71 | 26.1% |
| `PERMISSIONLESS_BY_DESIGN` | INFO | 23 | 8.5% |
| `UNBOUNDED_DYNAMIC_FEE` | MEDIUM | 30 | 11.0% |
| `MISSING_POOLMANAGER_GUARD` | HIGH | 10 | 3.7% |
| `REENTRANCY_SURFACE` | MEDIUM | 2 | 0.7% |
| `UPGRADEABLE_HOOK` | HIGH | 1 | 0.4% |

**153 of 272 contracts (56%) produce nothing at all, and only 11 (4.0%) carry any HIGH finding at all.** That is the number that
matters. A scanner which flags everything is worthless; half of all real deployed hooks coming back
silent is evidence the rules discriminate.

## Five false-positive classes, found by reading the corpus

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

### 2. Named return variables read as state writes

Verifying a finding before contacting Arrakis, by hand: their `beforeSwap` was
flagged for a missing PoolManager guard. Reading it, the function assigns two
**named return variables** and calls one `internal view` helper. It writes
nothing. Calling it directly from anywhere changes no state, so the finding was
wrong.

The inert check had counted `funcSelector = IHooks.beforeSwap.selector;` as a
mutation. Assignments whose target is a declared return name or a local are now
ignored, and any callback declared `view`/`pure` is inert by definition.

`MISSING_POOLMANAGER_GUARD` went from 20 contracts (7.4%) to **10 (3.7%)** —
half its findings were this class. It also correctly stopped flagging the
oracle-reading `beforeSwap` in our own risky fixture, which reads and returns
without writing.

### 3. Pool validation that isn't an allowlist

Preparing to contact the author of `WsgemBackstopHook`, I read it. It has no
`beforeInitialize` gate — which is what the rule fires on — but its `beforeSwap`
opens with:

```solidity
if (Currency.unwrap(key.currency0) != Currency.unwrap(currency0)
    || Currency.unwrap(key.currency1) != Currency.unwrap(currency1))
    revert PoolNotSupported();
```

An attacker can initialise a pool against that hook, and **every swap reverts**.
The author handled it. The rule only recognised PoolId allowlists, so it missed
validation by currency comparison — a perfectly ordinary way to do the same job.

`PERMISSIONLESS_ATTACHMENT` went from 101 contracts (37.1%) to **85 (31.2%)**,
and the clean rate rose from 44% to **50%**.

Had this gone out unverified, it would have told a named developer his hook had
a HIGH severity issue that he had explicitly already solved.

### 4. Pool validation via a registration flag

`SwayHookJIT` reverts `PoolNotInitialized()` for any pool absent from its own
`vaults` mapping. Attacker-created pools bounce off it. That is the same guard
as an allowlist, expressed as a per-pool registration flag — a fifth spelling of
the same idea, and the rule missed it too.

### 5. Non-hooks in the same source bundle

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

Both fixtures behave identically through all five fixes — `GuardedHook` stays at
zero findings, `RiskyHook` still trips all four of its rules. No fix cost a true
detection, which is the only kind worth making.

## The rule that could not survive verification

`PERMISSIONLESS_ATTACHMENT` was the highest-firing rule and it has now been
**wrong in half of every finding I hand-checked**. Not because the detection is
inaccurate — the flagged hooks genuinely have no `beforeInitialize` gate — but
because there turned out to be at least five distinct, legitimate ways to
validate a pool, and each hand-check found another one.

Two conclusions followed, and both are implemented:

1. Validation detection now covers currency comparison, PoolId allowlists,
   registration flags, and named rejection errors.
2. **The rule is downgraded from HIGH to MEDIUM**, and reworded. It no longer
   asserts that an attacker can corrupt state. It says the hook can be attached
   by any pool, that whether this is exploitable depends on what such a pool can
   reach, and that the author should confirm the open attachment is intended.

That last part matters. Deciding whether an attacker-chosen pool can cause harm
requires reading each contract's full logic — audit work. Claiming HIGH severity
for something this tool cannot determine was overreach, and shipping it at HIGH
would have failed builds on a claim it could not support.

`docs/precision.md` previously said the next step was to "retire or downgrade
any rule that cannot survive." This is that, applied to the tool's own flagship
rule.

## What this still does not establish

**This is not a false-positive rate.** Producing one means adjudicating each
finding against what the contract actually intends, which requires the authors
or an auditor — not me reading my own tool's output and marking my own homework.

What it does establish:

- rule-by-rule firing rates on real deployed code rather than fixtures
- that 56% of the corpus comes back clean and only 4% carries a HIGH finding
- five false-positive classes, found by reading source, characterised and fixed
- that published numbers get corrected when they turn out to be wrong

`PERMISSIONLESS_ATTACHMENT` now sits at 26.1% and MEDIUM, which is an honest
place for it: the detection is accurate, the consequence is unproven.

## Second pass: completing the corpus, and a rule that went silent

*2026-08-23. Reproduce with `python3 src/corpus.py --chain unichain`,
`python3 src/unregistered_source.py`, then `python3 src/scan.py corpus`.*

The first pass measured 272 contracts out of a registry that claims 486. This
pass closes most of that distance and points the scanner at production hooks
that were never in the registry at all:

- **Retry passes plus a keyless Blockscout fallback** (Sourcify → Blockscout →
  Etherscan-if-keyed, provenance recorded per contract) recovered the 44
  rate-limited fetches and part of the Sourcify-miss tail.
- **`src/unregistered_source.py`** pulls published source for the five
  *unregistered* Unichain hooks serving 10+ pools — real production hooks in
  the swap path of up to 1,034 pools that no registry-based corpus would ever
  include. It also follows verified proxies to their implementation; where the
  explorer lists none (`PrediXHookProxyV2`), it reads the EIP-1967 storage slot
  straight off the chain.

**A correction to the denominator.** The registry's 486 rows contain 37
same-chain duplicate listings — the same address registered twice under two
names. Unique (chain, address) pairs: **449**, not 486. Earlier "383 with
source" figures counted those duplicates twice. On unique contracts, keyless
retrieval now reaches **365 / 449**.

### The measurement

Against **291 hook contracts** (registry bundles plus the six off-registry
entries):

| Rule | Severity | Contracts | % of corpus |
|---|---|---:|---:|
| `PERMISSIONLESS_ATTACHMENT` | MEDIUM | 79 | 27.1% |
| `UNBOUNDED_DYNAMIC_FEE` | MEDIUM | 32 | 11.0% |
| `PERMISSIONLESS_BY_DESIGN` | INFO | 24 | 8.2% |
| `UPGRADEABLE_HOOK` | HIGH | 2 | 0.7% |
| `REENTRANCY_SURFACE` | MEDIUM | 2 | 0.7% |
| `REVERT_DOS_RISK` | MEDIUM | 1 | 0.3% |
| `MISSING_POOLMANAGER_GUARD` | HIGH | **0** | **0%** |

**165 of 291 (56.7%) come back completely clean. Exactly two carry any HIGH
finding — both the upgradeable-proxy class.** One of them is not an inference:
`PrediXHookProxyV2`'s implementation was read out of its EIP-1967 slot on-chain.
(`NFTXV4Hook` is pattern-level: `Initializable` in source, DELEGATECALL in
runtime bytecode confirmed via `eth_getCode`, empty EIP-1967 slot — kept at
HIGH on the pattern, labelled as unproven.)

*Addendum, later the same day:* extending retrieval to every unregistered
Unichain hook serving 2+ pools added ten more source bundles, moving the
corpus to **301 contracts / 56.1% clean** with the same two HIGH findings.
Nothing above shifted by more than a point.

### Three more false-positive classes, found by hand-checking every new HIGH

Finishing the corpus briefly took HIGH findings from 11 to 29. Every one of
the new ones was wrong, and each failure taught a spelling:

6. **Custom-named modifiers.** `SuperStrategy` and `wASSBLASTER` gate callbacks
   with `onlyManager`; `CellHook` uses `onlyPM`. All are the PoolManager check
   with an immutable named `manager` or `poolManager`. The rule knew only the
   OpenZeppelin spelling.
7. **Phantom implementations.** Explorer bundles concatenate whole projects.
   `MoonsendFeeHook` ships an `interface IHooks` whose bodyless declarations
   sat above the real contract — and the matcher happily let a declaration
   adopt the next contract's opening brace as its function body. Eight phantom
   findings from two files.
8. **Inline negated checks.** `LiquidityGenHook` opens with
   `if (msg.sender != poolManager) revert Unauthorized();`. The fast path only
   recognised `msg.sender == address(...)`.
9. **Assert-style helpers.** `Hook.sol` and `SlopPoolHook` call tiny internal
   functions (`_assertPoolManager()`) whose whole body is the comparison.

`MISSING_POOLMANAGER_GUARD` was rewritten to be structural rather than textual:
it parses modifier bodies, collects short internal functions that compare
`msg.sender`, accepts inline comparisons of either polarity, and never treats a
declaration as an implementation.

**The result: zero findings across all 291 contracts.** Every one of the ten
contracts it flagged in the first pass turned out to be an artifact of
spellings 6–9. The rule stays, because genuinely naked callbacks remain the
failure it exists for and the fixture proves it still fires — but the honest
summary today is that across every measurable hook in the ecosystem, this tool
found no unguarded callback at HIGH severity. That sentence was only writable
after the rewrite; the version of the rule that produced the first pass's ten
findings was measuring Solidity style, not security.

### The off-registry hooks specifically

| Hook | Pools | Result |
|---|---:|---|
| `PrediXHookProxyV2` (+impl) | 1,034 | proxy HIGH (proven upgradeable); implementation clean |
| `UniMemeHook` | 777 | MEDIUM — verified by reading source: no pool gate, takes platform fee via `poolManager.take()` on any attached pool |
| `BunniHook` | 50 | MEDIUM — same class, advisory |
| `PolymarketHook` | 34 | clean |
| `UniswapCupHook` | 32 | clean |

## What this still does not establish

(unchanged from above, with one addition)

- Findings against named projects remain advisories awaiting author response;
  the MEDIUM wording says "confirm", not "vulnerable"
- counting basis: one result row per hook contract per bundle; cross-chain
  duplicates of the same address are separate rows

## Next

- Retry the remaining rate-limited fetches until the Sourcify-miss tail is
  exhausted or explained
- Put a sample of `PERMISSIONLESS_ATTACHMENT` findings to their authors and
  record whether they consider them real — the only honest route to a
  false-positive rate
- Bytecode-level analysis for the hooks that publish nothing — the 25
  unverified Unichain hooks this corpus can never reach
