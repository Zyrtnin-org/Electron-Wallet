# Session Handoff — Radiant Glyph FT-send for Electron-Wallet

**Session window:** 2026-04-17 → 2026-04-18
**Ends at:** Ledger FT-signing test plan written, ready to run against a physical device.

---

## One-line status

Full software FT-send pipeline shipped to `Zyrtnin-org/Electron-Wallet` as 7
stacked feature branches + 1 squashed validator branch; mainnet-proven with
live `testmempoolaccept: allowed=true`; Ledger hardware signing is the
next piece, test plan ready.

---

## What lives where

### Local repos

- `/home/eric/apps/Electron-Wallet/` — the Python wallet, 8 branches
- `/home/eric/apps/Pinball/` — FlipperHub PHP web app (untouched this
  session except for the compound-docs solution file)
- `/home/eric/apps/radiant-ledger-app/` — planning/brainstorm/research
  docs for the whole Glyph work (this session's plan lives here)
- `/home/eric/apps/app-radiant/` — Ledger firmware (audit-only this
  session; full NFT + FT-capable opcode walker + `hashOutputHashes`
  streaming already present in the firmware)

### Remote

- `Zyrtnin-org/Electron-Wallet` (origin) — all 8 glyph branches pushed
- `Radiant-Core/Electron-Wallet` (upstream) — only PR #2 (the
  classifier) is in review; nothing else pushed upstream per user's
  explicit instruction

---

## The 8 branches on the fork

Stacked feature branches (each commit is atomic, builds + tests clean):

```
feat/glyph-classifier-clean   57cfd5f5  PR #2 (classifier)          [upstream PR open]
feat/glyph-ft-output          ef8f1682  PR C — GlyphFTOutput + glyph/ package
feat/glyph-preimage-refs      779108ff  PR A — hashOutputHashes refs
feat/glyph-input-signing      d2d1cab7  PR B — full-script scriptCode for Glyph inputs
feat/glyph-ft-builder         c10f3bfd  PR D — make_unsigned_ft_transaction + 7 invariants
feat/glyph-ft-gui             42d17c11  PR F+G — Qt GUI + integration test
feat/glyph-ft-commands        6e91d8bb  PR H — Commands CLI + size fix + mainnet proof + README
```

Squashed validator branch:

```
glyph-ft-all                  98828bb5  ← single commit, everything + README
```

Everything sits on top of PR #2's commit `57cfd5f5`. If that PR gets merged
upstream first, all of these rebase cleanly onto `upstream/master`.

---

## Mainnet evidence

Two live mainnet transactions prove the pipeline end-to-end:

- **FT mint (PR A's output-side working):**
  `0cb338176d91f21a0c7458d5c62cd78ceecd4eb662ffc3366951605b7b51de96`
  (plain P2PKH → 75B FT holder; `testmempoolaccept: allowed=true`;
  broadcast succeeded)

- **FT send via `make_unsigned_ft_transaction` (full pipeline):**
  `3115ec4bfc580dd22599e4b253509b4cc29f058e38ebb686a13097a6b4ab49c2`
  (FT input + RXD fee → FT recipient + FT change + RXD change;
  `testmempoolaccept: allowed=true`; broadcast succeeded)

Both confirmed accessible via:

```bash
ssh ericadmin@89.117.20.219 'sudo docker exec radiant-mainnet radiant-cli \
  -datadir=/home/radiant/.radiant \
  getrawtransaction <txid> 1'
```

Cryptographic parity with radiant-node's sighash is also verified by an
automated test that re-signs a historical tx: see
`electroncash/tests/test_transaction.py::TestRadiantPreimage::test_mainnet_signature_verifies_against_our_preimage`
(covers tx `8ab5cf40...e2ea92f`, block 421000, 409+ confirmations).

---

## What's DONE (don't redo)

- [x] Classifier (PR #2, already upstream)
- [x] `GlyphFTOutput` + `glyph/` package + policy constants + exceptions (PR C)
- [x] `hashOutputHashes` per-output refs populated for Glyph outputs (PR A)
- [x] Full-script `scriptCode` for Glyph inputs via `txin['type']` dispatch (PR B)
- [x] `make_unsigned_ft_transaction` + 3 helpers + 7 invariants + bounded fee
  fixed-point loop + `_finalize_unsigned_tx` extraction (PR D)
- [x] Qt Tokens tab + Asset dropdown + confirmation modal + label sanitization
  + UTXO coloring (PR F+G)
- [x] `Commands.send_ft / get_ft_balances / list_ft_utxos / setreflabel` with
  structured error reasons + `dry_run=True` default (PR H)
- [x] Mainnet `testmempoolaccept: allowed=true` proof (in PR H branch)
- [x] `estimate_ft_tx_size` FT-output coefficient 75 → 84 bug caught by live
  proof, fixed (in PR H branch)
- [x] Comprehensive README beta banner + Glyph FT support section (in both
  `glyph-ft-all` and `feat/glyph-ft-commands`)
- [x] Docs: `docs/MAINNET_PROOF.md`, `docs/plans/2026-04-18-feat-glyph-ft-send-plan.md`
- [x] Solution doc at `/home/eric/apps/Pinball/docs/solutions/integration-issues/radiant-electron-wallet-glyph-output-classifier.md`
- [x] All 122 tests pass on both `glyph-ft-all` and `feat/glyph-ft-commands`
- [x] 7 stacked + 1 squashed branch pushed to `origin` (Zyrtnin-org); upstream
  untouched

---

## What's NEXT

### 1. Ledger FT-signing live test (blocked on firmware rebuild)

**Wallet-side is ready.** Both the protocol and connectivity layers
are now handled:
- `get_preimage_script` returns full 75B/63B for Glyph inputs (PR B)
- `electroncash_plugins/ledger/ledger.py` supports Nano S+ on BOLOS 2.x
  (PID 0x5000, interface 2, channel framing — commits `99584204` on
  glyph-ft-all / `370dadfa` on feat/glyph-ft-commands)
- `commands.py` knows the FT command parameter names so the CLI parser
  doesn't crash at startup

**Firmware-side is blocked.** Live-test attempted 2026-04-19 against
a Nano S+ on BOLOS 2.4.10. The Radiant app binary currently installed
on the device doesn't register HID descriptors cleanly on BOLOS 2.x:
the USB device enumerates (lsusb sees it as `2c97:5000 Ledger Nano
S+`) but no `/dev/hidraw` nodes are created, so the plugin has nothing
to open. This is a firmware-side incompatibility — the Radiant app
source at `/home/eric/apps/app-radiant/` looks BOLOS-compliant in the
code audit, but the installed binary predates the current BOLOS SDK.

**To unblock:** rebuild the Radiant Ledger app against a current BOLOS
SDK, side-load to the device, retry the test below. Likely 30-60 min
of firmware work + toolchain setup.

Test plan:

1. Launch wallet from `glyph-ft-all` branch:
   ```bash
   cd /home/eric/apps/Electron-Wallet
   PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python python3 electron-radiant
   ```

2. Create a Ledger-backed wallet via GUI (File → New → "Use a hardware
   device"). Requires Ledger running the `radiant-ledger-512` firmware.

3. Note the first receive address (call it `$LEDGER_ADDR`).

4. Mint a small FT to that address using the already-written script at
   `/tmp/mint_ft_to_ledger.py`:
   ```bash
   LEDGER_ADDR=<your_addr> PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python \
     python3 /tmp/mint_ft_to_ledger.py
   ```

5. Wait 1 confirmation, refresh wallet (Ctrl+R), confirm Tokens tab shows
   the new ref + Coins tab shows the amber-colored FT UTXO.

6. Attempt a Send via the Asset dropdown. Ledger should prompt for:
   - 3 output confirmations (2 FT "unusual script" + 1 P2PKH RXD change)
   - 1 signature approval
   Then wallet broadcasts. `testmempoolaccept` should return `allowed=true`.

**Expected outcomes and how to diagnose:**

| Outcome | Diagnosis |
|---|---|
| ✅ Send succeeds | Ledger FT signing is DONE; document and close out |
| ⚠️ Succeeds but unusual-script warnings per output | UX polish, not broken; optional firmware PR to recognize FT/NFT templates and show token info |
| ❌ Ledger refuses at input parsing | Firmware's input script whitelist doesn't include 75B FT; needs a branch in `hash_input_start.c` |
| ❌ Sig verifies on device but network rejects | Preimage byte mismatch; diff firmware's byte stream against PR A's software preimage |

### 2. Deferred items (not blocking)

- **Third-party security audit.** README explicitly calls this out.
- **Coin-control integration** for per-FT-UTXO freezes.
- **Long-soaked mainnet usage** — only one live send so far; real-world
  edge cases (reorgs, fragmented RXD for fees, label injection attempts)
  under-tested.
- **Upstream PRs to `Radiant-Core/Electron-Wallet`.** User instructed to
  keep this local to the fork for now so others can validate the direction
  before pushing upstream.

### 3. Dependabot vulnerabilities on the fork

GitHub flagged 134 Dependabot vulnerabilities on `Zyrtnin-org/Electron-Wallet`
default branch (53 high). These are inherited from the upstream Electron-Cash
base — not introduced by this session. Worth cleaning up when the PRs move
upstream, but doesn't block Glyph FT review.

---

## Architecture quick-reference

### The glyph/ package layout (in PR C)

```
electroncash/glyph/
├── __init__.py          re-exports + registers GlyphFTOutput in ScriptOutput.protocol_classes
├── classifier.py        is_ft_holder, is_nft_singleton, classify_glyph_output, extract_all_pushrefs
├── core.py              GlyphFTOutput, policy constants (FT_DUST_THRESHOLD=2M, FT_MIN_FEE_RATE=10k),
│                        estimate_ft_tx_size, sanitize_ref_label, assert_ft_invariants (7 rules),
│                        exception hierarchy
└── wallet_data.py       per-wallet Glyph UTXO index with kind tracking
```

### The 7 invariants (raised as exceptions, never asserted)

Located in `electroncash/glyph/core.py::assert_ft_invariants`:

1. All FT inputs share the same 36-byte `ref`
2. Every FT output's `ref` equals the FT-input `ref`
3. Sum of FT input photons == Sum of FT output photons
4. RXD-change outputs are pure P2PKH (never Glyph scripts)
5. FT-change photons >= FT_DUST_THRESHOLD (2M photons)
6. No FT output below dust threshold (covers recipient + change)
7. For each FT input, re-extract `ref` from scriptPubKey bytes and assert
   it matches target_ref (**content-addressed, peer-proof**)

### Signing path

- **Output-side:** `transaction.py::serialize_hash_output` populates real
  `totalRefs | refsHash` for Glyph outputs (PR A), byte-identical to
  radiant-node.
- **Input-side:** `transaction.py::get_preimage_script` returns the full
  75B/63B script for `txin['type'] in ('glyph_ft', 'glyph_nft')` (PR B).
  Driven by `add_input_info` (PR B) which consults `wallet.glyph.kind_for_txo`
  and populates `prev_scriptPubKey_hex` from the stored parent tx.
- **scriptSig:** unchanged `<sig><pubkey>` P2PKH form for Glyph inputs —
  only the preimage scriptCode differs. Verified against Pinball's
  `transfer_nft.js` reference and radiant-node source.

### Builder decomposition

`wallet.py::make_unsigned_ft_transaction` orchestrates 3 private helpers:

- `_select_ft_inputs(target_ref_hex, amount)` — greedy largest-first, raises
  `SendFtError('dust_change')` or `SendFtError('ref_mismatch')`
- `_build_ft_outputs(recipient, amount, change_addr, ft_change, ref)` — pure
  function, constructs `GlyphFTOutput` for recipient + self-change
- `_resolve_and_pick_fee_inputs(...)` — bounded fee fixed-point loop (cap=4)
  tracking both `n_rxd_in` and `n_rxd_out`; distinguishes total-insufficient
  vs. fragmented RXD

After invariants check, `Transaction.from_io` + `_finalize_unsigned_tx`
(BIP_LI01 sort, locktime, `run_hook('make_unsigned_transaction')`,
ExcessiveFee). Second-pass invariants on the final tx.

---

## User-relevant memories set this session

These should persist in Claude's auto-memory for future conversations:

- **Product-name map:** Electron-Wallet = the Python wallet (not a separate
  "Python port" of anything — it's always been Python, forked from
  Electron-Cash). Photonic Wallet, Glyphium, and the Ledger firmware are
  distinct projects.
- **FT template invariant:** 75-byte FT holder = `76a914 <pkh:20> 88ac bd d0
  <ref:36> dec0e9aa76e378e4a269e69d`. Ref is 32B txid-hash + 4B vout LE = 36B total.
- **Radiant minimum relay fee:** 10,000 sat/byte. FT sends at 2-in/3-out are
  ~508 bytes = 5.08M sats = ~0.05 RXD in fees.
- **FT_DUST_THRESHOLD = 2M photons** — sized so recipient can later
  economically spend the change (consuming a 75B output costs ~180B × 10k =
  1.8M + 200k headroom).
- **Radiant sighash is NOT BIP143 verbatim** — adds a 32-byte
  `hashOutputHashes` field between nSequence and hashOutputs. Each per-output
  summary is 76B: `nValue (8B LE) | sha256d(spk) (32B) | totalRefs (u32 LE)
  | refsHash (32B)`. Refs sorted MSB-first reverse (C++ `std::set<uint288>`
  compare order).
- **Radiant sighash does NOT cut at OP_STATESEPARATOR** — the full 75B/63B
  script is what gets signed. Verified from radiant-node source.

---

## Useful scripts left behind

- `/tmp/mint_ft_direct.py` — mints a fresh FT holder on mainnet (parametrized
  by any local-wallet address; used to create our first evidence tx)
- `/tmp/mint_ft_to_ledger.py` — same but destination pkh = Ledger address
  (ready for the hardware test)
- `/tmp/ft_send_proof.py` — builds + signs + testmempoolaccept's an FT send
  using our Python code (produced the mainnet proof)
- `/tmp/ft_mint_state.json`, `/tmp/ft_send_proof.json` — state from both
  transactions; handy for replay/audit

---

## How to pick this back up

1. **If Ledger FT signing is next:** follow the test plan in section
   "What's NEXT → 1" above. Start by minting an FT to a Ledger-derived
   address.

2. **If upstreaming is next:** push `feat/glyph-classifier-clean` →
   `Radiant-Core/Electron-Wallet` first (the existing PR #2). After it
   merges, open stacked PRs (or one squashed PR from `glyph-ft-all`)
   against `upstream/master`. The PR description template lives in
   `docs/MAINNET_PROOF.md`.

3. **If audit/review is next:** point reviewers at
   https://github.com/Zyrtnin-org/Electron-Wallet — the `glyph-ft-all`
   branch is the single-diff view, stacked `feat/*` branches are the
   step-by-step view. README banner is the starting point.

4. **If something broke:** the mainnet proof tx
   `3115ec4b...b4ab49c2` is your ground truth. If our code produces
   different bytes from that tx's shape, something regressed.
