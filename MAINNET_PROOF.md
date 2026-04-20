# Radiant Ledger — mainnet proofs

Three transactions, each signed on a Ledger Nano S Plus running the community [`app-radiant`](https://github.com/Zyrtnin-org/app-radiant) firmware. Private keys stayed in the secure element for all three.

| # | Asset | First Ledger-signed mainnet tx | Host-side signing code | Notes |
| --- | --- | --- | --- | --- |
| 1 | Plain RXD | [`de3574979f986616b4152c4294b85562318292490d3587d8fe32aff456893743`](https://explorer.radiantblockchain.org/tx/de3574979f986616b4152c4294b85562318292490d3587d8fe32aff456893743) | [`radiant-ledger-app`](https://github.com/Zyrtnin-org/radiant-ledger-app) — direct-APDU Python harness | Standard P2PKH send. First Radiant tx ever signed by a Ledger. Block 420762, 2026-04-15. |
| 2 | Glyph NFT singleton | [`af0cd27d9cda2113cc9882274ff7015f09f759ffe8b71b0c17e86c64fb6201c9`](https://explorer.radiantblockchain.org/tx/af0cd27d9cda2113cc9882274ff7015f09f759ffe8b71b0c17e86c64fb6201c9) | [`radiant-ledger-app`](https://github.com/Zyrtnin-org/radiant-ledger-app) — `spend_real_glyph_2in.py` extended for transfer | 63-byte NFT-holder template output; device-computed `hashOutputHashes`. 2026-04-16. |
| 3 | Glyph FT transfer | [`5d5b2600d0f06c35f67778f8f103a8b8ff86bef49d99d7172afc6db12f047390`](https://explorer.radiantblockchain.org/tx/5d5b2600d0f06c35f67778f8f103a8b8ff86bef49d99d7172afc6db12f047390) | **this wallet** — `electroncash_plugins/ledger` + `btchip` + `send_ft` console command | 3-output: FT recipient + FT change + RXD change. Unblocked by `MAX_OUTPUT_TO_CHECK=200` buffer bump in firmware v0.0.4. 2026-04-20. |

Rows 1 and 2 used a direct-APDU harness (minimal host wrapping around the Ledger protocol). Row 3 is the first Radiant Glyph asset signed through a full wallet integration with UTXO selection, fee calculation, and change routing — the prerequisite for end-user Ledger signing.

## Known wallet-side gap — NFT transfer

Wallet-driven NFT transfers (via the Tokens-tab equivalent "Send NFT" dialog) build the correct 63-byte singleton output and reach the firmware's `finalizeInput`, but that APDU returns `SW_TECHNICAL_PROBLEM_2` (0x6F0F) on `lib-app-bitcoin` tag `f8c8a4a`. The `af0cd27d` proof above shows the firmware itself CAN sign NFT transfers; the direct-APDU harness reaches it through a different code path than btchip's streaming `e04a FF … / e04a 80 …` sequence. The discrepancy is not a chunk-size overflow (buffer is already 200B) — most likely an interaction between how `finalizeInput`'s output-streaming frames the 63-byte NFT output and how the firmware's per-output FSM or change-path comparison handles it.

The pipeline code (`GlyphNFTOutput`, `make_unsigned_nft_transfer`, `Commands.send_nft`, plugin bypass for `GlyphNFTOutput`, GUI dialog) is committed and correct at the wallet layer; the residual blocker is a firmware-side debug requiring a `PRINTF`-enabled build to trace which byte the FSM rejects.

## How to verify yourself

```bash
radiant-cli getrawtransaction <txid> true
```

For each row, the signature on every input verifies under the public key derived at `m/44'/512'/0'/<chain>/<index>` from the device's master seed — the private key never leaves the secure element.

## Repos

- Firmware: [`Zyrtnin-org/app-radiant`](https://github.com/Zyrtnin-org/app-radiant) tag `v0.0.4-glyph-ft-transfer`
- Opcode walker + output FSM: [`Zyrtnin-org/lib-app-bitcoin`](https://github.com/Zyrtnin-org/lib-app-bitcoin) branch `radiant-v1`
- Wallet: this repo, branch `glyph-ft-all`
