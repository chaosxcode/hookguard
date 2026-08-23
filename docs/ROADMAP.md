# Roadmap

*Living document. Order within tiers is priority, not schedule.*

## Now

- **Author responses.** Two advisories are live ([Uniderp #1](https://github.com/Uniderp-fun/uniderp-hook-smart-contract/issues/1), [VII-Finance #30](https://github.com/VII-Finance/yield-harvesting-hook/issues/30)). Responses get logged verbatim in [author-outreach.md](../findings/author-outreach.md); silence is recorded as silence.
- **Registry resync cadence.** The Aug 23 refresh showed the hooklist moving 486 → 551 entries (and 4 of our named hooks registering) inside one week. A weekly scheduled Action should re-run `risk.py`, diff the numbers, and open an issue when anything material moves — the gap is only useful if its changes are watched.

## Near

- **Library-aware corpus analysis.** BunniHook was flagged and then manually cleared because its guard lives in `BunniHookLogic`, not the analyzed file. Corpus fetch should follow imports into sibling files of the same bundle; scanner validation checks should see them.
- **Bytecode pass v2: prove upgradeability instead of implying it.** For each `DELEGATECALL`, classify the target: storage-derived (live-upgradeable in practice) vs constant (fixed delegation — and in shared-code families, one implementation serving every clone). This upgrades Finding 2 of the bytecode pass from opcode-presence to mechanism.
- **Wave-3 outreach cohort.** After a registry resync, whoever is *still* unregistered with 2+ pools becomes the next cohort; channels via deployer fields, contract natspec contacts, and code search.

## Mid

- **A real false-positive rate.** Once author responses reach a meaningful N, publish it per-rule — this is the number that separates a scanner from a toy, and precision.md has promised it since day one.
- **Machine-readable hook status feed.** Everything this project computes — registered? source? audit? bytecode signals? author-confirmed intent? — as one queryable record per address. That is the assessment layer "Hook Safety as a Service" underwrites against, and the natural bridge to the insurance track.
- **Scanner v2.** Structural rules throughout (the guard rewrite was the pilot): library-aware validation detection, delta-flag semantics checked against actual return construction, severity claims limited to what the rule can demonstrate.

## North star

The LP value-leakage meter (UHI10) needs exactly this measurement layer:
you cannot price order flow you haven't measured, and you cannot underwrite
a hook you can't score. Hook scoring → status feed → underwriting inputs is
the through-line from static analysis to insurance.
