#!/usr/bin/env bash
set -euo pipefail

tool_root="${CROSSLANG_TOOLCHAIN_ROOT:-/tmp/crosslang-toolchains}"
mkdir -p "${tool_root}/downloads" "${tool_root}/go-home" "${tool_root}/cargo-home" "${tool_root}/rustup-home"

go_version="1.27.0"
go_archive="go${go_version}.linux-amd64.tar.gz"
go_sha256="675c26c449cbb18fc24b74650de1eabbae6e16f64326fd85a283fb3b58280685"
go_url="https://go.dev/dl/${go_archive}"

if [[ ! -x "${tool_root}/go/bin/go" ]]; then
    curl --fail --location --retry 3 --output "${tool_root}/downloads/${go_archive}" "${go_url}"
    printf '%s  %s\n' "${go_sha256}" "${tool_root}/downloads/${go_archive}" | sha256sum --check
    tar -C "${tool_root}" -xzf "${tool_root}/downloads/${go_archive}"
fi

rustup_url="https://static.rust-lang.org/rustup/dist/x86_64-unknown-linux-gnu/rustup-init"
rustup_sha256="4acc9acc76d5079515b46346a485974457b5a79893cfb01112423c89aeb5aa10"
rustup_bin="${tool_root}/downloads/rustup-init"
if [[ ! -x "${tool_root}/cargo-home/bin/rustup" ]]; then
    curl --fail --location --retry 3 --output "${rustup_bin}" "${rustup_url}"
    printf '%s  %s\n' "${rustup_sha256}" "${rustup_bin}" | sha256sum --check
    chmod +x "${rustup_bin}"
    CARGO_HOME="${tool_root}/cargo-home" RUSTUP_HOME="${tool_root}/rustup-home" \
        "${rustup_bin}" -y --no-modify-path --profile minimal --default-toolchain 1.98.0
fi

export PATH="${tool_root}/go/bin:${tool_root}/cargo-home/bin:${PATH}"
export GOPATH="${tool_root}/go-home"
export CARGO_HOME="${tool_root}/cargo-home"
export RUSTUP_HOME="${tool_root}/rustup-home"

printf 'tool_root=%s\n' "${tool_root}"
printf 'go_archive_sha256=%s\n' "$(sha256sum "${tool_root}/downloads/${go_archive}" | cut -d' ' -f1)"
printf 'rustup_init_sha256=%s\n' "$(sha256sum "${rustup_bin}" | cut -d' ' -f1)"
go version
rustc --version --verbose
cargo --version --verbose
