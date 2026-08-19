# Unichain hook coverage: 1,211 deployed, 15 registered, and most of the busiest unregistered hooks have no published source

*August 19, 2026*

The Uniswap hooklist is opt-in, and it says so. This measures how much that
misses in practice on Unichain, by scanning every `Initialize` event in the
chain's full history — every pool ever created and the hook attached to it.

## What is deployed

| | |
|---|---|
| pools ever created on Unichain | **7,539** |
| pools that attach a hook | **5,366** (71%) |
| distinct hook contracts deployed | **1,211** |
| of those, in the hooklist | **15** |
| registry coverage | **1.24%** |

Taken alone, 1.24% oversells the gap, so here is the discount: **1,094 of the
1,211 serve exactly one pool each**. That is launchpads minting a hook per
token, not 1,094 distinct designs. The population that matters is the **117**
serving two or more pools and the **35** serving ten or more.

Even after that discount, the two busiest hooks on Unichain are not in the
hooklist: `PrediXHookProxyV2` (1,034 pools) and `UniMemeHook` (777 pools).

## The part that matters more: can anyone read them?

Coverage is the smaller half of the problem. Taking the **30 unregistered
Unichain hooks serving 10+ pools** and asking the block explorer whether each
has published source:

| | |
|---|---|
| hooklist hooks with verified source | **486 / 486 (100%)** |
| busiest unregistered hooks with verified source | **5 / 30 (17%)** |

The registry is 100% verified because publishing source is effectively a
condition of being listed. That number describes the listing process, not the
ecosystem.

Off the registry, **25 hooks sitting in the swap path of ten or more live pools
have no published source at all**. Nothing to read, nothing to audit, nothing
for an integrator to check.

That is a ceiling on every source-level analysis tool in v4, including this
one. HookGuard's scanner needs source; on the hooks that most need checking,
there is none. Bytecode-level analysis is the only thing that reaches them.

The five that do publish source are not obscure: `PrediXHookProxyV2` (1,034
pools), `UniMemeHook` (777), `BunniHook` (50), `PolymarketHook` (34) and
`UniswapCupHook` (32). Recognisable names are the exception off-registry, not
the rule.

One detail worth noting: the busiest unregistered hook, `PrediXHookProxyV2`, is
a verified **proxy**. The address bits fix its permissions permanently and pools
cannot detach, but the implementation behind it can still be swapped.

## What this is not

This is a counting exercise. I measured how many hooks exist, how many are
registered, and whether source is published. **I have not found a vulnerability
in any of them**, and neither "unregistered" nor "unverified" means "unsafe" —
plenty of legitimate projects never register, and plenty of good code is
unverified on an explorer.

An empty `auditUrl` in the registry likewise means no audit is *recorded*, not
that none exists. That ambiguity is itself part of the gap: there is no
machine-readable way for a router, LP, or integrator to tell a reviewed hook
from an unreviewed one.

## Reproduce it

```bash
CHAIN=unichain python3 src/discover.py     # discovery scan
python3 src/verify_status.py               # source-verification pass
```

Raw output: [`out/unichain-unregistered-top.json`](../out/unichain-unregistered-top.json)
and [`out/unichain-onchain.json`](../out/unichain-onchain.json).

The scan aborts rather than publish a partial result — an undercount is the one
error that would quietly invalidate the number. It is all public chain data, so
none of this requires taking my word for it.
