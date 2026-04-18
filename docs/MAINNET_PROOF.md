# Mainnet Consensus Proof — Live `testmempoolaccept: allowed: true`

**End-to-end mainnet proof of the Glyph FT send pipeline.** Built with
the PR C+A+B+D+H code, signed, submitted to a live Radiant mainnet
node's `testmempoolaccept`, and then broadcast.

## Result

```json
[
  {
    "txid": "3115ec4bfc580dd22599e4b253509b4cc29f058e38ebb686a13097a6b4ab49c2",
    "allowed": true
  }
]
```

Broadcast-confirmed in mempool (depends on parent mint tx below).

## Evidence tx 1 — FT mint (prerequisite)

A 75-byte FT holder output was created on mainnet by spending a plain
P2PKH UTXO whose outpoint becomes the new FT ref by consensus
construction (the spent outpoint == the pushed ref):

- **Mint txid:** `0cb338176d91f21a0c7458d5c62cd78ceecd4eb662ffc3366951605b7b51de96`
- **Source UTXO:** `8da2cc78…099c97:0` (0.5 RXD plain P2PKH, self-send)
- **Output 0 — 75-byte FT holder:**
  - Script: `76a91451b837c5317166ec016754dcaff533c26833f01588acbdd0979c09f848c2ad1b6a3987332853115e59a763983e1f8e7c9245ad1c78cca28d00000000dec0e9aa76e378e4a269e69d`
  - Value: 47,580,000 photons (~0.476 RXD)
  - Address: `18T6RDhvYNHLKwULbv2dJpKYigxuxpjbCZ`
  - Ref: `979c09f848c2ad1b6a3987332853115e59a763983e1f8e7c9245ad1c78cca28d00000000`

Testmempoolaccept returned `"allowed": true`; broadcast returned the
txid above. Script classifies correctly via our PR C classifier:

```
>>> from electroncash import glyph
>>> spk = bytes.fromhex('76a91451b837…88ac bdd0 979c09f8…00000000 dec0e9aa76e378e4a269e69d')
>>> glyph.classify_glyph_output(spk)
('ft_holder', b'Q\xb87\xc5…', b'\x97\x9c\t\xf8…')
```

## Evidence tx 2 — FT send via `make_unsigned_ft_transaction`

**This is the tx that proves the full pipeline end-to-end.** Built
using the Python code from PRs C+A+B+D: coin selection, invariant
enforcement, `get_preimage_script` for Glyph inputs, `hashOutputHashes`
ref summaries, final signing.

- **Send txid:** `3115ec4bfc580dd22599e4b253509b4cc29f058e38ebb686a13097a6b4ab49c2`
- **Inputs (2):**
  - FT: `0cb33817…1de96:0` (47,580,000 photons ref 979c09f8…)
  - RXD: `8da2cc78…099c97:1` (189.47567985 RXD fee)
- **Outputs (3):**
  - FT recipient: 10,000,000 photons → `12SeJUtkKTxgNtEHMn9ZrbZkrxd1woFjhd`
  - FT change: 37,580,000 photons → `18T6RDhvYNHLKwULbv2dJpKYigxuxpjbCZ`
  - RXD change: 18,942,487,985 sats → fee-input address
- **Fee:** 5,080,000 sats (507B × 10,000 sat/byte — exactly at relay minimum)
- **testmempoolaccept:** `"allowed": true`
- **Broadcast:** succeeded (in mempool)

The send path exercised every PR in the stack:

| PR | What the tx depended on |
|----|------------------------|
| PR #2 (merged) | Classifier recognizing the 75B FT holder UTXO |
| PR C | `GlyphFTOutput.from_pkh_ref(pkh, ref)` constructing the recipient + change outputs |
| PR A | `serialize_hash_output` emitting real `totalRefs|refsHash` for the two Glyph outputs (per-output summary in `hashOutputHashes`) |
| PR B | `get_preimage_script` returning the full 75B script for the FT input (via `txin['type'] == 'glyph_ft'`) |
| PR D | `assert_ft_invariants` enforcing all 7 rules before signing; bounded fee fixed-point loop |
| PR H | Structured error reasons returned from `Commands.send_ft` (though this particular proof bypassed the Commands wrapper for brevity) |

## Post-fix: size formula

This proof surfaced a bug in `estimate_ft_tx_size`: the FT-output
coefficient was 75 (script size) rather than 84 (wire size: script +
value + length varint). A 2-in / 3-out FT send estimated at 490B when
the actual serialized size is 508B. At 10k sat/byte this produced a
fee of 9,646 sat/byte — just below the relay minimum, resulting in a
`"min relay fee not met"` rejection.

Fixed in commit `addaa52b`; the EstimateFtTxSizeTests vectors now
match actual serialized sizes byte-for-byte. This is the kind of
latent bug that only live-mainnet proof catches — a golden-vector
test written against the pre-fix formula would have pinned the wrong
answer.

## Reproducibility

```bash
# 1. Verify the FT-send tx is on mainnet:
sudo docker exec radiant-mainnet radiant-cli \
  -datadir=/home/radiant/.radiant \
  getrawtransaction 3115ec4bfc580dd22599e4b253509b4cc29f058e38ebb686a13097a6b4ab49c2 1

# 2. Verify the mint parent is on mainnet:
sudo docker exec radiant-mainnet radiant-cli \
  -datadir=/home/radiant/.radiant \
  getrawtransaction 0cb338176d91f21a0c7458d5c62cd78ceecd4eb662ffc3366951605b7b51de96 1
```

## Cryptographic proof (complementary evidence)

Independently of the live broadcast above,
[`test_transaction.TestRadiantPreimage
.test_mainnet_signature_verifies_against_our_preimage`](
../electroncash/tests/test_transaction.py) reconstructs the preimage
for `vin[1]` of the historical mainnet tx
`8ab5cf40042672d5bd9e5c07bf79be43de0132eb3820cc05e09f91d61e2ea92f`
(block 421000, 409+ confirmations) and verifies the on-chain signature
against our computed message hash. Signature verification passing is
cryptographic proof that our preimage is byte-identical to what
radiant-node produced — a stronger proof for the *preimage* portion of
the pipeline than `testmempoolaccept` alone.

Together these two tests cover the pipeline:
- **Preimage parity with radiant-node** (PR A test)
- **Live mainnet acceptance of a new Python-built FT send** (this doc)

## Related commits

- PR C `ef8f1682` — `GlyphFTOutput` + `glyph/` package + policy
- PR A `779108ff` — `hashOutputHashes` populates per-output refs
- PR B `d2d1cab7` — Glyph-aware `get_preimage_script` + input tagging
- PR D `c10f3bfd` — `make_unsigned_ft_transaction` + 7 invariants
- PR F+G `d2029eb0` — Qt GUI surface
- Integration `42d17c11` — Qt-less builder smoke test
- PR H `6bac3f78` — CLI/JSON-RPC parity
- Size fix `addaa52b` — `estimate_ft_tx_size` FT-output coefficient 75 → 84
  (caught by live mainnet proof)
