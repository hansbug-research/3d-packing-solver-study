#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
tool_root="${CROSSLANG_TOOLCHAIN_ROOT:-/tmp/crosslang-toolchains}"
export PATH="${tool_root}/cargo-home/bin:${PATH}"
export CARGO_HOME="${tool_root}/cargo-home"
export RUSTUP_HOME="${tool_root}/rustup-home"
export CARGO_BUILD_JOBS=1
export RAYON_NUM_THREADS=1
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
source_commit="8cde85b029e4ade663185dacb93fd74440af170d"
adapter_dir="${root}/benchmarks/campaign/crosslang_rust_unesting"
raw_dir="${root}/raw/experiments/campaign/crosslang_rust_unesting"
build_root="${CROSSLANG_U_BUILD_ROOT:-/tmp/packing-crosslang-u-build}"
target_dir="${build_root}/target"
source_dir="${build_root}/nesting/u-nesting"
generated_adapter="${build_root}/adapter"
mkdir -p "${raw_dir}" "${target_dir}" "${build_root}/nesting" \
    "${build_root}/algorithms" "${build_root}/foundation" "${generated_adapter}/src"

sync_repo() {
    local url="$1"
    local destination="$2"
    local commit="$3"
    if [[ ! -d "${destination}/.git" ]]; then
        git clone --filter=blob:none "${url}" "${destination}"
    fi
    git -C "${destination}" remote set-url origin "${url}"
    git -C "${destination}" fetch --force origin "${commit}"
    git -C "${destination}" checkout --detach --force "${commit}"
}

# The core manifest uses paths four levels above the u-nesting checkout. Pin
# all sibling repositories in the exact directory layout it expects.
sync_repo "https://github.com/iyulab/U-Nesting.git" \
    "${source_dir}" "${source_commit}"
sync_repo "https://github.com/iyulab/u-geometry.git" \
    "${build_root}/algorithms/u-geometry" "e8d23e9b70ad2fdf4ff82918bc25057fd803e4f4"
sync_repo "https://github.com/iyulab/u-metaheur.git" \
    "${build_root}/algorithms/u-metaheur" "717192f7c5e39ff8d5e506b1909d58d5f762cd23"
sync_repo "https://github.com/iyulab/u-numflow.git" \
    "${build_root}/foundation/u-numflow" "652d405d18bd1eab47f0ddaab26386c9db9386c4"

actual_commit="$(git -C "${source_dir}" rev-parse HEAD)"
if [[ "${actual_commit}" != "${source_commit}" ]]; then
    printf 'u-nesting source mismatch: expected %s, got %s\n' "${source_commit}" "${actual_commit}" >&2
    exit 2
fi

rustc --version --verbose > "${raw_dir}/toolchain.txt"
cargo --version --verbose >> "${raw_dir}/toolchain.txt"
for repository in \
    "${source_dir}" \
    "${build_root}/algorithms/u-geometry" \
    "${build_root}/algorithms/u-metaheur" \
    "${build_root}/foundation/u-numflow"; do
    printf 'repository=%s\n' "${repository}"
    git -C "${repository}" show -s --format='commit=%H%ncommit_date=%cI%nsubject=%s'
done > "${raw_dir}/source.txt"
sha256sum "${source_dir}/crates/d3/src/packer.rs" "${source_dir}/crates/d3/src/geometry.rs" >> "${raw_dir}/source.txt"

cp "${adapter_dir}/src/main.rs" "${generated_adapter}/src/main.rs"
sed "s|../../../.cache/u-nesting/crates/d3|${source_dir}/crates/d3|" \
    "${adapter_dir}/Cargo.toml" > "${generated_adapter}/Cargo.toml"
if [[ -f "${adapter_dir}/Cargo.lock" ]]; then
    cp "${adapter_dir}/Cargo.lock" "${generated_adapter}/Cargo.lock"
else
    cargo generate-lockfile --manifest-path "${generated_adapter}/Cargo.toml"
    cp "${generated_adapter}/Cargo.lock" "${adapter_dir}/Cargo.lock"
fi

status=0
/usr/bin/time -v -o "${raw_dir}/upstream-test.resources.txt" \
    timeout --signal=TERM --kill-after=10s 600s cargo test \
    --manifest-path "${source_dir}/Cargo.toml" -p u-nesting-d3 --all-features -- --test-threads=1 \
    > "${raw_dir}/upstream-test.stdout" 2> "${raw_dir}/upstream-test.stderr" || status=$?
printf '%s\n' "${status}" > "${raw_dir}/upstream-test.exitcode"

status=0
/usr/bin/time -v -o "${raw_dir}/build.resources.txt" \
    timeout --signal=TERM --kill-after=10s 600s env \
    CARGO_TARGET_DIR="${target_dir}" CROSSLANG_RUSTC_VERSION="$(rustc --version)" \
    cargo build --locked --release --manifest-path "${generated_adapter}/Cargo.toml" \
    > "${raw_dir}/build.stdout" 2> "${raw_dir}/build.stderr" || status=$?
printf '%s\n' "${status}" > "${raw_dir}/build.exitcode"
if [[ "${status}" != 0 ]]; then
    exit "${status}"
fi
binary="${target_dir}/release/crosslang-rust-unesting"
sha256sum "${binary}" > "${raw_dir}/binary.sha256"

scenarios=(exact_grid rotation_required rotation_forbidden weight_limit heterogeneous_small_first heterogeneous_large_first thpack9_instance1)
for scenario in "${scenarios[@]}"; do
    status=0
    /usr/bin/time -v -o "${raw_dir}/${scenario}.resources.txt" \
        timeout --signal=TERM --kill-after=5s 35s "${binary}" "${scenario}" \
        > "${raw_dir}/${scenario}.stdout.json" 2> "${raw_dir}/${scenario}.stderr" || status=$?
    printf '%s\n' "${status}" > "${raw_dir}/${scenario}.exitcode"
done
