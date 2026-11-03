# Wikifier Python vs Rust benchmark

Measured by `scripts/benchmark_parity.sh` on 2026-11-03T08:54:31Z.

## Machine

- CPU: Intel(R) Xeon(R) Processor (4 cores)
- RAM: 15.6 GiB
- Kernel: Linux 6.12.94+
- Python: Python 3.12.3 (commit 24812eff13cf61cbf23ac5361a778b0013df6a5d)
- Rust binary: wikifier 4.7.0 (rustc 1.83.0 (90b35a623 2024-11-26))
- Runs per cell: 5. Times are milliseconds, median (min–max).
- Peak RSS is one extra cold and warm `update-maps`, from `/usr/bin/time -v`, in kilobytes.
- Rust binary size: 2197456 bytes. Python package tree `wikifier/`: 1560419 bytes.

## Trees

| Size | Tree |
|---|---|
| small | three Python modules under `src/pkg` |
| medium | this repo's `src/` and `tests/` |
| large | Django shallow clone, map roots `django/` and `tests/` (/tmp/bench-django) |

## Milliseconds

| Command | small Python | small Rust | medium Python | medium Rust | large Python | large Rust |
|---|---:|---:|---:|---:|---:|---:|
| startup | 63 (61–66) | 2 (1–2) | 63 (61–66) | 2 (1–2) | 63 (61–66) | 2 (1–2) |
| cold update-maps | 123 (121–126) | 8 (7–13) | 167 (163–168) | 62 (59–73) | 12675 (12540–13094) | 3142 (3114–3305) |
| warm update-maps | 69 (67–72) | 4 (3–5) | 73 (72–74) | 4 (4–5) | 422 (417–433) | 246 (243–253) |
| session-bootstrap | 66 (64–67) | 2 (1–2) | 65 (64–67) | 2 (1–2) | 270 (269–278) | 21 (21–21) |
| check-changes | 64 (62–65) | 3 (2–3) | 70 (69–75) | 5 (5–6) | 1232 (1217–1266) | 74 (73–76) |
| health --summary | 60 (60–62) | 2 (1–2) | 60 (59–63) | 1 (1–2) | 109 (108–114) | 8 (8–9) |
| verify-wikis | 60 (60–61) | 2 (1–2) | 62 (60–67) | 1 (1–2) | 106 (103–108) | 8 (7–8) |
| cycles | 60 (60–61) | 2 (1–2) | 61 (60–63) | 2 (2–2) | 63 (61–64) | 54 (53–55) |

## Peak RSS (kbytes) and resolved file edges

| | small Python | small Rust | medium Python | medium Rust | large Python | large Rust |
|---|---:|---:|---:|---:|---:|---:|
| cold update-maps RSS | 27544 | 3384 | 28392 | 4424 | 97564 | 40012 |
| warm update-maps RSS | 24584 | 3424 | 24248 | 3476 | 30520 | 13120 |
| resolved file edges | 2 | 2 | 44 | 98 | 9074 | 9074 |

Startup is `wikifier --version` and does not depend on the tree, so that row repeats the same pair.
A cold run deletes `.wikifier_staging` and the generated health and library files first.
The warm run is the next `update-maps` on that same tree.
