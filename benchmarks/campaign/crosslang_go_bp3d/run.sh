#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
tool_root="${CROSSLANG_TOOLCHAIN_ROOT:-/tmp/crosslang-toolchains}"
export PATH="${tool_root}/go/bin:${PATH}"
export GOPATH="${tool_root}/go-home"
export GO111MODULE=off
export GOMAXPROCS=1
source_commit="0ba3dcda7ab334c19b0979b1cf1fa05e09f33bc7"
source_dir="${root}/.cache/bp3d"
raw_dir="${root}/raw/experiments/campaign/crosslang_go_bp3d"
build_dir="${CROSSLANG_GO_BUILD_ROOT:-/tmp/packing-crosslang-go-build}"
gopath_dir="${CROSSLANG_GO_GOPATH:-/tmp/packing-crosslang-go-gopath}"
mkdir -p "${build_dir}" "${gopath_dir}/src/github.com/gedex"

actual_commit="$(git -C "${source_dir}" rev-parse HEAD)"
if [[ "${actual_commit}" != "${source_commit}" ]]; then
    printf 'bp3d source mismatch: expected %s, got %s\n' "${source_commit}" "${actual_commit}" >&2
    exit 2
fi
ln -sfn "${source_dir}" "${gopath_dir}/src/github.com/gedex/bp3d"
export GOPATH="${gopath_dir}"

go version > "${raw_dir}/toolchain.txt"
git -C "${source_dir}" show -s --format='%H%n%cI%n%s' > "${raw_dir}/source.txt"
sha256sum "${source_dir}/bp3d.go" >> "${raw_dir}/source.txt"

status=0
/usr/bin/time -v -o "${raw_dir}/upstream-test.resources.txt" \
    timeout --signal=TERM --kill-after=5s 120s go test github.com/gedex/bp3d \
    > "${raw_dir}/upstream-test.stdout" 2> "${raw_dir}/upstream-test.stderr" || status=$?
printf '%s\n' "${status}" > "${raw_dir}/upstream-test.exitcode"

status=0
/usr/bin/time -v -o "${raw_dir}/build.resources.txt" \
    timeout --signal=TERM --kill-after=5s 120s \
    go build -trimpath -o "${build_dir}/crosslang_go_bp3d" "${root}/benchmarks/campaign/crosslang_go_bp3d/main.go" \
    > "${raw_dir}/build.stdout" 2> "${raw_dir}/build.stderr" || status=$?
printf '%s\n' "${status}" > "${raw_dir}/build.exitcode"
if [[ "${status}" != 0 ]]; then
    exit "${status}"
fi
sha256sum "${build_dir}/crosslang_go_bp3d" > "${raw_dir}/binary.sha256"

scenarios=(exact_grid rotation_required rotation_forbidden weight_limit heterogeneous_small_first heterogeneous_large_first thpack9_instance1)
for scenario in "${scenarios[@]}"; do
    status=0
    /usr/bin/time -v -o "${raw_dir}/${scenario}.resources.txt" \
        timeout --signal=TERM --kill-after=5s 35s "${build_dir}/crosslang_go_bp3d" "${scenario}" \
        > "${raw_dir}/${scenario}.stdout.json" 2> "${raw_dir}/${scenario}.stderr" || status=$?
    printf '%s\n' "${status}" > "${raw_dir}/${scenario}.exitcode"
done
