#!/usr/bin/env bash
set -euo pipefail

study_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
raw_dir="${study_root}/raw/experiments/campaign/packingsolver-boxstacks"
mkdir -p "${raw_dir}"
status=0
/usr/bin/time -v -o "${raw_dir}/suite.resources.txt" \
    timeout --signal=TERM --kill-after=5s 240s \
    "${study_root}/.venv/bin/python" \
    "${study_root}/benchmarks/campaign/packingsolver_boxstacks_suite.py" \
    --binary "${study_root}/.cache/build-fork/src/boxstacks/packingsolver_boxstacks" \
    --data-dir "${study_root}/benchmarks/data/packingsolver" \
    --result "${study_root}/results/campaign/packingsolver-boxstacks.json" \
    --raw-dir "${raw_dir}" \
    > "${raw_dir}/suite.stdout" 2> "${raw_dir}/suite.stderr" || status=$?
printf '%s\n' "${status}" > "${raw_dir}/suite.exitcode"
exit "${status}"
