#!/usr/bin/env bash
set -euo pipefail
root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${root_dir}/.venv/bin/python"
if [[ ! -x "${python_bin}" ]]; then python_bin="python3"; fi
"${python_bin}" "${root_dir}/scripts/collect_raw.py"
"${python_bin}" "${root_dir}/benchmarks/benchmark_public_thpack9.py" > "${root_dir}/results/public/thpack9_baselines.json"
cp "${root_dir}/results/public/thpack9_baselines.json" "${root_dir}/raw/thpack9_baselines.json"
"${python_bin}" "${root_dir}/scripts/analyze.py"
"${python_bin}" "${root_dir}/scripts/plot.py"
"${python_bin}" "${root_dir}/scripts/build_manifest.py"
"${python_bin}" "${root_dir}/scripts/verify.py"
