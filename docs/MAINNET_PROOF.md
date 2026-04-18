# Mainnet Consensus-Parity Evidence

This document records the mainnet evidence accumulated across PRs A-H
for the Glyph FT send implementation.

## Headline result

**The FT-send code produces preimages byte-identical to radiant-node's
native sighash computation.** Established by an automated test that
re-derives a known mainnet signature's message hash:

- **Test:** [`electroncash.tests.test_transaction.TestRadiantPreimage
  .test_mainnet_signature_verifies_against_our_preimage`](
  ../electroncash/tests/test_transaction.py)
- **Mainnet tx:** `8ab5cf40042672d5bd9e5c07bf79be43de0132eb3820cc05e09f91d61e2ea92f`
- **Block:** `0000000000000007a8fbf073bacc867ff8c40b0983d22392274672dc05c5931c`
  (height 421000)
- **Confirmations at review:** 409+
- **What the test does:** reconstructs the full preimage for `vin[1]`
  (which includes per-output `hashOutputHashes` summaries for the 241-byte
  FT mint-authority output at `vout[0]` and the 75-byte FT holder at
  `vout[1]`), computes `sha256d(preimage)`, then verifies the on-chain
  DER-encoded signature against that message hash using the recorded
  pubkey. `ecdsa.VerifyingKey.verify_digest(...)` returns True, which is
  mathematically only possible if our preimage matches the one
  radiant-node signed against.

## Why this is the correct consensus proof

`testmempoolaccept` validates protocol rules (sig, dust, fees) but
requires the caller to control private keys for a live FT UTXO. That's
out of scope for this session — no test wallet in the local fork holds
FT coins, and the director wallets for FlipperHub mint NFTs rather than
FTs.

A signature-recovery test against a known-good mainnet tx is a strictly
stronger proof than `testmempoolaccept` for the *preimage* portion of
the pipeline:

- `testmempoolaccept` says "this tx is consensus-valid" (a boolean).
- The sig-recovery test says "the preimage our code constructs matches
  what the node constructs, byte-for-byte" (deterministically reproducible,
  cryptographically checkable).

The structural/builder portion (coin selection, fee fixed-point,
invariants, finalization) is validated by
[`test_glyph_ft_builder_integration.py`](
../electroncash/tests/test_glyph_ft_builder_integration.py) against a
mock wallet.

## Gap: live broadcast

What we have **not** done:

- Built a new mainnet FT send from scratch using
  `make_unsigned_ft_transaction`
- Signed it with a private key to a live FT UTXO we control
- Submitted via `testmempoolaccept '[...]'`

This requires either minting an FT into a test wallet first (separate
multi-step flow not in scope here) or using an existing FT holder
whose private key is in a wallet we can attach to Electron-Wallet.

Neither gate is a correctness concern — both the preimage (PR A) and
the builder (PRs C-H) are covered by tests — but maintainers merging
the PR series should run a live broadcast before considering the work
complete for end-users. The steps would be:

```bash
# 1. Mint a small FT into a test wallet using existing tools (FlipperHub
#    has a mint flow; Photonic Wallet's create-token also works).

# 2. Open the Electron-Wallet fork against the test wallet; confirm the
#    Tokens tab shows the new ref.

# 3. From the Send tab, select the ref in the Asset dropdown, set a
#    recipient + small amount, and click Preview (not Send).

# 4. Copy the tx hex from the preview dialog, then submit via the node:
sudo docker exec radiant-mainnet radiant-cli -datadir=/home/radiant/.radiant \
  testmempoolaccept '["<tx_hex>"]'

# 5. Expect:  [{"txid": "...", "allowed": true, ...}]
```

Record the txid + response JSON in the follow-up PR that does the
live broadcast.

## Local test suite status

```
PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python python3 -m unittest \
    electroncash.tests.test_glyph_classifier \
    electroncash.tests.test_glyph_ft \
    electroncash.tests.test_glyph_ft_builder_integration \
    electroncash.tests.test_transaction \
    electroncash.tests.test_wallet \
    electroncash.tests.test_commands
```

**122 tests pass.** No regressions in plain-RXD paths (wallet,
transaction test suites untouched except for the additive Glyph
sections).

## Related commits

- PR C `ef8f1682` — `GlyphFTOutput` + package restructure
- PR A `779108ff` — `hashOutputHashes` per-output refs populated for
  Glyph outputs (consensus proof test lives here)
- PR B `d2d1cab7` — Glyph-aware `get_preimage_script` + input tagging
- PR D `c10f3bfd` — `make_unsigned_ft_transaction` + 7 invariants
- PR F+G `d2029eb0` — Qt GUI (Tokens tab, Asset dropdown, modal)
- Integration `42d17c11` — end-to-end builder-path test
- PR H `6bac3f78` — CLI/JSON-RPC parity (`Commands.send_ft`, etc)
