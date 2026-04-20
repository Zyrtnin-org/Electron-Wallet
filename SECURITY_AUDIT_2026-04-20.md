# Radiant Ledger Stack — Security Audit (2026-04-20)

Five-reviewer audit of the Ledger-signing pipeline after the wallet-integrated FT and NFT transfers confirmed on mainnet. Reviewers:

1. **Firmware (C)** — memory safety, bounds, APDU surface, classifier soundness — `security-sentinel` on `app-radiant` + `lib-app-bitcoin` Radiant additions
2. **Wallet (Python)** — input validation, UI spoofing, silent-exception paths — `security-sentinel` on `electroncash` + `electroncash_plugins/ledger` + `electroncash_gui/qt` changes
3. **Crypto + red-team** — sighash correctness, pentest scenarios — `general-purpose` briefed as crypto auditor + red team
4. **Python code quality** — Pythonic idioms, test coverage, DRY, docs — `kieran-python-reviewer`
5. **Architecture + supply chain** — classifier parity, build reproducibility, version matrix — `architecture-strategist`

Four mainnet proofs stood as happy-path evidence the pipeline works end-to-end — but the audit looked for adversarial and latent failures where the happy path masks problems.

---

## Executive summary

**Posture: acceptable with remediation before the next signing session, unsafe to ship to third-party testers until Blockers fixed.**

Nothing in the audit overturns the four mainnet proofs. The private-key path (BIP32 derivation + RFC6979 ECDSA), sighash-scriptcode-for-Glyph (full 75B / 63B template not the P2PKH prologue), firmware bounds on `MAX_OUTPUT_TO_CHECK`, FSM push-ref cap, and sighash-type lock (0x41 enforced device-side) are all sound. Where findings land is in the periphery: display/consensus divergence risks, silent fallback paths, and missing cross-implementation parity.

---

## Blockers (fix before next mainnet send)

### B1 — Wallet never verifies device signature before broadcast
- **Location**: no call site in `electroncash_plugins/ledger/ledger.py` or `electroncash/wallet.py` after `untrustedHashSign`
- **Impact**: Any wallet↔firmware sighash divergence surfaces as a mempool rejection, not a pre-broadcast error. One of the audit findings (B2 below) is a real divergence that hasn't fired because no multi-ref-per-output tx has been signed yet.
- **Fix**: ~40 LoC in `ledger.py` after the sign loop: recompute preimage locally, `secp256k1_ecdsa_verify(pubkey, sig, sha256d(preimage))`, raise on mismatch. Single-best-RoI item in the audit.

### B2 — Wallet ref-sort order disagrees with firmware + oracle
- **Location**: `electroncash/transaction.py:811` sorts refs by `key=lambda r: r[::-1]` (reversed-byte)
- **Firmware**: `lib-app-bitcoin/helpers.c:263-268` sorts by raw `memcmp` (LSB-first)
- **Oracle**: `radiant-ledger-app/scripts/radiant_preimage_oracle.py:207` sorts by hex key (matches firmware)
- **Impact**: Wallet is the outlier. Today's signed txs all have ≤1 ref per output so ordering is moot. First multi-ref output (FT batch with two different tokens, or dMint control output) will produce a wallet-computed preimage the firmware won't validate → signature is against the wrong message → consensus rejection.
- **Fix**: Change `key=lambda r: r[::-1]` to `key=lambda r: r` (raw memcmp). Add a golden vector with ≥2 distinct refs per output to `preimage-vectors.json` so CI catches regressions.

### B3 — Firmware `check_output_displayable` uses hardcoded pkh offset 4, not the Glyph-wrapper-aware `output_script_p2pkh_offset` helper
- **Location**: `/home/eric/apps/app-radiant/lib-app-bitcoin/handler/hash_input_finalize_full.c:88-113`
- **Attack**: A 63-byte Glyph-wrapped output positions its pkh at offset 42, while the change-match compares against offset 4 = inside the 36-byte ref. An attacker who knows the victim's change pkh can embed those 20 bytes at offset 12..31 of a crafted ref, causing the firmware to mark the output as change (`displayable = false`) — the user never sees this output on screen but signs it and it counts toward `totalOutputAmount`. Fund-diversion class of bug.
- **Fix**: Call `output_script_p2pkh_offset(context.currentOutput + 8)` and use that (fallback 4) instead of the hardcoded `OUTPUT_SCRIPT_REGULAR_PRE_LENGTH`. Same helper already exists in `customizable_helpers.c:142-157` for the UI path.

### B4 — Wallet silently downgrades FT/NFT input type to `p2pkh` when parent tx is missing
- **Location**: `electroncash/wallet.py:2739-2743`
- **Impact**: When `prev_scriptpubkey_hex_for_txo` returns `None`, the txin's `type` is silently reset to `'p2pkh'` and signing continues with a 25-byte P2PKH scriptcode against a 75/63-byte consensus script. Signed tx will fail consensus at broadcast — not a silent drain, but a UX landmine. Current send-builders only use UTXOs from `get_utxos()` (parent guaranteed present) so unreachable today; any future PSBT import, co-signer, or invoice path will hit it.
- **Fix**: Raise `GlyphError('parent tx unavailable; cannot sign glyph input safely')` instead of falling through.

### B5 — No tests for `make_unsigned_nft_transfer` or `send_nft`
- **Location**: `electroncash/tests/` has 279 lines of FT builder tests, zero NFT builder tests
- **Impact**: The commit that introduced NFT sending admits "retest cleanly in a fresh session" — ships without regression safety net. Any bug in NFT builder goes straight to mainnet.
- **Fix**: Mirror `TestFtBuilder` with `TestNftTransferBuilder` (success, missing singleton, insufficient RXD, non-P2PKH recipient, post-sign ref-preservation).

---

## High severity

### H1 — Short-script classifier spoofing via stale `currentOutput` bytes
- **Location**: `lib-app-bitcoin/customizable_helpers.c:98-116` (Glyph-wrapper branch of `output_script_is_regular`) and `:142-157` (`output_script_p2pkh_offset`)
- **Attack**: Attacker submits output with declared `scriptSize=1` but `buffer[0]=0x3F`. The shape check dereferences `buffer[1..63]` from leftover bytes in `context.currentOutput`. If a prior output left a matching `0xD8 … 0x75 … 0x88AC` pattern resident, the short script passes `output_script_is_regular` and `get_address_from_output_script` extracts a pkh from stale data → display shows a random address, device signs the short script.
- **Fix**: Plumb the declared `scriptSize` through to the helpers and require `scriptSize == 63` for the Glyph-wrapper branch. (2026-04-16 audit made the same class of fix for the plain P2PKH branch with `buffer[0] >= 0x19`; the Glyph branch needs the analogous guard.)

### H2 — `send_nft` has no post-sign invariant check
- **Location**: `electroncash/commands.py:1020-1082`
- **Impact**: `send_ft` re-runs `assert_ft_invariants` post-sign as a second pass; `send_nft` doesn't. NFT consensus ultimately catches the "no ref preserved" case via `OP_PUSHINPUTREFSINGLETON`, but the wallet has no local check that the signed tx still matches what was built.
- **Fix**: Add `assert_nft_invariants` (or at minimum `is_nft_singleton(tx.outputs()[0])` verification) after `sign_transaction`.

### H3 — Ledger plugin `BaseException` flattens error origin
- **Location**: `electroncash_plugins/ledger/ledger.py:497-499`
- **Impact**: `except BaseException as e: … give_error(e, True)` wraps every error (including `SystemExit`, `KeyboardInterrupt`, torn USB) into a generic `Exception(str(e))`, losing `__cause__`. Operator can't distinguish "device swapped by MITM" from "user unplugged USB."
- **Fix**: Narrow to `except (BTChipException, HIDError, OSError, Exception)` preserving `__cause__`.

---

## Medium severity

- **M1** — Control-char injection in error `message` fields (`commands.py:957-960, 1049-1052`). Destination string passes through `Address.from_string` exceptions verbatim; can carry ANSI escapes or newlines into terminal output. Fix: `repr()` or backslash-replace.
- **M2** — `QMessageBox.setDetailedText(detail)` renders unsanitized node/mempool strings (`glyph_send_dialog.py:222-225`). Fix: pipe through `sanitize_ref_label`'s Cc/Cf filter before display.
- **M3** — `exclude_glyph=True` is the only guard against FT holders being used as RXD fee (`wallet.py:2224-2234`). Fix: assert `not c.get('glyph_kind')` before appending to `rxd_coins`.
- **M4** — `setreflabel` doesn't validate ref length (`commands.py:889-905`). Fix: require 72 hex chars.
- **M5** — Firmware `discardTransaction` echoes up to 200 bytes of attacker-supplied `currentOutput` back to host (`hash_input_finalize_full.c:549-557`). Fix: set `context.outLength = 0` on error path.
- **M6** — Firmware `output_script_is_op_return` reads `buffer[1]`/`[2]` without length check (`customizable_helpers.c:230-237`). Reachable on 0-byte scripts. Fix: gate on `buffer[0] >= 1`.
- **M7** — No wallet↔firmware compatibility check. Older firmware + newer wallet silently signs wrong sighashes. Fix: extend `getFirmwareVersion` with a Radiant-app-minor byte; refuse to sign below minimum supported.
- **M8** — Classifier exists in 3 implementations (firmware C, wallet Python, view-only JS) with no shared test harness. Fix: promote `classifier-vectors.json` to source-of-truth; consume from all three test runners.
- **M9** — Firmware `bip44_derivation_guard` operator-precedence bug (`helpers.c:120-126`). Ternary binds unexpectedly; warning may not fire. Fix: explicit parens.
- **M10** — Wallet console does `from electroncash import commands; commands.Commands(...)` at each click — fresh instance each time (minor performance, not security).

---

## Low severity / code quality

- `send_ft` signs before checking `dry_run` — dry-run preview still prompts for password. Move signing behind `if not dry_run:` or document.
- `SendFtError.reason` Literal overloaded for unrelated cases ("no change address", "amount <= 0"). Add explicit reasons.
- `_resolve_and_pick_fee_inputs` hardcoded 4-iteration budget; fall-through mis-reports "fragmented" when real cause is total shortfall. Split into pure `_compute_fee_iter` + coin selection.
- ~70% duplication between `tokens_list.py` and `nfts_list.py`. Extract `GlyphRefListBase`.
- `send_ft` / `send_nft` repeat 20-line exception-to-dict wrapper. Extract `_glyph_error_dict`.
- Submodule bumps in `app-radiant` are self-reviewed — same committer on both repos. Add PR requirement + branch protection.
- CI builds use `ledger-app-workflows` with `:latest` image reference (documented in `BUILDER.md` as known limitation). Fork the reusable workflow to parameterize the digest.
- Install UX has single-channel supply-chain signal (SHA256 on release page). Publish to multiple independent channels (GitHub release + Discord pinned + maintainer signed gist) and ship `verify_install.sh`.
- Diagnostic SWs `0x6FB1..0x6FB5` not documented in a reserved-range table. Add `doc/sw_codes.md` + `_Static_assert` that every code is in range.
- Firmware classifier uses magic offsets (38, 39, 40, 41, 62, 63) inline. Extract named constants `GLYPH_OUTER_LEN`, `GLYPH_REF_OFFSET`, etc.

---

## Crypto + pentest scenarios — results

| # | Scenario | Feasibility | Impact | Status |
|---|---|---|---|---|
| 1 | Compromised host forging APDUs | Medium | High | Mitigated (UI shows amount+address, sighash locked, BIP32 locked); add tx-level review screen |
| 2 | UI spoof (Alice shown, Bob signed) | High | Critical | **B3 + H1 are live attack surfaces** |
| 3 | Glyph-ref collision via non-standard shape | Medium | High | Classifier is whitelist; FSM is full opcode walker; add tx-level ref cap |
| 4 | Firmware downgrade | Easy | Critical | **M7 — no wallet-side check today** |
| 5 | Tampered build-image backdoor | Medium | Critical | SHA256 pinned; multi-channel publication missing |
| 6 | ElectrumX poisoning / phantom UTXOs | Easy | Med | Trusted-input mechanism blocks actual drain; UX bug only |
| 7 | Mempool pinning of change UTXO | Easy | Med | Ecosystem-level, out of scope |
| 8 | Confused deputy (sign A, bind B) | High | Critical | Trusted-input binds outpoint; **B1 means any firmware bug here is silent** |
| 9 | DoS via crafted output | Medium | Low | Bounds-checked; fuzz `radiant_opcode_feed_byte` (250 LoC hand-written FSM) |
| 10 | Supply-chain: ghcr digest rotation | High | Critical | Pin is `b82bfff7…`; mirror image + offline verify |

---

## Sequencing (highest-leverage first)

1. **B1 — wallet-side ecdsa_verify after sign, before broadcast** (40 LoC, ~1 h). Catches B2 and every future sighash divergence. Single most impactful change.
2. **B2 — fix ref sort order + add ≥2-ref golden vector** (2-char code change + 1 fixture, ~1 h).
3. **B3 — firmware: use `output_script_p2pkh_offset` in `check_output_displayable`** (~2 h including rebuild + flash + retest).
4. **B4 — hard-fail instead of silent p2pkh fallback in `add_input_info`** (~30 min).
5. **H1 — pass declared `scriptSize` into shape helpers, enforce `==63` for Glyph wrapper** (~2 h, firmware rebuild).
6. **B5 — NFT builder test suite** (~3 h, mirrors FT suite).
7. **M8 — promote `classifier-vectors.json` to source-of-truth** (~6 h but unblocks M7 + B3 regression tests + future classifier evolution; highest-leverage architectural work).
8. **M7 — wallet-side firmware-version gate** (~5 h firmware + wallet; dependency on M8 for version-semantic tests).

Top four fixes (B1-B4) under ~5 hours total bring the stack to **safe-for-mainnet-use** including multi-ref outputs.

---

## Aggregate verdict

| Area | Posture |
|---|---|
| Firmware memory safety | ✅ sound (bounds, FSM, push-ref cap, sighashType lock) |
| Firmware classifier | ⚠️ **B3 + H1** — display-vs-sign divergence risks |
| Wallet crypto | ⚠️ **B1 + B2** — no pre-broadcast sig verify, ref-sort drift |
| Wallet input validation | ⚠️ **B4 + M1-M4** — silent fallbacks, control-char leaks |
| Code quality | ⚠️ **B5** — zero NFT tests; otherwise acceptable |
| Architecture / supply chain | ⚠️ **M7 + M8** — classifier drift unmonitored, no version gate |
| Private-key path | ✅ sound (BIP32 on-chip, RFC6979 nonce, secure-element sign) |

**Ready for wider tester release once B1-B5 are patched.**
