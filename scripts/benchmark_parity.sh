#!/usr/bin/env bash
# Compare Python Wikifier at commit 24812ef with the Rust release binary.
# Stdlib and POSIX tools only. No extra crates.
# Usage: scripts/benchmark_parity.sh [results.md]
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out="${1:-$root/scripts/benchmark_results.md}"
py_src="${WIKIFIER_PY_SRC:-/tmp/wikifier-py}"
rs_bin="${WIKIFIER_RS_BIN:-$root/target/release/wikifier}"
runs="${WIKIFIER_BENCH_RUNS:-5}"
django_src="${WIKIFIER_DJANGO:-/tmp/bench-django}"

if [[ ! -x "$rs_bin" ]]; then
  echo "missing rust binary: $rs_bin (cargo build --release)" >&2
  exit 1
fi
if [[ ! -f "$py_src/wikifier/__init__.py" ]]; then
  git -C "$root" archive 24812eff13cf61cbf23ac5361a778b0013df6a5d | tar -x -C "$(dirname "$py_src")"
fi
if [[ ! -d "$django_src/django" ]]; then
  git clone --depth 1 https://github.com/django/django.git "$django_src"
fi

export PYTHONPATH="$py_src"
export PYTHONDONTWRITEBYTECODE=1

now_ns() { date +%s%N; }

median_of() {
  printf '%s\n' "$@" | sort -n | awk '
    { a[NR] = $1 }
    END {
      if (NR == 0) { print 0; exit }
      if (NR % 2 == 1) printf "%.0f\n", a[(NR + 1) / 2]
      else printf "%.0f\n", (a[NR / 2] + a[NR / 2 + 1]) / 2
    }'
}

min_of() { printf '%s\n' "$@" | sort -n | head -1; }
max_of() { printf '%s\n' "$@" | sort -n | tail -1; }

time_cmd() {
  local start end
  start="$(now_ns)"
  "$@" >/tmp/bench-cmd.out 2>/tmp/bench-cmd.err || true
  end="$(now_ns)"
  echo $(( (end - start) / 1000000 ))
}

rss_of() {
  /usr/bin/time -v "$@" >/tmp/bench-rss.out 2>/tmp/bench-rss.err || true
  awk -F: '/Maximum resident set size/ { gsub(/^[ \t]+/, "", $2); print $2; exit }' /tmp/bench-rss.err
}

prepare_small() {
  local dest="$1"
  rm -rf "$dest"
  mkdir -p "$dest/src/pkg"
  printf 'src\n' >"$dest/map_paths.txt"
  printf 'src\n' >"$dest/monitored_paths.txt"
  printf 'from pkg.core import run\n' >"$dest/src/pkg/__init__.py"
  printf 'from pkg.utils import helper\n\ndef run():\n    return helper()\n' >"$dest/src/pkg/core.py"
  printf 'def helper():\n    return 1\n' >"$dest/src/pkg/utils.py"
}

prepare_medium() {
  local dest="$1"
  rm -rf "$dest"
  mkdir -p "$dest"
  cp -a "$root/src" "$root/tests" "$root/Cargo.toml" "$root/map_paths.txt" "$root/monitored_paths.txt" "$dest/"
}

prepare_large() {
  local dest="$1"
  rm -rf "$dest"
  mkdir -p "$dest"
  cp -a "$django_src/django" "$django_src/tests" "$dest/"
  printf 'django\ntests\n' >"$dest/map_paths.txt"
  printf 'django\ntests\n' >"$dest/monitored_paths.txt"
}

wipe_cache() {
  local dest="$1"
  rm -rf "$dest/.wikifier_staging" "$dest/library.md" "$dest/file_health.json" "$dest/file_health.md" "$dest/pending_updates.md"
}

py_cmd() { python3 -m wikifier --target "$1" "${@:2}"; }
rs_cmd() { "$rs_bin" --target "$1" "${@:2}"; }

edge_count_py() {
  python3 - "$1" <<'PY'
import sqlite3, sys
from pathlib import Path
db = Path(sys.argv[1]) / ".wikifier_staging" / "import_cache.sqlite"
con = sqlite3.connect(db)
rows = {(a, b) for a, b in con.execute("select src, dst from edges") if a and b}
print(len(rows))
PY
}

edge_count_rs() {
  python3 - "$1" <<'PY'
import sys
from pathlib import Path
root = Path(sys.argv[1]) / ".wikifier_staging" / "wk_cache" / "by_src"
edges = set()
if root.is_dir():
    for path in root.glob("*.edges"):
        lines = path.read_text(errors="replace").splitlines()
        if not lines or not lines[0].startswith("@\t"):
            continue
        src = lines[0][2:].strip()
        for line in lines[1:]:
            dst = line.split("\t", 1)[0].strip()
            if dst and dst != src:
                edges.add((src, dst))
print(len(edges))
PY
}

declare -A CELL
measure_size() {
  local label="$1" prep="$2"
  local py_dir="/tmp/bench-work/${label}-py"
  local rs_dir="/tmp/bench-work/${label}-rs"
  "$prep" "$py_dir"
  "$prep" "$rs_dir"
  local -a py_cold rs_cold py_warm rs_warm py_boot rs_boot py_check rs_check py_health rs_health py_verify rs_verify py_cycles rs_cycles
  local i
  for ((i = 1; i <= runs; i++)); do
    wipe_cache "$py_dir"
    wipe_cache "$rs_dir"
    py_cold+=("$(time_cmd py_cmd "$py_dir" update-maps)")
    rs_cold+=("$(time_cmd rs_cmd "$rs_dir" update-maps)")
    py_warm+=("$(time_cmd py_cmd "$py_dir" update-maps)")
    rs_warm+=("$(time_cmd rs_cmd "$rs_dir" update-maps)")
    py_boot+=("$(time_cmd py_cmd "$py_dir" session-bootstrap)")
    rs_boot+=("$(time_cmd rs_cmd "$rs_dir" session-bootstrap)")
    py_check+=("$(time_cmd py_cmd "$py_dir" check-changes)")
    rs_check+=("$(time_cmd rs_cmd "$rs_dir" check-changes)")
    py_health+=("$(time_cmd py_cmd "$py_dir" health --summary)")
    rs_health+=("$(time_cmd rs_cmd "$rs_dir" health --summary)")
    py_verify+=("$(time_cmd py_cmd "$py_dir" verify-wikis)")
    rs_verify+=("$(time_cmd rs_cmd "$rs_dir" verify-wikis)")
    py_cycles+=("$(time_cmd py_cmd "$py_dir" cycles --json)")
    rs_cycles+=("$(time_cmd rs_cmd "$rs_dir" cycles)")
    echo "$label run $i done" >&2
  done
  CELL["${label}|py|cold"]="$(median_of "${py_cold[@]}") $(min_of "${py_cold[@]}") $(max_of "${py_cold[@]}")"
  CELL["${label}|rs|cold"]="$(median_of "${rs_cold[@]}") $(min_of "${rs_cold[@]}") $(max_of "${rs_cold[@]}")"
  CELL["${label}|py|warm"]="$(median_of "${py_warm[@]}") $(min_of "${py_warm[@]}") $(max_of "${py_warm[@]}")"
  CELL["${label}|rs|warm"]="$(median_of "${rs_warm[@]}") $(min_of "${rs_warm[@]}") $(max_of "${rs_warm[@]}")"
  CELL["${label}|py|boot"]="$(median_of "${py_boot[@]}") $(min_of "${py_boot[@]}") $(max_of "${py_boot[@]}")"
  CELL["${label}|rs|boot"]="$(median_of "${rs_boot[@]}") $(min_of "${rs_boot[@]}") $(max_of "${rs_boot[@]}")"
  CELL["${label}|py|check"]="$(median_of "${py_check[@]}") $(min_of "${py_check[@]}") $(max_of "${py_check[@]}")"
  CELL["${label}|rs|check"]="$(median_of "${rs_check[@]}") $(min_of "${rs_check[@]}") $(max_of "${rs_check[@]}")"
  CELL["${label}|py|health"]="$(median_of "${py_health[@]}") $(min_of "${py_health[@]}") $(max_of "${py_health[@]}")"
  CELL["${label}|rs|health"]="$(median_of "${rs_health[@]}") $(min_of "${rs_health[@]}") $(max_of "${rs_health[@]}")"
  CELL["${label}|py|verify"]="$(median_of "${py_verify[@]}") $(min_of "${py_verify[@]}") $(max_of "${py_verify[@]}")"
  CELL["${label}|rs|verify"]="$(median_of "${rs_verify[@]}") $(min_of "${rs_verify[@]}") $(max_of "${rs_verify[@]}")"
  CELL["${label}|py|cycles"]="$(median_of "${py_cycles[@]}") $(min_of "${py_cycles[@]}") $(max_of "${py_cycles[@]}")"
  CELL["${label}|rs|cycles"]="$(median_of "${rs_cycles[@]}") $(min_of "${rs_cycles[@]}") $(max_of "${rs_cycles[@]}")"
  wipe_cache "$py_dir"
  wipe_cache "$rs_dir"
  CELL["${label}|py|rss_cold"]="$(rss_of python3 -m wikifier --target "$py_dir" update-maps)"
  CELL["${label}|rs|rss_cold"]="$(rss_of "$rs_bin" --target "$rs_dir" update-maps)"
  CELL["${label}|py|rss_warm"]="$(rss_of python3 -m wikifier --target "$py_dir" update-maps)"
  CELL["${label}|rs|rss_warm"]="$(rss_of "$rs_bin" --target "$rs_dir" update-maps)"
  CELL["${label}|py|edges"]="$(edge_count_py "$py_dir")"
  CELL["${label}|rs|edges"]="$(edge_count_rs "$rs_dir")"
}

declare -a py_start rs_start
for ((i = 1; i <= runs; i++)); do
  py_start+=("$(time_cmd python3 -m wikifier --version)")
  rs_start+=("$(time_cmd "$rs_bin" --version)")
done

measure_size small prepare_small
measure_size medium prepare_medium
measure_size large prepare_large

cpu="$(lscpu | awk -F: '/Model name/ { gsub(/^[ \t]+/, "", $2); print $2; exit }')"
ncpu="$(nproc)"
mem="$(awk '/MemTotal/ { printf "%.1f GiB", $2/1024/1024 }' /proc/meminfo)"
py_ver="$(python3 --version 2>&1)"
rs_ver="$("$rs_bin" --version)"
rustc_ver="$(rustc --version)"
bin_bytes="$(stat -c %s "$rs_bin")"
py_bytes="$(du -sb "$py_src/wikifier" | awk '{print $1}')"

fmt_cell() {
  local key="$1"
  local value="${CELL[$key]}"
  local med min max
  read -r med min max <<<"$value"
  printf '%s (%s–%s)' "$med" "$min" "$max"
}

{
  echo "# Wikifier Python vs Rust benchmark"
  echo
  echo "Measured by \`scripts/benchmark_parity.sh\` on $(date -u +%Y-%m-%dT%H:%M:%SZ)."
  echo
  echo "## Machine"
  echo
  echo "- CPU: ${cpu} (${ncpu} cores)"
  echo "- RAM: ${mem}"
  echo "- Kernel: $(uname -sr)"
  echo "- Python: ${py_ver} (commit 24812eff13cf61cbf23ac5361a778b0013df6a5d)"
  echo "- Rust binary: ${rs_ver} (${rustc_ver})"
  echo "- Runs per cell: ${runs}. Times are milliseconds, median (min–max)."
  echo "- Peak RSS is one extra cold and warm \`update-maps\`, from \`/usr/bin/time -v\`, in kilobytes."
  echo "- Rust binary size: ${bin_bytes} bytes. Python package tree \`wikifier/\`: ${py_bytes} bytes."
  echo
  echo "## Trees"
  echo
  echo "| Size | Tree |"
  echo "|---|---|"
  echo "| small | three Python modules under \`src/pkg\` |"
  echo "| medium | this repo's \`src/\` and \`tests/\` |"
  echo "| large | Django shallow clone, map roots \`django/\` and \`tests/\` (${django_src}) |"
  echo
  echo "## Milliseconds"
  echo
  echo "| Command | small Python | small Rust | medium Python | medium Rust | large Python | large Rust |"
  echo "|---|---:|---:|---:|---:|---:|---:|"
  for pair in "startup|start" "cold update-maps|cold" "warm update-maps|warm" "session-bootstrap|boot" "check-changes|check" "health --summary|health" "verify-wikis|verify" "cycles|cycles"; do
    name="${pair%%|*}"
    key="${pair##*|}"
    if [[ "$key" == "start" ]]; then
      printf '| %s | %s | %s | %s | %s | %s | %s |\n' "$name" \
        "$(printf '%s (%s–%s)' "$(median_of "${py_start[@]}")" "$(min_of "${py_start[@]}")" "$(max_of "${py_start[@]}")")" \
        "$(printf '%s (%s–%s)' "$(median_of "${rs_start[@]}")" "$(min_of "${rs_start[@]}")" "$(max_of "${rs_start[@]}")")" \
        "$(printf '%s (%s–%s)' "$(median_of "${py_start[@]}")" "$(min_of "${py_start[@]}")" "$(max_of "${py_start[@]}")")" \
        "$(printf '%s (%s–%s)' "$(median_of "${rs_start[@]}")" "$(min_of "${rs_start[@]}")" "$(max_of "${rs_start[@]}")")" \
        "$(printf '%s (%s–%s)' "$(median_of "${py_start[@]}")" "$(min_of "${py_start[@]}")" "$(max_of "${py_start[@]}")")" \
        "$(printf '%s (%s–%s)' "$(median_of "${rs_start[@]}")" "$(min_of "${rs_start[@]}")" "$(max_of "${rs_start[@]}")")"
      continue
    fi
    printf '| %s | %s | %s | %s | %s | %s | %s |\n' "$name" \
      "$(fmt_cell "small|py|${key}")" "$(fmt_cell "small|rs|${key}")" \
      "$(fmt_cell "medium|py|${key}")" "$(fmt_cell "medium|rs|${key}")" \
      "$(fmt_cell "large|py|${key}")" "$(fmt_cell "large|rs|${key}")"
  done
  echo
  echo "## Peak RSS (kbytes) and resolved file edges"
  echo
  echo "| | small Python | small Rust | medium Python | medium Rust | large Python | large Rust |"
  echo "|---|---:|---:|---:|---:|---:|---:|"
  printf '| cold update-maps RSS | %s | %s | %s | %s | %s | %s |\n' \
    "${CELL[small|py|rss_cold]}" "${CELL[small|rs|rss_cold]}" \
    "${CELL[medium|py|rss_cold]}" "${CELL[medium|rs|rss_cold]}" \
    "${CELL[large|py|rss_cold]}" "${CELL[large|rs|rss_cold]}"
  printf '| warm update-maps RSS | %s | %s | %s | %s | %s | %s |\n' \
    "${CELL[small|py|rss_warm]}" "${CELL[small|rs|rss_warm]}" \
    "${CELL[medium|py|rss_warm]}" "${CELL[medium|rs|rss_warm]}" \
    "${CELL[large|py|rss_warm]}" "${CELL[large|rs|rss_warm]}"
  printf '| resolved file edges | %s | %s | %s | %s | %s | %s |\n' \
    "${CELL[small|py|edges]}" "${CELL[small|rs|edges]}" \
    "${CELL[medium|py|edges]}" "${CELL[medium|rs|edges]}" \
    "${CELL[large|py|edges]}" "${CELL[large|rs|edges]}"
  echo
  echo "Startup is \`wikifier --version\` and does not depend on the tree, so that row repeats the same pair."
  echo "A cold run deletes \`.wikifier_staging\` and the generated health and library files first."
  echo "The warm run is the next \`update-maps\` on that same tree."
} >"$out"

echo "wrote $out"
