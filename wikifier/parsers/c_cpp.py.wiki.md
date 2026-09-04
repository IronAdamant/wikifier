# wikifier/parsers/c_cpp.py

**Role:** Zero-dep C/C++ `#include` parser. `parse_c_cpp_imports(filepath)` → edge list for `.c/.h/.cpp/.hpp/.cc/.cxx/.hh`.

**Resolve:** Quoted includes — same-dir, then `include/`/`inc/`/`src/`/… up parents (bounded). Angle includes → external/bare.

**Wiring:** Lazy via `parsers/__init__.py`; `api.py` dispatches C/C++ extensions here.
