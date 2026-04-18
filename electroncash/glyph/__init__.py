# Glyph token awareness for Electron Radiant.
#
# Package layout (3 files, matches SLP precedent without over-subdividing):
#   classifier.py   — Exact-shape recognizers + opcode constants (PR #2).
#   core.py         — GlyphFTOutput builder + policy + invariants + errors.
#   wallet_data.py  — Per-wallet glyph UTXO index (storage + scan hook).
#
# This __init__.py re-exports the same public API that `glyph.py` did
# before the PR C package restructure, so existing callers
# (transaction.py, wallet.py, tests/test_glyph_classifier.py) continue to
# work without edits.

# Classifier (PR #2 — already in use by transaction.py and WalletData.add_tx):
from .classifier import (
    # Opcode + size constants
    OP_PUSHINPUTREF,
    OP_REQUIREINPUTREF,
    OP_DISALLOWPUSHINPUTREF,
    OP_PUSHINPUTREFSINGLETON,
    OP_STATESEPARATOR,
    OP_DROP,
    REF_DATA_SIZE,
    FT_HOLDER_LEN,
    NFT_SINGLETON_LEN,
    # Classification kinds
    GLYPH_NONE,
    GLYPH_NFT_SINGLETON,
    GLYPH_FT_HOLDER,
    # Helpers
    has_radiant_refs,
    strip_radiant_refs,
    extract_ref_id,
    is_nft_singleton,
    is_ft_holder,
    classify_glyph_output,
)

# Core — FT output builder + policy + errors (PR C, new in this package):
from .core import (
    # Policy constants
    FT_MIN_FEE_RATE,
    FT_DUST_THRESHOLD,
    REF_LEN,
    PKH_LEN,
    # Output builder
    GlyphFTOutput,
    # Exceptions
    GlyphError,
    GlyphInvalidScript,
    GlyphRefMismatch,
    SendFtError,
    NotEnoughRxdForFtFee,
    # Helpers (implementations arrive with PR D; symbols resolve now)
    estimate_ft_tx_size,
    assert_ft_invariants,
)

# WalletData — per-wallet glyph UTXO index (PR #2):
from .wallet_data import WalletData

# Register GlyphFTOutput with ScriptOutput.protocol_classes so that
# ScriptOutput.protocol_factory(script_bytes) returns a GlyphFTOutput
# instance whenever script_bytes matches the 75-byte FT holder template.
#
# Precedent: cashacct.ScriptOutput (cashacct.py:444) and slp.ScriptOutput
# (slp/slp.py:70) register the same way at module load. Import order is
# safe because address.py has no reverse dependency on glyph; it only
# exposes ScriptOutput as the registration target.
from ..address import ScriptOutput as _ScriptOutput
_ScriptOutput.protocol_classes.add(GlyphFTOutput)
del _ScriptOutput
