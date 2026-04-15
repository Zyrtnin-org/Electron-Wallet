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
requires = [('btchip', 'github.com/ledgerhq/btchip-python')]
registers_keystore = ('hardware', 'ledger', _("Ledger wallet"))
available_for = ['qt', 'cmdline']
