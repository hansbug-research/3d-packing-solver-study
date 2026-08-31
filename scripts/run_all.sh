#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${root_dir}/.venv/bin/python"
if [[ ! -x "${python_bin}" ]]; then
    python_bin="python3"
fi

"${python_bin}" "${root_dir}/benchmarks/convert_thpack9.py"
bash "${root_dir}/benchmarks/run_controlled.sh"
if [[ -x "${root_dir}/.cache/apache-maven/bin/mvn" ]] || command -v mvn >/dev/null 2>&1; then
    bash "${root_dir}/benchmarks/run_java_controlled.sh"
fi
bash "${root_dir}/scripts/collect_and_derive.sh"
