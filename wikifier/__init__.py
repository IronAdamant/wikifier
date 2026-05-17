"""
Wikifier Python Package

Provides the core Python components for Wikifier, including:
- Import parsers (Python + JavaScript/TypeScript)
- MCP Server
- Health Matrix (scalable implementation)
"""

from . import parsers
from . import mcp
from . import health
from . import locking
from . import import_cache
from . import resolution  # Robust Path Normalization Layer (Limitation #3 / Gap #1)
from . import diagnostics  # Failure Transparency & Diagnostics Layer (Limitation #5 / Gap #1) - schema, aggregates, get_resolution_diagnostics support

# Pre-Wave 0: Shared contracts (FROZEN foundation for all Gap #1 phases)
from . import contracts
from .contracts import (
    AnalysisTraceEntry,
    ConditionalAnalysis,
    DynamicAnalysis,
    ResolutionMetadata,
    encode_v1_payload,
    decode_v1_payload,
    pack_cdia_v1,
    unpack_cdia_v1,
    parse_pipeline_line,
    RICH_KEYS,
    RESERVED_TOP_LEVEL_KEYS,
    NODE_IDENTITY_VERSION_V0,
    NODE_IDENTITY_VERSION_V1,
    get_contracts_info,
    # R2: canonical ACS for consistent high-quality explanations + scores
    compute_acs_confidence,
)

__version__ = "0.3.3"
