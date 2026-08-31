#!/usr/bin/env bash
set -euo pipefail

study_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
maven="${study_root}/.cache/apache-maven/bin/mvn"
java_classes="${study_root}/benchmarks/java-skjolber/target/classes"
dependency_root="${HOME}/.m2/repository"
classpath="${java_classes}:${dependency_root}/com/github/skjolber/3d-bin-container-packing/core/4.2.2-SNAPSHOT/core-4.2.2-SNAPSHOT.jar:${dependency_root}/com/github/skjolber/3d-bin-container-packing/api/4.2.2-SNAPSHOT/api-4.2.2-SNAPSHOT.jar:${dependency_root}/com/github/skjolber/3d-bin-container-packing/points/4.2.2-SNAPSHOT/points-4.2.2-SNAPSHOT.jar:${dependency_root}/org/eclipse/collections/eclipse-collections/13.0.0/eclipse-collections-13.0.0.jar:${dependency_root}/org/eclipse/collections/eclipse-collections-api/13.0.0/eclipse-collections-api-13.0.0.jar"
raw_dir="${study_root}/raw/experiments/campaign/skjolber-algorithms"
mkdir -p "${raw_dir}" "${study_root}/results/campaign"

"${maven}" -q -o -f "${study_root}/benchmarks/java-skjolber/pom.xml" compile \
    > "${raw_dir}/build.stdout" 2> "${raw_dir}/build.stderr"
status=0
/usr/bin/time -v -o "${raw_dir}/suite.resources.txt" \
    timeout --signal=TERM --kill-after=5s 35s \
    java -Xms32m -Xmx512m -XX:ActiveProcessorCount=1 -cp "${classpath}" \
    study.SkjolberAlgorithmSuite \
    > "${study_root}/results/campaign/skjolber-algorithms.json" \
    2> "${raw_dir}/suite.stderr" || status=$?
printf '%s\n' "${status}" > "${raw_dir}/suite.exitcode"
exit "${status}"
