"""
Shared loader for tests that exercise a ``backend/scripts/*.py`` file
directly. ``scripts/`` has no ``__init__.py`` -- it is not an importable
package -- so a normal ``from scripts.foo import bar`` is not available;
this is the only way to load one of those files as a module under test.

Registers the loaded module in ``sys.modules`` under ``module_name`` (as the
scripts previously loaded this way already did individually), so it behaves
like any other imported module for the rest of the process.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


def load_script_module(filename: str, module_name: str) -> ModuleType:
    """Load ``backend/scripts/<filename>`` as a module named ``module_name``."""

    script_path = _SCRIPTS_DIR / filename
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
