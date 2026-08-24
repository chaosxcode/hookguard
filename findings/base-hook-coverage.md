# Base hook coverage — chain #2

*STATUS: census in progress — this document is completed when the run finishes.
Base PoolManager `0x498581fF…2b2b` (final v4), full history from deployment
block ~25.35M. Numbers land here automatically-derived from
`out/base-onchain.json`; nothing is estimated.*

## Why Base second

Base is the largest v4 hook ecosystem by deployments. If the registry-
undercount finding is a Unichain quirk, it's a curiosity; if it reproduces on
the biggest chain, it's structural — and the case for machine-readable hook
status becomes something a chain would fund.

## Method

Identical to [Unichain](unichain-hook-coverage.md): every `Initialize` event
in full chain history, hooks tallied per address, cross-referenced against
the live hooklist snapshot, then source-verification and bytecode passes on
the survivors of the launchpad discount.

Infrastructure note: dense mid-chain history forces smaller scan windows
(`HG_STEP=2000`) and checkpoint/resume (`HG_CHECKPOINT`) — the run survives
network interruptions and resumes exactly.

<!-- NUMBERS LAND BELOW THIS LINE -->
