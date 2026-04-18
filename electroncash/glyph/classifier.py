# Glyph Token Awareness for Electron Radiant
#
# This module provides detection of Radiant reference-prefixed scripts
# (used by Glyph tokens) to prevent accidental spending/destruction of
# tokens. It does NOT provide full Glyph protocol support — only
# protective awareness.
#
# Radiant reference opcodes (verified against Radiant-Core/Radiant-Node
# src/script/script.h):
#   OP_PUSHINPUTREF              (0xd0) + 36 bytes — FT-style push ref
#   OP_REQUIREINPUTREF           (0xd1) + 36 bytes — require ref present
#   OP_DISALLOWPUSHINPUTREF      (0xd2) — disallow push ref
#   OP_PUSHINPUTREFSINGLETON     (0xd8) + 36 bytes — NFT singleton push ref
#   OP_STATESEPARATOR            (0xbd) — runtime NOP separating
#                                         P2PKH prologue from FT epilogue
#
# Three on-chain shapes recognized by this module (from a 2309-sample
# mainnet scan across 6 distinct tokens, 500 blocks):
#
#   Plain P2PKH (25B):   76a914 <pkh:20> 88ac
#   NFT singleton (63B): d8 <ref:36> 75 76a914 <pkh:20> 88ac
#   FT holder    (75B):  76a914 <pkh:20> 88ac bd d0 <ref:36>
#                        dec0e9aa76e378e4a269e69d
#
# The FT epilogue's trailing 12 bytes implement Σ-in ≥ Σ-out conservation
# via OP_CODESCRIPTHASHVALUESUM_UTXOS / _OUTPUTS. Spending an FT holder
# requires the same scriptSig as plain P2PKH: <sig> <pubkey>.

# Radiant-specific opcodes for UTXO references
OP_PUSHINPUTREF = 0xd0
OP_REQUIREINPUTREF = 0xd1
OP_DISALLOWPUSHINPUTREF = 0xd2
OP_PUSHINPUTREFSINGLETON = 0xd8
OP_STATESEPARATOR = 0xbd
OP_DROP = 0x75

# Reference data size: 32-byte txid + 4-byte output index = 36 bytes total.
# See ref encoding notes in core.py.
REF_DATA_SIZE = 36

# Opcodes that take a 36-byte reference argument. Includes both OP_PUSHINPUTREF
# (0xd0, used by FTs) and OP_PUSHINPUTREFSINGLETON (0xd8, used by NFTs).
_REF_OPCODES = frozenset((OP_PUSHINPUTREF, OP_PUSHINPUTREFSINGLETON))

# Opcodes that are single-byte Radiant markers (no data).
_REF_MARKER_OPCODES = frozenset((OP_DISALLOWPUSHINPUTREF,))

# Byte constants for the 75-byte FT holder shape.
# Layout: 76a914 <pkh:20> 88ac bd d0 <ref:36> <FT_TAIL_BYTES>
_FT_MID_BYTES = bytes.fromhex('88acbdd0')       # 88ac ends P2PKH; bd=STATESEPARATOR; d0=PUSHINPUTREF
_FT_TAIL_BYTES = bytes.fromhex('dec0e9aa76e378e4a269e69d')
FT_HOLDER_LEN = 75
NFT_SINGLETON_LEN = 63

# Script-type classification returned by classify_glyph_output().
GLYPH_NONE = None       # plain output — defer to normal recognizer
GLYPH_NFT_SINGLETON = 'nft_singleton'
GLYPH_FT_HOLDER = 'ft_holder'


def has_radiant_refs(script_bytes):
    """Returns True if the script begins with Radiant reference opcodes
    (OP_PUSHINPUTREF 0xd0 or OP_PUSHINPUTREFSINGLETON 0xd8). This
    indicates the output likely carries a Glyph token.

    Note: OP_REQUIREINPUTREF (0xd1) is deliberately NOT checked here — it
    is used in spend-time constraint scripts, not in output-side ref
    prefixes. The _REF_OPCODES frozenset is authoritative; this docstring
    is documentation only.
    """
    if not script_bytes:
        return False
    return script_bytes[0] in _REF_OPCODES


def strip_radiant_refs(script_bytes):
    """Strip all leading Radiant reference prefixes from a script and return
    the inner (standard) locking script.

    Handles patterns like:
        d0 <36 bytes> 75 [d8 <36 bytes> 75] ... <standard_script>

    Returns the inner script bytes, or None if the script doesn't start
    with reference opcodes or is malformed. Also returns None if stripping
    would result in an empty script."""
    if not script_bytes:
        return None

    pos = 0
    found_ref = False

    while pos < len(script_bytes):
        op = script_bytes[pos]

        if op in _REF_OPCODES:
            # Need at least 1 (opcode) + 36 (ref data) bytes
            if pos + 1 + REF_DATA_SIZE > len(script_bytes):
                return None  # malformed
            pos += 1 + REF_DATA_SIZE
            found_ref = True

            # Optionally consume OP_DROP after the reference
            if pos < len(script_bytes) and script_bytes[pos] == OP_DROP:
                pos += 1

        elif op in _REF_MARKER_OPCODES:
            # Single-byte markers, skip them
            pos += 1
            found_ref = True

        else:
            # Not a reference opcode — remainder is the inner script
            break

    if not found_ref:
        return None

    inner = script_bytes[pos:]
    if not inner:
        return None

    return bytes(inner)


def extract_ref_id(script_bytes):
    """Extract the first reference ID (36 bytes) from a reference-prefixed
    script. Returns the raw 36-byte reference or None."""
    if not script_bytes or len(script_bytes) < 1 + REF_DATA_SIZE:
        return None
    if script_bytes[0] not in _REF_OPCODES:
        return None
    return bytes(script_bytes[1:1 + REF_DATA_SIZE])


# ---------------------------------------------------------------------------
# Precise shape classifier.
#
# Recognizes the three mainnet-observed spendable shapes with exact byte
# matching (not just prefix detection). Backed by 14 golden vectors in
# tests/test_glyph_classifier.py. The port target from the JavaScript
# reference is radiant-ledger-app/view-only-ui/classifier.mjs.
# ---------------------------------------------------------------------------

def _is_plain_p2pkh(b):
    return (len(b) == 25
            and b[0] == 0x76 and b[1] == 0xa9 and b[2] == 0x14
            and b[23] == 0x88 and b[24] == 0xac)


def is_nft_singleton(script_bytes):
    """Exact 63-byte NFT singleton shape: d8 <ref:36> 75 76a914 <pkh:20> 88ac.

    A match is a strong indicator of a Glyph NFT; the 36-byte ref uniquely
    identifies the mint. Returns True only on an exact shape match — does
    NOT accept any 63-byte d8-prefixed script."""
    b = script_bytes
    if not b or len(b) != NFT_SINGLETON_LEN:
        return False
    return (b[0] == OP_PUSHINPUTREFSINGLETON
            and b[37] == OP_DROP
            and b[38] == 0x76 and b[39] == 0xa9 and b[40] == 0x14
            and b[61] == 0x88 and b[62] == 0xac)


def is_ft_holder(script_bytes):
    """Exact 75-byte FT holder shape: 76a914 <pkh:20> 88ac bd d0 <ref:36>
    <FT_TAIL 12B>.

    The FT epilogue enforces photon-value conservation at consensus (Σ
    inputs >= Σ outputs per codeScriptHash). The prologue is standard
    P2PKH, so the spend scriptSig is <sig> <pubkey> — same as a plain
    P2PKH. The epilogue bytes are invariant across every FT token
    observed on mainnet (2309 samples, 6 tokens)."""
    b = script_bytes
    if not b or len(b) != FT_HOLDER_LEN:
        return False
    # First 25 bytes must be a well-formed P2PKH prologue:
    # 76a914 <pkh:20> 88ac — reuse the helper to avoid drifting the
    # pattern from the plain-P2PKH recognizer.
    if not _is_plain_p2pkh(b[0:25]):
        return False
    if b[25] != OP_STATESEPARATOR or b[26] != OP_PUSHINPUTREF:
        return False
    if b[63:] != _FT_TAIL_BYTES:
        return False
    return True


def classify_glyph_output(script_bytes):
    """Return (kind, pkh_bytes, ref_bytes_or_none) for a recognized Glyph
    shape, or None if not a recognized Glyph output.

    kind is GLYPH_NFT_SINGLETON or GLYPH_FT_HOLDER.
    pkh_bytes is the 20-byte pubkey hash (same as a standard P2PKH would
    extract) — this is the owning address of the output.
    ref_bytes is the 36-byte token identifier (None only if the output
    doesn't carry a ref, which shouldn't happen for the two recognized
    kinds but keeps the return shape uniform).

    Exact byte matches only. Malformed or near-miss shapes return None
    (callers should fall through to TYPE_SCRIPT / unknown).

    IMPORTANT — classifier-vs-consensus gap. A match indicates the output
    *has the shape of* a spendable Glyph UTXO. It does NOT guarantee that
    a spend will succeed at consensus. Spending a Glyph UTXO requires the
    spending transaction to (a) present a valid P2PKH scriptSig for the
    prologue, AND (b) satisfy the protocol's input-ref and conservation
    constraints on the spending tx as a whole. An attacker can mint a
    75-byte output with a ref that was never minted — the wallet will
    display it and mark it "spendable," but broadcast will fail consensus.
    Callers that surface these outputs as spendable balance should
    document this to the user, not treat a classifier match as proof of
    spendability."""
    if is_nft_singleton(script_bytes):
        return (GLYPH_NFT_SINGLETON,
                bytes(script_bytes[41:61]),
                bytes(script_bytes[1:37]))
    if is_ft_holder(script_bytes):
        return (GLYPH_FT_HOLDER,
                bytes(script_bytes[3:23]),
                bytes(script_bytes[27:63]))
    return None
