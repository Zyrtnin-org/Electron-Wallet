#!/usr/bin/env python3
# Tokens tab — per-ref FT balance view for the Radiant Glyph token flow.
#
# Mirrors the slp_token tab pattern but for Glyph fungible tokens. Rows
# are one-per-ref: user-editable label, truncated ref hex, total photon
# balance, UTXO count. Double-click a row to route to the Send tab with
# that ref preselected.

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QInputDialog,
    QMenu,
    QTreeWidgetItem,
)

from electroncash.glyph import sanitize_ref_label, REF_LABEL_MAX_LEN
from electroncash.i18n import _
from electroncash.util import print_error

from .util import MyTreeWidget, MONOSPACE_FONT, rate_limited


class TokensList(MyTreeWidget):
    """One-row-per-ref Glyph FT balance view.

    Data source: wallet.get_ft_balances() → dict[ref_hex, {balance, utxo_count}].
    Label source: wallet.storage['glyph_ref_labels'] → dict[ref_hex, str].

    Column layout:
      0: Label (user-editable, sanitized at save time)
      1: Ref (truncated hex, monospace)
      2: Balance (photons)
      3: UTXOs (count)
    """

    # Signal emitted when user double-clicks a row; main_window listens
    # and switches to the Send tab with that ref preselected.
    send_ft_requested = pyqtSignal(str)

    class Col:
        label   = 0
        ref     = 1
        balance = 2
        utxos   = 3

    filter_columns = [Col.label, Col.ref]
    default_sort = MyTreeWidget.SortSpec(Col.balance, Qt.DescendingOrder)

    def __init__(self, parent=None):
        columns = [_('Label'), _('Ref'), _('Balance'), _('UTXOs')]
        MyTreeWidget.__init__(
            self, parent, self.create_menu, columns,
            stretch_column=self.Col.label,
            deferred_updates=True, save_sort_settings=True,
        )
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSortingEnabled(True)
        self.wallet = self.parent.wallet
        self.monospaceFont = QFont(MONOSPACE_FONT)
        self.itemDoubleClicked.connect(self._on_double_clicked)
        self.cleaned_up = False

    def clean_up(self):
        self.cleaned_up = True
        try:
            self.itemDoubleClicked.disconnect(self._on_double_clicked)
        except TypeError:
            pass

    @rate_limited(1.0, ts_after=True)
    def update(self):
        """Refresh rows. Rate-limited to avoid thrashing during sync."""
        if self.cleaned_up:
            return
        super().update()

    def on_update(self):
        """Build rows from wallet.get_ft_balances() + glyph_ref_labels."""
        if self.cleaned_up:
            return
        # Snapshot current state for resilience against mutation during
        # rebuild (wallet network events can fire on other threads).
        balances = self.wallet.get_ft_balances()
        labels = dict(self.wallet.storage.get('glyph_ref_labels', {}))

        self.clear()
        for ref_hex, info in balances.items():
            label = sanitize_ref_label(labels.get(ref_hex, ''))
            ref_short = ref_hex[:16] + '…' + ref_hex[-6:]
            item = QTreeWidgetItem([
                label,
                ref_short,
                str(info['balance']),
                str(info['utxo_count']),
            ])
            # Full ref hex stored on the item so right-click / edit-label
            # actions can round-trip exact bytes (never parse out of
            # display text).
            item.setData(self.Col.ref, Qt.UserRole, ref_hex)
            item.setFont(self.Col.ref, self.monospaceFont)
            item.setFont(self.Col.balance, self.monospaceFont)
            item.setToolTip(self.Col.ref, ref_hex)
            self.addChild(item)

    def _on_double_clicked(self, item, col):
        if item is None:
            return
        ref_hex = item.data(self.Col.ref, Qt.UserRole)
        if ref_hex:
            self.send_ft_requested.emit(ref_hex)

    def create_menu(self, position):
        item = self.currentItem()
        if item is None:
            return
        ref_hex = item.data(self.Col.ref, Qt.UserRole)
        if not ref_hex:
            return
        menu = QMenu()
        menu.addAction(_('Send this token…'),
                       lambda: self.send_ft_requested.emit(ref_hex))
        menu.addAction(_('Edit label…'),
                       lambda: self._edit_label(ref_hex))
        menu.addAction(_('Copy ref hex'),
                       lambda: self.parent.app.clipboard().setText(ref_hex))
        menu.exec_(self.viewport().mapToGlobal(position))

    def _edit_label(self, ref_hex):
        """Prompt for a new label and persist it (sanitized) on the
        wallet's storage. Triggers a view refresh via the storage-save
        path."""
        labels = dict(self.wallet.storage.get('glyph_ref_labels', {}))
        current = sanitize_ref_label(labels.get(ref_hex, ''))
        new_label, ok = QInputDialog.getText(
            self, _('Edit token label'),
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
        print_error(f'[tokens_list] label for {ref_hex[:10]}… set to {sanitized!r}')
        self.update()
