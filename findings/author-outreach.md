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

### Wave 3: proactive scans of active v4 repos (Aug 23)

Instead of waiting to be found, we went to the hooks: every actively-developed
v4 hook repository surfaced by search had its first-party source pulled and
run through the scanner at HEAD. Results posted as issues — advisories where
findings survived hand-verification, clean-bill notes with a one-line CI
install where nothing fired:

| repo | scan result | contact |
|---|---|---|
| Mrwicks00/Spiderman-Homecoming | MEDIUM `PERMISSIONLESS_ATTACHMENT` — verified | [advisory #1](https://github.com/Mrwicks00/Spiderman-Homecoming/issues/1) |
| impetus82/airbag-hook | MEDIUM `PERMISSIONLESS_ATTACHMENT` — unknown-pool behavior flagged as unverifiable inline; **their file layout also exposed a scanner bug (fixed)** | [advisory #1](https://github.com/impetus82/airbag-hook/issues/1) |
| OKMEME001/okmeme-v4-contracts | clean (`OkMemeTaxHook`) | [invite #1](https://github.com/OKMEME001/okmeme-v4-contracts/issues/1) |
| sp0oby/woolfi | clean (`WoolFiHook`) | [invite #2](https://github.com/sp0oby/woolfi/issues/2) |
| MeltedMindz/relicsv4 | clean (`RelicsV4Hook`) | [invite #2](https://github.com/MeltedMindz/relicsv4/issues/2) |
| Shenhan01-sys/fluxa-hook | clean (`FluxaHook`) | [invite #1](https://github.com/Shenhan01-sys/fluxa-hook/issues/1) |
| voladelta/fuse-hook | clean (`FuseHook`) | [invite #1](https://github.com/voladelta/fuse-hook/issues/1) |
| Hookr-fun/hookr-contracts | clean (`HookrHook`) — launchpad, high leverage | [invite #1](https://github.com/Hookr-fun/hookr-contracts/issues/1) |

Plus two install PRs opened directly ([v4hook-starter#1](https://github.com/voladelta/v4hook-starter/pull/1),
[priority_fee_pulse_hook#1](https://github.com/no-hive/priority_fee_pulse_hook/pull/1))
and one collaboration probe ([dngr2/v4-hookguard#1](https://github.com/dngr2/v4-hookguard/issues/1)).

Running totals: **13 external contacts** across advisories, invites and PRs;
4 open advisories awaiting author confirmation; 6 projects scanned clean.

### Scanner corrections earned by this wave

- **Abstract-base qualification**: files whose first declaration was
  `abstract contract …` were skipped entirely — hookathon-style direct-IHooks
  repos were invisible. Now the first *concrete* contract is anchored and
  analyzed (+34 contracts to the corpus, 306 total).
- **Phantom `getHookPermissions` bodies**: an abstract's bodyless declaration
  could adopt a distant brace, yielding empty or wrong permission sets — which
  silently suppressed rules scoped to declared callbacks. Structural matching
  applied; fixtures unchanged, four previously-clean contracts now correctly
  flagged, zero flagged-to-clean regressions.

## Wave 4: broadened discovery, template filtering (Aug 23)

Second discovery pass (three search vectors, 44 new candidates, 18 with
Solidity hooks scanned at HEAD). Two engineering corrections fell out
immediately — demo artifacts (`ExampleVulnerableHook`, foundry's `Counter.sol`)
were being analyzed as if they were production hooks; both now filtered.

| repo | scan result | contact |
|---|---|---|
| Mosss-OS/WaveLength | **2× verified HIGH** — unguarded `beforeSwap`/`beforeRemoveLiquidity` mutate penalty/rebate accounting | [advisory #2](https://github.com/Mosss-OS/WaveLength/issues/2) |
| ferris007/project-fee-hook | MEDIUM `PERMISSIONLESS_ATTACHMENT` — question sent | [advisory #1](https://github.com/ferris007/project-fee-hook/issues/1) |
| dannyy2000/Cadence | MEDIUM `PERMISSIONLESS_ATTACHMENT` — per-PoolId batch state, question sent | [advisory #1](https://github.com/dannyy2000/Cadence/issues/1) |
| meshackyaro/weir | **compatibility bug, not risk**: no `getHookPermissions()` anywhere → pools cannot initialize against it on final v4 | [report #1](https://github.com/meshackyaro/weir/issues/1) |
| BLTC-520/landfall · bithookdev/bithook_mono · robertleifke/forex-swap · 0xprogrammable/hookbuilder | clean | install invites (#1 each; hookbuilder #79) |

Skipped as templates, not contacts: `Counter.sol` demos (v4hook-cli, Dobhooks),
`ExampleVulnerableHook` (HookVault).

Running totals: **21 external contacts**, 5 open advisories, 6 clean scans,
2 install PRs pending.

## Wave 2 method note

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
