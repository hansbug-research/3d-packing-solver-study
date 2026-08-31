#!/usr/bin/env bash
set -euo pipefail

study_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
java_project="${study_root}/benchmarks/java-skjolber"
classpath_file="${java_project}/classpath.txt"
mkdir -p "${study_root}/results/raw"

export MAVEN_OPTS="-Xmx768m -XX:ActiveProcessorCount=1"
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

if command -v mvn >/dev/null 2>&1; then
    maven_bin="$(command -v mvn)"
elif [[ -x "${study_root}/.cache/apache-maven/bin/mvn" ]]; then
    maven_bin="${study_root}/.cache/apache-maven/bin/mvn"
else
    echo "Maven is required (mvn on PATH or .cache/apache-maven/bin/mvn)." >&2
    exit 127
fi

timeout --signal=TERM --kill-after=5s 120s \
    "${maven_bin}" -q -f "${java_project}/pom.xml" -DskipTests compile \
    dependency:build-classpath -Dmdep.outputFile="${classpath_file}" \
    > "${study_root}/results/raw/skjolber-build.stdout" \
    2> "${study_root}/results/raw/skjolber-build.stderr"

java_classpath="${java_project}/target/classes:$(<"${classpath_file}")"
status=0
/usr/bin/time -v -o "${study_root}/results/raw/skjolber.resources.txt" \
    timeout --signal=TERM --kill-after=5s 35s \
    java -Xms32m -Xmx512m -XX:ActiveProcessorCount=1 \
    -cp "${java_classpath}" study.SkjolberBenchmark \
    > "${study_root}/results/skjolber.json" \
    2> "${study_root}/results/raw/skjolber.stderr" || status=$?
printf '%s\n' "${status}" > "${study_root}/results/raw/skjolber.exitcode"
exit "${status}"
