import compileall
import importlib
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_every_file_compiles():
    assert compileall.compile_dir(os.path.join(ROOT, "xmeltunnel"), quiet=1, force=True)
    assert compileall.compile_dir(os.path.join(ROOT, "tools"), quiet=1, force=True)


@pytest.mark.parametrize("mod", ["xmeltunnel.core", "xmeltunnel.server_setup", "xmeltunnel.ui.app",
                                 "xmeltunnel.ui.dialogs", "xmeltunnel.ui.widgets", "xmeltunnel.ui.frameless"])
def test_modules_import(mod):
    importlib.import_module(mod)
