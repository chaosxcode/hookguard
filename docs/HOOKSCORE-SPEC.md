# HookScore Record Specification — draft 1.0

*Status: implemented by HookGuard ≥0.9 · feedback welcome*

## Why

There is no machine-readable way to tell a reviewed Uniswap v4 hook from an
unreadable one. Registries are opt-in and drift; audits live in prose;
bytecode signals exist but no consumer agrees on how to read them. This spec
defines one small JSON record that any wallet, router, front-end, registry or
underwriter can serve and consume — produced by any tool willing to publish
its weights.

A score without its receipt is marketing. A record under this spec always
ships the receipt.

## Canonical record

```json
{
  "schema": "hookscore/1.0",
  "chainId": 130,
  "address": "0x000052423c1db6b7ff8641b85a7eefc7b2791888",
  "generatedAt": "2026-08-24T00:00:00Z",
  "generator": {
    "tool": "hookguard",
    "version": "0.9.1",
    "weightsSha256": "<sha256 of weight table>"
  },
  "score": {
    "value": 12,
    "band": "LOW",
    "confidence": "medium",
    "factors": [
      {"key": "unregistered", "label": "absent from the hooklist registry",
       "delta": 8, "detail": "opt-in transparency signal not exercised"}
    ]
  },
  "signals": {
    "sourcePublished": true,
    "registered": false,
    "auditRecorded": null,
    "proxy": {
      "kind": null,
      "implementation": null
    },
    "delegatecallOpcode": false,
    "selfdestructOpcode": false,
    "permissionBits": 6,
    "permissionBitLayout": "preview-reversed"
  }
}
```

## Field semantics

### score.confidence

| tier | meaning |
|---|---|
| `high` | source analysis **and** runtime-bytecode analysis both contributed |
| `medium` | exactly one evidence layer contributed |
| `low` | verdict rests on address metadata alone |

Consumers MUST treat confidence as part of the verdict. A HIGH-band / low-
confidence record is a prompt for review, not a rating.

### signals.permissionBitLayout

Final v4 encodes callback permissions in the low bits of the hook address in
documented order. Some deployments — notably the v4 *preview* PoolManager
family (`0x1F984000…0004`), e.g. Unichain — order the ten CALLBACK flags in
reverse, and the four return-delta positions match neither layout. Producers
MUST state which layout their `permissionBits` were decoded with; consumers
MUST NOT assume final-v4 order.

Reference: [measured validation](https://github.com/chaosxcode/hookguard/blob/master/findings/unichain-bytecode.md)
— 17/18 source-verifiable hooks agree with reversed order, 1/18 with final.

### score.factors

Every delta applied, itemized. Absent factors = absent evidence, not
mitigation. Negative deltas are reserved for positive external evidence
(author confirmation); tools MUST NOT award points for unverifiable good
intentions.

### weightsSha256

SHA-256 over the sorted `(key, delta)` pairs of the producing tool's weight
table. Consumers can pin a methodology version and detect silent changes.

## Producer obligations

1. Publish the reproduction commands next to the records.
2. Never present heuristic findings as vulnerability claims.
3. Distinguish measured facts (`sourcePublished`) from inferences
   (`proxy.kind == "opaque"` means "we could not read it", never "it is bad").
4. Version every change to weights or factor keys as a new spec revision.

## Consumer obligations

1. Render confidence beside band.
2. Link the generator's methodology.
3. Treat missing addresses as "unmeasured", never "unsafe".

## Reference implementation

HookGuard's feed implements this spec verbatim:

- aggregate: [`https://chaosxcode.github.io/hookguard/status/feed.json`](https://chaosxcode.github.io/hookguard/status/feed.json)
- per-hook: `.../status/<chain>/<address>.json`
- generator: [`src/status_feed.py`](https://github.com/chaosxcode/hookguard/blob/master/src/status_feed.py),
  scoring: [`src/score.py`](https://github.com/chaosxcode/hookguard/blob/master/src/score.py)

## Roadmap

- `attestation` block: EAS attestation UID binding a record to an on-chain
  signer, enabling revocable third-party endorsements
- `authorResponse` block: pointer to the public outreach ledger entry
- multi-chain aggregate records keyed by codeHash for clone families
