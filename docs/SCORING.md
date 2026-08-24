# How HookGuard scores hooks

Every hook in the [status feed](status/index.html) carries a risk score from
0–100 plus a confidence tier. This page is the complete rulebook — there is
no hidden term anywhere in the pipeline.

## Design rules

1. **Nothing is hidden.** Every point ships with a label and a reason,
   attached to the record itself.
2. **Only facts move the number.** Absence of evidence costs less than
   proven badness: an unaudited hook is *unknown*, priced cheaply; a
   delegate into unreadable bytecode is *demonstrated*, priced heavily.
3. **Confidence travels with score.** `high` confidence means source and
   bytecode layers both contributed; `low` means the verdict rests on thin
   evidence. Consumers should read both fields.
4. **Author responses rewrite history.** A maintainer confirming a pattern
   was intended subtracts points; a false positive is removed and recorded
   in the public ledger.

## Weights

| delta | signal | why |
|---|---|---|
| +25 | no published source | nothing else can be checked; opacity itself |
| +20 | delegates to opaque implementation | logic lives in unreadable code |
| +15 | storage-derived delegatecall | upgradeable in practice |
| +12 | standard proxy pattern | upgrade surface exists (impl may be readable) |
| +5 | SELFDESTRUCT opcode | capability present in runtime |
| +5 | all 14 permission flags set | maximum trust surface declared |
| +15 | each HIGH source finding | demonstrated invariant break |
| +7 | each MEDIUM finding | accurate detection, unproven consequence |
| +3 | each LOW finding | minor |
| +1 | each INFO | informational |
| +10 | no audit URL recorded | means "unknown" — priced cheaply on purpose |
| +8 | absent from the registry | opt-in transparency signal not exercised |
| −12 | author confirms pattern intended | strongest evidence that exists |

## Bands

| band | range | meaning |
|---|---|---|
| LOW | 0–24 | no demonstrated concerns |
| MODERATE | 25–49 | advisory-level patterns worth confirming |
| ELEVATED | 50–74 | structural opacity or capability signals stacked |
| HIGH | 75–100 | reserved for stacked demonstrated risks |

## What scoring deliberately does not do

- It does not claim vulnerability. A HIGH-band hook may be perfectly sound;
  the score says "here is everything unverifiable about it", which is what
  an underwriter needs priced.
- It does not reward good behavior it cannot measure. An audited, verified,
  registered hook simply accrues no penalties — the floor is zero, not
  praise.
- It does not hide behind confidence. Thin evidence lowers the confidence
  tier visibly rather than inflating certainty.

Implementation: [`src/score.py`](https://github.com/chaosxcode/hookguard/blob/master/src/score.py)
— one function, one weight table, no exceptions.
