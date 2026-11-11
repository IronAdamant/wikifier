# tests/limit_rule.rs

**Role:** One cap rule for `limit`, `max_items`, and `max_files` on the CLI and over MCP.

`every_mcp_cap_reads_absent_zero_and_one_the_same_way` and `every_cli_cap_reads_absent_zero_and_one_the_same_way` build a 121-file tree. Absent means the tool's default, `0` means no cap, and `1` means one item. `suggest-next` on that tree is four actions: three recorded changes and the fan-in alert on `core.py`. `the_shared_parser` checks `Cap::parse`.
