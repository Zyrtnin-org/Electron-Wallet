# Session Narrative — Radiant Glyph FT-send for Electron-Wallet

**Window:** 2026-04-17 → 2026-04-18 (two calendar days, one long session
with a context-compaction break in the middle)

**What it is:** a readable account of how the work came together, the
decisions made, and the things that surprised us. For the raw index,
see [`HANDOFF.md`](HANDOFF.md). For the plan doc, see
[`docs/plans/2026-04-18-feat-glyph-ft-send-plan.md`](docs/plans/2026-04-18-feat-glyph-ft-send-plan.md).

---

## Opening state

The session began with the **Radiant Glyph classifier PR** already
written and committed to a local branch. That work recognized FT holder
(75-byte) and NFT singleton (63-byte) scripts via exact byte-shape
matching and wired them into `get_address_from_output_script` so the
wallet's Coins tab could display FT UTXOs as normal P2PKH addresses.
What the classifier could NOT do was let anyone spend them — that's
what this session added.

The classifier was at commit `049765ef` on branch `feat/glyph-classifier`.
Four golden-vector tests passed. Good bones, nothing visible to an end
user yet.

---

## Phase 1 — Shipping the classifier (PR #2)

Before starting new work, we pushed the classifier into a clean state
for upstream review.

**What went in:** cherry-picked `049765ef` onto a fresh branch based on
`Radiant-Core/Electron-Wallet:master` (`feat/glyph-classifier-clean`).
Opened PR #2 at `https://github.com/Radiant-Core/Electron-Wallet/pull/2`
with a detailed description, reviewer-ready evidence, and a consensus-
proof citation: mainnet tx `8ab5cf40042672d5bd9e5c07bf79be43de0132eb3820cc05e09f91d61e2ea92f`
from block 421000 was fetched live, inspected output-by-output, and its
per-output classifications were confirmed to match the classifier's
expectations (vout[0] 241B FT control → correctly rejected as
non-spendable; vout[1] 75B FT holder → classified with correct pkh and
ref).

**The PR-size question.** About this time we paused to discuss the
small-vs-large PR tradeoff. The answer landed on: for this codebase
(Electron-Cash fork, small maintainer team, consensus-critical code),
**small PRs are better**. Reviewers can hold the whole diff in their
head; bugs land in isolation; reverts are surgical.

That decision shaped everything that followed: we'd write one big plan,
but deliver it as a stack of small PRs.

---

## Phase 2 — Research before commitment

Before writing a single line of builder code, we:

1. **Verified Radiant's sighash cut-point** by reading
   `radiant-node/src/script/interpreter.cpp`. Our initial hypothesis
   was that sighash might cut at `OP_STATESEPARATOR`, letting the
   signing path stay byte-identical to plain P2PKH. The source said
   otherwise — `OP_STATESEPARATOR` is a NOP at runtime, and
   `SignatureHash` serializes the full scriptCode verbatim. Documented
   in `/home/eric/apps/radiant-ledger-app/docs/research/2026-04-18-radiant-sighash-cutpoint.md`.
   This meant signing Glyph inputs needs a new code path, not zero-diff.

2. **Brainstormed the full FT-send implementation** via four parallel
   research agents (coin chooser, tx builder, GUI, test strategy).
   Output consolidated into
   `/home/eric/apps/radiant-ledger-app/docs/brainstorms/2026-04-17-electron-wallet-ft-send-brainstorm.md`.
   Most important finding at this stage: the existing
   `CoinChooserPrivacy` hardcodes its usage in
   `make_unsigned_transaction`; bolting FT logic in would be invasive.
   Cleaner to bypass and write our own builder.

3. **Ran `/workflows:plan`** to turn the brainstorm into a formal,
   sequenced plan. Two refinement passes: one local review, one
   parallel deepening with 9 review+research agents. Several mistakes
   in the plan got caught by reviewers:
   - Bug `hashOutputHashes` plumbing already exists in
     `serialize_preimage` — I had scoped PR A as "add the field." The
     architect found this via source reading. Real work: populate the
     existing zero placeholder for Glyph outputs.
   - `FT_DUST_THRESHOLD = 546` copy-pasted from Bitcoin was wrong for
     Radiant's 10k sat/byte fee regime — at that rate, 546 sats is
     below a 75B output's self-relay cost. Raised to 2M photons with
     a derivation.
   - The plan initially had 7 PRs including a "PR E: contrib/ smoke
     test script." Simplicity review collapsed this to a manual
     testmempoolaccept step cited in the builder PR's body.
   - An **invariant #8** (verify prev scriptPubKey against parent tx)
     got added during deepening but dropped in the second pass: refs
     are content-addressed hashes, so invariant #7 (re-extract ref
     from scriptPubKey bytes at sign time) already closes the entire
     class of peer-substitution attacks. Dropping #8 saved a per-input
     RPC round-trip for zero incremental safety.
   - PR H (CLI parity) added by agent-native reviewer, then deferred
     by simplicity review ("speculative, no user asked"), then added
     back when the user explicitly requested it later.

Plan landed at 649 lines of markdown by the end. Felt like a lot but
proved necessary.

---

## Phase 3 — The build (PRs C → A → B → D → F+G → H)

Branch ordering note: PR C landed first even though it's lettered after
PRs A and B. Reason: PR A's per-output ref computation needs
`GlyphFTOutput.from_script()` to extract refs, so the output class has
to exist before the preimage code can consume it. Discovered during
architect's second-pass review.

Each branch on the fork:

- **PR C (`feat/glyph-ft-output`, `ef8f1682`)** — restructured
  `glyph.py` into a `glyph/` package (classifier.py, core.py,
  wallet_data.py, matching SLP's layout). Added `GlyphFTOutput` as a
  `ScriptOutput` subclass with a single-arg `__new__` (required by
  `protocol_factory` dispatch — kieran caught the earlier
  dual-signature draft as broken). Exception hierarchy with dual
  inheritance: `GlyphInvalidScript(GlyphError, ValueError)` and
  `NotEnoughRxdForFtFee(NotEnoughFunds, GlyphError)` so both generic
  catch-all shapes work. 28 new tests.

- **PR A (`feat/glyph-preimage-refs`, `779108ff`)** — the consensus-
  critical one. Taught `serialize_hash_output` to emit real
  `totalRefs | refsHash` bytes for Glyph outputs instead of the
  hardcoded 36 zero bytes. Added `extract_all_pushrefs()` walker
  (handles both `OP_PUSHINPUTREF` 0xd0 and `OP_PUSHINPUTREFSINGLETON`
  0xd8, since both contribute to pushRefSet per radiant-node source).
  Sort order: MSB-first reverse of ref bytes (matching C++
  `std::set<uint288>::Compare`). Added `_output_script_hex()` helper
  that prefers raw bytes from `_output_scripts` over `addr.to_script()`
  — necessary because the classifier maps FT outputs to `TYPE_ADDRESS`
  whose `to_script()` emits only the 25B P2PKH prologue, losing the
  FT epilogue.

  **The test that is the proof.** `test_transaction.TestRadiantPreimage
  .test_mainnet_signature_verifies_against_our_preimage` reconstructs
  the preimage for vin[1] of mainnet tx
  `8ab5cf40...e2ea92f` and verifies the on-chain DER signature against
  our computed message hash. Signature verification passing is
  mathematically only possible if our preimage is byte-identical to
  what radiant-node signed against. First run of this test: passed.
  That's consensus parity, cryptographically.

- **PR B (`feat/glyph-input-signing`, `d2d1cab7`)** — input-side
  counterpart. Extended `get_preimage_script` to return the full 75B
  or 63B script when `txin['type'] in ('glyph_ft', 'glyph_nft')`.
  Extended `input_script` so Glyph inputs share the `<sig><pubkey>`
  shape with P2PKH (the device signs with full script but the
  scriptSig format is unchanged — confirmed against Pinball's
  production `transfer_nft.js`). Extended `add_input_info` to detect
  `glyph_kind` from `WalletData` and populate `prev_scriptPubKey_hex`
  from the wallet's stored parent tx. Relaxed two strict `assert
  txin['type'] == 'p2pkh'` to allow Glyph types in keystore signing.
  Grep-audit of `txin['type']` across `transaction.py`, `wallet.py`,
  `keystore.py`, plugins — architect's second-pass finding that PR B
  should include this audit.

- **PR D (`feat/glyph-ft-builder`, `c10f3bfd`)** — the builder.
  `make_unsigned_ft_transaction()` + three private helpers
  (`_select_ft_inputs`, `_build_ft_outputs`,
  `_resolve_and_pick_fee_inputs`). The fee loop has a subtle detail:
  adding an RXD input at 10k sat/byte costs 1.48M sats of marginal
  fee, which may demand yet another input. Bounded fixed-point loop
  (cap=4) tracks BOTH `n_rxd_in` and `n_rxd_out` so change-output
  toggles don't desync fee estimation. Distinguishes
  total-insufficient from fragmented-too-small via
  `NotEnoughRxdForFtFee.fragmented`. Extracted `_finalize_unsigned_tx`
  helper so FT txs honor the same `ExcessiveFee` / `BIP_LI01_sort` /
  `run_hook('make_unsigned_transaction')` post-processing as plain-RXD
  txs (architect's review caught this — bypassing
  `make_unsigned_transaction` would silently drop plugin hooks). All
  7 invariants implemented as `raise` (never `assert`, because
  `python -O` strips assertions). 12 new invariant tests.

- **Integration test (`42d17c11`)** — drives
  `make_unsigned_ft_transaction` end-to-end against a mocked wallet.
  5 scenarios: full balance, partial with change, dust error,
  insufficient RXD, ref mismatch. Qt-less.

- **PR F+G (`feat/glyph-ft-gui`, `d2029eb0`)** — Qt surface. Tokens
  tab as a new `MyTreeWidget` (one row per ref, editable label,
  balance, UTXO count). Confirmation modal with full 72-char ref hex
  shown monospace ABOVE the editable label (so a bidi-override attack
  on the label can't rewrite the authoritative identifier). Label
  sanitization strips Unicode Cc + Cf categories and caps at 64
  chars. UTXO list amber coloring for Glyph UTXOs (new
  `ColorScheme.GLYPHBG` entry, mirrors the slpBG pattern).
  One-shot "Confirm recipient" warning stored in
  `wallet.storage['glyph_confirmed_recipients']` with differentiated
  copy for self-send vs. first-send-to-new-address.

- **PR H (`feat/glyph-ft-commands`, `6bac3f78`)** — `Commands.send_ft
  / get_ft_balances / list_ft_utxos / setreflabel` for CLI/JSON-RPC
  parity. `send_ft` defaults to `dry_run=True` — broadcasting is an
  explicit opt-in, matching the GUI's build→confirm→broadcast flow.
  Returns structured error reasons (`dust_change`, `invalid_ref`,
  `insufficient_fee_fragmented`, etc) so agents can branch on them.
  10 new tests exercising the RPC surface without Qt.

Throughout: 122 tests green. No regressions in plain-RXD flows.

---

## Phase 4 — The mainnet gauntlet

With all six PRs built, we set out to prove the whole pipeline on
mainnet. The existing PR A test was already cryptographic proof of
preimage parity, but we wanted a live `testmempoolaccept: allowed=true`
on a Python-built, Python-signed FT send.

**The catch:** nobody local held an FT UTXO. The node wallet had
1,371 addresses but zero FT holdings (scanned 135 recent blocks).
FlipperHub mints NFT singletons, not FTs. No FHC_TOKEN_REF configured
anywhere.

**The decision.** The user chose Option A (full mainnet mint), even
though it meant burning a little RXD. Safer to pay the cost and have
a real artifact than leave a gap in the proof.

**What I did:**

1. **Minted a fresh FT directly** — bypassing the FlipperHub
   commit/reveal choreography. The Radiant consensus rule for creating
   a new FT ref is simple: the spent outpoint becomes the ref by
   construction. So: spent a 0.5 RXD P2PKH UTXO, wrote a 75B FT
   holder output whose ref was `<src_txid_LE><src_vout_LE>`, signed
   via `signrawtransactionwithwallet`. `testmempoolaccept: allowed=
   true`, broadcast succeeded. Mint txid
   `0cb338176d91f21a0c7458d5c62cd78ceecd4eb662ffc3366951605b7b51de96`.

2. **Attempted the FT send via our new code.** First try:
   `testmempoolaccept` rejected with "min relay fee not met." The fee
   came in at 9,646 sat/byte — just under the 10,000 minimum.

**The bug only a live test could catch.** The `estimate_ft_tx_size`
formula had the FT-output coefficient as 75 (script size only),
forgetting the 8B value + 1B length varint wrapper. Actual wire size
is 84 bytes per FT output. At 2-in/3-out, formula produced 490B,
actual was 508B, fee was 9,646 sat/byte → one relay-check below
minimum → rejected. A golden-vector test would have pinned the wrong
answer.

Fixed the coefficient (commit `addaa52b`), updated the corresponding
test vectors, re-ran: `testmempoolaccept: allowed=true`. Send txid
`3115ec4bfc580dd22599e4b253509b4cc29f058e38ebb686a13097a6b4ab49c2`.
Broadcast succeeded.

That's the headline artifact. A new Python-built, Python-signed FT
send accepted by a live Radiant mainnet node. The code went from
theoretical to proven.

---

## Phase 5 — Staging for others to review

The user wanted this on their fork without pushing upstream yet, so
others could validate the direction before committing Radiant-Core to
it.

**What happened:**

- Added a README beta banner listing what's verified vs. what's
  deferred vs. where bugs are most likely. Explicit warning against
  using the fork to move real money.
- Added a "Radiant Glyph FT support" section introducing the Tokens
  tab, Asset dropdown, confirmation modal, label sanitization, and
  the four CLI commands.
- Created `glyph-ft-all` as a single squashed-commit branch — one
  diff to review. Kept all 7 stacked feature branches as well for
  reviewers who want the step-by-step history.
- Pushed all 8 branches to `Zyrtnin-org/Electron-Wallet` (origin).
  Nothing to `Radiant-Core/Electron-Wallet` (upstream) per user's
  explicit instruction.

---

## Phase 6 — Ledger hardware reality check

The user asked if integrating Ledger signing would still take 1-2
weeks of firmware work. Initial response quoted that estimate, but
they pushed back ("would it take this amount of work since we already
have NFT signing from ledger?") — fair challenge.

**Audited the firmware** at `/home/eric/apps/app-radiant/`. Found:

- Full `hashOutputHashes` streaming accumulator already present in
  `helpers.c` — initialized in `radiant_output_hash_init()`, fed
  via opcode walker, finalized into the preimage at the right
  position in `transaction.c:727`.
- Generic opcode walker at `helpers.c:348-360` recognizes all five
  pushref opcodes (`OP_PUSHINPUTREF`, `OP_REQUIREINPUTREF`,
  `OP_DISALLOWPUSHINPUTREF`, `OP_DISALLOWPUSHINPUTREFSIBLING`,
  `OP_PUSHINPUTREFSINGLETON`) and correctly routes both push kinds
  into the refs accumulator.
- Per-ref dedup and sorting already implemented for the inner hash
  at `helpers.c:405-408`.

Firmware isn't "NFT-only." It's **generic over both ref opcodes**.
And the Ledger plugin side (`electroncash_plugins/ledger/ledger.py:366`)
calls `Transaction.get_preimage_script(txin)` — which we already
updated in PR B to return the full 75B/63B script for Glyph inputs.
The preimage bytes the plugin sends to the device are already correct.

**Revised estimate:** ~1 day of hardware testing + optional UX
polish. Not 1-2 weeks of firmware work.

Wrote a test plan (documented in `HANDOFF.md` §"What's NEXT → 1").
Next session: run it against a physical device.

---

## Things we got right

- **Exact-shape classification over loose prefix.** The earlier
  `has_radiant_refs` would have mapped a 241B FT mint-authority
  control script to P2PKH. Exact shape matching makes that shape a
  negative case by length alone. Saved us from a catastrophic
  false-positive class.

- **Content-addressed invariant #7.** Re-extracting the ref from
  scriptPubKey bytes at sign time closes the peer-substitution
  attack class with a single pure-Python check. We almost added an
  invariant #8 (fetch parent tx, verify scriptPubKey) during
  deepening, but realized refs are content-hashes — #7 subsumes it.

- **PR ordering fix (C before A).** Architect caught this: PR A's
  ref-population code needs `GlyphFTOutput.from_script()` to extract
  refs. Without reordering, PR A would have shipped a knowingly
  invalid-signing preimage until PR C landed. Reordered to C → A → B
  → D → F+G → H.

- **Live mainnet proof as the bug-catching layer.** The size-formula
  bug was invisible to golden-vector tests — the tests would have
  pinned the wrong answer. Only the live `testmempoolaccept` caught
  it. Shipping software that touches consensus-critical bytes without
  at least one live mainnet broadcast is risky.

---

## Things we got wrong (and corrected)

- **Initial FT_DUST_THRESHOLD = 546.** Copy-paste from Bitcoin. Wrong
  for Radiant's 10k sat/byte fee regime. Corrected to 2M photons
  during the first plan-refinement pass, before any code depended
  on it.

- **Initial Ledger estimate of 1-2 weeks.** Quoted without reading
  the firmware. User pushed back; audit revealed the firmware was
  already ready. Corrected to ~1 day.

- **Fee size coefficient 75 → 84.** Only caught by the live mainnet
  run. Would have caused real users to hit "min relay fee not met"
  on every send until fixed.

- **Dual-signature GlyphFTOutput.__new__.** Initial draft took
  `(pkh_bytes, ref_bytes)` but `ScriptOutput.protocol_factory`
  dispatches with one positional arg. Kieran caught this; rewritten
  to single-arg `__new__(cls, script)` with a classmethod
  `from_pkh_ref(pkh, ref)` for builder use.

- **Dropped invariant #8 after briefly adding it.** Second-pass
  simplicity review caught that refs are content-addressed, so the
  bytes-level verification was redundant with invariant #7.

---

## Things to remember for next time

- **Always read the firmware before estimating firmware work.** The
  user's pushback on the Ledger estimate was right; my initial
  estimate was based on assumption, not audit.

- **Live broadcast catches bugs golden-vector tests can't.** Size
  formulae, fee estimation, dust thresholds — these have mainnet-only
  failure modes.

- **Small PRs, stacked, with a squashed validator branch.** This
  pattern let us keep atomic commits (for upstream review) AND give
  validators a single diff (for quick "does it work" verification).
  Cost: one extra branch, kept in sync manually. Worth it.

- **The PR ordering fix was non-obvious.** Dependency graphs between
  PRs get tricky when one PR's code consumes types another PR defines.
  Ran into this twice (C before A; also considered during deepening
  whether A+C could be merged, correctly rejected).

- **Research before coding, even when in a hurry.** The sighash
  cut-point research took 2 hours and would have been wasted
  elsewhere in the session if I'd started writing code on the wrong
  signing assumption. The deepening pass caught 9 different mistakes
  in the plan before any of them shipped as bugs.

---

## Scale

**Lines of code landed in this session** (net, not counting the
pre-existing classifier):

- Production code: ~1,400 lines across `electroncash/glyph/`,
  `electroncash/transaction.py`, `electroncash/wallet.py`,
  `electroncash/commands.py`, `electroncash_gui/qt/`
- Tests: ~1,200 lines across 5 test files, 122 new tests
- Documentation: ~1,800 lines across `docs/plans/`,
  `docs/MAINNET_PROOF.md`, `HANDOFF.md`, `SESSION_NARRATIVE.md` (this
  doc), README updates
- Scripts: ~300 lines (`/tmp/mint_ft_direct.py`,
  `/tmp/ft_send_proof.py`, `/tmp/mint_ft_to_ledger.py`)

**Mainnet fees burned:** ~0.15 RXD across the mint + the FT-send.

**Elapsed wall-clock time:** ~two calendar days. Most of the code
arrived in the second day; the first day was spent on brainstorm,
plan, and research.

---

## Where this leaves things

We ended with:

- A fully-functional Glyph FT send wallet in Python
- Cryptographic preimage parity proof (PR A's test)
- Live mainnet `testmempoolaccept: allowed=true` + broadcast (both
  tx ids in HANDOFF.md)
- 8 branches on the fork, staged for others to validate or review
- README banner making beta status explicit
- An understanding that Ledger FT signing is ~1 day of hardware
  testing away — next obvious milestone
- 122 automated tests green

The user now has a clear path to:

1. Run the Ledger test against a device.
2. Invite others to review `glyph-ft-all` or walk the stacked
   branches.
3. Push upstream when Radiant-Core is ready.
4. Ship it.

None of those are blocked on unfinished work here.
