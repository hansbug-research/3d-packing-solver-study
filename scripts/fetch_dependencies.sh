#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cache_dir="${root_dir}/.cache"
mkdir -p "${cache_dir}"

checkout() {
    local name="$1"
    local url="$2"
    local commit="$3"
    local destination="${cache_dir}/${name}"

    if [[ ! -d "${destination}/.git" ]]; then
        git clone --filter=blob:none "${url}" "${destination}"
    fi
    git -C "${destination}" fetch --depth=1 origin "${commit}"
    git -C "${destination}" checkout --detach --force "${commit}"
    printf '%s %s\n' "${name}" "$(git -C "${destination}" rev-parse HEAD)"
}

# These are the exact snapshots used for the public conversion and audits.
checkout esicup-datasets https://github.com/ESICUP/datasets.git 154a8f006a8e72f65d734f2d1e36777f678f31f8
checkout jerry-3d-bin-packing https://github.com/jerry800416/3D-bin-packing.git 75764a2b8a5c8e0a6713a4f672c0a8ff81b1107a
checkout packingsolver-src https://github.com/fontanf/packingsolver.git 367ebfdaad11424ded3696b7dae799a30c1375d0
checkout skjolber https://github.com/skjolber/3d-bin-container-packing.git c73d52190c029a14e64f1bbdd2ea70452d1eb83d

if [[ ! -x "${cache_dir}/packingsolver/packingsolver_box" || ! -x "${cache_dir}/packingsolver/packingsolver_boxstacks" ]]; then
    echo "NOTICE: pinned source is ready, but .cache/packingsolver/packingsolver_box{,stacks} is absent; download a verified binary or build it locally." >&2
fi
if ! command -v mvn >/dev/null 2>&1 && [[ ! -x "${cache_dir}/apache-maven/bin/mvn" ]]; then
    echo "NOTICE: Maven is absent; Skjolber Java benchmark remains optional." >&2
fi
