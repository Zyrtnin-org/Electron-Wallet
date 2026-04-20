# Radiant Ledger — mainnet proofs

Three transactions, each signed entirely on a Ledger Nano S Plus running the community [`app-radiant`](https://github.com/Zyrtnin-org/app-radiant) firmware and broadcast through this wallet.

| # | Asset | First Ledger-signed mainnet tx | Notes |
| --- | --- | --- | --- |
| 1 | Plain RXD | [`de3574979f986616b4152c4294b85562318292490d3587d8fe32aff456893743`](https://explorer.radiantblockchain.org/tx/de3574979f986616b4152c4294b85562318292490d3587d8fe32aff456893743) | Standard P2PKH send. First Radiant tx ever signed by a Ledger. Block 420762, 2026-04-15. |
| 2 | Glyph NFT singleton | [`af0cd27d9cda2113cc9882274ff7015f09f759ffe8b71b0c17e86c64fb6201c9`](https://explorer.radiantblockchain.org/tx/af0cd27d9cda2113cc9882274ff7015f09f759ffe8b71b0c17e86c64fb6201c9) | 63-byte NFT-holder template output; device-computed `hashOutputHashes`. 2026-04-16. |
| 3 | Glyph FT transfer | [`5d5b2600d0f06c35f67778f8f103a8b8ff86bef49d99d7172afc6db12f047390`](https://explorer.radiantblockchain.org/tx/5d5b2600d0f06c35f67778f8f103a8b8ff86bef49d99d7172afc6db12f047390) | 3-output: FT recipient + FT change + RXD change. Unblocked by `MAX_OUTPUT_TO_CHECK=200` buffer bump in firmware v0.0.4. 2026-04-20. |

## How to verify yourself

```bash
radiant-cli getrawtransaction <txid> true
```

For each row, the signature on every input verifies under the public key derived at `m/44'/512'/0'/<chain>/<index>` from the device's master seed — the private key never leaves the secure element.

## Repos

- Firmware: [`Zyrtnin-org/app-radiant`](https://github.com/Zyrtnin-org/app-radiant) tag `v0.0.4-glyph-ft-transfer`
- Opcode walker + output FSM: [`Zyrtnin-org/lib-app-bitcoin`](https://github.com/Zyrtnin-org/lib-app-bitcoin) branch `radiant-v1`
- Wallet: this repo, branch `glyph-ft-all`
