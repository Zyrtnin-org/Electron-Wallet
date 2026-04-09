from electroncash.i18n import _

fullname = _('Ledger Wallet')
description = _('Provides support for Ledger hardware wallet. Requires the Bitcoin app on your Ledger device (use BIP44 derivation m/44\'/0\'/0\').')
requires = [('btchip', 'github.com/ledgerhq/btchip-python')]
registers_keystore = ('hardware', 'ledger', _("Ledger wallet"))
available_for = ['qt', 'cmdline']
