# Glyph WalletData — tracks Glyph reference UTXOs in the wallet to prevent
# accidental spending and to enable future FT-send flows.

from ..util import PrintError
from .classifier import (
    classify_glyph_output, extract_ref_id, has_radiant_refs,
)


class WalletData(PrintError):
    """Tracks Glyph reference UTXOs in the wallet to prevent accidental
    spending. Mirrors the pattern used by slp.WalletData but much simpler
    since we only need to track which UTXOs have references, not parse
    full token semantics."""

    def __init__(self, wallet):
        self.wallet = wallet
        # Set of txo strings ("txid:n") that have Radiant reference scripts
        self.ref_txos = set()
        # Maps txo string → first reference ID bytes (for display)
        self.ref_ids = {}
        # Maps txo string → kind ('ft_holder' | 'nft_singleton') for the
        # two classifier-recognized shapes. Loose-prefix (non-template)
        # refs carry None — they're still tracked in ref_txos but not
        # considered spendable via the Glyph-aware signing path.
        self.kinds = {}
        self.need_rebuild = False

    def diagnostic_name(self):
        return f'{type(self).__name__}/{self.wallet.diagnostic_name()}'

    def clear(self):
        self.ref_txos.clear()
        self.ref_ids.clear()
        self.kinds.clear()

    def is_glyph_ref(self, txo):
        """Returns True if the given txo (string 'txid:n') is a Glyph
        reference UTXO that should not be spent via the normal RXD path."""
        return txo in self.ref_txos

    def ref_info_for_txo(self, txo):
        """Returns the reference ID hex for the given txo, or None."""
        ref_id = self.ref_ids.get(txo)
        if ref_id is not None:
            return ref_id.hex()
        return None

    def kind_for_txo(self, txo):
        """Returns the classifier kind for the given txo ('ft_holder' or
        'nft_singleton') or None if the txo is a ref-prefixed shape that
        wasn't recognized by the template classifier (e.g. 241B FT
        control, dMint containers). Callers that sign Glyph inputs only
        accept the two template kinds."""
        return self.kinds.get(txo)

    def prev_scriptpubkey_hex_for_txo(self, txo):
        """Returns the raw scriptPubKey hex for a Glyph txo by looking up
        the parent transaction in the wallet store. Used by
        add_input_info to populate `prev_scriptPubKey_hex` on a txin —
        this is the full 75B / 63B script that Radiant's sighash preimage
        covers (not the 25B P2PKH prologue that addr.to_script() returns
        after the classifier mapped the output to TYPE_ADDRESS).

        Returns None if the parent tx isn't in the wallet's store."""
        try:
            tx_hash, n_str = txo.rsplit(':', 1)
            n = int(n_str)
        except (ValueError, AttributeError):
            return None
        parent = self.wallet.transactions.get(tx_hash)
        if parent is None:
            return None
        raw = parent.output_script(n)
        if raw is None:
            return None
        return raw.hex()

    def add_tx(self, tx_hash, tx):
        """Scan a transaction for Glyph reference outputs and track them.
        Called by wallet.add_transaction with lock held.

        Handles two shapes:
          1. Ref-prefixed scripts (NFT singletons + older ref-prefix variants)
             detected via has_radiant_refs() at the start of the script.
          2. FT holders (75B, P2PKH prologue + glyph epilogue) — these do
             NOT start with a ref opcode. classify_glyph_output() exact-
             matches the 75-byte template and returns the embedded ref.
        """
        for n, (typ, addr, value) in enumerate(tx.outputs()):
            raw_script = tx.output_script(n)
            if not raw_script:
                continue
            # Precise classifier first: covers NFT singletons (63B) and
            # FT holders (75B). Returns the canonical 36-byte ref for
            # balance grouping.
            gm = classify_glyph_output(raw_script)
            if gm is not None:
                kind, _pkh, ref_bytes = gm
                txo = f"{tx_hash}:{n}"
                self.ref_txos.add(txo)
                self.kinds[txo] = kind
                if ref_bytes is not None:
                    self.ref_ids[txo] = ref_bytes
                continue
            # Fall back to loose prefix detection for shapes the precise
            # classifier doesn't recognize (241B FT control, dMint, etc).
            # These have no classifier `kind` — intentional: they are not
            # spendable via the Glyph-aware signing path.
            if has_radiant_refs(raw_script):
                txo = f"{tx_hash}:{n}"
                self.ref_txos.add(txo)
                ref_id = extract_ref_id(raw_script)
                if ref_id is not None:
                    self.ref_ids[txo] = ref_id

    def rm_tx(self, tx_hash):
        """Remove tracking for a transaction. Called by
        wallet.remove_transaction with lock held."""
        to_remove = [txo for txo in self.ref_txos
                     if txo.rsplit(':', 1)[0] == tx_hash]
        for txo in to_remove:
            self.ref_txos.discard(txo)
            self.ref_ids.pop(txo, None)
            self.kinds.pop(txo, None)

    def load(self):
        """Load persisted glyph data from wallet storage."""
        data = self.wallet.storage.get('glyph_ref_txos')
        if isinstance(data, list):
            self.ref_txos = set(data)
        data = self.wallet.storage.get('glyph_ref_ids')
        if isinstance(data, dict):
            self.ref_ids = {k: bytes.fromhex(v) for k, v in data.items()
                           if isinstance(v, str)}
        else:
            self.need_rebuild = True
        data = self.wallet.storage.get('glyph_kinds')
        if isinstance(data, dict):
            self.kinds = {k: v for k, v in data.items()
                          if isinstance(v, str)}
        else:
            # Old wallets have ref_txos but no persisted kinds; force a
            # rebuild so the classifier populates them.
            self.need_rebuild = True

    def save(self):
        """Persist glyph data to wallet storage."""
        self.wallet.storage.put('glyph_ref_txos', list(self.ref_txos))
        self.wallet.storage.put('glyph_ref_ids',
                                {k: v.hex() for k, v in self.ref_ids.items()})
        self.wallet.storage.put('glyph_kinds', self.kinds)

    def rebuild(self):
        """Rebuild glyph data from wallet transactions."""
        self.clear()
        for tx_hash, tx in self.wallet.transactions.items():
            self.add_tx(tx_hash, tx)
        self.need_rebuild = False
