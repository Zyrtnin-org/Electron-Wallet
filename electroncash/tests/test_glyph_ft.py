# Tests for GlyphFTOutput, the exception hierarchy, and policy constants
# landed in PR C.
#
# Scope of this file — consolidated per plan reviewer note (one test file
# per submodule of glyph/):
#
#   - GlyphFTOutput construction from raw script bytes
#   - GlyphFTOutput.from_pkh_ref builder
#   - Byte-identical round-trip against the same 3 mainnet FT vectors used
#     by test_glyph_classifier.py
#   - protocol_classes dispatch (ScriptOutput.protocol_factory(bytes)
#     returns GlyphFTOutput on FT holder input)
#   - Hashability + set/dict round-trips
#   - Exception hierarchy dual-inheritance contracts
#   - Policy constants are the expected values + types
#
# PR D tests (coin chooser, builder, invariants) land in this same file
# when PR D is authored.

import unittest

from .. import glyph
from ..address import Address, ScriptOutput


# -------- Fixtures — same 3 mainnet FT vectors as test_glyph_classifier.py -

FT_VECTORS = [
    # (name, spk_hex, pkh_hex, ref_hex)
    ('ft_holder_75b_262a4d95',
     '76a91432e092994ebdf8db0861b0e9208878c4221c472188acbdd08b87c3c771b1a9f5015a4f26bfd80979ed196b5366257a6f30929646dfd943a400000000dec0e9aa76e378e4a269e69d',
     '32e092994ebdf8db0861b0e9208878c4221c4721',
     '8b87c3c771b1a9f5015a4f26bfd80979ed196b5366257a6f30929646dfd943a400000000'),
    ('ft_holder_75b_6ce2bdb5_vout0',
     '76a9146fdc2880d5afbefcdbc89b31850414beec7d56bd88acbdd04bbba9407337be1465de8182dd88f5fb82355dd94e6acb45b1bc5e6f826aee4c00000000dec0e9aa76e378e4a269e69d',
     '6fdc2880d5afbefcdbc89b31850414beec7d56bd',
     '4bbba9407337be1465de8182dd88f5fb82355dd94e6acb45b1bc5e6f826aee4c00000000'),
    ('ft_holder_75b_6ce2bdb5_vout1',
     '76a914a434fbfe62e6cda47168f0ce4db4edb3c1b808e988acbdd04bbba9407337be1465de8182dd88f5fb82355dd94e6acb45b1bc5e6f826aee4c00000000dec0e9aa76e378e4a269e69d',
     'a434fbfe62e6cda47168f0ce4db4edb3c1b808e9',
     '4bbba9407337be1465de8182dd88f5fb82355dd94e6acb45b1bc5e6f826aee4c00000000'),
]

# Malformed / non-FT scripts that must fail construction with GlyphInvalidScript.
INVALID_FT_SCRIPTS = [
    ('plain_p2pkh_25b',
     '76a914800d0414e758f790a48ad0f2960d566ef56cd5bf88ac'),
    ('nft_singleton_63b',
     'd808480623910ba219a0903afa9f10140c31c30f0529d51f860401cb79caf24ed0000000007576a914a9763e88160a63a3f03bf846268ed0fb8abd8b5588ac'),
    ('ft_control_241b',
     '043bd10000d88b87c3c771b1a9f5015a4f26bfd80979ed196b5366257a6f30929646dfd943a406000000d08b87c3c771b1a9f5015a4f26bfd80979ed196b5366257a6f30929646dfd943a400000000036889090350c3000874da40a70d74da00bd5175c0c855797ea8597959797ea87e5a7a7eaabc01147f77587f040000000088817600a269a269577ae500a069567ae600a06901d053797e0cdec0e9aa76e378e4a269e69d7eaa76e47b9d547a818b76537a9c537ade789181547ae6939d635279cd01d853797e016a7e886778de519d547854807ec0eb557f777e5379ec78885379eac0e9885379cc519d75686d7551'),
    ('ft_holder_wrong_tail',
     '76a91432e092994ebdf8db0861b0e9208878c4221c472188acbdd08b87c3c771b1a9f5015a4f26bfd80979ed196b5366257a6f30929646dfd943a400000000ffffffffffffffffffffffff'),
    ('ft_holder_74b_truncated',
     '76a91432e092994ebdf8db0861b0e9208878c4221c472188acbdd08b87c3c771b1a9f5015a4f26bfd80979ed196b5366257a6f30929646dfd943a400000000dec0e9aa76e378e4a269e6'),
    ('empty', ''),
]


class GlyphFTOutputConstructionTests(unittest.TestCase):
    """GlyphFTOutput(bytes) validates shape and raises on malformed input."""

    def test_construct_from_valid_ft_holder_scripts(self):
        """All 3 mainnet FT holder vectors construct successfully and
        round-trip byte-for-byte."""
        for name, spk_hex, _pkh_hex, _ref_hex in FT_VECTORS:
            with self.subTest(name=name):
                script = bytes.fromhex(spk_hex)
                out = glyph.GlyphFTOutput(script)
                self.assertEqual(
                    out.script, script,
                    f'{name}: script round-trip mismatch')
                self.assertEqual(
                    out.to_script(), script,
                    f'{name}: to_script() should return raw bytes')

    def test_construct_raises_on_malformed(self):
        """Every malformed / non-FT script raises GlyphInvalidScript."""
        for name, spk_hex in INVALID_FT_SCRIPTS:
            with self.subTest(name=name):
                script = bytes.fromhex(spk_hex) if spk_hex else b''
                with self.assertRaises(glyph.GlyphInvalidScript):
                    glyph.GlyphFTOutput(script)

    def test_construct_raises_ValueError_too(self):
        """GlyphInvalidScript dual-inherits ValueError — Pythonic
        `except ValueError` callers must still catch it."""
        with self.assertRaises(ValueError):
            glyph.GlyphFTOutput(b'\x00\x01\x02')


class GlyphFTOutputFromPkhRefTests(unittest.TestCase):
    """GlyphFTOutput.from_pkh_ref(pkh, ref) builds a valid 75-byte script."""

    def test_from_pkh_ref_produces_mainnet_scripts(self):
        """For each of the 3 mainnet FT vectors, re-building via
        from_pkh_ref(pkh, ref) must produce a byte-identical script."""
        for name, spk_hex, pkh_hex, ref_hex in FT_VECTORS:
            with self.subTest(name=name):
                expected = bytes.fromhex(spk_hex)
                built = glyph.GlyphFTOutput.from_pkh_ref(
                    bytes.fromhex(pkh_hex),
                    bytes.fromhex(ref_hex),
                )
                self.assertEqual(
                    built.script, expected,
                    f'{name}: from_pkh_ref produced non-matching script')

    def test_round_trip_parse_rebuild_parse(self):
        """GlyphFTOutput(from_pkh_ref(pkh, ref).script).{pkh,ref} == (pkh, ref)."""
        for name, _spk_hex, pkh_hex, ref_hex in FT_VECTORS:
            with self.subTest(name=name):
                pkh = bytes.fromhex(pkh_hex)
                ref = bytes.fromhex(ref_hex)
                built = glyph.GlyphFTOutput.from_pkh_ref(pkh, ref)
                reparsed = glyph.GlyphFTOutput(built.script)
                self.assertEqual(reparsed.pkh, pkh)
                self.assertEqual(reparsed.ref, ref)
                self.assertEqual(len(reparsed.ref), 36)

    def test_from_pkh_ref_rejects_wrong_pkh_length(self):
        valid_ref = bytes(36)
        with self.assertRaises(glyph.GlyphInvalidScript):
            glyph.GlyphFTOutput.from_pkh_ref(b'\x00' * 19, valid_ref)
        with self.assertRaises(glyph.GlyphInvalidScript):
            glyph.GlyphFTOutput.from_pkh_ref(b'\x00' * 21, valid_ref)

    def test_from_pkh_ref_rejects_wrong_ref_length(self):
        valid_pkh = bytes(20)
        # 32B ref (missing vout suffix) must fail.
        with self.assertRaises(glyph.GlyphInvalidScript):
            glyph.GlyphFTOutput.from_pkh_ref(valid_pkh, b'\x00' * 32)
        # 35B ref must fail.
        with self.assertRaises(glyph.GlyphInvalidScript):
            glyph.GlyphFTOutput.from_pkh_ref(valid_pkh, b'\x00' * 35)
        # 37B ref must fail.
        with self.assertRaises(glyph.GlyphInvalidScript):
            glyph.GlyphFTOutput.from_pkh_ref(valid_pkh, b'\x00' * 37)


class GlyphFTOutputPropertyTests(unittest.TestCase):
    """pkh and ref are properties (not methods) and return the correct
    byte slices."""

    def test_properties_return_correct_byte_slices(self):
        for name, spk_hex, pkh_hex, ref_hex in FT_VECTORS:
            with self.subTest(name=name):
                out = glyph.GlyphFTOutput(bytes.fromhex(spk_hex))
                # Access as property, not method call.
                self.assertEqual(out.pkh.hex(), pkh_hex)
                self.assertEqual(out.ref.hex(), ref_hex)
                self.assertEqual(len(out.ref), 36)

    def test_properties_are_not_methods(self):
        """Guardrail: make sure `.pkh` / `.ref` are property descriptors,
        not methods. If a future refactor turns them into methods,
        existing callers like `out.pkh == expected` silently fail
        (bound-method comparison)."""
        out = glyph.GlyphFTOutput(bytes.fromhex(FT_VECTORS[0][1]))
        # Property access returns bytes directly.
        self.assertIsInstance(out.pkh, bytes)
        self.assertIsInstance(out.ref, bytes)


class GlyphFTOutputProtocolFactoryTests(unittest.TestCase):
    """ScriptOutput.protocol_factory(bytes) returns GlyphFTOutput on any
    of the 3 FT vectors. Falls through to plain ScriptOutput otherwise."""

    def test_protocol_factory_dispatches_to_GlyphFTOutput(self):
        for name, spk_hex, _pkh_hex, _ref_hex in FT_VECTORS:
            with self.subTest(name=name):
                script = bytes.fromhex(spk_hex)
                out = ScriptOutput.protocol_factory(script)
                self.assertIsInstance(
                    out, glyph.GlyphFTOutput,
                    f'{name}: expected GlyphFTOutput, got {type(out).__name__}')

    def test_protocol_factory_falls_through_for_non_ft(self):
        """Non-FT scripts go through the default ScriptOutput (or another
        registered protocol class) — NOT GlyphFTOutput."""
        # Plain P2PKH (25B)
        plain = bytes.fromhex('76a914800d0414e758f790a48ad0f2960d566ef56cd5bf88ac')
        out = ScriptOutput.protocol_factory(plain)
        self.assertNotIsInstance(out, glyph.GlyphFTOutput)

        # 241B FT control — must NOT dispatch to GlyphFTOutput.
        control = bytes.fromhex(INVALID_FT_SCRIPTS[2][1])
        out = ScriptOutput.protocol_factory(control)
        self.assertNotIsInstance(out, glyph.GlyphFTOutput)


class GlyphFTOutputHashabilityTests(unittest.TestCase):
    """GlyphFTOutput must be hashable; equality is by script bytes.
    The is_mine cache in wallet.py depends on this."""

    def test_equal_scripts_have_equal_hashes(self):
        name, spk_hex, _, _ = FT_VECTORS[0]
        a = glyph.GlyphFTOutput(bytes.fromhex(spk_hex))
        b = glyph.GlyphFTOutput(bytes.fromhex(spk_hex))
        self.assertEqual(a, b, f'{name}: equal scripts should compare equal')
        self.assertEqual(hash(a), hash(b),
                         f'{name}: equal scripts should hash equal')

    def test_distinct_scripts_have_distinct_hashes(self):
        """Two different FT holders must have distinct hashes (not
        strictly required by Python, but a collision would be suspicious
        enough to surface as a test failure)."""
        a = glyph.GlyphFTOutput(bytes.fromhex(FT_VECTORS[0][1]))
        b = glyph.GlyphFTOutput(bytes.fromhex(FT_VECTORS[1][1]))
        self.assertNotEqual(a, b)
        self.assertNotEqual(hash(a), hash(b))

    def test_set_roundtrip(self):
        """Constructed GlyphFTOutput round-trips through a set."""
        a = glyph.GlyphFTOutput(bytes.fromhex(FT_VECTORS[0][1]))
        b = glyph.GlyphFTOutput(bytes.fromhex(FT_VECTORS[0][1]))
        s = {a}
        self.assertIn(a, s)
        self.assertIn(b, s, 'equal-script instance should be found in set')

    def test_dict_key_roundtrip(self):
        """Constructed GlyphFTOutput usable as a dict key."""
        a = glyph.GlyphFTOutput(bytes.fromhex(FT_VECTORS[0][1]))
        b = glyph.GlyphFTOutput(bytes.fromhex(FT_VECTORS[0][1]))
        d = {a: 'value'}
        self.assertEqual(d[b], 'value',
                         'equal-script instance should look up in dict')


class GlyphFTOutputIsMineIntegrationTests(unittest.TestCase):
    """The reason hashability is load-bearing: wallet.py's is_mine cache
    assumes ScriptOutput subclasses are hashable. Simulate that with a
    minimal cache dict."""

    def test_is_mine_cache_shape(self):
        cache = {}
        for name, spk_hex, _, _ in FT_VECTORS:
            out = glyph.GlyphFTOutput(bytes.fromhex(spk_hex))
            cache[out] = True
        # Each lookup by a freshly-constructed equal instance must hit.
        for name, spk_hex, _, _ in FT_VECTORS:
            with self.subTest(name=name):
                lookup = glyph.GlyphFTOutput(bytes.fromhex(spk_hex))
                self.assertIn(
                    lookup, cache,
                    f'{name}: freshly-constructed instance must hit cache')


class ExceptionHierarchyTests(unittest.TestCase):
    """Verify the dual-inheritance contracts for exceptions."""

    def test_GlyphError_catches_all_glyph_exceptions(self):
        """Every Glyph exception is catchable as GlyphError."""
        cases = [
            glyph.GlyphInvalidScript('test'),
            glyph.GlyphRefMismatch('test'),
            glyph.SendFtError('dust_change', 'test'),
            glyph.NotEnoughRxdForFtFee('test', fragmented=False),
        ]
        for exc in cases:
            with self.subTest(exc_type=type(exc).__name__):
                self.assertIsInstance(exc, glyph.GlyphError)

    def test_GlyphInvalidScript_is_ValueError(self):
        """Dual-inherits from ValueError per kieran-review feedback."""
        exc = glyph.GlyphInvalidScript('test')
        self.assertIsInstance(exc, ValueError)
        self.assertIsInstance(exc, glyph.GlyphError)

    def test_NotEnoughRxdForFtFee_is_NotEnoughFunds(self):
        """Dual-inherits from existing upstream NotEnoughFunds so that
        `except NotEnoughFunds` callers still catch FT fee shortfalls."""
        from ..util import NotEnoughFunds
        exc = glyph.NotEnoughRxdForFtFee('test')
        self.assertIsInstance(exc, NotEnoughFunds)
        self.assertIsInstance(exc, glyph.GlyphError)

    def test_NotEnoughRxdForFtFee_fragmented_flag(self):
        """The `fragmented` attribute distinguishes total-insufficient
        from chunk-too-small cases."""
        exc = glyph.NotEnoughRxdForFtFee('test', fragmented=True)
        self.assertTrue(exc.fragmented)
        exc2 = glyph.NotEnoughRxdForFtFee('test', fragmented=False)
        self.assertFalse(exc2.fragmented)

    def test_SendFtError_reason_attribute(self):
        """SendFtError.reason is exposed as an attribute for structured
        GUI / CLI error handling."""
        exc = glyph.SendFtError('dust_change', 'change 500k < 2M dust')
        self.assertEqual(exc.reason, 'dust_change')


class PolicyConstantTests(unittest.TestCase):
    """Pinning policy constants to their expected values. If any of
    these change, the build will fail and the plan doc must be updated
    in the same commit."""

    def test_fee_rate_matches_radiant_minimum(self):
        # Radiant's minimum relay fee. Don't lower without explicit
        # justification; the node will refuse to relay.
        self.assertEqual(glyph.FT_MIN_FEE_RATE, 10_000)

    def test_dust_threshold_is_2M_photons(self):
        # Sized so recipient can later economically spend FT change:
        # ~180B × 10k sat/byte = 1.8M sats; 2M gives 200k headroom.
        # If this drops below ~1.8M, recipients get stranded dust.
        self.assertEqual(glyph.FT_DUST_THRESHOLD, 2_000_000)

    def test_size_constants(self):
        self.assertEqual(glyph.FT_HOLDER_LEN, 75)
        self.assertEqual(glyph.NFT_SINGLETON_LEN, 63)
        self.assertEqual(glyph.REF_LEN, 36)
        self.assertEqual(glyph.PKH_LEN, 20)


class EstimateFtTxSizeTests(unittest.TestCase):
    """estimate_ft_tx_size centralizes the size formula; this pins the
    known-good value so PR D's fee loop can't silently drift."""

    def test_typical_2_in_3_out_ft_send(self):
        # 1 FT input + 1 RXD fee input, 1 FT recipient + 1 FT change +
        # 1 RXD change = 10 + 148*2 + 75*2 + 34*1 = 490 bytes.
        self.assertEqual(
            glyph.estimate_ft_tx_size(
                n_ft_in=1, n_rxd_in=1, n_ft_out=2, n_rxd_out=1),
            10 + 148 * 2 + 75 * 2 + 34,
        )

    def test_full_balance_send_no_ft_change(self):
        # 1 FT in + 1 RXD in, 1 FT recipient only, 1 RXD change.
        self.assertEqual(
            glyph.estimate_ft_tx_size(
                n_ft_in=1, n_rxd_in=1, n_ft_out=1, n_rxd_out=1),
            10 + 148 * 2 + 75 + 34,
        )

    def test_no_rxd_change_case(self):
        # 1 FT in + 1 RXD in, 1 FT recipient + 1 FT change, no RXD change.
        self.assertEqual(
            glyph.estimate_ft_tx_size(
                n_ft_in=1, n_rxd_in=1, n_ft_out=2, n_rxd_out=0),
            10 + 148 * 2 + 75 * 2,
        )


class AssertFtInvariantsStubTests(unittest.TestCase):
    """PR C lands the symbol; body is implemented in PR D. Confirm the
    stub raises NotImplementedError so downstream PRs can't accidentally
    ship while thinking invariants are enforced."""

    def test_stub_raises_not_implemented(self):
        with self.assertRaises(NotImplementedError):
            glyph.assert_ft_invariants([], [], b'\x00' * 36)


if __name__ == '__main__':
    unittest.main()
