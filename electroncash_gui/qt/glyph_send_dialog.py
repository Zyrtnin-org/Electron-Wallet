#!/usr/bin/env python3
# Confirmation modal for Glyph FT sends.
#
# Shows the full 72-char ref hex (monospace, authoritative identifier)
# above the user-editable label (sanitized), then amount / recipient /
# fee / RXD change, then an irreversibility warning and an optional
# "Confirm recipient" one-shot check for unfamiliar destinations.
#
# Label injection protections (security-sentinel H3):
#   - Full ref hex shown above the label, visually distinct (monospace)
#   - Label sanitized via glyph.sanitize_ref_label (strips bidi
#     overrides + control chars, caps at 64 chars)
#   - Recipient address shown on its own line, select-copyable

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QDialog,
    QGridLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)

from electroncash.glyph import sanitize_ref_label
from electroncash.i18n import _

from .util import (
    Buttons,
    CancelButton,
    ColorScheme,
    MONOSPACE_FONT,
    OkButton,
    WindowModalDialog,
)


def show_ft_confirm(parent, wallet, ref_hex, amount_photons, recipient,
                    fee_sats, rxd_change_sats):
    """Display the FT-send confirmation modal.

    Returns True if the user clicked Sign & Send, False if cancelled or
    if a pre-send warning ("unfamiliar recipient") was declined.

    Arguments:
      parent:              parent Qt widget (usually main_window)
      wallet:              wallet instance (for label lookup + warning-
                           flag storage)
      ref_hex:             full 72-char FT ref as hex string
      amount_photons:      int, photons being sent
      recipient:           Address the user is sending to
      fee_sats:            int, network fee in sats
      rxd_change_sats:     int, RXD change (0 if none)
    """
    # Label lookup + sanitization
    labels = wallet.storage.get('glyph_ref_labels', {})
    raw_label = labels.get(ref_hex, '')
    safe_label = sanitize_ref_label(raw_label) or _('(no label)')

    # Build the dialog
    d = WindowModalDialog(parent.top_level_window(), _('Confirm FT send'))
    d.setMinimumWidth(520)
    vbox = QVBoxLayout(d)

    # --- Ref header (authoritative identifier, monospace, on top) -----
    ref_header = QLabel(_('Token reference:'))
    vbox.addWidget(ref_header)
    ref_display = QLabel(ref_hex)
    ref_font = QFont(MONOSPACE_FONT)
    ref_display.setFont(ref_font)
    ref_display.setTextInteractionFlags(
        Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
    )
    ref_display.setWordWrap(True)
    vbox.addWidget(ref_display)

    # --- Label (sanitized, clearly distinguished from ref) -----------
    label_widget = QLabel(_('Label: {}').format(safe_label))
    vbox.addWidget(label_widget)
    vbox.addSpacing(6)

    # --- Fields grid ---------------------------------------------------
    grid = QGridLayout()
    row = 0
    grid.addWidget(QLabel(_('Amount:')), row, 0)
    amount_lbl = QLabel(f'{amount_photons:,} photons')
    amount_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
    grid.addWidget(amount_lbl, row, 1)
    row += 1
    grid.addWidget(QLabel(_('Recipient:')), row, 0)
    recipient_lbl = QLabel(recipient.to_ui_string())
    recipient_lbl.setFont(QFont(MONOSPACE_FONT))
    recipient_lbl.setTextInteractionFlags(
        Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
    )
    recipient_lbl.setWordWrap(True)
    grid.addWidget(recipient_lbl, row, 1)
    row += 1
    grid.addWidget(QLabel(_('Network fee:')), row, 0)
    grid.addWidget(QLabel(f'{fee_sats:,} RXD sats'), row, 1)
    row += 1
    if rxd_change_sats:
        grid.addWidget(QLabel(_('RXD change:')), row, 0)
        grid.addWidget(QLabel(f'{rxd_change_sats:,} sats'), row, 1)
    vbox.addLayout(grid)
    vbox.addSpacing(6)

    # --- Irreversibility warning ---------------------------------------
    warning = QLabel(
        '<b><font color="{color}">{text}</font></b>'.format(
            color=ColorScheme.RED._get_color(False),
            text=_('This action cannot be reversed.'),
        )
    )
    vbox.addWidget(warning)
    second_line = QLabel(
        _('Verify the ref and recipient above. Tokens sent to a wallet '
          'that doesn\'t recognize Glyph FT cannot be spent by the '
          'recipient.')
    )
    second_line.setWordWrap(True)
    vbox.addWidget(second_line)
    vbox.addSpacing(8)

    # --- Buttons -------------------------------------------------------
    ok_btn = OkButton(d, _('Sign && Send'))
    vbox.addLayout(Buttons(CancelButton(d), ok_btn))

    if d.exec_() != QDialog.Accepted:
        return False

    # --- Second gate: unfamiliar-recipient warning (one-shot per addr)
    confirmed_recipients = set(
        wallet.storage.get('glyph_confirmed_recipients', [])
    )
    recipient_str = recipient.to_ui_string()
    if recipient_str not in confirmed_recipients:
        # Differentiated copy for self-send vs. external first-time.
        is_self = wallet.is_mine(recipient)
        if is_self:
            msg = _(
                'You are sending this token to an address this wallet '
                'controls. The network fee is burned for no economic '
                'benefit. Continue?'
            )
        else:
            msg = _(
                'This is the first time you are sending this token to '
                'the recipient above. Confirm the recipient wallet '
                'supports Radiant Glyph FTs — tokens sent to an '
                'incompatible wallet may be unspendable.\n\n'
                'Continue?'
            )
        reply = QMessageBox.warning(
            parent.top_level_window(),
            _('Confirm recipient'),
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return False
        confirmed_recipients.add(recipient_str)
        wallet.storage.put(
            'glyph_confirmed_recipients', list(confirmed_recipients)
        )

    return True


def show_ft_error(parent, reason, detail=None):
    """User-facing error after a failed FT send. Maps structured
    SendFtError reasons to short, localizable messages; falls back to
    QMessageBox's detailed-text disclosure for unmapped rejections.

    Mirrors plan's error-mapping table for testmempoolaccept rejection
    strings; see docs/plans/2026-04-18-feat-glyph-ft-send-plan.md.
    """
    # Structured-reason → short user message.
    reasons = {
        'dust_change': _(
            'FT change is below the dust threshold. Send the full '
            'balance, or pick a larger FT UTXO.'
        ),
        'ref_mismatch': _(
            'This transaction would destroy tokens. Please report this '
            'bug.'
        ),
        'invalid_ref': _(
            'Invalid token reference (must be 36 bytes).'
        ),
        'invalid_recipient': _(
            'Invalid recipient address. Glyph FT requires a Radiant '
            'P2PKH address.'
        ),
    }
    # testmempoolaccept string-pattern mapping (best-effort; display the
    # raw message in the detail section so reviewers / power users can
    # see what actually failed).
    if detail:
        lower = detail.lower()
        if 'codescripthash' in lower or 'bad-txns-inputvalues' in lower:
            user_msg = _('This transaction would destroy tokens. Please '
                         'report this bug.')
        elif 'min relay fee' in lower or 'mempool min fee' in lower:
            user_msg = _('Network fee too low; Radiant requires at least '
                         '10,000 sats per byte.')
        elif 'dust' in lower:
            user_msg = _('Output below dust threshold.')
        elif 'missing-inputs' in lower:
            user_msg = _('One of the selected coins was already spent. '
                         'Please refresh and try again.')
        else:
            user_msg = reasons.get(reason, _('Transaction rejected.'))
    else:
        user_msg = reasons.get(reason, _('Transaction rejected.'))

    box = QMessageBox(parent.top_level_window())
    box.setWindowTitle(_('Cannot send FT'))
    box.setIcon(QMessageBox.Warning)
    box.setText(user_msg)
    if detail:
        # "Show Details..." disclosure built into QMessageBox — Qt's
        # idiomatic answer to the plan's collapsible <details> section.
        box.setDetailedText(detail)
    box.exec_()
