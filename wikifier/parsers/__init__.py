"""Language parsers — shared edge contract for update-maps.

Supported (deep import/include graphs):
  python, javascript/typescript, rust, go, c/c++, csharp, java

Language modules are loaded lazily so `import wikifier` does not pay for
JS/BREE/CDIA on health/check-changes-only sessions.
"""

from typing import Any

__all__ = [
    "python",
    "javascript",
    "rust",
    "go_lang",
    "c_cpp",
    "csharp",
    "java",
]

_LAZY = {
    "python": ".python",
    "javascript": ".javascript",
    "rust": ".rust",
    "go_lang": ".go_lang",
    "c_cpp": ".c_cpp",
    "csharp": ".csharp",
    "java": ".java",
}


def __getattr__(name: str) -> Any:
    modname = _LAZY.get(name)
    if modname is None:
        raise AttributeError(name)
    from importlib import import_module
    mod = import_module(modname, __name__)
    globals()[name] = mod
    return mod
