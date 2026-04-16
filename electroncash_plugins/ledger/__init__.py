import os
import sys

# Prefer the vendored btchip (patched 0.1.32). Upstream LedgerHQ/btchip-python is
# archived and its setup.py declares a non-PEP-440 dependency that modern pip rejects.
# See vendor/README.md for the patch and upgrade procedure.
_vendor_dir = os.path.join(os.path.dirname(__file__), 'vendor')
if _vendor_dir not in sys.path:
    sys.path.insert(0, _vendor_dir)

from electroncash.i18n import _

fullname = _('Ledger Wallet')
description = _(
    "Provides support for Ledger hardware wallet.\n\n"
    "Requires the community-built Radiant app on your Ledger device "
    "(NOT the stock Bitcoin app). The Radiant app uses SLIP-44 coin type "
    "512 and derives at m/44'/512'/0'. If your seed has existing RXD at "
    "m/44'/0'/... from Samara/Electron/Chainbow, you must transfer those "
    "funds to your new Ledger-derived address before using this wallet. "
    "See the Radiant Ledger app migration guide."
)
requires = []  # btchip is vendored at electroncash_plugins/ledger/vendor/btchip
registers_keystore = ('hardware', 'ledger', _("Ledger wallet"))
available_for = ['qt', 'cmdline']
