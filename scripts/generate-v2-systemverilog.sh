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

if [[ ! -f "$source_dir/build.sc" || ! -f "$source_dir/.mill-version" ]]; then
  echo "missing vendored XiangShan source checkout: $source_dir" >&2
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
# Nested git metadata is not needed by Mill and can contain host-specific
# gitdir pointers when the source was prepared on Windows.
find "$work_dir" -mindepth 2 -type f -name .git -delete

# Mill's source-version annotation expects a Git worktree.  A fresh checkout
# of this repository has vendored source but no nested .git directory, so make
# a local, disposable metadata repository without contacting any remote.
if ! git -C "$work_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git -C "$work_dir" init -q
  git -C "$work_dir" config user.name "XiangShan V2 Local"
  git -C "$work_dir" config user.email "local@xiangshan.invalid"
  git -C "$work_dir" add -A
  git -C "$work_dir" commit -q -m "vendored XiangShan V2 source"
fi

cd "$work_dir"
export NOOP_HOME="$work_dir"
if [[ "${OFFLINE:-0}" == "1" ]]; then
  export COURSIER_MODE=offline
  export COURSIER_OFFLINE=true
fi

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
