Electron Radiant - Lightweight Radiant client
=====================================

Forked from Electron Cash.

::

  Licence: MIT Licence
  Author: Electron Radiant Developers (2022)
  Author: Electron Cash Developers
  Language: Python
  Homepage: https://electroncash.org/

.. WARNING ::

   This fork (``Zyrtnin-org/Electron-Wallet``) is an **experimental
   beta** adding Radiant Glyph FT (fungible token) send support on top
   of the upstream ``Radiant-Core/Electron-Wallet`` classifier work
   (PR #2). It has NOT been audited by a third party, NOT shipped as
   a signed release, and NOT reviewed by the upstream maintainers at
   Radiant-Core.

   Do not use this build to move funds you are not willing to lose.
   Do not treat ``testmempoolaccept: allowed=true`` as a substitute
   for an end-to-end review of the signing, consensus, and GUI paths.

   **What's been verified:**

   - Consensus parity with ``radiant-node`` is proven cryptographically
     (the signing preimage assembled by this code byte-matches the one
     the node signs against). See
     ``electroncash/tests/test_transaction.py::TestRadiantPreimage``.
   - A Python-built, Python-signed FT send was accepted by a live
     mainnet ``testmempoolaccept`` and broadcast successfully (txid
     ``3115ec4bfc580dd22599e4b253509b4cc29f058e38ebb686a13097a6b4ab49c2``).
     See ``docs/MAINNET_PROOF.md``.
   - 122 local unit + integration tests pass.

   **What's been deliberately deferred:**

   - Third-party security audit. The signing, coin-selection, and
     sighash-extension code paths touch consensus-critical bytes; a
     subtle bug can burn mint authority or misdirect photons.
   - Hardware wallet (Ledger) signing for FT inputs — the firmware
     path only handles NFT singletons today. Spending FTs via Ledger
     will fail until ``Radiant-Core/app-radiant`` ships matching
     firmware.
   - Long-soaked mainnet usage. The live-proof tx above is a single
     self-send; real-world edge cases (reorgs, fragmented RXD for
     fees, label injection attempts in the confirmation modal) have
     limited production exposure.
   - Coin-control integration for per-FT-UTXO freezes. Advanced users
     should wait for this.

   **Where bugs are most likely:** (a) the fee fixed-point loop when
   RXD is highly fragmented, (b) the per-output ``hashOutputHashes``
   summary computation for unusual scriptPubKey shapes beyond 75B FT
   holders / 63B NFT singletons / 25B P2PKH / OP_RETURN, (c) label
   sanitization edge cases (new Unicode categories, emoji ZWJ
   sequences). The ``docs/MAINNET_PROOF.md`` section "Post-fix: size
   formula" records one bug the live proof already caught.

   Please report problems as GitHub issues on
   https://github.com/Zyrtnin-org/Electron-Wallet/issues — and DO NOT
   push FT sends to production exchanges or merchants using this
   build until the upstream PR series has merged and been tagged.

Radiant Glyph FT support
========================

This fork adds **send** support for Radiant Glyph fungible tokens on
top of the classifier landed in upstream PR #2. After updating, your
wallet will:

- Display per-ref FT balances in a new Tokens tab (opt-in via
  ``Show Tokens tab``; off by default for wallets with no FT holdings).
- Color-highlight FT UTXOs in the Coins tab (amber) so they're
  distinguishable from plain RXD at a glance.
- Add an Asset dropdown to the Send tab — picking a ref routes the
  send through a dedicated FT builder with its own confirmation modal.

The confirmation modal shows the full 72-char ref hex (monospace, the
authoritative identifier) above the user-editable label. Labels are
sanitized (Unicode bidi overrides and control characters stripped,
64-character cap) to neutralize any attempt to visually rewrite the
recipient line via a malicious token name.

For CLI / JSON-RPC agents, four new Commands methods match the GUI
surface: ``send_ft`` (defaults to ``dry_run=True``),
``get_ft_balances``, ``list_ft_utxos``, ``setreflabel``. Structured
error reasons (``dust_change``, ``insufficient_fee``,
``insufficient_fee_fragmented``, ``ref_mismatch``,
``invalid_recipient``, etc) are returned instead of raw exception
strings so agents can branch on them.

The architecture, rationale, and PR-by-PR breakdown are documented at
`docs/plans/2026-04-18-feat-glyph-ft-send-plan.md
<docs/plans/2026-04-18-feat-glyph-ft-send-plan.md>`_. Live mainnet
evidence is at `docs/MAINNET_PROOF.md <docs/MAINNET_PROOF.md>`_.

Server Mainnet List
===============

- electrumx.radiantexplorer.com (50012 and 50010)
- electrumx2.radiantexplorer.com (50012 and 50010)
- electrumx.radiantblockchain.org (50012 and 50010)
- electrumx.radiant4people.com (50012 and 50010)

Server Testnet List 
===============
- electrumx-testnet.radiant4people.com (51012 and 51010)


Getting started
===============

**Note: If running from source, Python 3.6 or above is required to run Electron Radiant.** If your system lacks Python 3.6,
you have other options, such as the `AppImage / binary releases <https://github.com/Radiant-Core/Electron-Wallet/releases/>`_
or running from source using `pyenv` (see section `Running from source on old Linux`_ below).

**macOS:** It is recommended that macOS users run `the binary .dmg https://github.com/Radiant-Core/Electron-Wallet/releases/>`_  as that's simpler to use and has everything included.  Otherwise, if you want to run from source, see section `Running from source on macOS`_ below.

Electron Radiant is a pure python application forked from Electrum and Electron-Cash. If you want to use the Qt interface, install the Qt dependencies::

    sudo apt-get install python3-pyqt5 python3-pyqt5.qtsvg

If you downloaded the official package (tar.gz), you can run
Electron Radiant from its root directory (called Electron Radiant), without installing it on your
system; all the python dependencies are included in the 'packages'
directory. To run Electron Radiant from its root directory, just do::

    ./electron-radiant

You can also install Electron Radiant on your system, by running this command::

    sudo apt-get install python3-setuptools
    python3 setup.py install

This will download and install the Python dependencies used by
Electron Radiant, instead of using the 'packages' directory.

If you cloned the git repository, you need to compile extra files
before you can run Electron Radiant. Read the next section, "Development
Version".

Hardware Wallet - Ledger Nano S (NOT YET SUPPORTED, MUST VERIFY)
-------------------------------

Electron Radiant natively support Ledger Nano S hardware wallet. If you plan to use
you need an additional dependency, namely btchip. To install it run this command::

    sudo pip3 install btchip-python

If you still have problems connecting to your Nano S please have a look at this
`troubleshooting <https://support.ledger.com/hc/en-us/articles/115005165269-Fix-connection-issues>`_ section on Ledger website.


Development version
===================

Check your python version >= 3.6, and install pyqt5, as instructed above in the
`Getting started`_ section above or `Running from source on old Linux`_ section below.

If you are on macOS, see the `Running from source on macOS`_ section below.

Check out the code from Github::

    git clone https://github.com/Radiant-Core/Electron-Wallet.git
    cd Electron-Radiant

Install the python dependencies::

    pip3 install -r contrib/requirements/requirements.txt --user

Create translations (optional)::

    sudo apt-get install python-requests gettext
    ./contrib/make_locale

Compile libsecp256k1 (optional, yet highly recommended)::

    sudo apt-get install libtool automake
    ./contrib/make_secp

For plugin development, see the `plugin documentation <plugins/README.rst>`_.

Running unit tests (very optional, advanced users only)::

    pip install tox
    tox

Tox will take care of building a faux installation environment, and ensure that
the mapped import paths work correctly.

Running from source on old Linux
================================

If your Linux distribution has a different version of python 3 (such as python
3.5 in Debian 9), it is recommended to do a user dir install with
`pyenv <https://github.com/pyenv/pyenv-installer>`_. This allows Electron
Radiant to run completely independently of your system configuration.

1. Install `pyenv <https://github.com/pyenv/pyenv-installer>`_ in your user
   account. Follow the printed instructions about updating your environment
   variables and ``.bashrc``, and restart your shell to ensure that they are
   loaded.
2. Run ``pyenv install 3.6.9``. This will download and compile that version of
   python, storing it under ``.pyenv`` in your home directory.
3. ``cd`` into the Electron Radiant directory. Run ``pyenv local 3.6.9`` which inserts
   a file ``.python-version`` into the current directory.
4. While still in this directory, run ``pip install pyqt5``.
5. If you are installing from the source file (.tar.gz or .zip) then you are
   ready and you may run ``./electron-radiant``. If you are using the git version,
   then continue by following the Development version instructions above.

Running from source on macOS
============================

You need to install **either** `MacPorts <https://www.macports.org>`_  **or** `HomeBrew <https://www.brew.sh>`_.  Follow the instructions on either site for installing (Xcode from `Apple's developer site <https://developer.apple.com>`_ is required for either).

1. After installing either HomeBrew or MacPorts, clone this repository and switch to the directory: ``git clone https://github.com/Radiant-Core/Electron-Wallet.git && cd Electron-Radiant``
2. Install python 3.6 or 3.7. For brew: ``brew install python3`` or if using MacPorts: ``sudo port install python36``
3. Install PyQt5: ``python3 -m pip install --user pyqt5``
4. Install Electron Radiant requirements: ``python3 -m pip install --user -r contrib/requirements/requirements.txt``
5. Compile libsecp256k1 (optional, yet highly recommended): ``./contrib/make_secp``.
   This requires GNU tools and automake, install with brew: ``brew install coreutils automake`` or if using MacPorts: ``sudo port install coreutils automake``
6. At this point you should be able to just run the sources: ``./electron-radiant``


Creating Binaries
=================

Linux AppImage & Source Tarball
--------------

See `contrib/build-linux/README.md <contrib/build-linux/README.md>`_.

Mac OS X / macOS
--------

See `contrib/osx/ <contrib/osx/>`_.

Windows
-------

See `contrib/build-wine/ <contrib/build-wine>`_.

Android
-------

See `android/ <android/>`_.

iOS
-------

See `ios/ <ios/>`_.
