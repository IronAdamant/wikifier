"""Language parsers — shared edge contract for update-maps.

Supported (deep import/include graphs):
  python, javascript/typescript, rust, go, c/c++, csharp, java
"""

from . import python
from . import javascript
from . import rust
from . import go_lang
from . import c_cpp
from . import csharp
from . import java

__all__ = [
    "python",
    "javascript",
    "rust",
    "go_lang",
    "c_cpp",
    "csharp",
    "java",
]
