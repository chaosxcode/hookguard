# Contributing to HookGuard

HookGuard is a precision-first heuristic scanner for Uniswap v4 hooks.
The culture here is unusual on purpose, and contributions are judged against
it:

1. **Verify before you flag.** Every finding that leaves this repo has been
   hand-read against the contract it concerns. If you add a rule or change
   one, show it surviving the corpus (`python3 src/scan.py corpus`), not just
   the fixtures.
2. **Precision over recall.** A scanner that fires on everything trains
   people to ignore it. A rule that cannot justify its severity gets
   downgraded — see [docs/precision.md](docs/precision.md) for two rules that
   already were.
3. **Corrections are published, not buried.** When a number turns out to be
   wrong, the correction ships next to the original claim.
4. **No dependencies unless unavoidable.** The entire pipeline runs on the
   Python standard library plus public RPCs/explorers, so anyone can reproduce
   anything from a clone with no signup.

## Ways to contribute

- **False-positive reports** — open an issue with the contract address,
  chain, rule code, and why the pattern is handled. These are gold: five FP
  classes came from exactly this kind of reading, and each one made the
  scanner better. Template provided when opening an issue.
- **Rule proposals** — cite the mechanism (post-mortem, security guide, real
  incident) and the detection sketch. Severity must match what the rule can
  *demonstrate*.
- **Corpus & attribution work** — new chain RPCs/explorers for
  `src/attribution.py`, sibling-library fetching for corpus completeness.
- **Bytecode analysis** — the classifier's window heuristic is honest but
  crude; symbolic stack tracking would upgrade `unknown` verdicts.

## Development

```bash
python3 src/ci.py tests/fixtures/GuardedHook.sol --comment false --fail-on never
python3 src/ci.py tests/fixtures/RiskyHook.sol   --comment false --fail-on HIGH   # must exit non-zero
```

`GuardedHook` must always produce zero findings; `RiskyHook` must always trip
all four of its rules. Both gates run in CI on every push — if your change
breaks discrimination, it breaks the build.

## Findings etiquette

Findings against named projects are advisories, never verdicts. If you
contact an author through this project: state plainly that it is not a
vulnerability report, ask whether the pattern is intended, link the method,
and log the exchange in [findings/author-outreach.md](findings/author-outreach.md).
Responses get published verbatim; silence is recorded as silence.
