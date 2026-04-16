# Vendored btchip-python

This directory contains a vendored copy of [`LedgerHQ/btchip-python`](https://github.com/LedgerHQ/btchip-python) (v0.1.32) with a one-line fix to the `setup.py` `extras_require` block.

## Why vendored

Upstream is **archived** (2023-10-10) and has an open unreviewed PR ([#54](https://github.com/LedgerHQ/btchip-python/pull/54)) for this exact issue since 2023. Modern `setuptools` (>= 68) rejects the `'python-pyscard>=1.6.12-4build1'` extras pin because `-4build1` is a Debian package suffix, not valid PEP 440.

Because upstream will not merge, vendoring is the only durable path for a clean install experience for testers.

## The fix applied to upstream source

```diff
-	'smartcard': [ 'python-pyscard>=1.6.12-4build1' ]
+	'smartcard': [ 'python-pyscard>=1.6.12' ]
```

## How the Electron Radiant plugin loads it

At plugin init time, `electroncash_plugins/ledger/__init__.py` (or a shim module) prepends this `vendor/` directory to `sys.path` so that `from btchip.btchip import btchip` resolves here rather than to any system-installed `btchip` package.

## Upgrade procedure

If/when upstream un-archives or a trusted community fork appears:

1. Remove this `vendor/btchip/` directory
2. Re-add `btchip-python>=0.1.32` (or equivalent) to `contrib/requirements/requirements-hw.txt`
3. Remove the `sys.path` prepend

## License

Apache-2.0 (same as upstream btchip-python). See upstream repository for the full LICENSE file.
