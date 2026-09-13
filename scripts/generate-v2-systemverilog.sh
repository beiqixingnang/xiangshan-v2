#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="$repo_root/upstream"
work_dir="${XIANGSHAN_V2_WSL_WORK:-/home/lishuo/xs-v2-local}"
target_dir="${XIANGSHAN_V2_WSL_RTL:-$work_dir/build/rtl}"
config="${CONFIG:-DefaultConfig}"
issue="${ISSUE:-E.b}"
num_cores="${NUM_CORES:-1}"
jvm_xmx="${JVM_XMX:-8G}"

if [[ ! -d "$source_dir/.git" ]]; then
  echo "missing upstream checkout: $source_dir" >&2
  exit 2
fi

mkdir -p "$work_dir"
if [[ "$source_dir" != "$work_dir" ]]; then
  rsync -a --delete --exclude '.git' --exclude 'build/' --exclude 'out/' \
    "$source_dir/" "$work_dir/"
fi

# Nested submodule gitdir pointer files refer to the Windows superproject and
# are not needed by Mill.  Keep only the WSL mirror's top-level .git metadata so
# the VCS plugin can query the selected V2 commit without broken nested paths.
find "$work_dir" -mindepth 2 -type f -name .git -delete

cd "$work_dir"
MILL_WORKSPACE_ROOT="$work_dir" mill -i -Djvm-xmx="$jvm_xmx" -Djvm-xss=256m \
  xiangshan.runMain top.TopMain \
  --target-dir "$target_dir" \
  --config "$config" \
  --issue "$issue" \
  --target systemverilog \
  --num-cores "$num_cores" \
  --fpga-platform

xstop="$target_dir/XSTop.sv"
if [[ ! -s "$xstop" ]]; then
  echo "generation finished but expected non-empty output is missing: $xstop" >&2
  exit 3
fi

bytes="$(stat -c '%s' "$xstop")"
hash="$(sha256sum "$xstop" | awk '{print $1}')"
echo "[PASS] V2 SystemVerilog generated: $xstop (${bytes} bytes, sha256 ${hash})"
