#!/usr/bin/env bash
set -euo pipefail

study_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
runner="${study_root}/benchmarks/campaign/packingsolver_strategies.py"
binary="${study_root}/.cache/build-fork/src/box/packingsolver_box"
data_root="${study_root}/.cache/packingsolver-fork/data/box"
result_dir="${study_root}/results/campaign"
raw_dir="${study_root}/raw/experiments/campaign/packingsolver-strategies"
mkdir -p "${result_dir}" "${raw_dir}"

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

status=0
/usr/bin/time -v -o "${raw_dir}/campaign.resources.txt" \
    timeout --signal=TERM --kill-after=5s 240s \
    "${study_root}/.venv/bin/python" "${runner}" \
    --binary "${binary}" \
    --source-commit d953148b8f710c06fa6c410949b7272f9e36327b \
    --data-root "${data_root}" \
    --results-dir "${result_dir}" \
    --raw-dir "${raw_dir}" \
    > "${raw_dir}/campaign.stdout" \
    2> "${raw_dir}/campaign.stderr" || status=$?
printf '%s\n' "${status}" > "${raw_dir}/campaign.exitcode"
