"""Graph + reverse-dependency helpers."""
from ._core import (
    get_reverse_dependencies,
    set_reverse_dependencies,
    maintain_reverse_dependencies_for_source,
    rebuild_reverse_dependencies,
    get_reverse_dependency_stats,
    build_dependency_graph,
    graph_signature,
    reverse_dependency_signature,
    get_reverse_signature,
    set_reverse_signature,
    get_graph_signature,
    set_graph_signature,
    compute_graph_integrity,
    set_graph_integrity,
    build_graph_with_edge_metadata,
)
