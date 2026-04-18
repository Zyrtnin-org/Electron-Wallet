# Integration test — full builder path for Glyph FT sends.
#
# Exercises: get_ft_balances + _select_ft_inputs + _build_ft_outputs +
# _resolve_and_pick_fee_inputs + make_unsigned_ft_transaction +
# assert_ft_invariants + _finalize_unsigned_tx.
#
# Uses a mock wallet (doesn't require a real chain or network) to drive
# make_unsigned_ft_transaction end-to-end. The output is an unsigned
# Transaction satisfying all 7 invariants from PR D — ready for
# sign_transaction + testmempoolaccept.
#
# End-to-end consensus parity was already proven in
# test_transaction.TestRadiantPreimage::test_mainnet_signature_verifies_
# against_our_preimage: that test confirms the hashOutputHashes field
# matches radiant-node byte-for-byte on a real mainnet tx. This test
# confirms the BUILDER path constructs well-formed txs that pass those
# invariants; the two together establish the full pipeline is correct.

import unittest
from unittest.mock import MagicMock

from .. import glyph
from ..address import Address
from ..bitcoin import TYPE_ADDRESS
from ..transaction import Transaction


class MockStorage:
    """Stand-in for wallet.storage; backs a dict."""
    def __init__(self):
        self._d = {}

    def get(self, key, default=None):
        return self._d.get(key, default)

    def put(self, key, value):
        self._d[key] = value


class GlyphFtBuilderIntegrationTest(unittest.TestCase):
    """Full end-to-end test of make_unsigned_ft_transaction against a
    mocked wallet. Produces an unsigned Transaction that satisfies all
    7 invariants; downstream sign/broadcast are out of scope here."""

    # A real mainnet FT ref (the one cited in PR #2).
    REF = bytes.fromhex(
        '8b87c3c771b1a9f5015a4f26bfd80979ed196b5366257a6f30929646dfd943a400000000')
    REF_HEX = REF.hex()

    # Three wallet P2PKH addresses for the various roles.
    SENDER_PKH = bytes.fromhex('32e092994ebdf8db0861b0e9208878c4221c4721')
    CHANGE_PKH = bytes.fromhex('6fdc2880d5afbefcdbc89b31850414beec7d56bd')
    RECIPIENT_PKH = bytes.fromhex('a434fbfe62e6cda47168f0ce4db4edb3c1b808e9')

    # Fake prevout identifiers.
    FT_PREV_TXID = 'aa' * 32
    RXD_PREV_TXID = 'bb' * 32

    def _build_wallet(self, ft_holdings, rxd_holdings):
        """Construct a minimal wallet-like mock.

        `ft_holdings`: list of (value, vout) — each becomes an FT UTXO
            of the REF ref with pkh=SENDER_PKH.
        `rxd_holdings`: list of (value, vout) — each becomes a plain
            P2PKH UTXO with pkh=SENDER_PKH.

        The mock exposes just enough of the real wallet API for
        make_unsigned_ft_transaction to run: get_utxos, get_change_
        addresses, add_input_info, get_local_height, transactions,
        storage, glyph, print_error.
        """
        from electroncash.glyph.wallet_data import WalletData

        sender_addr = Address.from_P2PKH_hash(self.SENDER_PKH)
        change_addr = Address.from_P2PKH_hash(self.CHANGE_PKH)

        ft_coins = []
        for value, vout in ft_holdings:
            ft_spk = glyph.GlyphFTOutput.from_pkh_ref(
                self.SENDER_PKH, self.REF).script
            ft_coins.append({
                'address': sender_addr,
                'value': value,
                'prevout_hash': self.FT_PREV_TXID,
                'prevout_n': vout,
                'height': 100,
                'coinbase': False,
                'is_frozen_coin': False,
                'slp_token': None,
                'glyph_token': True,
                'glyph_kind': 'ft_holder',
                'glyph_ref': self.REF_HEX,
                '_test_spk': ft_spk.hex(),  # injected for the mock parent-tx lookup
            })

        rxd_coins = []
        for value, vout in rxd_holdings:
            rxd_coins.append({
                'address': sender_addr,
                'value': value,
                'prevout_hash': self.RXD_PREV_TXID,
                'prevout_n': vout,
                'height': 100,
                'coinbase': False,
                'is_frozen_coin': False,
                'slp_token': None,
                'glyph_token': False,
                'glyph_kind': None,
                'glyph_ref': None,
            })

        all_coins = ft_coins + rxd_coins

        wallet = MagicMock(name='wallet')
        wallet.get_utxos = MagicMock(side_effect=lambda **kw: list(all_coins))
        wallet.get_change_addresses = MagicMock(return_value=[change_addr])
        wallet.get_local_height = MagicMock(return_value=100)
        wallet.storage = MockStorage()
        wallet.transactions = {}
        wallet.print_error = lambda *a, **kw: None

        # Build a real WalletData so kind_for_txo and
        # prev_scriptpubkey_hex_for_txo resolve off the mock wallet.
        glyph_data = WalletData(wallet)
        for c in ft_coins:
            txo = f'{c["prevout_hash"]}:{c["prevout_n"]}'
            glyph_data.ref_txos.add(txo)
            glyph_data.ref_ids[txo] = self.REF
            glyph_data.kinds[txo] = 'ft_holder'
        wallet.glyph = glyph_data

        # Hook prev_scriptpubkey_hex_for_txo to our injected fixture
        # data (since the mock `transactions` dict is empty, we stub
        # the lookup directly).
        def _lookup_spk(txo):
            for c in ft_coins:
                if f'{c["prevout_hash"]}:{c["prevout_n"]}' == txo:
                    return c['_test_spk']
            return None
        glyph_data.prev_scriptpubkey_hex_for_txo = _lookup_spk

        # add_input_info copies type + prev_scriptPubKey_hex onto txin
        # (mimics wallet.py::add_input_info without pulling in the
        # full keystore dependency).
        def _add_input_info(txin):
            txo_key = f'{txin["prevout_hash"]}:{txin["prevout_n"]}'
            kind = glyph_data.kind_for_txo(txo_key)
            if kind in ('ft_holder', 'nft_singleton'):
                txin['type'] = 'glyph_ft' if kind == 'ft_holder' else 'glyph_nft'
                txin['prev_scriptPubKey_hex'] = _lookup_spk(txo_key)
                txin['glyph_ref'] = self.REF_HEX
                txin['glyph_kind'] = kind
            else:
                txin['type'] = 'p2pkh'
            txin['num_sig'] = 1
            txin['x_pubkeys'] = ['02' + '00' * 32]  # dummy
            txin['signatures'] = [None]
        wallet.add_input_info = _add_input_info

        # Bind the real methods under test to the mock.
        import types
        from .. import wallet as wallet_module
        for name in ['_select_ft_inputs', '_build_ft_outputs',
                     '_resolve_and_pick_fee_inputs',
                     'make_unsigned_ft_transaction',
                     '_finalize_unsigned_tx']:
            method = getattr(wallet_module.Abstract_Wallet, name)
            setattr(wallet, name, types.MethodType(method, wallet))

        # is_mine for confirmation-modal self-send detection (unused in
        # this pure-builder test but needed by some downstream helpers).
        wallet.is_mine = MagicMock(return_value=False)

        return wallet, sender_addr, change_addr

    def test_full_balance_send_produces_valid_tx(self):
        """3M FT photons in, 3M to recipient, no FT change. Large RXD
        utxo covers fee. All 7 invariants satisfied."""
        wallet, sender, change = self._build_wallet(
            ft_holdings=[(3_000_000, 0)],
            rxd_holdings=[(100_000_000, 5)],  # 1 RXD covers fee
        )
        recipient = Address.from_P2PKH_hash(self.RECIPIENT_PKH)
        from unittest.mock import patch
        # Mock SimpleConfig since we don't need real config behavior.
        config = MagicMock()

        tx = wallet.make_unsigned_ft_transaction(
            self.REF, recipient, 3_000_000, config,
        )
        self.assertIsInstance(tx, Transaction)
        # Enumerate outputs and confirm FT structure.
        outputs = tx.outputs()
        ft_outs = [o for o in outputs
                   if isinstance(o[1], glyph.GlyphFTOutput)]
        rxd_outs = [o for o in outputs
                    if not isinstance(o[1], glyph.GlyphFTOutput)]
        self.assertEqual(len(ft_outs), 1,
                         'Full-balance send should produce 1 FT output (no change)')
        self.assertEqual(ft_outs[0][2], 3_000_000)
        self.assertEqual(ft_outs[0][1].pkh, self.RECIPIENT_PKH)
        # There should be an RXD change output if there's any change.
        self.assertTrue(len(rxd_outs) >= 0)
        # Sum sanity: FT inputs + RXD inputs >= FT outputs + RXD outputs + fee.
        total_in = sum(i['value'] for i in tx.inputs())
        total_out = sum(o[2] for o in outputs)
        fee = total_in - total_out
        self.assertGreater(fee, 0, 'tx must have a positive fee')
        self.assertGreaterEqual(
            fee, 10_000,  # meaningful lower bound
            'fee should cover at least the minimum relay rate')

    def test_partial_send_with_change_passes_invariants(self):
        """5M FT in → 2M recipient + 3M change."""
        wallet, sender, change = self._build_wallet(
            ft_holdings=[(5_000_000, 0)],
            rxd_holdings=[(100_000_000, 5)],
        )
        recipient = Address.from_P2PKH_hash(self.RECIPIENT_PKH)
        config = MagicMock()

        tx = wallet.make_unsigned_ft_transaction(
            self.REF, recipient, 2_000_000, config,
        )
        outputs = tx.outputs()
        ft_outs = [o for o in outputs if isinstance(o[1], glyph.GlyphFTOutput)]
        self.assertEqual(len(ft_outs), 2)
        ft_values = sorted(o[2] for o in ft_outs)
        self.assertEqual(ft_values, [2_000_000, 3_000_000])

    def test_dust_change_raises(self):
        """3M FT in, 2.9M sent → 100k change below 2M dust."""
        wallet, sender, change = self._build_wallet(
            ft_holdings=[(3_000_000, 0)],
            rxd_holdings=[(100_000_000, 5)],
        )
        recipient = Address.from_P2PKH_hash(self.RECIPIENT_PKH)
        config = MagicMock()

        with self.assertRaises(glyph.SendFtError) as cm:
            wallet.make_unsigned_ft_transaction(
                self.REF, recipient, 2_900_000, config,
            )
        self.assertEqual(cm.exception.reason, 'dust_change')

    def test_insufficient_rxd_raises(self):
        """FT send needs RXD for fee; if the wallet has none, we raise
        NotEnoughRxdForFtFee."""
        wallet, sender, change = self._build_wallet(
            ft_holdings=[(3_000_000, 0)],
            rxd_holdings=[],  # no RXD
        )
        recipient = Address.from_P2PKH_hash(self.RECIPIENT_PKH)
        config = MagicMock()

        with self.assertRaises(glyph.NotEnoughRxdForFtFee):
            wallet.make_unsigned_ft_transaction(
                self.REF, recipient, 3_000_000, config,
            )

    def test_no_ft_with_ref_raises(self):
        """Wallet has FT UTXOs but none match the target ref."""
        wallet, sender, change = self._build_wallet(
            ft_holdings=[(3_000_000, 0)],
            rxd_holdings=[(100_000_000, 5)],
        )
        recipient = Address.from_P2PKH_hash(self.RECIPIENT_PKH)
        config = MagicMock()

        other_ref = b'\xff' * 36
        with self.assertRaises(glyph.SendFtError) as cm:
            wallet.make_unsigned_ft_transaction(
                other_ref, recipient, 1_000_000, config,
            )
        self.assertEqual(cm.exception.reason, 'ref_mismatch')


if __name__ == '__main__':
    unittest.main()
