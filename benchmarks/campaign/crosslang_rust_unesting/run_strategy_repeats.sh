#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
tool_root="${CROSSLANG_TOOLCHAIN_ROOT:-/tmp/crosslang-toolchains}"
build_root="${CROSSLANG_U_BUILD_ROOT:-/tmp/packing-crosslang-u-build}"
binary="${build_root}/target/release/crosslang-rust-unesting"
raw_dir="${root}/raw/experiments/campaign/crosslang_rust_unesting_strategy_repeats"
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

# Rebuild the pinned adapter before measuring five identical process-level repeats.
"${root}/benchmarks/campaign/crosslang_rust_unesting/run.sh"
for artifact in toolchain.txt source.txt binary.sha256 build.exitcode upstream-test.exitcode; do
    cp "${root}/raw/experiments/campaign/crosslang_rust_unesting/${artifact}" "${raw_dir}/${artifact}"
done
printf '%s\n' \
    'Build/test streams are stored in sibling crosslang_rust_unesting; this directory contains repeated THPACK9-1 runs.' \
    > "${raw_dir}/build.stdout"
: > "${raw_dir}/build.stderr"
/usr/bin/time -v -o "${raw_dir}/build.resources.txt" true
printf '%s\n' 'Upstream test streams are stored in sibling crosslang_rust_unesting.' \
    > "${raw_dir}/upstream-test.stdout"
: > "${raw_dir}/upstream-test.stderr"
/usr/bin/time -v -o "${raw_dir}/upstream-test.resources.txt" true
printf 'process_timeout_seconds=20\nmemory_limit_bytes=%s\nrayon_num_threads=1\nrepeats=5\n' \
    "${memory_limit_bytes}" > "${raw_dir}/limits.txt"

strategies=(bottomleftfill ga brkga sa extremepoint)
for strategy in "${strategies[@]}"; do
    for repeat in 01 02 03 04 05; do
        run_id="thpack9_instance1__${strategy}__repeat_${repeat}"
        status=0
        /usr/bin/time -v -o "${raw_dir}/${run_id}.resources.txt" \
            prlimit --as="${memory_limit_bytes}" -- \
            timeout --signal=TERM --kill-after=5s 20s \
            "${binary}" thpack9_instance1 "${strategy}" 1000 \
            > "${raw_dir}/${run_id}.stdout.json" \
            2> "${raw_dir}/${run_id}.stderr" || status=$?
        printf '%s\n' "${status}" > "${raw_dir}/${run_id}.exitcode"
    done
done

python3 "${root}/benchmarks/campaign/crosslang_validate.py" \
    crosslang_rust_unesting_strategy_repeats
