#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export CROSSLANG_TOOLCHAIN_ROOT="${CROSSLANG_TOOLCHAIN_ROOT:-/tmp/crosslang-toolchains}"
"${root}/benchmarks/campaign/crosslang_go_bp3d/run.sh"
"${root}/benchmarks/campaign/crosslang_rust_unesting/run.sh"
python3 "${root}/benchmarks/campaign/crosslang_thpack9_campaign.py"
