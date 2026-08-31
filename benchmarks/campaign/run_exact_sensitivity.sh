#!/usr/bin/env bash
set -euo pipefail

study_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python_bin="${study_root}/.venv/bin/python"
result_dir="${study_root}/results/campaign"
raw_dir="${study_root}/raw/experiments/campaign/exact-sensitivity"
mkdir -p "${result_dir}" "${raw_dir}"

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

for formulation in legacy reduced strengthened; do
    for backend in cp-sat scip gurobi cplex; do
        run_id="${formulation}-${backend}"
        status=0
        /usr/bin/time -v -o "${raw_dir}/${run_id}.resources.txt" \
            timeout --signal=TERM --kill-after=5s 180s \
            "${python_bin}" "${study_root}/benchmarks/campaign/exact_suite.py" \
            --backend "${backend}" --formulation "${formulation}" --time-limit 20 \
            > "${result_dir}/exact-${run_id}.json" \
            2> "${raw_dir}/${run_id}.stderr" || status=$?
        printf '%s\n' "${status}" > "${raw_dir}/${run_id}.exitcode"
    done
done
