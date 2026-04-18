# Glyph FT output builder, policy constants, invariants helper, and
# exception hierarchy. One file to avoid premature sub-division; split
# further if this grows past ~400 lines.
#
# ---------------------------------------------------------------------------
# Ref encoding (canonical, referenced everywhere)
# ---------------------------------------------------------------------------
# A Radiant ref is 36 bytes:
#   - First 32 bytes:  txid-hash of the mint transaction (content-addressed).
#   - Last  4 bytes:   vout index of the mint output, little-endian u32.
# The 32-byte portion is what gets hashed for the per-output summary used
# in the Radiant sighash preimage (`hashOutputHashes`); the 4-byte vout
# suffix is carried but not included in the hash. Any size ambiguity in
# downstream code is a bug — prefer the GlyphFTOutput.ref (36B) and
# GlyphFTOutput.ref_hash (32B) accessors over raw slicing.
# ---------------------------------------------------------------------------

from typing import Final, Literal, Optional

from ..address import ScriptOutput
from ..util import NotEnoughFunds

from .classifier import (
    FT_HOLDER_LEN,
    NFT_SINGLETON_LEN,
    _FT_TAIL_BYTES,
    is_ft_holder,
)

# --- Policy constants ------------------------------------------------------

# Radiant's minimum relay fee (photons/byte). Wallets default to this; lower
# than 10,000 and the node refuses to relay. Source: RadiantBlockchain/radiant-node
# policy. Confirmed via Photonic Wallet's coinSelect.ts and Electron-Radiant's
# 2026-04 release notes.
FT_MIN_FEE_RATE: Final[int] = 10_000

# Minimum FT change output, in photons. Sized so the recipient can later
# economically spend the change: consuming a 75B FT-holder output costs
# ~180B on the wire at 10k sat/byte = 1.8M photons. 2M photons gives ~200k
# headroom. Sub-2M residuals trigger SendFtError(reason='dust_change')
# telling the user to send the full balance instead. No configuration knob
# in v1.
FT_DUST_THRESHOLD: Final[int] = 2_000_000

# Script size constants (bytes). See classifier.py for template layouts.
_FT_PREFIX: Final[bytes] = bytes.fromhex('76a914')
_FT_MID:    Final[bytes] = bytes.fromhex('88acbdd0')
_FT_TAIL:   Final[bytes] = _FT_TAIL_BYTES

# Ref length (32B hash + 4B vout LE = 36B total). Pinned here; see module
# docstring above for the canonical encoding. The full 36 bytes are what
# gets fed into Radiant's sighash `hashOutputHashes` per-output refs hash
# (verified against radiant-node/src/primitives/transaction.h).
REF_LEN: Final[int] = 36

# Pubkey-hash length (20 bytes for standard RIPEMD160(SHA256(pubkey))).
PKH_LEN: Final[int] = 20


# --- Exception hierarchy ---------------------------------------------------

class GlyphError(Exception):
    """Base class for all Glyph-specific errors. GUI and callers can
    `except GlyphError` to catch any FT/NFT-related failure."""


class GlyphInvalidScript(GlyphError, ValueError):
    """Raised when a script is expected to be a valid Glyph output but
    fails shape validation (wrong length, wrong opcodes, wrong tail).
    Dual-inherits from ValueError so callers using the Pythonic generic
    `except ValueError` also catch it."""


class GlyphRefMismatch(GlyphError):
    """Raised when a cached `glyph_ref` tag on a txin/coin differs from
    the ref re-extracted from the raw scriptPubKey bytes. Indicates
    tampering, ElectrumX misreporting, or a classifier regression."""


class SendFtError(GlyphError):
    """Raised by make_unsigned_ft_transaction when an FT send cannot be
    built. The `reason` attribute is a Literal string that callers can
    branch on to map to structured errors or localized messages.

    Reasons:
      - 'dust_change':                    FT change < FT_DUST_THRESHOLD
      - 'ref_mismatch':                   cached ref != re-extracted ref
      - 'invalid_ref':                    target_ref not a 36-byte value
      - 'invalid_recipient':              recipient address not Radiant P2PKH
    """
    def __init__(
        self,
        reason: Literal[
            'dust_change',
            'ref_mismatch',
            'invalid_ref',
            'invalid_recipient',
        ],
        msg: str = '',
    ):
        super().__init__(f'{reason}: {msg}' if msg else reason)
        self.reason = reason


class NotEnoughRxdForFtFee(NotEnoughFunds, GlyphError):
    """Raised when RXD inputs don't cover the 10k sat/byte fee for an FT
    send. Dual-inherits from NotEnoughFunds (existing upstream exception)
    so that any caller doing `except NotEnoughFunds` continues to work,
    and from GlyphError so that Glyph-aware callers can distinguish FT
    fee failures from generic RXD shortfalls.

    Distinguishes two failure modes via the `fragmented` flag:
      - fragmented=False: total available RXD < required fee
      - fragmented=True:  enough total RXD but chunks too small to pay
                          their own marginal fee at 10k sat/byte
    """
    def __init__(self, msg: str = '', fragmented: bool = False):
        super().__init__(msg)
        self.fragmented = fragmented


# --- GlyphFTOutput ---------------------------------------------------------

class GlyphFTOutput(ScriptOutput):
    """Output-side representation of a Radiant Glyph FT holder (75-byte
    template). Immutable namedtuple subclass; hashable; registered in
    ScriptOutput.protocol_classes so ScriptOutput.protocol_factory(bytes)
    returns an instance on a byte-shape match.

    Construction:
      - GlyphFTOutput(script_bytes): validates the 75-byte template;
        raises GlyphInvalidScript on any deviation.
      - GlyphFTOutput.from_pkh_ref(pkh, ref): builds the 75-byte script
        from a 20-byte pubkey hash and a 36-byte ref.

    Accessors (properties, not methods — idiomatic namedtuple-subclass):
      - .pkh:       20 bytes
      - .ref:       36 bytes (32B hash + 4B vout LE)
      - .ref_hash:  32 bytes (the hash portion only, for per-output
                    sighash summary computation)
    """

    # attrs_extra is the convention used by cashacct.ScriptOutput and
    # slp.ScriptOutput for __str__ parity.
    attrs_extra = ('pkh', 'ref')

    def __new__(cls, script: bytes) -> 'GlyphFTOutput':
        # Single-arg signature matches ScriptOutput.protocol_factory's
        # call convention at address.py:325-327. Raises (never asserts)
        # so `python -O` doesn't silently skip the check.
        if not is_ft_holder(script):
            raise GlyphInvalidScript(
                f'not a valid FT holder script (len={len(script)})'
            )
        return super().__new__(cls, script)

    @classmethod
    def from_pkh_ref(cls, pkh: bytes, ref: bytes) -> 'GlyphFTOutput':
        """Build a 75-byte FT holder output from pkh + ref.

        pkh must be exactly 20 bytes. ref must be exactly 36 bytes
        (32B txid-hash + 4B vout LE)."""
        if len(pkh) != PKH_LEN:
            raise GlyphInvalidScript(
                f'pkh must be {PKH_LEN} bytes, got {len(pkh)}'
            )
        if len(ref) != REF_LEN:
            raise GlyphInvalidScript(
                f'ref must be {REF_LEN} bytes (32B hash + 4B vout LE), '
                f'got {len(ref)}'
            )
        return cls(_FT_PREFIX + pkh + _FT_MID + ref + _FT_TAIL)

    @classmethod
    def protocol_match(cls, script: bytes) -> bool:
        """Protocol-classes dispatch hook. Returns True if the given
        script matches the 75-byte FT holder template."""
        return is_ft_holder(script)

    @property
    def pkh(self) -> bytes:
        """20-byte pubkey hash extracted from the P2PKH prologue."""
        return self.script[3:23]

    @property
    def ref(self) -> bytes:
        """36-byte ref (32B txid hash + 4B vout LE) from the mid-tail
        region. This is the full `uint288` value that goes into the
        Radiant sighash `hashOutputHashes` summary as a push-ref — do
        NOT slice off the vout suffix before hashing. The entire 36
        bytes are serialized into the refs hash input."""
        return self.script[27:63]


# --- Public helpers used by builder (PR D) ---------------------------------

def estimate_ft_tx_size(
    n_ft_in: int,
    n_rxd_in: int,
    n_ft_out: int,
    n_rxd_out: int,
) -> int:
    """Estimate the wire size (bytes) of an FT send transaction.

    Centralized so future script variants only edit one place. Varint-
    corrected for typical FT send sizes (inputs + outputs fit comfortably
    within single-byte varints).

    Formula components:
      10                   = tx overhead (version 4B + locktime 4B + two
                             single-byte input/output count varints)
      148 * (n_ft_in +
             n_rxd_in)     = input wire size (32B prev_txid + 4B vout +
                             1B scriptsig_len + ~107B scriptsig +
                             4B sequence = 148B typical for P2PKH spend)
      75  * n_ft_out       = FT holder output (75B script + 8B value +
                             1B script_len; we round up to 84B but the
                             input dominates so 75 is conservative-close)
      34  * n_rxd_out      = P2PKH output (25B script + 8B value + 1B len)
    """
    return (
        10
        + 148 * (n_ft_in + n_rxd_in)
        + 75 * n_ft_out
        + 34 * n_rxd_out
    )


def assert_ft_invariants(inputs, outputs, target_ref: bytes) -> None:
    """Enforce the seven FT-send invariants on a prospective or fully-
    built transaction's inputs and outputs. Called before signing (pure-
    data check) and again after signing (semantic preflight).

    Raises on any violation — never uses `assert` because `python -O`
    strips assertions.

    Invariants (see plan doc for rationale):
      1. All FT inputs share the same 36-byte ref.
      2. Every FT output's ref equals the FT-input ref.
      3. Sum of FT input photons == Sum of FT output photons.
      4. RXD-change outputs are pure P2PKH (never Glyph scripts).
      5. FT-change photons >= FT_DUST_THRESHOLD (or zero).
      6. RXD fee funding suffices (caller's fee loop must succeed first;
         this invariant assumes the tx as passed has already converged).
      7. For each FT input, re-extract ref from scriptPubKey bytes and
         assert it matches target_ref. Content-addressed check; closes
         peer-substitution attacks.

    Implementation will be completed in PR D (the builder PR) — this
    stub lands in PR C so callers can import the symbol now and the
    exception types are all resolvable."""
    raise NotImplementedError(
        'assert_ft_invariants is implemented in PR D (builder). '
        'PR C lands the symbol, constants, and exception hierarchy; '
        'the body requires builder helpers (_select_ft_inputs, etc) '
        'that arrive in PR D.'
    )
