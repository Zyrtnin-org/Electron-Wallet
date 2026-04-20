#!/usr/bin/env python3
# NFTs tab — per-singleton Glyph NFT view for the Radiant Glyph token flow.
#
# Mirrors tokens_list.py but for NFT singletons: one row per owned NFT
# UTXO (singletons are 1:1 with their ref). Columns are label, truncated
# ref, address, outpoint, height.
#
# Phase 1 scope (read-only): list + label editing + copy ref/outpoint/
# address. NFT sending is deferred — it needs a dedicated
# `make_unsigned_nft_transfer` in electroncash/wallet.py that emits the
# 63-byte singleton template (d8 <ref> 75 76a914 <pkh> 88ac), because
# the existing FT pipeline builds 75-byte holder outputs.

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QInputDialog,
    QMenu,
    QTreeWidgetItem,
)

from electroncash.glyph import sanitize_ref_label
from electroncash.i18n import _
from electroncash.util import print_error

from .util import MyTreeWidget, MONOSPACE_FONT, rate_limited


class NftsList(MyTreeWidget):
    """One-row-per-singleton Glyph NFT view.

    Data source: wallet.get_nft_holdings() → list of dicts (ref, outpoint,
    value, address, height).
    Label source: wallet.storage['glyph_ref_labels'] → shared with FT tab
    (refs are globally unique, so one label namespace covers both).

    Column layout:
      0: Label (user-editable, sanitized at save time)
      1: Ref (truncated hex, monospace, full ref in tooltip)
      2: Address (truncated, monospace)
      3: Outpoint (txid:vout, truncated, monospace)
      4: Height (int; 0 = mempool)
    """

    # No send_nft_requested signal in Phase 1: the receiving end would have
    # to build a 63-byte singleton-template output, which the wallet's FT
    # pipeline does not produce. Adding NFT send is a follow-on PR.

    class Col:
        label    = 0
        ref      = 1
        address  = 2
        outpoint = 3
        height   = 4

    filter_columns = [Col.label, Col.ref, Col.address]
    default_sort = MyTreeWidget.SortSpec(Col.height, Qt.DescendingOrder)

    def __init__(self, parent=None):
        columns = [_('Label'), _('Ref'), _('Address'), _('Outpoint'), _('Height')]
        MyTreeWidget.__init__(
            self, parent, self.create_menu, columns,
            stretch_column=self.Col.label,
            deferred_updates=True, save_sort_settings=True,
        )
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSortingEnabled(True)
        self.wallet = self.parent.wallet
        self.monospaceFont = QFont(MONOSPACE_FONT)
        self.cleaned_up = False

    def clean_up(self):
        self.cleaned_up = True

    @rate_limited(1.0, ts_after=True)
    def update(self):
        if self.cleaned_up:
            return
        super().update()

    def on_update(self):
        """Build rows from wallet.get_nft_holdings() + glyph_ref_labels."""
        if self.cleaned_up:
            return
        nfts   = self.wallet.get_nft_holdings()
        labels = dict(self.wallet.storage.get('glyph_ref_labels', {}))

        self.clear()
        for nft in nfts:
            ref_hex = nft['ref']
            label = sanitize_ref_label(labels.get(ref_hex, ''))
            ref_short = ref_hex[:16] + '…' + ref_hex[-6:]
            addr_str = nft['address'].to_ui_string()
            addr_short = addr_str[:10] + '…' + addr_str[-6:] if len(addr_str) > 20 else addr_str
            outpoint = nft['outpoint']
            outpoint_short = outpoint[:12] + '…:' + outpoint.split(':')[1]
            height_str = str(nft['height']) if nft['height'] > 0 else _('mempool')
            item = QTreeWidgetItem([
                label, ref_short, addr_short, outpoint_short, height_str,
            ])
            item.setData(self.Col.ref,      Qt.UserRole, ref_hex)
            item.setData(self.Col.outpoint, Qt.UserRole, outpoint)
            item.setData(self.Col.address,  Qt.UserRole, addr_str)
            for col in (self.Col.ref, self.Col.address, self.Col.outpoint):
                item.setFont(col, self.monospaceFont)
            item.setToolTip(self.Col.ref,      ref_hex)
            item.setToolTip(self.Col.address,  addr_str)
            item.setToolTip(self.Col.outpoint, outpoint)
            self.addChild(item)

    def create_menu(self, position):
        item = self.currentItem()
        if item is None:
            return
        ref_hex  = item.data(self.Col.ref, Qt.UserRole)
        outpoint = item.data(self.Col.outpoint, Qt.UserRole)
        addr_str = item.data(self.Col.address, Qt.UserRole)
        if not ref_hex:
            return
        menu = QMenu()
        menu.addAction(_('Edit label…'),
                       lambda: self._edit_label(ref_hex))
        menu.addAction(_('Copy ref hex'),
                       lambda: self.parent.app.clipboard().setText(ref_hex))
        if outpoint:
            menu.addAction(_('Copy outpoint'),
                           lambda: self.parent.app.clipboard().setText(outpoint))
        if addr_str:
            menu.addAction(_('Copy address'),
                           lambda: self.parent.app.clipboard().setText(addr_str))
        menu.exec_(self.viewport().mapToGlobal(position))

    def _edit_label(self, ref_hex):
        labels = dict(self.wallet.storage.get('glyph_ref_labels', {}))
        current = sanitize_ref_label(labels.get(ref_hex, ''))
        new_label, ok = QInputDialog.getText(
            self, _('Edit NFT label'),
            _('Label for ref {}').format(ref_hex[:16] + '…'),
            text=current,
        )
        if not ok:
            return
        sanitized = sanitize_ref_label(new_label)
        if sanitized:
            labels[ref_hex] = sanitized
        else:
            labels.pop(ref_hex, None)
        self.wallet.storage.put('glyph_ref_labels', labels)
        print_error(f'[nfts_list] label for {ref_hex[:10]}… set to {sanitized!r}')
