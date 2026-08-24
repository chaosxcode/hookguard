# Roadmap

*Living document. Order within tiers is priority, not schedule.*

## Success criteria

The project has explicit external-validation goals. Each is measured, not
claimed; `src/reach.py` and the [status feed](status/index.html) report the
numbers.

| goal | measured by | status |
|---|---|---|
| 3–5 unrelated hook projects installing `chaosxcode/hookguard@v1` | public code search (`src/reach.py`) | **0 / 5** — advisories now include a one-line install ask |
| maintainers responding to findings, confirming usefulness | [author-outreach ledger](../findings/author-outreach.md) | 2 advisories live, awaiting response |
| one external pull request or contributor | git history | contributor path documented ([CONTRIBUTING.md](../CONTRIBUTING.md), issue templates) |
| one integration: registry, incubator cohort, audit workflow, or security team | links from this repo | UHI application submitted before Sep 21 deadline |
| public testimonials from identifiable builders | quoted in ledger/README | follows responses above |
| usage metrics excluding own repositories | `reach.py` excludes `chaosxcode/*` by design | tracked since day one |
| case study: HookGuard caused a real fix or documented risk decision | written up in findings/ | candidate pending any author response |

## Now

- ✅ **SHIPPED — Registry resync cadence.** Weekly workflow refreshes snapshot + artifacts, commits drift, files a rolling drift-report issue.
- ✅ **SHIPPED — PyPI distribution.** `pip install hookguard` (0.9.1); tag-push releases via trusted publishing.
- ✅ **SHIPPED — Comment-driven public scans.** `/hookguard-scan owner/repo` returns a full scored report — zero-install surface.
- ✅ **SHIPPED — In-browser scanner.** Client-side JS port, parity-tested on 38 real bundles.
- ✅ **SHIPPED — HookScore spec draft 1.0** ([HOOKSCORE-SPEC.md](HOOKSCORE-SPEC.md)).
- **Author responses.** Five advisories live; responses logged verbatim in [author-outreach.md](../findings/author-outreach.md).

- **Author responses.** Two advisories are live ([Uniderp #1](https://github.com/Uniderp-fun/uniderp-hook-smart-contract/issues/1), [VII-Finance #30](https://github.com/VII-Finance/yield-harvesting-hook/issues/30)). Responses get logged verbatim in [author-outreach.md](../findings/author-outreach.md); silence is recorded as silence.
- **Registry resync cadence.** The Aug 23 refresh showed the hooklist moving 486 → 551 entries (and 4 of our named hooks registering) inside one week. A weekly scheduled Action should re-run `risk.py`, diff the numbers, and open an issue when anything material moves — the gap is only useful if its changes are watched.

## Near

- ✅ SHIPPED — Library-aware validation (sibling delegation + zero-state guards; auto-clears the Bunni pattern).
- ~~**Library-aware corpus analysis.**~~ BunniHook was flagged and then manually cleared because its guard lives in `BunniHookLogic`, not the analyzed file. Corpus fetch should follow imports into sibling files of the same bundle; scanner validation checks should see them.
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
