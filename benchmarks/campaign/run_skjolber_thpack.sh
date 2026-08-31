#!/usr/bin/env bash
set -euo pipefail

study_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
maven="${study_root}/.cache/apache-maven/bin/mvn"
java_classes="${study_root}/benchmarks/java-skjolber/target/classes"
dependency_root="${HOME}/.m2/repository"
classpath="${java_classes}:${dependency_root}/com/github/skjolber/3d-bin-container-packing/core/4.2.2-SNAPSHOT/core-4.2.2-SNAPSHOT.jar:${dependency_root}/com/github/skjolber/3d-bin-container-packing/api/4.2.2-SNAPSHOT/api-4.2.2-SNAPSHOT.jar:${dependency_root}/com/github/skjolber/3d-bin-container-packing/points/4.2.2-SNAPSHOT/points-4.2.2-SNAPSHOT.jar:${dependency_root}/org/eclipse/collections/eclipse-collections/13.0.0/eclipse-collections-13.0.0.jar:${dependency_root}/org/eclipse/collections/eclipse-collections-api/13.0.0/eclipse-collections-api-13.0.0.jar"
data_root="${study_root}/.cache/packingsolver-fork/data/box/ivancic1989"
raw_dir="${study_root}/raw/experiments/campaign/skjolber-thpack"
result_dir="${study_root}/results/campaign"
mkdir -p "${raw_dir}" "${result_dir}"

build_status=0
/usr/bin/time -v -o "${raw_dir}/build.resources.txt" \
    "${maven}" -q -o -f "${study_root}/benchmarks/java-skjolber/pom.xml" compile \
    > "${raw_dir}/build.stdout" 2> "${raw_dir}/build.stderr" || build_status=$?
printf '%s\n' "${build_status}" > "${raw_dir}/build.exitcode"
if [[ "${build_status}" -ne 0 ]]; then
    exit "${build_status}"
fi

run_status=0
/usr/bin/time -v -o "${raw_dir}/campaign.resources.txt" \
    timeout --signal=TERM --kill-after=5s 600s \
    java -Xms32m -Xmx512m -XX:ActiveProcessorCount=1 -cp "${classpath}" \
    study.SkjolberThpackCampaign "${data_root}" \
    "${raw_dir}/java-records.jsonl" "${raw_dir}/certificate.csv" \
    > "${raw_dir}/campaign.stdout" 2> "${raw_dir}/campaign.stderr" || run_status=$?
printf '%s\n' "${run_status}" > "${raw_dir}/campaign.exitcode"
if [[ "${run_status}" -ne 0 ]]; then
    exit "${run_status}"
fi

"${study_root}/.venv/bin/python" "${study_root}/benchmarks/campaign/skjolber_validate.py" \
    --java-records "${raw_dir}/java-records.jsonl" \
    --certificate "${raw_dir}/certificate.csv" \
    --data-root "${data_root}" \
    --output "${result_dir}/skjolber-thpack9.json"
