#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
tool_root="${CROSSLANG_TOOLCHAIN_ROOT:-/tmp/crosslang-toolchains}"
build_root="${CROSSLANG_U_BUILD_ROOT:-/tmp/packing-crosslang-u-build}"
binary="${build_root}/target/release/crosslang-rust-unesting"
raw_dir="${root}/raw/experiments/campaign/crosslang_rust_unesting_strategies"
mkdir -p "${raw_dir}"
export PATH="${tool_root}/cargo-home/bin:${PATH}"
export CARGO_HOME="${tool_root}/cargo-home"
export RUSTUP_HOME="${tool_root}/rustup-home"
export RAYON_NUM_THREADS=1
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
memory_limit_bytes=2147483648

# Rebuild and retest the exact adapter source before strategy comparisons.
"${root}/benchmarks/campaign/crosslang_rust_unesting/run.sh"
cp "${root}/raw/experiments/campaign/crosslang_rust_unesting/toolchain.txt" "${raw_dir}/toolchain.txt"
cp "${root}/raw/experiments/campaign/crosslang_rust_unesting/source.txt" "${raw_dir}/source.txt"
cp "${root}/raw/experiments/campaign/crosslang_rust_unesting/binary.sha256" "${raw_dir}/binary.sha256"
cp "${root}/raw/experiments/campaign/crosslang_rust_unesting/build.exitcode" "${raw_dir}/build.exitcode"
cp "${root}/raw/experiments/campaign/crosslang_rust_unesting/upstream-test.exitcode" "${raw_dir}/upstream-test.exitcode"
printf '%s\n' \
    'Adapter build/test details are stored in sibling crosslang_rust_unesting; hashes and exit codes are copied here.' \
    > "${raw_dir}/build.stdout"
: > "${raw_dir}/build.stderr"
/usr/bin/time -v -o "${raw_dir}/build.resources.txt" true
printf '%s\n' \
    'Upstream test details are stored in sibling crosslang_rust_unesting.' \
    > "${raw_dir}/upstream-test.stdout"
: > "${raw_dir}/upstream-test.stderr"
/usr/bin/time -v -o "${raw_dir}/upstream-test.resources.txt" true
printf 'process_timeout_seconds=20\nmemory_limit_bytes=%s\nrayon_num_threads=1\n' \
    "${memory_limit_bytes}" > "${raw_dir}/limits.txt"

strategies=(bottomleftfill ga brkga sa extremepoint)
scenarios=(exact_grid rotation_required rotation_forbidden weight_limit thpack9_instance1)
for strategy in "${strategies[@]}"; do
    for scenario in "${scenarios[@]}"; do
        run_id="${scenario}__${strategy}"
        status=0
        /usr/bin/time -v -o "${raw_dir}/${run_id}.resources.txt" \
            prlimit --as="${memory_limit_bytes}" -- \
            timeout --signal=TERM --kill-after=5s 20s \
            "${binary}" "${scenario}" "${strategy}" 1000 \
            > "${raw_dir}/${run_id}.stdout.json" \
            2> "${raw_dir}/${run_id}.stderr" || status=$?
        printf '%s\n' "${status}" > "${raw_dir}/${run_id}.exitcode"
    done
done
