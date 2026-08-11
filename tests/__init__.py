"""Test suite as a package.

Without this file pytest derives module names from the bare filename, so a
stray copy of `test_blaze.py` anywhere else in the tree collides with this one
and aborts collection ("import file mismatch"). As a package the modules are
named `tests.test_blaze`, which cannot collide.
"""
