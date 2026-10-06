"""Shared temp paths. Override with ODT_EDIT_ROOT / ODT_EDIT_PYLIB / ODT_EDIT_WORK."""
import os, sys


def root():
    return os.environ.get(
        "ODT_EDIT_ROOT",
        os.path.join(os.environ.get("TMPDIR", "/tmp"), f"odt-edit-{os.getuid()}"),
    )


def pylib():
    return os.environ.get("ODT_EDIT_PYLIB", os.path.join(root(), "pylibs"))


def work():
    return os.environ.get("ODT_EDIT_WORK", os.path.join(root(), "work"))


def add_pylib():
    lib = pylib()
    if lib not in sys.path:
        sys.path.insert(0, lib)
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    return lib
