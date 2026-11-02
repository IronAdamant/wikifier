# src/parse.rs

**Role:** Comment-masked import scans for Python, JS/TS, Rust, Go, C/C++, C#, and Java.

Unknown suffixes emit no edges. Named JS/TS re-exports are followed to depth 8 and flagged `via_barrel`. A Python import with indent greater than zero is `conditional`. `import()` is `dynamic`. Direct edges clear `via_barrel` when the same destination is also reached that way.

The scan does not use CPython `ast` and does not read tsconfig paths, package exports, or workspaces. The frozen fixtures are the accuracy gate.
