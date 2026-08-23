# HookGuard Status API

The status feed is static, versioned, and served straight from GitHub Pages —
no auth, no rate limits beyond Pages' own generosity, no tracking.

## Aggregate

```
GET https://chaosxcode.github.io/hookguard/status/feed.json
```

Registry pulse, scanner measurement summary, Unichain census + coverage,
attribution families, adoption progress, advisory ledger, and every scored
hook record.

## Per-hook record

One JSON file per known hook contract:

```
GET https://chaosxcode.github.io/hookguard/status/<chain>/<address>.json
```

```json
{
  "generated": "2026-08-23",
  "chain": "unichain",
  "address": "0x…",
  "name": "SomeHook",
  "source": true,
  "score": 17,
  "band": "LOW",
  "confidence": "medium",
  "factors": [{"key":"medium_finding","label":"1× MEDIUM finding(s)","delta":7,"detail":"…"}],
  "pools": 12,
  "proxy": false,
  "delegatecall": true,
  "selfdestruct": false,
  "permBits": 3
}
```

`404` means HookGuard has not yet analyzed that address — it does not mean
the address is not a hook.

### Field notes

- `band`: LOW (<25) · MODERATE (<50) · ELEVATED (<75) · HIGH risk
- `confidence`: `high` = source + bytecode layers both present;
  `medium`/`low` = partial evidence. **Read confidence before band.**
- `factors`: only deltas actually applied; weights are public in
  [`src/score.py`](https://github.com/chaosxcode/hookguard/blob/master/src/score.py)
- `permBits`: count of set permission bits in the address's low 14 bits.
  On Unichain these read in preview-reversed order — see
  [findings/unichain-bytecode.md](../findings/unichain-bytecode.md).

## Regenerating

Everything is derived from public chain data:

```bash
python3 src/risk.py && python3 src/reach.py && python3 src/status_feed.py
```
