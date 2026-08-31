#!/usr/bin/env bash
set -euo pipefail

study_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
raw_dir="${study_root}/raw/experiments/campaign/packingsolver-10s"
mkdir -p "${raw_dir}" "${study_root}/results/campaign"

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

status=0
/usr/bin/time -v -o "${raw_dir}/campaign.resources.txt" \
    timeout --signal=TERM --kill-after=10s 10800s \
    "${study_root}/.venv/bin/python" \
    "${study_root}/benchmarks/campaign/packingsolver_thpack_parallel.py" \
    --binary "${study_root}/.cache/build-fork/src/box/packingsolver_box" \
    --source-commit d953148b8f710c06fa6c410949b7272f9e36327b \
    --data-root "${study_root}/.cache/packingsolver-fork/data/box" \
    --results-dir "${study_root}/results/campaign" \
    --raw-dir "${raw_dir}" --time-limit 10 --jobs 4 --label 10s \
    > >(tee "${raw_dir}/campaign.stdout") \
    2> >(tee "${raw_dir}/campaign.stderr" >&2) || status=$?
printf '%s\n' "${status}" > "${raw_dir}/campaign.exitcode"
exit "${status}"
