import types
import unittest
from decimal import Decimal as PyDecimal
from unittest.mock import MagicMock

from ..commands import Commands


class TestCommands(unittest.TestCase):

    def test_setconfig_non_auth_number(self):
        self.assertEqual(7777, Commands._setconfig_normalize_value('rpcport', "7777"))
        self.assertEqual(7777, Commands._setconfig_normalize_value('rpcport', '7777'))
        self.assertAlmostEqual(PyDecimal(2.3), Commands._setconfig_normalize_value('somekey', '2.3'))

    def test_setconfig_non_auth_number_as_string(self):
        self.assertEqual("7777", Commands._setconfig_normalize_value('somekey', "'7777'"))

    def test_setconfig_non_auth_boolean(self):
        self.assertEqual(True, Commands._setconfig_normalize_value('show_console_tab', "true"))
        self.assertEqual(True, Commands._setconfig_normalize_value('show_console_tab', "True"))

    def test_setconfig_non_auth_list(self):
        self.assertEqual(['file:///var/www/', 'https://electrum.org'],
            Commands._setconfig_normalize_value('url_rewrite', "['file:///var/www/','https://electrum.org']"))
        self.assertEqual(['file:///var/www/', 'https://electrum.org'],
            Commands._setconfig_normalize_value('url_rewrite', '["file:///var/www/","https://electrum.org"]'))

    def test_setconfig_auth(self):
        self.assertEqual("7777", Commands._setconfig_normalize_value('rpcuser', "7777"))
        self.assertEqual("7777", Commands._setconfig_normalize_value('rpcuser', '7777'))
        self.assertEqual("7777", Commands._setconfig_normalize_value('rpcpassword', '7777'))
        self.assertEqual("2asd", Commands._setconfig_normalize_value('rpcpassword', '2asd'))
        self.assertEqual("['file:///var/www/','https://electrum.org']",
            Commands._setconfig_normalize_value('rpcpassword', "['file:///var/www/','https://electrum.org']"))


class TestGlyphFtCommands(unittest.TestCase):
    """PR H: Commands.send_ft / get_ft_balances / list_ft_utxos /
    setreflabel. Exercises the RPC surface without Qt. The builder
    itself is covered by test_glyph_ft_builder_integration; these
    tests focus on the Commands wrapper's argument parsing, structured
    error return, and dry_run contract."""

    REF = bytes.fromhex(
        '8b87c3c771b1a9f5015a4f26bfd80979ed196b5366257a6f30929646dfd943a400000000')
    REF_HEX = REF.hex()

    SENDER_PKH = bytes.fromhex('32e092994ebdf8db0861b0e9208878c4221c4721')
    CHANGE_PKH = bytes.fromhex('6fdc2880d5afbefcdbc89b31850414beec7d56bd')
    RECIPIENT_PKH = bytes.fromhex('a434fbfe62e6cda47168f0ce4db4edb3c1b808e9')

    def _make_commands(self, ft_holdings=None, rxd_holdings=None):
        """Build a Commands with a wallet mock that has the specified
        FT/RXD UTXO holdings. Returns (commands, recipient_address)."""
        from ..address import Address
        from ..glyph.wallet_data import WalletData
        from .. import wallet as wallet_module

        ft_holdings = ft_holdings or []
        rxd_holdings = rxd_holdings or []
        sender_addr = Address.from_P2PKH_hash(self.SENDER_PKH)
        change_addr = Address.from_P2PKH_hash(self.CHANGE_PKH)
        recipient = Address.from_P2PKH_hash(self.RECIPIENT_PKH)

        # Shared storage dict backing the mock.
        storage_data = {}

        class _Storage:
            def get(self, k, default=None): return storage_data.get(k, default)
            def put(self, k, v): storage_data[k] = v

        ft_coins = []
        for value, vout in ft_holdings:
            from ..glyph import GlyphFTOutput
            ft_spk = GlyphFTOutput.from_pkh_ref(self.SENDER_PKH, self.REF).script
            ft_coins.append({
                'address': sender_addr, 'value': value,
                'prevout_hash': 'aa' * 32, 'prevout_n': vout,
                'height': 100, 'coinbase': False,
                'is_frozen_coin': False, 'slp_token': None,
                'glyph_token': True, 'glyph_kind': 'ft_holder',
                'glyph_ref': self.REF_HEX, '_test_spk': ft_spk.hex(),
            })

        rxd_coins = []
        for value, vout in rxd_holdings:
            rxd_coins.append({
                'address': sender_addr, 'value': value,
                'prevout_hash': 'bb' * 32, 'prevout_n': vout,
                'height': 100, 'coinbase': False,
                'is_frozen_coin': False, 'slp_token': None,
                'glyph_token': False, 'glyph_kind': None,
                'glyph_ref': None,
            })
        all_coins = ft_coins + rxd_coins

        wallet = MagicMock(name='wallet')
        wallet.get_utxos = MagicMock(side_effect=lambda **kw: list(all_coins))
        wallet.get_change_addresses = MagicMock(return_value=[change_addr])
        wallet.get_local_height = MagicMock(return_value=100)
        wallet.storage = _Storage()
        wallet.transactions = {}
        wallet.print_error = lambda *a, **kw: None
        wallet.has_password = MagicMock(return_value=False)
        wallet.sign_transaction = MagicMock()  # no-op; tests check shape, not signatures

        glyph_data = WalletData(wallet)
        for c in ft_coins:
            txo = f'{c["prevout_hash"]}:{c["prevout_n"]}'
            glyph_data.ref_txos.add(txo)
            glyph_data.ref_ids[txo] = self.REF
            glyph_data.kinds[txo] = 'ft_holder'
        wallet.glyph = glyph_data

        def _lookup_spk(txo):
            for c in ft_coins:
                if f'{c["prevout_hash"]}:{c["prevout_n"]}' == txo:
                    return c['_test_spk']
            return None
        glyph_data.prev_scriptpubkey_hex_for_txo = _lookup_spk

        def _add_input_info(txin):
            txo_key = f'{txin["prevout_hash"]}:{txin["prevout_n"]}'
            kind = glyph_data.kind_for_txo(txo_key)
            if kind == 'ft_holder':
                txin['type'] = 'glyph_ft'
                txin['prev_scriptPubKey_hex'] = _lookup_spk(txo_key)
                txin['glyph_ref'] = self.REF_HEX
                txin['glyph_kind'] = kind
            else:
                txin['type'] = 'p2pkh'
            txin['num_sig'] = 1
            txin['x_pubkeys'] = ['02' + '00' * 32]
            txin['signatures'] = [None]
        wallet.add_input_info = _add_input_info

        # Bind real wallet methods (bypasses the Abstract_Wallet
        # keystore/address book machinery).
        for name in ['_select_ft_inputs', '_build_ft_outputs',
                     '_resolve_and_pick_fee_inputs',
                     'make_unsigned_ft_transaction',
                     '_finalize_unsigned_tx', 'get_ft_balances']:
            method = getattr(wallet_module.Abstract_Wallet, name)
            setattr(wallet, name, types.MethodType(method, wallet))

        config = MagicMock()
        commands = Commands(config, wallet, network=None)
        return commands, recipient

    def test_get_ft_balances_returns_per_ref_dict(self):
        cmds, _ = self._make_commands(
            ft_holdings=[(3_000_000, 0), (5_000_000, 1)],
            rxd_holdings=[(50_000_000, 2)],
        )
        balances = cmds.get_ft_balances()
        self.assertIn(self.REF_HEX, balances)
        self.assertEqual(balances[self.REF_HEX]['balance'], 8_000_000)
        self.assertEqual(balances[self.REF_HEX]['utxo_count'], 2)

    def test_list_ft_utxos_filters_by_ref(self):
        cmds, _ = self._make_commands(
            ft_holdings=[(3_000_000, 0), (5_000_000, 1)],
            rxd_holdings=[(50_000_000, 2)],
        )
        all_ft = cmds.list_ft_utxos()
        self.assertEqual(len(all_ft), 2)
        for row in all_ft:
            self.assertEqual(row['glyph_kind'], 'ft_holder')
            self.assertEqual(row['glyph_ref'], self.REF_HEX)
        # Filter to a different ref → empty.
        none = cmds.list_ft_utxos(ref='ff' * 36)
        self.assertEqual(none, [])
        # Filter to the known ref → same as all.
        filtered = cmds.list_ft_utxos(ref=self.REF_HEX)
        self.assertEqual(len(filtered), 2)

    def test_setreflabel_sanitizes_and_persists(self):
        cmds, _ = self._make_commands()
        # Label with an RTL override that would visually rewrite a line.
        result = cmds.setreflabel(self.REF_HEX, 'My\u202eToken')
        self.assertEqual(result['label'], 'MyToken')  # stripped
        labels = cmds.wallet.storage.get('glyph_ref_labels')
        self.assertEqual(labels.get(self.REF_HEX), 'MyToken')
        # Clearing works.
        result = cmds.setreflabel(self.REF_HEX, '')
        self.assertNotIn(self.REF_HEX, cmds.wallet.storage.get('glyph_ref_labels'))

    def test_send_ft_invalid_ref_returns_structured_error(self):
        cmds, recipient = self._make_commands(
            ft_holdings=[(3_000_000, 0)],
            rxd_holdings=[(50_000_000, 2)],
        )
        result = cmds.send_ft('not_hex', recipient.to_ui_string(), 1_000_000)
        self.assertIsNotNone(result['error'])
        self.assertEqual(result['error']['reason'], 'invalid_ref')
        self.assertFalse(result['broadcast'])

    def test_send_ft_invalid_ref_length_returns_structured_error(self):
        cmds, recipient = self._make_commands(
            ft_holdings=[(3_000_000, 0)],
            rxd_holdings=[(50_000_000, 2)],
        )
        result = cmds.send_ft('aa' * 32, recipient.to_ui_string(), 1_000_000)
        self.assertEqual(result['error']['reason'], 'invalid_ref')

    def test_send_ft_invalid_recipient_returns_structured_error(self):
        cmds, _ = self._make_commands(
            ft_holdings=[(3_000_000, 0)],
            rxd_holdings=[(50_000_000, 2)],
        )
        result = cmds.send_ft(self.REF_HEX, 'not_an_address', 1_000_000)
        self.assertEqual(result['error']['reason'], 'invalid_recipient')

    def test_send_ft_dry_run_returns_tx_hex_without_broadcast(self):
        cmds, recipient = self._make_commands(
            ft_holdings=[(3_000_000, 0)],
            rxd_holdings=[(100_000_000, 2)],
        )
        result = cmds.send_ft(
            self.REF_HEX, recipient.to_ui_string(), 3_000_000,
            dry_run=True,
        )
        self.assertIsNone(result['error'])
        self.assertFalse(result['broadcast'])
        self.assertIsNotNone(result['tx_hex'])
        # Tx hex should be a hex string. (tx_hash is only meaningful
        # for signed txs; our mock sign_transaction is a no-op so the
        # returned hash may be for an unsigned-skeleton — caller must
        # verify against the real network anyway.)
        bytes.fromhex(result['tx_hex'])  # must parse without raising

    def test_send_ft_dust_change_returns_structured_error(self):
        cmds, recipient = self._make_commands(
            ft_holdings=[(3_000_000, 0)],
            rxd_holdings=[(100_000_000, 2)],
        )
        # 2.9M sent → 100k change below 2M dust.
        result = cmds.send_ft(
            self.REF_HEX, recipient.to_ui_string(), 2_900_000,
            dry_run=True,
        )
        self.assertEqual(result['error']['reason'], 'dust_change')

    def test_send_ft_insufficient_rxd_returns_structured_error(self):
        cmds, recipient = self._make_commands(
            ft_holdings=[(3_000_000, 0)],
            rxd_holdings=[],
        )
        result = cmds.send_ft(
            self.REF_HEX, recipient.to_ui_string(), 3_000_000,
            dry_run=True,
        )
        self.assertIn(
            result['error']['reason'],
            ('insufficient_fee', 'insufficient_fee_fragmented'),
        )

    def test_send_ft_broadcast_mode_requires_network(self):
        cmds, recipient = self._make_commands(
            ft_holdings=[(3_000_000, 0)],
            rxd_holdings=[(100_000_000, 2)],
        )
        # cmds was built with network=None; broadcasting must fail
        # gracefully with a structured error.
        result = cmds.send_ft(
            self.REF_HEX, recipient.to_ui_string(), 3_000_000,
            dry_run=False,
        )
        self.assertFalse(result['broadcast'])
        self.assertEqual(result['error']['reason'], 'broadcast_failed')
        # Signing still happened — tx_hex is populated.
        self.assertIsNotNone(result['tx_hex'])


class TestGlyphNftCommands(unittest.TestCase):
    """B5 (SECURITY_AUDIT_2026-04-20): Commands.send_nft + the
    make_unsigned_nft_transfer builder. Mirrors TestGlyphFtCommands
    structure. Covers argument validation, ref-mismatch detection,
    dry_run contract, broadcast-without-network, and output-shape
    preservation (the 63-byte singleton template is byte-identical
    between input and output)."""

    REF = bytes.fromhex(
        '8b87c3c771b1a9f5015a4f26bfd80979ed196b5366257a6f30929646dfd943a400000000')
    REF_HEX = REF.hex()

    SENDER_PKH = bytes.fromhex('32e092994ebdf8db0861b0e9208878c4221c4721')
    CHANGE_PKH = bytes.fromhex('6fdc2880d5afbefcdbc89b31850414beec7d56bd')
    RECIPIENT_PKH = bytes.fromhex('a434fbfe62e6cda47168f0ce4db4edb3c1b808e9')

    def _make_commands(self, nft_holdings=None, rxd_holdings=None):
        """Same shape as TestGlyphFtCommands._make_commands but
        produces GlyphNFTOutput-typed coins for the singleton UTXO."""
        from ..address import Address
        from ..glyph.wallet_data import WalletData
        from .. import wallet as wallet_module

        nft_holdings = nft_holdings or []
        rxd_holdings = rxd_holdings or []
        sender_addr = Address.from_P2PKH_hash(self.SENDER_PKH)
        change_addr = Address.from_P2PKH_hash(self.CHANGE_PKH)
        recipient = Address.from_P2PKH_hash(self.RECIPIENT_PKH)

        storage_data = {}

        class _Storage:
            def get(self, k, default=None): return storage_data.get(k, default)
            def put(self, k, v): storage_data[k] = v

        nft_coins = []
        for value, vout in nft_holdings:
            from ..glyph import GlyphNFTOutput
            nft_spk = GlyphNFTOutput.from_pkh_ref(self.SENDER_PKH, self.REF).script
            nft_coins.append({
                'address': sender_addr, 'value': value,
                'prevout_hash': 'cc' * 32, 'prevout_n': vout,
                'height': 100, 'coinbase': False,
                'is_frozen_coin': False, 'slp_token': None,
                'glyph_token': True, 'glyph_kind': 'nft_singleton',
                'glyph_ref': self.REF_HEX, '_test_spk': nft_spk.hex(),
            })

        rxd_coins = []
        for value, vout in rxd_holdings:
            rxd_coins.append({
                'address': sender_addr, 'value': value,
                'prevout_hash': 'dd' * 32, 'prevout_n': vout,
                'height': 100, 'coinbase': False,
                'is_frozen_coin': False, 'slp_token': None,
                'glyph_token': False, 'glyph_kind': None,
                'glyph_ref': None,
            })
        all_coins = nft_coins + rxd_coins

        wallet = MagicMock(name='wallet')
        wallet.get_utxos = MagicMock(side_effect=lambda **kw: list(all_coins))
        wallet.get_change_addresses = MagicMock(return_value=[change_addr])
        wallet.get_local_height = MagicMock(return_value=100)
        wallet.storage = _Storage()
        wallet.transactions = {}
        wallet.print_error = lambda *a, **kw: None
        wallet.has_password = MagicMock(return_value=False)
        wallet.sign_transaction = MagicMock()

        glyph_data = WalletData(wallet)
        for c in nft_coins:
            txo = f'{c["prevout_hash"]}:{c["prevout_n"]}'
            glyph_data.ref_txos.add(txo)
            glyph_data.ref_ids[txo] = self.REF
            glyph_data.kinds[txo] = 'nft_singleton'
        wallet.glyph = glyph_data

        def _lookup_spk(txo):
            for c in nft_coins:
                if f'{c["prevout_hash"]}:{c["prevout_n"]}' == txo:
                    return c['_test_spk']
            return None
        glyph_data.prev_scriptpubkey_hex_for_txo = _lookup_spk

        def _add_input_info(txin):
            txo_key = f'{txin["prevout_hash"]}:{txin["prevout_n"]}'
            kind = glyph_data.kind_for_txo(txo_key)
            if kind == 'nft_singleton':
                txin['type'] = 'glyph_nft'
                txin['prev_scriptPubKey_hex'] = _lookup_spk(txo_key)
                txin['glyph_ref'] = self.REF_HEX
                txin['glyph_kind'] = kind
            else:
                txin['type'] = 'p2pkh'
            txin['num_sig'] = 1
            txin['x_pubkeys'] = ['02' + '00' * 32]
            txin['signatures'] = [None]
        wallet.add_input_info = _add_input_info

        for name in ['_resolve_and_pick_fee_inputs',
                     'make_unsigned_nft_transfer',
                     '_finalize_unsigned_tx', 'get_nft_holdings']:
            method = getattr(wallet_module.Abstract_Wallet, name)
            setattr(wallet, name, types.MethodType(method, wallet))

        config = MagicMock()
        commands = Commands(config, wallet, network=None)
        return commands, recipient

    def test_send_nft_invalid_ref_returns_structured_error(self):
        cmds, recipient = self._make_commands(
            nft_holdings=[(1_880_000, 0)],
            rxd_holdings=[(50_000_000, 2)],
        )
        result = cmds.send_nft('not_hex', recipient.to_ui_string())
        self.assertIsNotNone(result['error'])
        self.assertEqual(result['error']['reason'], 'invalid_ref')
        self.assertFalse(result['broadcast'])

    def test_send_nft_invalid_ref_length_returns_structured_error(self):
        cmds, recipient = self._make_commands(
            nft_holdings=[(1_880_000, 0)],
            rxd_holdings=[(50_000_000, 2)],
        )
        result = cmds.send_nft('aa' * 20, recipient.to_ui_string())
        self.assertEqual(result['error']['reason'], 'invalid_ref')

    def test_send_nft_invalid_recipient_returns_structured_error(self):
        cmds, _ = self._make_commands(
            nft_holdings=[(1_880_000, 0)],
            rxd_holdings=[(50_000_000, 2)],
        )
        result = cmds.send_nft(self.REF_HEX, 'not_an_address')
        self.assertEqual(result['error']['reason'], 'invalid_recipient')

    def test_send_nft_missing_singleton_returns_structured_error(self):
        """B2 (build): wallet holds no singleton for this ref →
        make_unsigned_nft_transfer raises SendFtError(ref_mismatch),
        wrapped into structured error."""
        cmds, recipient = self._make_commands(
            nft_holdings=[],  # no NFT owned
            rxd_holdings=[(50_000_000, 2)],
        )
        result = cmds.send_nft(self.REF_HEX, recipient.to_ui_string())
        self.assertEqual(result['error']['reason'], 'ref_mismatch')

    def test_send_nft_dry_run_returns_tx_hex_without_broadcast(self):
        cmds, recipient = self._make_commands(
            nft_holdings=[(1_880_000, 0)],
            rxd_holdings=[(100_000_000, 2)],
        )
        result = cmds.send_nft(
            self.REF_HEX, recipient.to_ui_string(), dry_run=True,
        )
        self.assertIsNone(result['error'])
        self.assertFalse(result['broadcast'])
        self.assertIsNotNone(result['tx_hex'])
        bytes.fromhex(result['tx_hex'])  # parses

    def test_send_nft_output_preserves_ref_and_is_63_bytes(self):
        """Singleton transfer must emit exactly one 63-byte NFT output
        carrying the SAME 36-byte ref as the input — this is the
        consensus-critical preservation invariant for OP_PUSHINPUTREFSINGLETON.

        On deserialize the classifier maps 63B singletons to
        TYPE_ADDRESS (stripping the Glyph wrapper for UI purposes), so
        we inspect the raw output scripts in the tx wire bytes and
        run them back through the classifier."""
        from ..glyph import classify_glyph_output
        from ..transaction import Transaction
        cmds, recipient = self._make_commands(
            nft_holdings=[(1_880_000, 0)],
            rxd_holdings=[(100_000_000, 2)],
        )
        result = cmds.send_nft(
            self.REF_HEX, recipient.to_ui_string(), dry_run=True,
        )
        self.assertIsNone(result['error'])
        tx = Transaction(result['tx_hex'])
        tx.deserialize()
        nft_hits = []
        for n in range(len(tx.outputs())):
            spk = tx.output_script(n)
            if not spk:
                continue
            match = classify_glyph_output(spk)
            if match is not None:
                kind, pkh, ref = match
                nft_hits.append((kind, pkh, ref, len(spk)))
        self.assertEqual(len(nft_hits), 1,
                         "expected exactly one NFT output (singleton invariant)")
        kind, pkh, ref, spk_len = nft_hits[0]
        self.assertEqual(kind, 'nft_singleton')
        self.assertEqual(spk_len, 63)
        self.assertEqual(ref, self.REF,
                         "NFT output must carry the same ref as the input")
        self.assertEqual(pkh, self.RECIPIENT_PKH)

    def test_send_nft_broadcast_mode_requires_network(self):
        cmds, recipient = self._make_commands(
            nft_holdings=[(1_880_000, 0)],
            rxd_holdings=[(100_000_000, 2)],
        )
        result = cmds.send_nft(
            self.REF_HEX, recipient.to_ui_string(), dry_run=False,
        )
        self.assertFalse(result['broadcast'])
        self.assertEqual(result['error']['reason'], 'broadcast_failed')
        self.assertIsNotNone(result['tx_hex'])

    def test_get_nft_holdings_returns_one_row_per_singleton(self):
        cmds, _ = self._make_commands(
            nft_holdings=[(1_880_000, 0)],
            rxd_holdings=[(50_000_000, 2)],
        )
        nfts = cmds.wallet.get_nft_holdings()
        self.assertEqual(len(nfts), 1)
        self.assertEqual(nfts[0]['ref'], self.REF_HEX)
        self.assertEqual(nfts[0]['value'], 1_880_000)
