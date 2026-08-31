#!/usr/bin/env bash
set -euo pipefail

study_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
raw_dir="${study_root}/raw/experiments/campaign/packingsolver-10s"
result_dir="${study_root}/results/campaign"

"${study_root}/.venv/bin/python" \
    "${study_root}/benchmarks/campaign/revalidate_packingsolver_archive.py" \
    --archive "${raw_dir}/packingsolver-thpack-10s-artifacts.tar.gz" \
    --records "${result_dir}/packingsolver-thpack-10s.jsonl" \
    --data-root "${study_root}/.cache/packingsolver-fork/data/box" \
    --result-jsonl "${result_dir}/packingsolver-thpack-10s.jsonl" \
    --summary "${result_dir}/packingsolver-thpack-10s-summary.json" \
    --raw-records-gzip "${raw_dir}/packingsolver-thpack-10s-records.jsonl.gz" \
    --source-commit d953148b8f710c06fa6c410949b7272f9e36327b \
    --binary-sha256 1a1a114938a9c2ebf12225751b8c88d69b9fc2b2a434f6ca2f51531d3cf26285 \
    --campaign-label packingsolver-thpack-10s/2-offline-revalidation/1 \
    --time-limit 10 \
    --parallel-processes 4 \
    --harness-provenance "VERSIONED_PARALLEL_RUNNER; solver artifacts revalidated offline"
