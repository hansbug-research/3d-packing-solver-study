#!/usr/bin/env bash
set -euo pipefail

study_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "${study_root}/results/raw"
python_bin="${study_root}/.venv/bin/python"
if [[ ! -x "${python_bin}" ]]; then
    python_bin="python3"
fi

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
ulimit -v 4194304

run_one() {
    local name="$1"
    local script="$2"
    local stdout_path="${study_root}/results/${name}.json"
    local stderr_path="${study_root}/results/raw/${name}.stderr"
    local exitcode_path="${study_root}/results/raw/${name}.exitcode"
    local status

    # Keep the JSON output path stable while preserving diagnostics and the
    # process status as separate raw artifacts for later collection.
    /usr/bin/time -v -o "${study_root}/results/raw/${name}.resources.txt" \
        timeout --signal=TERM --kill-after=5s 35s \
        "${python_bin}" "${study_root}/benchmarks/${script}" \
        > "${stdout_path}" 2> "${stderr_path}" || status=$?
    status="${status:-0}"
    printf '%s\n' "${status}" > "${exitcode_path}"
    if [[ "${status}" != 0 ]]; then
        printf 'benchmark %s exited with status %s; see %s\n' "${name}" "${status}" "${stderr_path}" >&2
        return "${status}"
    fi
}

run_one py3dbp benchmark_py3dbp.py
run_one jerry benchmark_jerry.py
run_one ortools benchmark_ortools.py
run_one scip benchmark_scip.py
run_one packingsolver benchmark_packingsolver.py
