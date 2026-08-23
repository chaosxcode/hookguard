# Author outreach ledger

*Opened August 23, 2026.*

[docs/precision.md](../docs/precision.md) named the one honest route to a
false-positive rate: put findings to their authors and record what they say.
This ledger is that record, public by default. Rules of engagement:

- advisories only — every message states plainly it is not a vulnerability
  claim and not an audit; the question is always "is this intended?"
- nothing is sent before the flagged path is hand-read in full; anything we
  cannot fully verify (external dependencies whose behavior decides the
  question) is marked unverified and either excluded or sent with the gap
  stated inline
- responses are published verbatim if the author does not object; silence is
  recorded as silence, never as confirmation

## Sample selection

Wave 1 targets the off-registry Unichain hooks flagged `PERMISSIONLESS_
ATTACHMENT` — the population with no listing process behind them, where an
author conversation settles the question fastest.

| target | pools | status |
|---|---:|---|
| UniderpHook ×3 (`0xcc2e…`, `0xe5cd…`, `0x966c…`) | 114 / 4 / 3 | **sent** — [Uniderp-fun/uniderp-hook-smart-contract#1](https://github.com/Uniderp-fun/uniderp-hook-smart-contract/issues/1), Aug 23 |
| AssetToAssetSwapHookForERC4626 (`0xc923…`) | unichain | **sent** — [VII-Finance/yield-harvesting-hook#30](https://github.com/VII-Finance/yield-harvesting-hook/issues/30), Aug 23 · repo match verified 100% on constants; unknown-pool behavior flagged as unverified inline |
| BunniHook (`0x00005242…`) | 50 | **resolved — false positive**. `BunniHookLogic.beforeSwap` reverts `BunniHook__InvalidSwap` when `slot0.sqrtPriceX96 == 0`, which is exactly the state of any pool unknown to Bunni. Author handled it; same shape as the Wsgem precedent. Manual clearance recorded here — single-file analysis cannot see library-level guards, which is a known scanner ceiling (roadmap item). |
| UniMemeHook (`0xb496…`) | 777 | superseded — registered post-snapshot; listing documents the fee design. No contact channel (deployer field empty). Monitoring. |

### Wave 2 method note

Channel hunt across the remaining 45 unique-name `PERMISSIONLESS_ATTACHMENT`
contracts (code search + two-stage verification: constant overlap, then
function-set Jaccard where constants were absent):

| outcome | count |
|---|---:|
| repos found | 6 |
| identity verified against deployed source | **1** (VII-Finance — contacted) |
| repo exists but source does not match deployment | 3 (KyberNetwork KEM, Livo, Asterix — parked; wrong-repo outreach is worse than silence) |
| no identifiable channel | the rest |

Two issues total went out in waves 1–2, both fully verified first. The cap
was never the constraint; verification was.

## Registry drift discovered during selection

Cross-checking against the live hooklist before sending turned up something
worth recording on its own: **four of the hooks named in the August 19
coverage finding registered within days of it going public** — PrediX,
UniMeme, Polymarket and UniswapCup were absent from the registry on Aug 19
and present on Aug 23. Coverage moved 1.24% → 1.57%. Correlation, not proven
causation, but exactly the observable-closing behavior this project exists to
measure. Corrections applied to [unichain-hook-coverage.md](unichain-hook-coverage.md).

The census numbers are unaffected: verification status (who publishes
source) and bytecode analysis never depended on registry membership.

## Wave 2 queue

- BunniHook, after `BunniHookLogic` review
- re-run of the full discovery cross-reference once `data/hooklist.json` is
  refreshed from the live repo — whoever is *still* unregistered at scale
  becomes the next outreach cohort
- a sample of registry-corpus `PERMISSIONLESS_ATTACHMENT` flags, chosen for
  identifiable maintainer channels
