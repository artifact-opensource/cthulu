"""Compatibility shim package named ``cthulu``.

This package points its import path to the project root so that imports
like ``cthulu.connector`` resolve to the modules in the repo (which live
in the directory named ``cthulu``). This keeps the original filesystem
layout while satisfying imports that use the single-H name.
"""
import os

# Make this package's search path include both the package directory and
# the project root (parent dir). This allows `import cthulu.connector`
# to find `connector/` under the repository root while still allowing
# submodules like `cthulu.__main__` to be resolved from the package dir.
pkg_dir = os.path.dirname(__file__)
parent = os.path.abspath(os.path.join(pkg_dir, ".."))
__path__ = [pkg_dir, parent]

