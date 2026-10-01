# wikifier/cache/graph.py

**Purpose:** dependency-graph primitives over the cache dict: `build_dependency_graph` (optionally canonical node ids), reverse index maintenance (`maintain_reverse_dependencies_for_source`, `rebuild_reverse_dependencies`, `remove_file_from_graph` for deletions), iterative Tarjan `_tarjan_sccs`, `graph_signature` / `reverse_dependency_signature`, `build_graph_with_edge_metadata`.
