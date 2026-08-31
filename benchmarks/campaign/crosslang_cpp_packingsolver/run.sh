#!/usr/bin/env bash
set -euo pipefail

variant="${1:?usage: run.sh official|fixed}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
adapter_dir="${root}/benchmarks/campaign/crosslang_cpp_packingsolver"
data_dir="${adapter_dir}/data"
raw_dir="${root}/raw/experiments/campaign/crosslang_cpp_packingsolver_${variant}"
mkdir -p "${raw_dir}"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1

case "${variant}" in
    official)
        binary="${root}/.cache/packingsolver/packingsolver_box"
        commit="rolling-binary-no-embedded-commit"
        source_dir="${root}/.cache/packingsolver-src"
        printf '%s\n' \
            'PREBUILT_ARTIFACT: no campaign build was possible because the official rolling binary has no embedded source revision.' \
            'The nearby pristine source checkout is recorded only as a dated comparison, not asserted as this binary source.' \
            > "${raw_dir}/build.stdout"
        : > "${raw_dir}/build.stderr"
        printf '0\n' > "${raw_dir}/build.exitcode"
        printf 'NOT_APPLICABLE_PREBUILT_ARTIFACT\n' > "${raw_dir}/build.status.txt"
        /usr/bin/time -v -o "${raw_dir}/build.resources.txt" true
        printf '%s\n' \
            'NOT_APPLICABLE_PREBUILT_ARTIFACT: upstream tests cannot be tied to this rolling binary.' \
            > "${raw_dir}/upstream-test.stdout"
        : > "${raw_dir}/upstream-test.stderr"
        printf '0\n' > "${raw_dir}/upstream-test.exitcode"
        printf 'NOT_APPLICABLE_PREBUILT_ARTIFACT\n' > "${raw_dir}/upstream-test.status.txt"
        /usr/bin/time -v -o "${raw_dir}/upstream-test.resources.txt" true
        ;;
    fixed)
        binary="${root}/.cache/build-fork/src/box/packingsolver_box"
        commit="d953148b8f710c06fa6c410949b7272f9e36327b"
        source_dir="${root}/.cache/packingsolver-fork"
        actual_commit="$(git -C "${source_dir}" rev-parse HEAD)"
        if [[ "${actual_commit}" != "${commit}" ]]; then
            printf 'source mismatch: expected %s, got %s\n' "${commit}" "${actual_commit}" >&2
            exit 2
        fi
        status=0
        /usr/bin/time -v -o "${raw_dir}/build.resources.txt" \
            timeout --signal=TERM --kill-after=10s 600s \
            "${root}/.venv/bin/cmake" --build "${root}/.cache/build-fork" \
                --target PackingSolver_box_main --parallel 1 \
            > "${raw_dir}/build.stdout" 2> "${raw_dir}/build.stderr" || status=$?
        printf '%s\n' "${status}" > "${raw_dir}/build.exitcode"
        printf 'EXECUTED\n' > "${raw_dir}/build.status.txt"
        if [[ "${status}" != 0 ]]; then
            exit "${status}"
        fi
        status=0
        /usr/bin/time -v -o "${raw_dir}/upstream-test.resources.txt" \
            timeout --signal=TERM --kill-after=10s 600s \
            "${root}/.venv/bin/ctest" --test-dir "${root}/.cache/build-fork/test" \
                --output-on-failure --parallel 1 \
            > "${raw_dir}/upstream-test.stdout" 2> "${raw_dir}/upstream-test.stderr" || status=$?
        printf '%s\n' "${status}" > "${raw_dir}/upstream-test.exitcode"
        printf 'EXECUTED\n' > "${raw_dir}/upstream-test.status.txt"
        ;;
    *)
        printf 'unknown variant: %s\n' "${variant}" >&2
        exit 2
        ;;
esac

if [[ ! -x "${binary}" ]]; then
    printf 'missing binary: %s\n' "${binary}" >&2
    exit 2
fi
{
    c++ --version | head -n 1
    "${root}/.venv/bin/cmake" --version | head -n 1
} > "${raw_dir}/toolchain.txt"
{
    printf 'declared_commit=%s\n' "${commit}"
    git -C "${source_dir}" show -s --format='nearby_source_commit=%H%ncommit_date=%cI%nsubject=%s' HEAD
    sha256sum "${binary}"
} > "${raw_dir}/source.txt"
sha256sum "${binary}" > "${raw_dir}/binary.sha256"

scenarios=(exact_grid rotation_required rotation_forbidden weight_limit heterogeneous_small_first heterogeneous_large_first thpack9_instance1)
for scenario in "${scenarios[@]}"; do
    objective="bin-packing"
    case "${scenario}" in
        exact_grid)
            items="${data_dir}/exact_grid_items.csv"; bins="${data_dir}/exact_grid_bins.csv" ;;
        rotation_required)
            items="${data_dir}/rotation_required_items.csv"; bins="${data_dir}/rotation_bins.csv" ;;
        rotation_forbidden)
            items="${data_dir}/rotation_forbidden_items.csv"; bins="${data_dir}/rotation_bins.csv" ;;
        weight_limit)
            items="${data_dir}/weight_limit_items.csv"; bins="${data_dir}/weight_limit_bins.csv" ;;
        heterogeneous_small_first)
            items="${data_dir}/heterogeneous_items.csv"; bins="${data_dir}/heterogeneous_small_first_bins.csv"; objective="variable-sized-bin-packing" ;;
        heterogeneous_large_first)
            items="${data_dir}/heterogeneous_items.csv"; bins="${data_dir}/heterogeneous_large_first_bins.csv"; objective="variable-sized-bin-packing" ;;
        thpack9_instance1)
            items="${data_dir}/thpack9_instance1_items.csv"; bins="${data_dir}/thpack9_instance1_bins.csv" ;;
    esac
    certificate="${raw_dir}/${scenario}.certificate.csv"
    solver_output="${raw_dir}/${scenario}.solver.output.json"
    status=0
    started_ns="$(date +%s%N)"
    /usr/bin/time -v -o "${raw_dir}/${scenario}.resources.txt" \
        timeout --signal=TERM --kill-after=5s 35s \
        "${binary}" --items "${items}" --bins "${bins}" \
            --objective "${objective}" --time-limit 2 --memory-limit 1024 \
            --verbosity-level 0 --certificate "${certificate}" \
            --output "${solver_output}" --only-write-at-the-end \
        > "${raw_dir}/${scenario}.solver.stdout" \
        2> "${raw_dir}/${scenario}.stderr" || status=$?
    ended_ns="$(date +%s%N)"
    printf '%s\n' "${status}" > "${raw_dir}/${scenario}.exitcode"
    elapsed_ms="$(( (ended_ns - started_ns) / 1000000 ))"
    python3 "${adapter_dir}/normalize.py" \
        --variant "${variant}" --commit "${commit}" --scenario "${scenario}" \
        --items "${items}" --bins "${bins}" --certificate "${certificate}" \
        --exitcode "${status}" --elapsed-ms "${elapsed_ms}" \
        --toolchain "$(head -n 1 "${raw_dir}/toolchain.txt")" \
        > "${raw_dir}/${scenario}.stdout.json"
done
